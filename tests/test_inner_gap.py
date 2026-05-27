"""Test that gap creates clearance around characters, including inside holes."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trimesh
import numpy as np
from src.generator.generate_3d_text import (
    Generate3DInput, generate_3d_both, _render_char, _char_to_2d_polygon,
    _build_gap_ring_cutters, _build_outline_polygon,
)
from src.generator.font_manager import get_font_path
from shapely.geometry import box


FONT = "Omnes Black"
FONT_SIZE = 24.0
EXTRUDE = 4.0
GAP_MM = 1.0


def _make_input(**overrides):
    defaults = dict(
        text="O", font=FONT, fontSize=FONT_SIZE, letterSpacing=0,
        lineSpacing=0, extrudeHeight=EXTRUDE, addBorder=True,
        fillBorder=True, fillColor="#ffffff", gap=GAP_MM,
        addOutline=False, outlineWidth=1, borderPaddingTop=4,
        borderPaddingRight=4, borderPaddingBottom=4, borderPaddingLeft=4,
        scale=1.0, color="#009de0", exportFormat="stl",
    )
    defaults.update(overrides)
    return Generate3DInput(**defaults)


def test_chars_with_holes_detected():
    """_char_to_2d_polygon must find interior holes for D, O, A, P, Q, R."""
    font_path = get_font_path(FONT)
    chars_with_holes = list("DOAQPR")
    chars_without_holes = list("FNTLI")

    for ch in chars_with_holes:
        solid, _ = _render_char(ch, FONT_SIZE, font_path, EXTRUDE)
        poly = _char_to_2d_polygon(solid, EXTRUDE)
        assert poly is not None, f"char '{ch}' returned None polygon"
        n_holes = len(list(poly.interiors))
        assert n_holes >= 1, f"char '{ch}' should have ≥1 hole, got {n_holes}"
        print(f"  '{ch}': {n_holes} hole(s) ✓")

    for ch in chars_without_holes:
        solid, _ = _render_char(ch, FONT_SIZE, font_path, EXTRUDE)
        poly = _char_to_2d_polygon(solid, EXTRUDE)
        assert poly is not None, f"char '{ch}' returned None polygon"
        n_holes = len(list(poly.interiors))
        assert n_holes == 0, f"char '{ch}' should have 0 holes, got {n_holes}"
        print(f"  '{ch}': 0 holes ✓")


def test_gap_ring_cutters_for_all_chars():
    """_build_gap_ring_cutters must produce ring meshes for any char (outside gap)
    and additional rings for chars with holes (inside gap)."""
    font_path = get_font_path(FONT)
    for ch in "DOAFNL":
        solid, _ = _render_char(ch, FONT_SIZE, font_path, EXTRUDE)
        poly = _char_to_2d_polygon(solid, EXTRUDE)
        assert poly is not None
        cutters = _build_gap_ring_cutters([poly], GAP_MM, EXTRUDE)
        assert len(cutters) >= 1, f"char '{ch}' should produce ≥1 ring cutter, got {len(cutters)}"
        total_vol = sum(m.volume for m in cutters)
        assert total_vol > 0, f"char '{ch}' ring cutters have zero volume"
        print(f"  '{ch}': {len(cutters)} ring(s), vol={total_vol:.1f}mm³ ✓")


def test_outline_respects_gap():
    """Outline should start outside the requested gap, not directly at text edge."""
    char_poly = box(0, 0, 10, 10)
    outline = _build_outline_polygon([char_poly], outline_width=2.0, gap_mm=0.2)

    assert outline.distance(char_poly) >= 0.19
    assert not outline.touches(char_poly)


def _measure_hole_fill_radius(border_stl_buf, char_center_xy, z_mid):
    """Measure how far the fill plate extends into a hole from its center."""
    border_stl_buf.seek(0)
    mesh = trimesh.load(border_stl_buf, file_type="stl")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
    lines = trimesh.intersections.mesh_plane(
        mesh, plane_normal=[0, 0, 1], plane_origin=[0, 0, z_mid])
    if lines is None or len(lines) == 0:
        return 0.0
    cx, cy = char_center_xy
    dists = []
    for seg in lines:
        for pt in seg:
            dists.append(np.sqrt((pt[0] - cx)**2 + (pt[1] - cy)**2))
    return min(dists) if dists else 0.0


def test_gap_reduces_fill_inside_hole():
    """With gap, the fill plate inside O's hole must be smaller than without gap."""
    input_no_gap = _make_input(text="O", gap=0)
    input_with_gap = _make_input(text="O", gap=GAP_MM)

    result_no_gap = generate_3d_both(input_no_gap)
    result_with_gap = generate_3d_both(input_with_gap)

    assert result_no_gap.border_stl is not None
    assert result_with_gap.border_stl is not None

    no_gap_stl = result_no_gap.border_stl
    no_gap_stl.seek(0)
    no_gap_mesh = trimesh.load(no_gap_stl, file_type="stl")
    if isinstance(no_gap_mesh, trimesh.Scene):
        no_gap_mesh = trimesh.util.concatenate(list(no_gap_mesh.geometry.values()))
    no_gap_vol = no_gap_mesh.volume

    with_gap_stl = result_with_gap.border_stl
    with_gap_stl.seek(0)
    with_gap_mesh = trimesh.load(with_gap_stl, file_type="stl")
    if isinstance(with_gap_mesh, trimesh.Scene):
        with_gap_mesh = trimesh.util.concatenate(list(with_gap_mesh.geometry.values()))
    with_gap_vol = with_gap_mesh.volume

    vol_diff = no_gap_vol - with_gap_vol
    print(f"  Fill volume without gap: {no_gap_vol:.1f}mm³")
    print(f"  Fill volume with gap:    {with_gap_vol:.1f}mm³")
    print(f"  Volume removed by gap:   {vol_diff:.1f}mm³")

    assert with_gap_vol < no_gap_vol, (
        f"Gap should reduce fill volume: {with_gap_vol:.1f} >= {no_gap_vol:.1f}")

    min_expected_removal = GAP_MM * 3.0
    assert vol_diff > min_expected_removal, (
        f"Gap should remove at least {min_expected_removal:.1f}mm³, "
        f"only removed {vol_diff:.1f}mm³")
    print(f"  ✓ Gap removed {vol_diff:.1f}mm³ from fill plate")


def test_outside_gap_increases_cutout():
    """With gap, the text cutout in the fill plate must be larger than without gap."""
    input_no_gap = _make_input(text="H", gap=0)
    input_with_gap = _make_input(text="H", gap=GAP_MM)

    result_no_gap = generate_3d_both(input_no_gap)
    result_with_gap = generate_3d_both(input_with_gap)

    no_gap_stl = result_no_gap.border_stl
    no_gap_stl.seek(0)
    no_gap_mesh = trimesh.load(no_gap_stl, file_type="stl")
    if isinstance(no_gap_mesh, trimesh.Scene):
        no_gap_mesh = trimesh.util.concatenate(list(no_gap_mesh.geometry.values()))

    with_gap_stl = result_with_gap.border_stl
    with_gap_stl.seek(0)
    with_gap_mesh = trimesh.load(with_gap_stl, file_type="stl")
    if isinstance(with_gap_mesh, trimesh.Scene):
        with_gap_mesh = trimesh.util.concatenate(list(with_gap_mesh.geometry.values()))

    vol_diff = no_gap_mesh.volume - with_gap_mesh.volume
    print(f"  'H' fill without gap: {no_gap_mesh.volume:.1f}mm³")
    print(f"  'H' fill with gap:    {with_gap_mesh.volume:.1f}mm³")
    print(f"  Volume removed:        {vol_diff:.1f}mm³")

    assert vol_diff > 0, "Gap should remove material from fill plate around H"
    print(f"  ✓ Outside gap removed {vol_diff:.1f}mm³")


if __name__ == "__main__":
    print("test_chars_with_holes_detected:")
    test_chars_with_holes_detected()
    print("\ntest_gap_ring_cutters_for_all_chars:")
    test_gap_ring_cutters_for_all_chars()
    print("\ntest_outside_gap_increases_cutout:")
    test_outside_gap_increases_cutout()
    print("\ntest_gap_reduces_fill_inside_hole:")
    test_gap_reduces_fill_inside_hole()
    print("\nAll tests passed!")
