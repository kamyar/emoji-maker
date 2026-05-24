#!/usr/bin/env python3
"""Convert WOFF2 font files to OTF format.

Used as a Docker build step and optionally by developers locally.
Requires: pip install fonttools brotli
"""
import glob
import os
import sys

from fontTools.ttLib import TTFont

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "generator", "fonts")


def convert_woff2_fonts(fonts_dir: str = FONTS_DIR) -> None:
    fonts_dir = os.path.abspath(fonts_dir)
    woff2_files = glob.glob(os.path.join(fonts_dir, "*.woff2"))

    if not woff2_files:
        print("No WOFF2 files found.")
        return

    for woff2_path in woff2_files:
        otf_path = woff2_path.rsplit(".", 1)[0] + ".otf"
        if os.path.exists(otf_path):
            print(f"  skip {os.path.basename(woff2_path)} (OTF already exists)")
            continue

        tt = TTFont(woff2_path)
        tt.flavor = None
        tt.save(otf_path)
        print(f"  {os.path.basename(woff2_path)} -> {os.path.basename(otf_path)}")


if __name__ == "__main__":
    fonts_dir = sys.argv[1] if len(sys.argv) > 1 else FONTS_DIR
    convert_woff2_fonts(fonts_dir)
