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

    compound = cq.Compound.makeCompound(all_solids)

    if input_data.addBorder:
        bb = compound.BoundingBox()
        pt = input_data.borderPaddingTop
        pr = input_data.borderPaddingRight
        pb = input_data.borderPaddingBottom
        pl = input_data.borderPaddingLeft
        outer_w = (bb.xmax - bb.xmin) + pl + pr
        outer_h = (bb.ymax - bb.ymin) + pt + pb
        wall = input_data.fontSize * 0.08
        inner_w = outer_w - 2 * wall
        inner_h = outer_h - 2 * wall
        center_x = bb.xmin + (bb.xmax - bb.xmin) / 2 + (pr - pl) / 2
        center_y = bb.ymin + (bb.ymax - bb.ymin) / 2 + (pt - pb) / 2

        frame = (
            cq.Workplane("front")
            .center(center_x, center_y)
            .rect(outer_w, outer_h)
            .rect(inner_w, inner_h)
            .extrude(input_data.extrudeHeight)
        )
        compound = cq.Compound.makeCompound([frame.val(), compound])

    if input_data.scale != 1.0:
        compound = compound.transformShape(cq.Matrix([
            [input_data.scale, 0, 0, 0],
            [0, input_data.scale, 0, 0],
            [0, 0, input_data.scale, 0],
        ]))

    bb = compound.BoundingBox()
    dimensions = Generate3DResult(
        width=round(bb.xmax - bb.xmin, 2),
        height=round(bb.ymax - bb.ymin, 2),
        depth=round(bb.zmax - bb.zmin, 2),
    )

    result = cq.Workplane("front").newObject([compound])
    return result, dimensions


def generate_3d_text(input_data: Generate3DInput) -> tuple[BytesIO, str, Generate3DResult]:
    result, dimensions = _build_geometry(input_data)

    if input_data.exportFormat == "stl":
        return _export_stl(result), "model/stl", dimensions
    else:
        return _export_3mf(result, input_data.color), "model/3mf", dimensions


def generate_3d_both(input_data: Generate3DInput) -> tuple[BytesIO, BytesIO, Generate3DResult]:
    result, dimensions = _build_geometry(input_data)
    stl_buf = _export_stl(result)
    mf_buf = _export_3mf_from_stl(stl_buf, input_data.color)
    return stl_buf, mf_buf, dimensions


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


def _export_3mf(result, color: str = "#667eea") -> BytesIO:
    stl_buf = _export_stl(result)
    return _export_3mf_from_stl(stl_buf, color)


def _export_3mf_from_stl(stl_buf: BytesIO, color: str = "#667eea") -> BytesIO:
    import trimesh
    import numpy as np

    stl_buf.seek(0)
    mesh = trimesh.load(stl_buf, file_type="stl")

    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    if isinstance(mesh, trimesh.Scene):
        for geom in mesh.geometry.values():
            geom.visual.face_colors = np.array([r, g, b, 255], dtype=np.uint8)
    else:
        mesh.visual.face_colors = np.array([r, g, b, 255], dtype=np.uint8)

    buf = BytesIO()
    mesh.export(buf, file_type="3mf")
    buf.seek(0)
    stl_buf.seek(0)
    return buf
