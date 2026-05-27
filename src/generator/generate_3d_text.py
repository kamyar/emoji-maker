import tempfile
import os
import logging
import time
from io import BytesIO
from typing import Literal

import cadquery as cq
from pydantic import BaseModel, Field

from src.generator.font_manager import get_font_path

logger = logging.getLogger("gen3d")


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
    fillColor: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    gap: float = Field(default=0, ge=0.0, le=5.0)
    addOutline: bool = False
    outlineWidth: float = Field(default=1.0, ge=0.2, le=10.0)
    keychainHole: bool = False
    keychainCorner: Literal["bottom-left", "bottom-right", "top-left", "top-right"] = (
        "bottom-left"
    )
    keychainRadius: float = Field(default=3.0, ge=1.0, le=20.0)
    keychainEdgeH: float = Field(default=3.0, ge=0.0, le=50.0)
    keychainEdgeV: float = Field(default=3.0, ge=0.0, le=50.0)
    keychainThickness: float = Field(default=3.0, ge=0.5, le=20.0)
    backplate: bool = False
    backplateThickness: float = Field(default=1.0, ge=0.2, le=10.0)
    scale: float = Field(default=1.0, ge=0.1, le=10.0)
    color: str = Field(default="#667eea", pattern=r"^#[0-9a-fA-F]{6}$")
    exportFormat: Literal["stl", "3mf"] = "stl"


_char_cache = {}
_poly_cache = {}


def _render_char(char: str, font_size: float, font_path: str, extrude_height: float):
    key = (char, font_size, font_path, extrude_height)
    if key in _char_cache:
        return _char_cache[key]
    t0 = time.time()
    wp = cq.Workplane("front").text(char, font_size, extrude_height, fontPath=font_path)
    solid = wp.val()
    bb = solid.BoundingBox()
    logger.debug(
        "_render_char %r: %.0fms  bb=(%.2f,%.2f)-(%.2f,%.2f)",
        char,
        (time.time() - t0) * 1000,
        bb.xmin,
        bb.ymin,
        bb.xmax,
        bb.ymax,
    )
    _char_cache[key] = (solid, bb)
    return solid, bb


def _prerender_chars(text, font_size, font_path, extrude_height, need_polys):
    """Pre-render all unique characters and their 2D polygons in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    unique_chars = sorted(set(c for c in text if c not in (" ", "\n")))
    if not unique_chars:
        return

    t0 = time.time()

    def render_one(ch):
        solid, bb = _render_char(ch, font_size, font_path, extrude_height)
        if need_polys:
            key = (ch, font_size, font_path, extrude_height)
            _poly_cache[key] = _char_to_2d_polygon(solid, extrude_height)

    workers = min(len(unique_chars), os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(render_one, unique_chars))

    logger.info(
        "_prerender_chars: %d chars, %d workers, %.0fms",
        len(unique_chars),
        workers,
        (time.time() - t0) * 1000,
    )


def _render_line(
    text: str,
    font_size: float,
    font_path: str,
    letter_spacing: float,
    extrude_height: float,
) -> tuple[list, float]:
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

    return solids, (x - letter_spacing) if solids else 0.0


def _char_to_2d_polygon(char_solid, extrude_height):
    """Extract a 2D polygon from a 3D char via BREP face wires (no STL round-trip)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopoDS import TopoDS

    t0 = time.time()
    top_faces = []
    explorer = TopExp_Explorer(char_solid.wrapped, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surf = BRep_Tool.Surface_s(face)
        # Check if face normal points up (top face of extrusion)
        try:
            from OCP.GeomLProp import GeomLProp_SLProps

            props = GeomLProp_SLProps(surf, 0.5, 0.5, 1, 1e-6)
            if props.IsNormalDefined():
                normal = props.Normal()
                if (
                    abs(normal.Z() - 1.0) < 0.1
                    and abs(normal.X()) < 0.1
                    and abs(normal.Y()) < 0.1
                ):
                    top_faces.append(face)
        except Exception:
            pass
        explorer.Next()

    if not top_faces:
        logger.warning("_char_to_2d_polygon: no top faces found, falling back to STL")
        return _char_to_2d_polygon_stl(char_solid, extrude_height)

    polygons = []
    for face in top_faces:
        wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
        wires = []
        while wire_exp.More():
            wires.append(wire_exp.Current())
            wire_exp.Next()

        if not wires:
            continue

        wire_coords = []
        for wire in wires:
            w = TopoDS.Wire_s(wire)
            pts = []
            we = BRepTools_WireExplorer(w)
            while we.More():
                edge = TopoDS.Edge_s(we.Current())
                try:
                    from OCP.BRepAdaptor import BRepAdaptor_Curve
                    from OCP.GCPnts import GCPnts_TangentialDeflection

                    adaptor = BRepAdaptor_Curve(edge)
                    discretizer = GCPnts_TangentialDeflection(adaptor, 0.1, 0.1)
                    for i in range(1, discretizer.NbPoints() + 1):
                        p = discretizer.Value(i)
                        pts.append((round(p.X(), 4), round(p.Y(), 4)))
                except Exception:
                    pass
                we.Next()
            if len(pts) >= 3:
                wire_coords.append(pts)

        if not wire_coords:
            continue

        wire_coords.sort(
            key=lambda c: Polygon(c).area if len(c) >= 3 else 0, reverse=True
        )
        outer = wire_coords[0]
        holes = [c for c in wire_coords[1:] if len(c) >= 3]
        try:
            poly = Polygon(outer, holes)
            if poly.is_valid and poly.area > 0.01:
                polygons.append(poly)
        except Exception:
            pass

    if not polygons:
        logger.warning(
            "_char_to_2d_polygon: BREP extraction failed, falling back to STL"
        )
        return _char_to_2d_polygon_stl(char_solid, extrude_height)

    result = unary_union(polygons)
    logger.debug(
        "_char_to_2d_polygon: BREP path, %d faces, area=%.2f, %.0fms",
        len(polygons),
        result.area,
        (time.time() - t0) * 1000,
    )
    return result


def _char_to_2d_polygon_stl(char_solid, extrude_height):
    """Fallback: extract 2D polygon via STL cross-section."""
    import trimesh
    import trimesh.intersections
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union

    t0 = time.time()
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        stl_path = f.name
    try:
        cq.exporters.export(
            cq.Workplane("front").newObject([char_solid]),
            stl_path,
            exportType="STL",
            tolerance=0.01,
            angularTolerance=0.05,
        )
        mesh = trimesh.load(stl_path, file_type="stl")
    finally:
        os.unlink(stl_path)

    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

    lines3d = trimesh.intersections.mesh_plane(
        mesh, plane_normal=[0, 0, 1], plane_origin=[0, 0, extrude_height / 2]
    )
    if lines3d is None or len(lines3d) == 0:
        logger.warning("_char_to_2d_polygon_stl: no cross-section lines found")
        return None

    snap = 3
    segments = [
        LineString(
            [
                (round(s[0][0], snap), round(s[0][1], snap)),
                (round(s[1][0], snap), round(s[1][1], snap)),
            ]
        )
        for s in lines3d
    ]
    segments = [s for s in segments if s.length > 0]

    raw_polys = list(polygonize(unary_union(segments)))
    if not raw_polys:
        logger.warning(
            "_char_to_2d_polygon_stl: polygonize returned 0 polys from %d segments",
            len(segments),
        )
        return None

    raw_polys.sort(key=lambda p: p.area, reverse=True)
    outer = raw_polys[0]
    holes = []
    outer_filled = Polygon(outer.exterior.coords)
    for p in raw_polys[1:]:
        if outer_filled.contains(p.representative_point()):
            holes.append(p.exterior.coords)
    result = Polygon(outer.exterior.coords, holes)

    logger.debug(
        "_char_to_2d_polygon_stl: %d polys, %d holes, area=%.2f, %.0fms",
        len(raw_polys),
        len(holes),
        result.area,
        (time.time() - t0) * 1000,
    )
    return result


def _build_outline_polygon(all_char_polys, outline_width, gap_mm=0.0):
    from shapely.ops import unary_union

    all_chars = unary_union(all_char_polys)
    inner = (
        all_chars.buffer(gap_mm, quad_segs=16, join_style=1)
        if gap_mm > 0
        else all_chars
    )
    outer = all_chars.buffer(gap_mm + outline_width, quad_segs=16, join_style=1)
    return outer.difference(inner)


def _build_outline_compound(
    cutter_compound, all_char_polys, outline_width, extrude_height, gap_mm=0.0
):
    import trimesh
    from shapely.geometry import MultiPolygon

    t0 = time.time()
    logger.debug(
        "_build_outline: width=%.2f gap=%.2f, %d char polys",
        outline_width,
        gap_mm,
        len(all_char_polys),
    )

    outline_poly = _build_outline_polygon(all_char_polys, outline_width, gap_mm)
    logger.debug("_build_outline: outline_poly area=%.2f", outline_poly.area)

    if outline_poly.is_empty:
        logger.warning("_build_outline: outline polygon is empty")
        return None

    if isinstance(outline_poly, MultiPolygon):
        parts = [
            trimesh.creation.extrude_polygon(p, extrude_height)
            for p in outline_poly.geoms
        ]
        result_mesh = trimesh.util.concatenate(parts)
    else:
        result_mesh = trimesh.creation.extrude_polygon(outline_poly, extrude_height)
    logger.debug(
        "_build_outline: result_mesh verts=%d faces=%d",
        len(result_mesh.vertices),
        len(result_mesh.faces),
    )

    if not hasattr(result_mesh, "vertices") or len(result_mesh.vertices) == 0:
        logger.warning("_build_outline: extrusion produced empty mesh")
        return None

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        out_path = f.name
    try:
        result_mesh.export(out_path, file_type="stl")
        from OCP.StlAPI import StlAPI_Reader
        from OCP.TopoDS import TopoDS_Shape as OCP_Shape

        reader = StlAPI_Reader()
        shape = OCP_Shape()
        status = reader.Read(shape, out_path)
        if not status or shape.IsNull():
            logger.warning(
                "_build_outline: StlAPI_Reader produced null shape (status=%s)", status
            )
            return None
        logger.debug("_build_outline: done %.0fms", (time.time() - t0) * 1000)
        return cq.Shape.cast(shape)
    finally:
        os.unlink(out_path)


class Generate3DResult(BaseModel):
    width: float
    height: float
    depth: float


def _build_gap_ring_cutters(all_char_polys, gap_mm, extrude_height):
    """Create gap ring meshes via 2D offset — like Fusion360 outline/offset.

    For each char polygon, buffer outward by gap_mm then subtract the original.
    This produces uniform-width gap rings on the outside AND inside holes
    (D, O, A, R, etc.) in one operation.
    """
    import trimesh
    from shapely.geometry import MultiPolygon

    t0 = time.time()
    meshes = []
    for poly in all_char_polys:
        if poly is None:
            continue
        expanded = poly.buffer(gap_mm, quad_segs=16)
        gap_ring = expanded.difference(poly)
        if gap_ring.is_empty:
            continue
        if isinstance(gap_ring, MultiPolygon):
            for p in gap_ring.geoms:
                meshes.append(trimesh.creation.extrude_polygon(p, extrude_height))
        else:
            meshes.append(trimesh.creation.extrude_polygon(gap_ring, extrude_height))
    logger.debug(
        "_build_gap_ring_cutters: %d rings from %d polys, %.0fms",
        len(meshes),
        len(all_char_polys),
        (time.time() - t0) * 1000,
    )
    return meshes


def _build_expanded_text_cutters(all_char_polys, gap_mm, extrude_height):
    """Extrude gap-expanded char polygons for single-pass plate cutting.

    Unlike _build_gap_ring_cutters (which creates rings), this creates the
    full expanded shape so we can cut text+gap from the plate in one boolean.
    Avoids slivers from double-cut (BREP text + mesh gap ring).
    """
    import trimesh
    from shapely.geometry import MultiPolygon

    t0 = time.time()
    meshes = []
    for poly in all_char_polys:
        if poly is None:
            continue
        expanded = poly.buffer(gap_mm, quad_segs=16)
        if expanded.is_empty:
            continue
        if isinstance(expanded, MultiPolygon):
            for p in expanded.geoms:
                meshes.append(trimesh.creation.extrude_polygon(p, extrude_height))
        else:
            meshes.append(trimesh.creation.extrude_polygon(expanded, extrude_height))
    logger.debug(
        "_build_expanded_text_cutters: %d meshes from %d polys, %.0fms",
        len(meshes),
        len(all_char_polys),
        (time.time() - t0) * 1000,
    )
    return meshes


def _apply_scale(compound, scale):
    if scale != 1.0:
        from OCP.gp import gp_Trsf, gp_Pnt
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), scale)
        builder = BRepBuilderAPI_Transform(compound.wrapped, trsf, True)
        compound = cq.Shape.cast(builder.Shape())
    return compound


def _position_solids(
    lines: list[str],
    font_size: float,
    font_path: str,
    letter_spacing: float,
    line_spacing: float,
    extrude_height: float,
) -> tuple[list[cq.Shape], float]:
    """Render all lines of text and position solids in a centered multi-line layout."""
    line_results = []
    for line in lines:
        solids, width = _render_line(
            line, font_size, font_path, letter_spacing, extrude_height
        )
        line_results.append((solids, width))

    max_width = max((w for _, w in line_results), default=0)
    if max_width == 0:
        raise ValueError("No visible characters in text")

    all_solids: list[cq.Shape] = []
    line_height = font_size + line_spacing

    for line_idx, (solids, width) in enumerate(line_results):
        if not solids:
            continue
        x_offset = (max_width - width) / 2
        y_offset = -line_idx * line_height

        if letter_spacing == 0 and solids:
            bb = solids[0].BoundingBox()
            centered = solids[0].moved(
                cq.Location(cq.Vector(x_offset - bb.xmin, y_offset, 0))
            )
            all_solids.append(centered)
        else:
            for solid in solids:
                moved = solid.moved(cq.Location(cq.Vector(x_offset, y_offset, 0)))
                all_solids.append(moved)

    logger.debug(
        "_position_solids: %d solids, max_width=%.2f", len(all_solids), max_width
    )
    return all_solids, max_width


def _collect_char_polys(
    lines: list[str],
    font_size: float,
    font_path: str,
    letter_spacing: float,
    line_spacing: float,
    extrude_height: float,
    max_width: float,
) -> list:
    """Build positioned 2D shapely polygons for each character across all lines."""
    from shapely import affinity

    local_poly_cache: dict[str, object] = {}
    all_char_polys = []
    line_height = font_size + line_spacing

    for li, line in enumerate(lines):
        if not line.strip():
            continue

        if letter_spacing == 0:
            wp = cq.Workplane("front").text(
                line, font_size, extrude_height, fontPath=font_path
            )
            solid = wp.val()
            bb = solid.BoundingBox()
            line_width = bb.xmax - bb.xmin
            poly = _char_to_2d_polygon(solid, extrude_height)
            if poly is not None:
                x_off = (max_width - line_width) / 2 - bb.xmin
                y_off = -li * line_height
                all_char_polys.append(
                    affinity.translate(poly, xoff=x_off, yoff=y_off)
                )
            continue

        x = 0.0
        line_polys = []
        for char in line:
            if char == " ":
                x += font_size * 0.3 + letter_spacing
                continue
            orig_solid, orig_bb = _render_char(
                char, font_size, font_path, extrude_height
            )
            orig_w = orig_bb.xmax - orig_bb.xmin
            if char not in local_poly_cache:
                key = (char, font_size, font_path, extrude_height)
                if key in _poly_cache:
                    local_poly_cache[char] = _poly_cache[key]
                else:
                    local_poly_cache[char] = _char_to_2d_polygon(
                        orig_solid, extrude_height
                    )
            poly = local_poly_cache[char]
            if poly is not None:
                line_polys.append(affinity.translate(poly, xoff=x - orig_bb.xmin))
            x += orig_w + letter_spacing
        line_width = x - letter_spacing if line_polys else 0.0
        x_off = (max_width - line_width) / 2
        y_off = -li * line_height
        for p in line_polys:
            all_char_polys.append(affinity.translate(p, xoff=x_off, yoff=y_off))

    logger.debug("_collect_char_polys: %d polys", len(all_char_polys))
    return all_char_polys


def _build_fill_plate(
    content_bb: cq.BoundBox,
    padding: tuple[float, float, float, float],
    extrude_height: float,
    cutter_compound: cq.Compound = None,
) -> cq.Workplane:
    """Create a filled rectangular plate with text-shaped cutouts."""
    pt, pr, pb, pl = padding
    outer_w = (content_bb.xmax - content_bb.xmin) + pl + pr
    outer_h = (content_bb.ymax - content_bb.ymin) + pt + pb
    center_x = content_bb.xmin + (content_bb.xmax - content_bb.xmin) / 2 + (pr - pl) / 2
    center_y = content_bb.ymin + (content_bb.ymax - content_bb.ymin) / 2 + (pt - pb) / 2

    logger.debug(
        "_build_fill_plate: %.2fx%.2f center=(%.2f,%.2f)",
        outer_w,
        outer_h,
        center_x,
        center_y,
    )

    fill_inset = 0.2
    fill_plane = cq.Plane(origin=(0, 0, fill_inset), normal=(0, 0, 1))
    plate = (
        cq.Workplane(fill_plane)
        .center(center_x, center_y)
        .rect(outer_w, outer_h)
        .extrude(extrude_height - 2 * fill_inset)
    )
    if cutter_compound is not None:
        for i, solid in enumerate(cutter_compound.Solids()):
            plate = plate.cut(cq.Workplane("front").newObject([solid]))
        logger.debug("_build_fill_plate: %d solids cut", i + 1)
    return plate


def _keychain_hole_center(content_bb, padding, corner, radius, edge_h, edge_v):
    """Compute the XY center of the keychain hole."""
    pt, pr, pb, pl = padding
    fill_xmin = content_bb.xmin - pl
    fill_xmax = content_bb.xmax + pr
    fill_ymin = content_bb.ymin - pb
    fill_ymax = content_bb.ymax + pt

    if corner == "bottom-left":
        return fill_xmin + edge_h + radius, fill_ymin + edge_v + radius
    elif corner == "bottom-right":
        return fill_xmax - edge_h - radius, fill_ymin + edge_v + radius
    elif corner == "top-left":
        return fill_xmin + edge_h + radius, fill_ymax - edge_v - radius
    else:
        return fill_xmax - edge_h - radius, fill_ymax - edge_v - radius


def _cut_keychain_hole(
    plate, content_bb, padding, corner, radius, edge_h, edge_v, extrude_height
):
    """Subtract a cylindrical keychain hole from the plate (BREP path)."""
    hole_x, hole_y = _keychain_hole_center(
        content_bb, padding, corner, radius, edge_h, edge_v
    )
    hole = (
        cq.Workplane("front")
        .center(hole_x, hole_y)
        .circle(radius)
        .extrude(extrude_height)
    )
    return plate.cut(hole)


def _keychain_hole_mesh(
    content_bb, padding, corner, radius, edge_h, edge_v, extrude_height, z_min=0.0
):
    """Create a trimesh cylinder for the keychain hole (mesh boolean path)."""
    import trimesh

    hole_x, hole_y = _keychain_hole_center(
        content_bb, padding, corner, radius, edge_h, edge_v
    )
    cyl = trimesh.creation.cylinder(radius=radius, height=extrude_height, sections=32)
    cyl.apply_translation([hole_x, hole_y, z_min + extrude_height / 2])
    return cyl


def _keychain_clearance_mesh(
    content_bb, padding, corner, radius, thickness, edge_h, edge_v, extrude_height, z_min=0.0
):
    """Create a cylinder covering the ring's outer footprint, used to clear border geometry."""
    import trimesh

    hole_x, hole_y = _keychain_hole_center(
        content_bb, padding, corner, radius, edge_h, edge_v
    )
    cyl = trimesh.creation.cylinder(
        radius=radius + thickness, height=extrude_height, sections=32
    )
    cyl.apply_translation([hole_x, hole_y, z_min + extrude_height / 2])
    return cyl


def _keychain_ring_mesh(
    content_bb, padding, corner, radius, thickness, edge_h, edge_v, extrude_height, z_min=0.0
):
    """Create an annular reinforcement ring around the keychain hole."""
    import trimesh
    from shapely.geometry import Point

    hole_x, hole_y = _keychain_hole_center(
        content_bb, padding, corner, radius, edge_h, edge_v
    )
    outer_circle = Point(hole_x, hole_y).buffer(radius + thickness, resolution=32)
    inner_circle = Point(hole_x, hole_y).buffer(radius, resolution=32)
    ring_poly = outer_circle.difference(inner_circle)
    ring_mesh = trimesh.creation.extrude_polygon(ring_poly, extrude_height)
    if z_min:
        ring_mesh.apply_translation([0, 0, z_min])
    return ring_mesh


def _build_frame_border(
    content_bb: cq.BoundBox,
    padding: tuple[float, float, float, float],
    font_size: float,
    extrude_height: float,
) -> cq.Shape:
    """Create an unfilled rectangular frame border (outline only)."""
    pt, pr, pb, pl = padding
    outer_w = (content_bb.xmax - content_bb.xmin) + pl + pr
    outer_h = (content_bb.ymax - content_bb.ymin) + pt + pb
    center_x = content_bb.xmin + (content_bb.xmax - content_bb.xmin) / 2 + (pr - pl) / 2
    center_y = content_bb.ymin + (content_bb.ymax - content_bb.ymin) / 2 + (pt - pb) / 2

    wall = font_size * 0.08
    inner_w = outer_w - 2 * wall
    inner_h = outer_h - 2 * wall
    frame = (
        cq.Workplane("front")
        .center(center_x, center_y)
        .rect(outer_w, outer_h)
        .rect(inner_w, inner_h)
        .extrude(extrude_height)
    )
    return frame.val()


def _compute_dimensions(combined: cq.Shape) -> Generate3DResult:
    """Compute bounding-box dimensions of a compound shape."""
    bb = combined.BoundingBox()
    return Generate3DResult(
        width=round(bb.xmax - bb.xmin, 2),
        height=round(bb.ymax - bb.ymin, 2),
        depth=round(bb.zmax - bb.zmin, 2),
    )


def _build_geometry(input_data: Generate3DInput):
    t_start = time.time()
    _char_cache.clear()
    _poly_cache.clear()
    font_path = get_font_path(input_data.font)
    if not font_path:
        raise ValueError(f"Unknown font: {input_data.font}")
    logger.debug("_build_geometry: font=%s path=%s", input_data.font, font_path)

    lines = input_data.text.split("\n")
    need_polys = (
        input_data.addOutline
        or (input_data.gap > 0 and input_data.fillBorder)
        or input_data.backplate
    )

    # Pre-render all unique chars (and their 2D polys) in parallel
    _prerender_chars(
        input_data.text,
        input_data.fontSize,
        font_path,
        input_data.extrudeHeight,
        need_polys,
    )

    # Extrude each char, position per-line centered on the widest line
    all_solids, max_width = _position_solids(
        lines,
        input_data.fontSize,
        font_path,
        input_data.letterSpacing,
        input_data.lineSpacing,
        input_data.extrudeHeight,
    )

    text_compound = cq.Compound.makeCompound(all_solids)
    border_compound = None
    cutter_compound = text_compound

    # Collect 2D char polygons if needed for outline, gap, or backplate
    all_char_polys = None
    need_polys = (
        input_data.addOutline
        or (input_data.gap > 0 and input_data.fillBorder)
        or input_data.backplate
    )
    if need_polys:
        all_char_polys = _collect_char_polys(
            lines,
            input_data.fontSize,
            font_path,
            input_data.letterSpacing,
            input_data.lineSpacing,
            input_data.extrudeHeight,
            max_width,
        )

    # Outline: 2D buffer around char polygons, extruded, then boolean-subtract text
    outline_compound = None
    if input_data.addOutline and all_char_polys:
        outline_compound = _build_outline_compound(
            cutter_compound,
            all_char_polys,
            input_data.outlineWidth,
            input_data.extrudeHeight,
            input_data.gap,
        )
        logger.debug(
            "_build_geometry: outline_compound=%s", "ok" if outline_compound else "None"
        )

    # Border: sized to fit text (+ outline if present) + padding
    if input_data.addBorder:
        if outline_compound is not None:
            content_bb = cq.Compound.makeCompound(
                [text_compound, outline_compound]
            ).BoundingBox()
        else:
            content_bb = text_compound.BoundingBox()

        padding = (
            input_data.borderPaddingTop,
            input_data.borderPaddingRight,
            input_data.borderPaddingBottom,
            input_data.borderPaddingLeft,
        )

        if input_data.fillBorder:
            if input_data.gap > 0 and all_char_polys:
                # Single-pass: text+gap cut via one mesh boolean
                plate = _build_fill_plate(content_bb, padding, input_data.extrudeHeight)
                import trimesh as _tm

                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                    plate_stl = f.name
                try:
                    cq.exporters.export(plate, plate_stl, exportType="STL")
                    plate_mesh = _tm.load(plate_stl, file_type="stl")
                finally:
                    os.unlink(plate_stl)
                if isinstance(plate_mesh, _tm.Scene):
                    plate_mesh = _tm.util.concatenate(
                        list(plate_mesh.geometry.values())
                    )
                expanded_meshes = _build_expanded_text_cutters(
                    all_char_polys, input_data.gap, input_data.extrudeHeight
                )
                if expanded_meshes:
                    cutter_mesh = _tm.util.concatenate(expanded_meshes)
                    result_mesh = _tm.boolean.difference(
                        [plate_mesh, cutter_mesh], engine="manifold"
                    )
                else:
                    result_mesh = plate_mesh
                if hasattr(result_mesh, "vertices") and len(result_mesh.vertices) > 0:
                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                        out_stl = f.name
                    try:
                        result_mesh.export(out_stl, file_type="stl")
                        from OCP.StlAPI import StlAPI_Reader
                        from OCP.TopoDS import TopoDS_Shape as OCP_Shape

                        reader = StlAPI_Reader()
                        shape = OCP_Shape()
                        reader.Read(shape, out_stl)
                    finally:
                        os.unlink(out_stl)
                    if not shape.IsNull():
                        plate = cq.Workplane("front").newObject([cq.Shape.cast(shape)])
                logger.debug(
                    "_build_geometry: single-pass gap cut %d meshes",
                    len(expanded_meshes),
                )
            else:
                plate = _build_fill_plate(
                    content_bb,
                    padding,
                    input_data.extrudeHeight,
                    cutter_compound,
                )
            border_compound = plate.val()
        else:
            # Thin rectangular frame, no fill
            border_compound = _build_frame_border(
                content_bb,
                padding,
                input_data.fontSize,
                input_data.extrudeHeight,
            )

    # Collect border pieces individually (don't merge yet — keychain needs clean per-piece booleans)
    border_parts = []
    if border_compound is not None:
        border_parts.append(border_compound)
    if outline_compound is not None:
        border_parts.append(outline_compound)

    # Backplate: thin extrusion following the content silhouette
    if input_data.backplate and all_char_polys:
        import trimesh as _tm
        from shapely.ops import unary_union
        from shapely.geometry import MultiPolygon

        all_chars_union = unary_union(all_char_polys)
        if input_data.addOutline:
            bp_poly = all_chars_union.buffer(
                input_data.gap + input_data.outlineWidth,
                quad_segs=16,
                join_style=1,
            )
        else:
            bp_poly = all_chars_union
        if not bp_poly.is_empty:
            if isinstance(bp_poly, MultiPolygon):
                parts = [
                    _tm.creation.extrude_polygon(p, input_data.backplateThickness)
                    for p in bp_poly.geoms
                ]
                bp_mesh = _tm.util.concatenate(parts)
            else:
                bp_mesh = _tm.creation.extrude_polygon(
                    bp_poly, input_data.backplateThickness
                )
            bp_mesh.apply_translation([0, 0, -input_data.backplateThickness])
            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                bp_stl = f.name
            try:
                bp_mesh.export(bp_stl, file_type="stl")
                from OCP.StlAPI import StlAPI_Reader
                from OCP.TopoDS import TopoDS_Shape as OCP_Shape

                reader = StlAPI_Reader()
                shape = OCP_Shape()
                reader.Read(shape, bp_stl)
            finally:
                os.unlink(bp_stl)
            if not shape.IsNull():
                border_parts.append(cq.Shape.cast(shape))

    # Keychain: cut clearance from each border piece individually, add ring, cut hole
    if input_data.keychainHole:
        if outline_compound is not None:
            kc_bb = cq.Compound.makeCompound(
                [text_compound, outline_compound]
            ).BoundingBox()
        else:
            kc_bb = text_compound.BoundingBox()
        kc_padding = (
            input_data.borderPaddingTop,
            input_data.borderPaddingRight,
            input_data.borderPaddingBottom,
            input_data.borderPaddingLeft,
        )
        import trimesh as _tm

        backplate_depth = input_data.backplateThickness if input_data.backplate else 0
        keychain_z_min = -backplate_depth
        keychain_height = input_data.extrudeHeight + backplate_depth
        cut_z_min = keychain_z_min - 1
        cut_height = keychain_height + 2
        clearance_mesh = _keychain_clearance_mesh(
            kc_bb,
            kc_padding,
            input_data.keychainCorner,
            input_data.keychainRadius,
            input_data.keychainThickness,
            input_data.keychainEdgeH,
            input_data.keychainEdgeV,
            cut_height,
            cut_z_min,
        )
        # Step 1: cut solid cylinder (ring outer footprint) from each border piece individually
        cut_parts = []
        for part in border_parts:
            try:
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                    part_stl = f.name
                try:
                    cq.exporters.export(
                        cq.Workplane("front").newObject([part]),
                        part_stl,
                        exportType="STL",
                    )
                    part_mesh = _tm.load(part_stl, file_type="stl")
                finally:
                    os.unlink(part_stl)
                if isinstance(part_mesh, _tm.Scene):
                    part_mesh = _tm.util.concatenate(list(part_mesh.geometry.values()))
                result = _tm.boolean.difference(
                    [part_mesh, clearance_mesh], engine="manifold"
                )
                if hasattr(result, "vertices") and len(result.vertices) > 0:
                    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                        out_stl = f.name
                    try:
                        result.export(out_stl, file_type="stl")
                        from OCP.StlAPI import StlAPI_Reader
                        from OCP.TopoDS import TopoDS_Shape as OCP_Shape

                        reader = StlAPI_Reader()
                        s = OCP_Shape()
                        reader.Read(s, out_stl)
                    finally:
                        os.unlink(out_stl)
                    if not s.IsNull():
                        cut_parts.append(cq.Shape.cast(s))
                    else:
                        cut_parts.append(part)
                else:
                    cut_parts.append(part)
            except Exception as e:
                logger.warning("keychain clearance cut on part failed: %s", e)
                cut_parts.append(part)

        # Step 2: build ring with hole already cut
        ring_mesh = _keychain_ring_mesh(
            kc_bb,
            kc_padding,
            input_data.keychainCorner,
            input_data.keychainRadius,
            input_data.keychainThickness,
            input_data.keychainEdgeH,
            input_data.keychainEdgeV,
            keychain_height,
            keychain_z_min,
        )
        hole_mesh = _keychain_hole_mesh(
            kc_bb,
            kc_padding,
            input_data.keychainCorner,
            input_data.keychainRadius,
            input_data.keychainEdgeH,
            input_data.keychainEdgeV,
            cut_height,
            cut_z_min,
        )
        ring_with_hole = _tm.boolean.difference(
            [ring_mesh, hole_mesh], engine="manifold"
        )
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            ring_stl = f.name
        try:
            ring_with_hole.export(ring_stl, file_type="stl")
            from OCP.StlAPI import StlAPI_Reader
            from OCP.TopoDS import TopoDS_Shape as OCP_Shape

            reader = StlAPI_Reader()
            shape = OCP_Shape()
            reader.Read(shape, ring_stl)
        finally:
            os.unlink(ring_stl)
        if not shape.IsNull():
            cut_parts.append(cq.Shape.cast(shape))

        border_parts = cut_parts

    # Merge all border parts into border_compound
    if border_parts:
        border_compound = (
            cq.Compound.makeCompound(border_parts)
            if len(border_parts) > 1
            else border_parts[0]
        )
    else:
        border_compound = None

    # Final uniform scale (e.g. mm → inches)
    text_compound = _apply_scale(text_compound, input_data.scale)
    if border_compound is not None:
        border_compound = _apply_scale(border_compound, input_data.scale)

    if border_compound is not None:
        combined = cq.Compound.makeCompound([border_compound, text_compound])
    else:
        combined = text_compound

    dimensions = _compute_dimensions(combined)

    logger.info(
        "_build_geometry: border_compound=%s, outline=%s, backplate=%s, keychain=%s",
        "yes" if border_compound is not None else "None",
        "yes" if outline_compound is not None else "None",
        input_data.backplate,
        input_data.keychainHole,
    )
    logger.info(
        "_build_geometry: %.1fx%.1fx%.1fmm, total %.0fms",
        dimensions.width,
        dimensions.height,
        dimensions.depth,
        (time.time() - t_start) * 1000,
    )
    return text_compound, border_compound, dimensions


def _compound_to_workplane(compound):
    return cq.Workplane("front").newObject([compound])


def generate_3d_text(
    input_data: Generate3DInput,
) -> tuple[BytesIO, str, Generate3DResult]:
    text_compound, border_compound, dimensions = _build_geometry(input_data)

    if border_compound is not None:
        combined = cq.Compound.makeCompound([border_compound, text_compound])
    else:
        combined = text_compound

    result = _compound_to_workplane(combined)

    if input_data.exportFormat == "stl":
        return _export_stl(result), "model/stl", dimensions
    else:
        return (
            _export_3mf_multi(
                text_compound,
                border_compound,
                input_data.color,
                input_data.fillColor,
                model_name=input_data.text.split("\n")[0][:20],
            ),
            "model/3mf",
            dimensions,
        )


class Generate3DBothResult:
    def __init__(
        self,
        combined_stl: BytesIO,
        mf_buf: BytesIO,
        dimensions: Generate3DResult,
        text_stl: BytesIO,
        border_stl: BytesIO | None,
    ):
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
    border_stl = (
        _export_stl(_compound_to_workplane(border_compound))
        if border_compound
        else None
    )
    logger.info(
        "generate_3d_both: combined=%d text=%d border=%d bytes",
        len(combined_stl.getvalue()),
        len(text_stl.getvalue()),
        len(border_stl.getvalue()) if border_stl else 0,
    )

    mf_buf = _export_3mf_multi(
        text_compound,
        border_compound,
        input_data.color,
        input_data.fillColor,
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
        geoms = list(mesh.geometry.values())
        if geoms:
            mesh = trimesh.util.concatenate(geoms)
        else:
            mesh = trimesh.Trimesh()
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
        " <resources>",
        f'  <object id="{obj_id}" p:UUID="{uuid_str}" type="model">',
        "   <mesh>",
        "    <vertices>",
    ]
    for v in verts:
        lines.append(f'     <vertex x="{v[0]}" y="{v[1]}" z="{v[2]}"/>')
    lines.append("    </vertices>")
    lines.append("    <triangles>")
    for f in faces:
        lines.append(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>')
    lines.append("    </triangles>")
    lines.append("   </mesh>")
    lines.append("  </object>")
    lines.append(" </resources>")
    lines.append("</model>")
    return "\n".join(lines)


def _get_plate_for_object(wrap_id, object_files, has_border):
    if not has_border:
        return 1
    idx = next(i for i, o in enumerate(object_files) if o[2] == wrap_id)
    if idx <= 1:
        return 1
    if idx == 2:
        return 2
    return 3


def _export_3mf_multi(
    text_compound,
    border_compound,
    text_color: str,
    fill_color: str,
    model_name: str = "model",
) -> BytesIO:
    import trimesh
    import zipfile
    import re
    import uuid as uuid_mod

    safe_name = re.sub(r"[^\w\s-]", "", model_name).strip().replace(" ", "_") or "model"

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

    object_files = (
        []
    )  # (filename, part_id, wrapper_id, part_uuid, wrapper_uuid, mesh, name, extruder)

    if has_border:
        # Object 1: text for combined plate
        object_files.append(
            (
                "object_1.model",
                1,
                2,
                str(uuid_mod.uuid4()),
                str(uuid_mod.uuid4()),
                text_mesh,
                f"{safe_name} - Text",
                "1",
            )
        )
        # Object 2: fill for combined plate
        object_files.append(
            (
                "object_2.model",
                3,
                4,
                str(uuid_mod.uuid4()),
                str(uuid_mod.uuid4()),
                border_mesh,
                f"{safe_name} - Fill",
                "2",
            )
        )
        # Object 3: text-only plate
        object_files.append(
            (
                "object_3.model",
                5,
                6,
                str(uuid_mod.uuid4()),
                str(uuid_mod.uuid4()),
                text_mesh,
                f"{safe_name} - Text Only",
                "1",
            )
        )
        # Object 4: fill-only plate
        object_files.append(
            (
                "object_4.model",
                7,
                8,
                str(uuid_mod.uuid4()),
                str(uuid_mod.uuid4()),
                border_mesh,
                f"{safe_name} - Fill Only",
                "2",
            )
        )
    else:
        object_files.append(
            (
                "object_1.model",
                1,
                2,
                str(uuid_mod.uuid4()),
                str(uuid_mod.uuid4()),
                text_mesh,
                safe_name,
                "1",
            )
        )

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
    for (
        fname,
        part_id,
        wrap_id,
        part_uuid,
        wrap_uuid,
        mesh,
        name,
        extruder,
    ) in object_files:
        resource_lines.append(
            f'  <object id="{wrap_id}" p:UUID="{wrap_uuid}" type="model">\n'
            f"   <components>\n"
            f'    <component p:path="/3D/Objects/{fname}" objectid="{part_id}"'
            f' p:UUID="{part_uuid}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            f"   </components>\n"
            f"  </object>"
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
        " <resources>\n" + "\n".join(resource_lines) + "\n"
        " </resources>\n"
        f' <build p:UUID="{build_uuid}">\n' + "\n".join(build_lines) + "\n"
        " </build>\n"
        "</model>"
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
        + "\n".join(rel_lines)
        + "\n"
        "</Relationships>"
    )

    # model_settings.config with object metadata and plate assignments
    config_objects = []
    for (
        fname,
        part_id,
        wrap_id,
        part_uuid,
        wrap_uuid,
        mesh,
        name,
        extruder,
    ) in object_files:
        if isinstance(mesh, trimesh.Scene):
            geoms = list(mesh.geometry.values())
            geom = trimesh.util.concatenate(geoms) if geoms else trimesh.Trimesh()
        else:
            geom = mesh
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
            f"    </part>\n"
            f"  </object>"
        )

    identify_counter = [100]

    def _next_identify_id():
        identify_counter[0] += 11
        return identify_counter[0]

    plate_configs = []
    if has_border:
        plate_configs.append(
            "  <plate>\n"
            '    <metadata key="plater_id" value="1"/>\n'
            f'    <metadata key="plater_name" value="Combined"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_files[0][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            "    </model_instance>\n"
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_files[1][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            "    </model_instance>\n"
            "  </plate>"
        )
        plate_configs.append(
            "  <plate>\n"
            '    <metadata key="plater_id" value="2"/>\n'
            f'    <metadata key="plater_name" value="Text Only"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_files[2][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            "    </model_instance>\n"
            "  </plate>"
        )
        plate_configs.append(
            "  <plate>\n"
            '    <metadata key="plater_id" value="3"/>\n'
            f'    <metadata key="plater_name" value="Fill Only"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_files[3][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            "    </model_instance>\n"
            "  </plate>"
        )
    else:
        plate_configs.append(
            "  <plate>\n"
            '    <metadata key="plater_id" value="1"/>\n'
            f'    <metadata key="plater_name" value="{safe_name}"/>\n'
            '    <metadata key="locked" value="false"/>\n'
            '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            "    <model_instance>\n"
            f'      <metadata key="object_id" value="{object_files[0][2]}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{_next_identify_id()}"/>\n'
            "    </model_instance>\n"
            "  </plate>"
        )

    assemble_items = []
    for (
        fname,
        part_id,
        wrap_id,
        part_uuid,
        wrap_uuid,
        mesh,
        name,
        extruder,
    ) in object_files:
        tx, ty, tz = build_transforms[wrap_id]
        assemble_items.append(
            f'   <assemble_item object_id="{wrap_id}" instance_id="0"'
            f' transform="1 0 0 0 1 0 0 0 1 {tx} {ty} {tz}" offset="0 0 0" />'
        )

    config_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        + "\n".join(config_objects)
        + "\n"
        + "\n".join(plate_configs)
        + "\n"
        "  <assemble>\n" + "\n".join(assemble_items) + "\n"
        "  </assemble>\n"
        "</config>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType='
        '"application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType='
        '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        "</Relationships>"
    )

    slice_info = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        "  <header>\n"
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        '    <header_item key="X-BBL-Client-Version" value="02.05.00.66"/>\n'
        "  </header>\n"
        "</config>"
    )

    num_plates = 3 if has_border else 1
    plate_seqs = ", ".join(
        f'"plate_{i}": {{"sequence": []}}' for i in range(1, num_plates + 1)
    )
    filament_seq = "{" + plate_seqs + "}"

    project_settings_path = os.path.join(
        os.path.dirname(__file__), "bambu_project_settings.json"
    )
    project_settings = ""
    if os.path.exists(project_settings_path):
        with open(project_settings_path, "r") as f:
            project_settings = f.read()

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("3D/3dmodel.model", main_model)
        zf.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        for (
            fname,
            part_id,
            wrap_id,
            part_uuid,
            wrap_uuid,
            mesh,
            name,
            extruder,
        ) in object_files:
            obj_xml = _mesh_to_object_model(mesh, part_id, part_uuid)
            zf.writestr(f"3D/Objects/{fname}", obj_xml)
        zf.writestr("Metadata/model_settings.config", config_xml)
        zf.writestr("Metadata/slice_info.config", slice_info)
        zf.writestr("Metadata/filament_sequence.json", filament_seq)
        if project_settings:
            zf.writestr("Metadata/project_settings.config", project_settings)
    buf.seek(0)
    return buf
