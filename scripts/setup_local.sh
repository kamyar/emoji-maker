#!/bin/bash
# Local setup: install deps with extended timeout and convert fonts
set -e

export POETRY_HTTP_TIMEOUT=600

echo "==> Installing Python dependencies..."
poetry install

echo "==> Converting WOFF2 fonts to OTF..."
poetry run python scripts/convert_fonts.py

echo "==> Done! Start the backend with: poetry run uvicorn src.main:app --reload"
