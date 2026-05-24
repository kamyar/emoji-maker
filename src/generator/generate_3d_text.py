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
    scale: float = Field(default=1.0, ge=0.1, le=10.0)
    color: str = Field(default="#667eea", pattern=r"^#[0-9a-fA-F]{6}$")
    exportFormat: Literal["stl", "3mf"] = "stl"


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
        wp = cq.Workplane("front").text(
            char, font_size, extrude_height, fontPath=font_path
        )
        bb = wp.val().BoundingBox()
        char_width = bb.xmax - bb.xmin
        solid = wp.val().moved(cq.Location(cq.Vector(x - bb.xmin, 0, 0)))
        solids.append(solid)
        x += char_width + letter_spacing

    return solids, x


class Generate3DResult(BaseModel):
    width: float
    height: float
    depth: float


def _apply_scale(compound, scale):
    if scale != 1.0:
        compound = compound.transformShape(cq.Matrix([
            [scale, 0, 0, 0],
            [0, scale, 0, 0],
            [0, 0, scale, 0],
        ]))
    return compound


def _build_geometry(input_data: Generate3DInput):
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

    if input_data.addBorder:
        bb = text_compound.BoundingBox()
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
                .rect(outer_w - 2 * gap, outer_h - 2 * gap)
                .extrude(input_data.extrudeHeight - 2 * fill_inset)
            )
            text_wp = cq.Workplane("front").newObject([text_compound])
            plate = plate.cut(text_wp)
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


def _add_mesh_to_scene(scene, mesh, prefix, offset_y=0.0):
    import trimesh
    import numpy as np
    translate = np.eye(4)
    translate[1, 3] = offset_y
    if isinstance(mesh, trimesh.Scene):
        for name, geom in mesh.geometry.items():
            scene.add_geometry(geom, node_name=f"{prefix}_{name}",
                               transform=translate)
    else:
        scene.add_geometry(mesh, node_name=prefix, transform=translate)


def _export_3mf_multi(text_compound, border_compound,
                       text_color: str, fill_color: str) -> BytesIO:
    import trimesh

    text_stl = _export_stl(_compound_to_workplane(text_compound))
    text_mesh = _stl_buf_to_mesh(text_stl, text_color)

    if border_compound is not None:
        border_stl = _export_stl(_compound_to_workplane(border_compound))
        border_mesh = _stl_buf_to_mesh(border_stl, fill_color)

        combined_bb = text_mesh.bounds if hasattr(text_mesh, 'bounds') else text_mesh.bounding_box.bounds
        model_height = combined_bb[1][1] - combined_bb[0][1]
        spacing = model_height + 20

        scene = trimesh.Scene()

        _add_mesh_to_scene(scene, text_mesh, "combined_text", offset_y=0.0)
        _add_mesh_to_scene(scene, border_mesh, "combined_fill", offset_y=0.0)

        _add_mesh_to_scene(scene, text_mesh, "text_only", offset_y=spacing)

        _add_mesh_to_scene(scene, border_mesh, "fill_only", offset_y=spacing * 2)
    else:
        scene = text_mesh

    buf = BytesIO()
    scene.export(buf, file_type="3mf")
    buf.seek(0)
    return buf
