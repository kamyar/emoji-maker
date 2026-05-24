"""Test that the fill plate is thinner than the text when fillBorder is enabled."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trimesh
from src.generator.generate_3d_text import Generate3DInput, generate_3d_both


def measure_z_depth(stl_buf):
    stl_buf.seek(0)
    mesh = trimesh.load(stl_buf, file_type="stl")
    bounds = mesh.bounds
    return round(bounds[1][2] - bounds[0][2], 4)


def test_fill_plate_thinner_than_text():
    input_data = Generate3DInput(
        text="AB",
        font="Omnes Medium",
        fontSize=24,
        letterSpacing=0.5,
        lineSpacing=0,
        extrudeHeight=4.0,
        addBorder=True,
        fillBorder=True,
        fillColor="#ffffff",
        borderPaddingTop=2,
        borderPaddingRight=2,
        borderPaddingBottom=2,
        borderPaddingLeft=2,
        scale=1.0,
        color="#667eea",
        exportFormat="3mf",
    )

    result = generate_3d_both(input_data)

    text_depth = measure_z_depth(result.text_stl)
    assert result.border_stl is not None, "border_stl should exist when fillBorder=True"
    fill_depth = measure_z_depth(result.border_stl)

    print(f"Text depth:  {text_depth} mm")
    print(f"Fill depth:  {fill_depth} mm")
    print(f"Difference:  {round(text_depth - fill_depth, 4)} mm")

    assert text_depth == 4.0, f"Text should be 4mm, got {text_depth}"
    assert fill_depth < 4.0, f"Fill plate should be < 4mm, got {fill_depth}"
    assert fill_depth == 3.6, f"Fill plate should be 3.6mm (0.2mm inset each side), got {fill_depth}"

    print("\nPASS: fill plate is thinner than text")


def test_no_fill_same_depth():
    input_data = Generate3DInput(
        text="AB",
        font="Omnes Medium",
        fontSize=24,
        letterSpacing=0.5,
        extrudeHeight=4.0,
        addBorder=True,
        fillBorder=False,
        scale=1.0,
        color="#667eea",
        exportFormat="stl",
    )

    result = generate_3d_both(input_data)

    text_depth = measure_z_depth(result.text_stl)
    assert result.border_stl is not None, "border_stl should exist when addBorder=True"
    border_depth = measure_z_depth(result.border_stl)

    print(f"\nText depth:   {text_depth} mm")
    print(f"Border depth: {border_depth} mm")

    assert text_depth == 4.0, f"Text should be 4mm, got {text_depth}"
    assert border_depth == 4.0, f"Border frame should be 4mm, got {border_depth}"

    print("PASS: border frame matches text depth")


if __name__ == "__main__":
    test_fill_plate_thinner_than_text()
    test_no_fill_same_depth()
    print("\nAll tests passed!")
