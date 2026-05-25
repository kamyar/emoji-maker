import tempfile
import os
from io import BytesIO
from typing import Literal

import cadquery as cq
from pydantic import BaseModel, Field

from src.generator.font_manager import get_font_path


class Generate3DInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)
    font: str
    fontSize: float = Field(default=24.0, ge=1.0, le=200.0)
    letterSpacing: float = Field(default=0.5, ge=-5.0, le=50.0)
    lineSpacing: float = Field(default=0.0, ge=-50.0, le=100.0)
    extrudeHeight: float = Field(default=4.0, ge=0.5, le=50.0)
    addBorder: bool = True
    borderPaddingTop: float = Field(default=2.0, ge=0.0, le=50.0)
    borderPaddingRight: float = Field(default=2.0, ge=0.0, le=50.0)
    borderPaddingBottom: float = Field(default=2.0, ge=0.0, le=50.0)
    borderPaddingLeft: float = Field(default=2.0, ge=0.0, le=50.0)
    fillBorder: bool = False
    fillGap: float = Field(default=0.1, ge=0.0, le=2.0)
    fillColor: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    addOutline: bool = False
    outlineWidth: float = Field(default=1.0, ge=0.2, le=10.0)
    keychainHole: bool = False
    keychainCorner: Literal["bottom-left", "bottom-right", "top-left", "top-right"] = "bottom-left"
    keychainRadius: float = Field(default=3.0, ge=1.0, le=20.0)
    keychainEdgeH: float = Field(default=3.0, ge=0.0, le=50.0)
    keychainEdgeV: float = Field(default=3.0, ge=0.0, le=50.0)
    scale: float = Field(default=1.0, ge=0.1, le=10.0)
    color: str = Field(default="#667eea", pattern=r"^#[0-9a-fA-F]{6}$")
    exportFormat: Literal["stl", "3mf"] = "stl"


_char_cache = {}


def _render_char(char: str, font_size: float, font_path: str, extrude_height: float):
    key = (char, font_size, font_path, extrude_height)
    if key in _char_cache:
        return _char_cache[key]
    wp = cq.Workplane("front").text(char, font_size, extrude_height, fontPath=font_path)
    solid = wp.val()
    bb = solid.BoundingBox()
    _char_cache[key] = (solid, bb)
    return solid, bb


def _render_line(text: str, font_size: float, font_path: str,
                 letter_spacing: float, extrude_height: float) -> tuple[list, float]:
    if not text.strip():
        return [], 0.0

    if letter_spacing == 0:
        wp = cq.Workplane("front").text(
            text, font_size, extrude_height, fontPath=font_path
        )
        bb = wp.val().BoundingBox()
        return [wp.val()], bb.xmax - bb.xmin

    solids = []
    x = 0.0
    for char in text:
        if char == " ":
            x += font_size * 0.3 + letter_spacing
            continue
        solid, bb = _render_char(char, font_size, font_path, extrude_height)
        char_width = bb.xmax - bb.xmin
        moved = solid.moved(cq.Location(cq.Vector(x - bb.xmin, 0, 0)))
        solids.append(moved)
        x += char_width + letter_spacing

    return solids, x


def _offset_solid(solid, offset):
    """Create a uniformly offset copy of a solid using OCCT."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_COMPOUND
    from OCP.TopExp import TopExp_Explorer

    offsetter = BRepOffsetAPI_MakeOffsetShape()
    offsetter.PerformBySimple(solid.wrapped, offset)
    if not offsetter.IsDone():
        return None

    result_shape = offsetter.Shape()
    shape_type = result_shape.ShapeType()

    if shape_type == TopAbs_SOLID:
        return cq.Shape.cast(result_shape)

    if shape_type == TopAbs_SHELL:
        try:
            maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(result_shape))
            if maker.IsDone():
                return cq.Shape.cast(maker.Solid())
        except Exception:
            pass

    if shape_type == TopAbs_COMPOUND:
        explorer = TopExp_Explorer(result_shape, TopAbs_SOLID)
        solids = []
        while explorer.More():
            solids.append(cq.Shape.cast(explorer.Current()))
            explorer.Next()
        if solids:
            if len(solids) == 1:
                return solids[0]
            return cq.Compound.makeCompound(solids)

        shell_exp = TopExp_Explorer(result_shape, TopAbs_SHELL)
        shells = []
        while shell_exp.More():
            try:
                maker = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(shell_exp.Current()))
                if maker.IsDone():
                    shells.append(cq.Shape.cast(maker.Solid()))
            except Exception:
                pass
            shell_exp.Next()
        if shells:
            if len(shells) == 1:
                return shells[0]
            return cq.Compound.makeCompound(shells)

    return cq.Shape.cast(result_shape)


def _render_outline_line(text: str, font_size: float, font_path: str,
                         letter_spacing: float, extrude_height: float,
                         outline_width: float) -> tuple[list, float]:
    """Render per-char outline using 3D offset. Overlaps with text; slicer handles intersection."""
    if not text.strip():
        return [], 0.0

    outlines = []
    x = 0.0
    offset_cache = {}
    for char in text:
        if char == " ":
            x += font_size * 0.3 + letter_spacing
            continue
        orig_solid, orig_bb = _render_char(char, font_size, font_path, extrude_height)
        orig_w = orig_bb.xmax - orig_bb.xmin

        if char not in offset_cache:
            bigger = _offset_solid(orig_solid, outline_width)
            if bigger is not None:
                try:
                    bigger.BoundingBox()
                    offset_cache[char] = bigger
                except Exception:
                    offset_cache[char] = None
            else:
                offset_cache[char] = None

        outline = offset_cache[char]
        if outline is not None:
            obb = outline.BoundingBox()
            moved = outline.moved(cq.Location(cq.Vector(x - orig_bb.xmin, 0, 0)))
            outlines.append(moved)
        x += orig_w + letter_spacing

    return outlines, x


def _mesh_subtract(compound_a, compound_b):
    """Subtract compound_b from compound_a using trimesh mesh boolean (robust for font geometry)."""
    import trimesh

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as fa:
        path_a = fa.name
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as fb:
        path_b = fb.name
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as fo:
        path_out = fo.name

    try:
        cq.exporters.export(
            cq.Workplane("front").newObject([compound_a]),
            path_a, exportType="STL",
        )
        cq.exporters.export(
            cq.Workplane("front").newObject([compound_b]),
            path_b, exportType="STL",
        )

        mesh_a = trimesh.load(path_a, file_type="stl")
        mesh_b = trimesh.load(path_b, file_type="stl")

        if isinstance(mesh_a, trimesh.Scene):
            mesh_a = trimesh.util.concatenate(list(mesh_a.geometry.values()))
        if isinstance(mesh_b, trimesh.Scene):
            mesh_b = trimesh.util.concatenate(list(mesh_b.geometry.values()))

        result = trimesh.boolean.difference([mesh_a, mesh_b], engine="manifold")

        result.export(path_out, file_type="stl")

        from OCP.StlAPI import StlAPI_Reader
        from OCP.TopoDS import TopoDS_Shape as OCP_Shape
        reader = StlAPI_Reader()
        shape = OCP_Shape()
        reader.Read(shape, path_out)
        return cq.Shape.cast(shape)
    except Exception as e:
        print(f"Mesh subtract failed: {e}", flush=True)
        return compound_a
    finally:
        for p in [path_a, path_b, path_out]:
            try:
                os.unlink(p)
            except OSError:
                pass


class Generate3DResult(BaseModel):
    width: float
    height: float
    depth: float


def _apply_scale(compound, scale):
    if scale != 1.0:
        from OCP.gp import gp_Trsf, gp_Pnt
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), scale)
        builder = BRepBuilderAPI_Transform(compound.wrapped, trsf, True)
        compound = cq.Shape.cast(builder.Shape())
    return compound


def _build_geometry(input_data: Generate3DInput):
    _char_cache.clear()
    font_path = get_font_path(input_data.font)
    if not font_path:
        raise ValueError(f"Unknown font: {input_data.font}")

    lines = input_data.text.split("\n")
    line_results = []

    for line in lines:
        solids, width = _render_line(
            line, input_data.fontSize, font_path,
            input_data.letterSpacing, input_data.extrudeHeight,
        )
        line_results.append((solids, width))

    max_width = max((w for _, w in line_results), default=0)
    if max_width == 0:
        raise ValueError("No visible characters in text")

    all_solids = []
    line_height = input_data.fontSize + input_data.lineSpacing

    for line_idx, (solids, width) in enumerate(line_results):
        if not solids:
            continue
        x_offset = (max_width - width) / 2
        y_offset = -line_idx * line_height

        if input_data.letterSpacing == 0 and solids:
            bb = solids[0].BoundingBox()
            centered = solids[0].moved(cq.Location(cq.Vector(
                x_offset - bb.xmin, y_offset, 0
            )))
            all_solids.append(centered)
        else:
            for solid in solids:
                moved = solid.moved(cq.Location(cq.Vector(x_offset, y_offset, 0)))
                all_solids.append(moved)

    text_compound = cq.Compound.makeCompound(all_solids)
    border_compound = None

    outline_compound = None
    if input_data.addOutline:
        ow = input_data.outlineWidth
        outline_line_results = []
        for line in lines:
            s, w = _render_outline_line(
                line, input_data.fontSize, font_path,
                input_data.letterSpacing, input_data.extrudeHeight, ow,
            )
            outline_line_results.append((s, w))
        outline_solids = []
        for li, (outlines_l, width_l) in enumerate(outline_line_results):
            if not outlines_l:
                continue
            x_off = (max_width - width_l) / 2
            y_off = -li * line_height
            for sol in outlines_l:
                moved = sol.moved(cq.Location(cq.Vector(x_off, y_off, 0)))
                outline_solids.append(moved)
        if outline_solids:
            raw_outline = cq.Compound.makeCompound(outline_solids)
            outline_compound = _mesh_subtract(raw_outline, text_compound)

    if input_data.addBorder:
        text_bb = text_compound.BoundingBox()
        if outline_compound is not None:
            text_plus_outline = cq.Compound.makeCompound(
                [text_compound, outline_compound]
            )
            bb = text_plus_outline.BoundingBox()
        else:
            bb = text_bb
        pt = input_data.borderPaddingTop
        pr = input_data.borderPaddingRight
        pb = input_data.borderPaddingBottom
        pl = input_data.borderPaddingLeft
        outer_w = (bb.xmax - bb.xmin) + pl + pr
        outer_h = (bb.ymax - bb.ymin) + pt + pb
        center_x = bb.xmin + (bb.xmax - bb.xmin) / 2 + (pr - pl) / 2
        center_y = bb.ymin + (bb.ymax - bb.ymin) / 2 + (pt - pb) / 2

        if input_data.fillBorder:
            fill_inset = 0.2
            gap = input_data.fillGap
            fill_plane = cq.Plane(origin=(0, 0, fill_inset), normal=(0, 0, 1))
            plate = (
                cq.Workplane(fill_plane)
                .center(center_x, center_y)
                .rect(outer_w, outer_h)
                .extrude(input_data.extrudeHeight - 2 * fill_inset)
            )
            if outline_compound is not None:
                cutter = cq.Compound.makeCompound([text_compound, outline_compound])
            else:
                cutter = text_compound
            cutter_wp = cq.Workplane("front").newObject([cutter])
            plate = plate.cut(cutter_wp)

            if input_data.keychainHole:
                r = input_data.keychainRadius
                eh = input_data.keychainEdgeH
                ev = input_data.keychainEdgeV
                fill_xmin = bb.xmin - pl
                fill_xmax = bb.xmax + pr
                fill_ymin = bb.ymin - pb
                fill_ymax = bb.ymax + pt
                corner = input_data.keychainCorner
                if corner == "bottom-left":
                    hole_x = fill_xmin + eh + r
                    hole_y = fill_ymin + ev + r
                elif corner == "bottom-right":
                    hole_x = fill_xmax - eh - r
                    hole_y = fill_ymin + ev + r
                elif corner == "top-left":
                    hole_x = fill_xmin + eh + r
                    hole_y = fill_ymax - ev - r
                else:
                    hole_x = fill_xmax - eh - r
                    hole_y = fill_ymax - ev - r
                hole = (
                    cq.Workplane("front")
                    .center(hole_x, hole_y)
                    .circle(r)
                    .extrude(input_data.extrudeHeight)
                )
                plate = plate.cut(hole)
            border_compound = plate.val()

        else:
            wall = input_data.fontSize * 0.08
            inner_w = outer_w - 2 * wall
            inner_h = outer_h - 2 * wall
            frame = (
                cq.Workplane("front")
                .center(center_x, center_y)
                .rect(outer_w, outer_h)
                .rect(inner_w, inner_h)
                .extrude(input_data.extrudeHeight)
            )
            border_compound = frame.val()

    if outline_compound is not None:
        if border_compound is not None:
            border_compound = cq.Compound.makeCompound([border_compound, outline_compound])
        else:
            border_compound = outline_compound

    text_compound = _apply_scale(text_compound, input_data.scale)
    if border_compound is not None:
        border_compound = _apply_scale(border_compound, input_data.scale)

    if border_compound is not None:
        combined = cq.Compound.makeCompound([border_compound, text_compound])
    else:
        combined = text_compound

    bb = combined.BoundingBox()
    dimensions = Generate3DResult(
        width=round(bb.xmax - bb.xmin, 2),
        height=round(bb.ymax - bb.ymin, 2),
        depth=round(bb.zmax - bb.zmin, 2),
    )

    return text_compound, border_compound, dimensions


def _compound_to_workplane(compound):
    return cq.Workplane("front").newObject([compound])


def generate_3d_text(input_data: Generate3DInput) -> tuple[BytesIO, str, Generate3DResult]:
    text_compound, border_compound, dimensions = _build_geometry(input_data)

    if border_compound is not None:
        combined = cq.Compound.makeCompound([border_compound, text_compound])
    else:
        combined = text_compound

    result = _compound_to_workplane(combined)

    if input_data.exportFormat == "stl":
        return _export_stl(result), "model/stl", dimensions
    else:
        return _export_3mf_multi(
            text_compound, border_compound,
            input_data.color, input_data.fillColor,
            model_name=input_data.text.split("\n")[0][:20],
        ), "model/3mf", dimensions


class Generate3DBothResult:
    def __init__(self, combined_stl: BytesIO, mf_buf: BytesIO,
                 dimensions: Generate3DResult,
                 text_stl: BytesIO, border_stl: BytesIO | None):
        self.combined_stl = combined_stl
        self.mf_buf = mf_buf
        self.dimensions = dimensions
        self.text_stl = text_stl
        self.border_stl = border_stl


def generate_3d_both(input_data: Generate3DInput) -> Generate3DBothResult:
    text_compound, border_compound, dimensions = _build_geometry(input_data)

    if border_compound is not None:
        combined = cq.Compound.makeCompound([border_compound, text_compound])
    else:
        combined = text_compound

    combined_stl = _export_stl(_compound_to_workplane(combined))
    text_stl = _export_stl(_compound_to_workplane(text_compound))
    border_stl = _export_stl(_compound_to_workplane(border_compound)) if border_compound else None

    mf_buf = _export_3mf_multi(
        text_compound, border_compound,
        input_data.color, input_data.fillColor,
        model_name=input_data.text.split("\n")[0][:20],
    )
    return Generate3DBothResult(combined_stl, mf_buf, dimensions, text_stl, border_stl)


def _export_stl(result) -> BytesIO:
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cq.exporters.export(result, tmp_path, exportType="STL")
        buf = BytesIO()
        with open(tmp_path, "rb") as f:
            buf.write(f.read())
        buf.seek(0)
        return buf
    finally:
        os.unlink(tmp_path)


def _hex_to_rgba(color: str):
    import numpy as np
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return np.array([r, g, b, 255], dtype=np.uint8)


def _stl_buf_to_mesh(stl_buf: BytesIO, color: str):
    import trimesh
    stl_buf.seek(0)
    mesh = trimesh.load(stl_buf, file_type="stl")
    rgba = _hex_to_rgba(color)
    if isinstance(mesh, trimesh.Scene):
        for geom in mesh.geometry.values():
            geom.visual.face_colors = rgba
    else:
        mesh.visual.face_colors = rgba
    return mesh


def _mesh_to_object_model(mesh, obj_id, uuid_str):
    import trimesh
    if isinstance(mesh, trimesh.Scene):
        geom = list(mesh.geometry.values())[0]
    else:
        geom = mesh
    verts = geom.vertices
    faces = geom.faces

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <resources>',
        f'  <object id="{obj_id}" p:UUID="{uuid_str}" type="model">',
        '   <mesh>',
        '    <vertices>',
    ]
    for v in verts:
        lines.append(f'     <vertex x="{v[0]}" y="{v[1]}" z="{v[2]}"/>')
    lines.append('    </vertices>')
    lines.append('    <triangles>')
    for f in faces:
        lines.append(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>')
    lines.append('    </triangles>')
    lines.append('   </mesh>')
    lines.append('  </object>')
    lines.append(' </resources>')
    lines.append('</model>')
    return '\n'.join(lines)


def _get_plate_for_object(wrap_id, object_files, has_border):
    if not has_border:
        return 1
    idx = next(i for i, o in enumerate(object_files) if o[2] == wrap_id)
    if idx <= 1:
        return 1
    if idx == 2:
        return 2
    return 3


def _export_3mf_multi(text_compound, border_compound,
                       text_color: str, fill_color: str,
                       model_name: str = "model") -> BytesIO:
    import trimesh
    import zipfile
    import re
    import uuid as uuid_mod

    safe_name = re.sub(r'[^\w\s-]', '', model_name).strip().replace(' ', '_') or "model"

    text_stl = _export_stl(_compound_to_workplane(text_compound))
    text_mesh = _stl_buf_to_mesh(text_stl, text_color)

    has_border = border_compound is not None
    if has_border:
        border_stl = _export_stl(_compound_to_workplane(border_compound))
        border_mesh = _stl_buf_to_mesh(border_stl, fill_color)

    # Each mesh gets a separate object file in 3D/Objects/
    # Bambu pattern: part ids are odd (1,3,5,...), wrapper object ids are even (2,4,6,...)
    # For 3 plates with border: combined(text+fill), text-only, fill-only
    # Without border: single plate with text

    object_files = []  # (filename, part_id, wrapper_id, part_uuid, wrapper_uuid, mesh, name, extruder)

    if has_border:
        # Object 1: text for combined plate
        object_files.append(("object_1.model", 1, 2,
                             str(uuid_mod.uuid4()), str(uuid_mod.uuid4()),
                             text_mesh, f"{safe_name} - Text", "1"))
        # Object 2: fill for combined plate
        object_files.append(("object_2.model", 3, 4,
                             str(uuid_mod.uuid4()), str(uuid_mod.uuid4()),
                             border_mesh, f"{safe_name} - Fill", "2"))
        # Object 3: text-only plate
        object_files.append(("object_3.model", 5, 6,
                             str(uuid_mod.uuid4()), str(uuid_mod.uuid4()),
                             text_mesh, f"{safe_name} - Text Only", "1"))
        # Object 4: fill-only plate
        object_files.append(("object_4.model", 7, 8,
                             str(uuid_mod.uuid4()), str(uuid_mod.uuid4()),
                             border_mesh, f"{safe_name} - Fill Only", "2"))
    else:
        object_files.append(("object_1.model", 1, 2,
                             str(uuid_mod.uuid4()), str(uuid_mod.uuid4()),
                             text_mesh, safe_name, "1"))

    # Build main model with component references
    # Positions match Bambu Studio's plate layout in the overview
    plate_positions = {
        1: (128.0, 68.0),
        2: (474.0, 68.0),
        3: (128.0, -218.0),
    }
    build_uuid = str(uuid_mod.uuid4())
    resource_lines = []
    build_lines = []
    build_transforms = {}
    for (fname, part_id, wrap_id, part_uuid, wrap_uuid, mesh, name, extruder) in object_files:
        resource_lines.append(
            f'  <object id="{wrap_id}" p:UUID="{wrap_uuid}" type="model">\n'
            f'   <components>\n'
            f'    <component p:path="/3D/Objects/{fname}" objectid="{part_id}"'
            f' p:UUID="{part_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            f'   </components>\n'
            f'  </object>'
        )
        plate_idx = _get_plate_for_object(wrap_id, object_files, has_border)
        px, py = plate_positions.get(plate_idx, (128.0, 68.0))
        build_transforms[wrap_id] = (px, py, 0.0)
        build_lines.append(
            f'  <item objectid="{wrap_id}" p:UUID="{str(uuid_mod.uuid4())}"'
            f' transform="1 0 0 0 1 0 0 0 1 {px} {py} 0" printable="1"/>'
        )

    from datetime import date
    today = date.today().isoformat()

    main_model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">\n'
        f' <metadata name="Application">BambuStudio-02.05.00.66</metadata>\n'
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        ' <metadata name="Copyright"></metadata>\n'
        f' <metadata name="CreationDate">{today}</metadata>\n'
        ' <metadata name="Description"></metadata>\n'
        ' <metadata name="Designer"></metadata>\n'
        ' <metadata name="DesignerCover"></metadata>\n'
        ' <metadata name="License"></metadata>\n'
        f' <metadata name="ModificationDate">{today}</metadata>\n'
        ' <metadata name="Origin"></metadata>\n'
        f' <metadata name="Title">{safe_name}</metadata>\n'
        ' <resources>\n'
        + '\n'.join(resource_lines) + '\n'
        ' </resources>\n'
        f' <build p:UUID="{build_uuid}">\n'
        + '\n'.join(build_lines) + '\n'
        ' </build>\n'
        '</model>'
    )

    # Relationships for object files
    rel_lines = []
    for i, (fname, *_) in enumerate(object_files, 1):
        rel_lines.append(
            f' <Relationship Target="/3D/Objects/{fname}" Id="rel-{i}"'
            f' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        )
    model_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        + '\n'.join(rel_lines) + '\n'
        '</Relationships>'
    )

    # model_settings.config with object metadata and plate assignments
    config_objects = []
    for (fname, part_id, wrap_id, part_uuid, wrap_uuid, mesh, name, extruder) in object_files:
        geom = mesh if not isinstance(mesh, trimesh.Scene) else list(mesh.geometry.values())[0]
        face_count = len(geom.faces)
        config_objects.append(
            f'  <object id="{wrap_id}">\n'
            f'    <metadata key="name" value="{name}"/>\n'
            f'    <metadata key="extruder" value="{extruder}"/>\n'
            f'    <metadata face_count="{face_count}"/>\n'
            f'    <part id="{part_id}" subtype="normal_part">\n'
            f'      <metadata key="name" value="{name}"/>\n'
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <mesh_stat face_count="{face_count}" edges_fixed="0"'
            f' degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
            f'    </part>\n'
            f'  </object>'
        )

    identify_counter = [100]
    def _next_identify_id():
        identify_counter[0] += 11
        return identify_counter[0]

    plate_configs = []
    if has_border:
        plate_configs.append(
            '  <plate>\n'
            '    <metadata key="plater_id" value="1"/>\n'
            f'    <metadata key="plater_name" value="Combined"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{object_files[0][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            '    </model_instance>\n'
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{object_files[1][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            '    </model_instance>\n'
            '  </plate>'
        )
        plate_configs.append(
            '  <plate>\n'
            '    <metadata key="plater_id" value="2"/>\n'
            f'    <metadata key="plater_name" value="Text Only"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{object_files[2][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            '    </model_instance>\n'
            '  </plate>'
        )
        plate_configs.append(
            '  <plate>\n'
            '    <metadata key="plater_id" value="3"/>\n'
            f'    <metadata key="plater_name" value="Fill Only"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{object_files[3][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            '    </model_instance>\n'
            '  </plate>'
        )
    else:
        plate_configs.append(
            '  <plate>\n'
            '    <metadata key="plater_id" value="1"/>\n'
            f'    <metadata key="plater_name" value="{safe_name}"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{object_files[0][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            '    </model_instance>\n'
            '  </plate>'
        )

    assemble_items = []
    for (fname, part_id, wrap_id, part_uuid, wrap_uuid, mesh, name, extruder) in object_files:
        tx, ty, tz = build_transforms[wrap_id]
        assemble_items.append(
            f'   <assemble_item object_id="{wrap_id}" instance_id="0"'
            f' transform="1 0 0 0 1 0 0 0 1 {tx} {ty} {tz}" offset="0 0 0" />'
        )

    config_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<config>\n'
        + '\n'.join(config_objects) + '\n'
        + '\n'.join(plate_configs) + '\n'
        '  <assemble>\n'
        + '\n'.join(assemble_items) + '\n'
        '  </assemble>\n'
        '</config>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType='
        '"application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType='
        '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '</Types>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>'
    )

    slice_info = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<config>\n'
        '  <header>\n'
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        '    <header_item key="X-BBL-Client-Version" value="02.05.00.66"/>\n'
        '  </header>\n'
        '</config>'
    )

    num_plates = 3 if has_border else 1
    plate_seqs = ", ".join(
        f'"plate_{i}": {{"sequence": []}}' for i in range(1, num_plates + 1)
    )
    filament_seq = "{" + plate_seqs + "}"

    project_settings_path = os.path.join(
        os.path.dirname(__file__), 'bambu_project_settings.json'
    )
    project_settings = ""
    if os.path.exists(project_settings_path):
        with open(project_settings_path, 'r') as f:
            project_settings = f.read()

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', root_rels)
        zf.writestr('3D/3dmodel.model', main_model)
        zf.writestr('3D/_rels/3dmodel.model.rels', model_rels)
        for (fname, part_id, wrap_id, part_uuid, wrap_uuid, mesh, name, extruder) in object_files:
            obj_xml = _mesh_to_object_model(mesh, part_id, part_uuid)
            zf.writestr(f'3D/Objects/{fname}', obj_xml)
        zf.writestr('Metadata/model_settings.config', config_xml)
        zf.writestr('Metadata/slice_info.config', slice_info)
        zf.writestr('Metadata/filament_sequence.json', filament_seq)
        if project_settings:
            zf.writestr('Metadata/project_settings.config', project_settings)
    buf.seek(0)
    return buf
