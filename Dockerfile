# Stage 1: Build webapp
FROM node:18 as webapp-builder
WORKDIR /app
COPY webapp/package*.json ./
RUN npm install --legacy-peer-deps
COPY webapp/ ./
RUN npm run build

# Stage 2: Install Python deps + convert fonts
FROM python:3.11 as python-builder

RUN pip install --upgrade pip
COPY poetry.lock pyproject.toml ./
RUN pip install poetry==1.6.1
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev --no-interaction --no-ansi --no-root

# Convert WOFF2 fonts to OTF (build-only dependency)
RUN pip install fonttools brotli
COPY src/generator/fonts/ /tmp/fonts/
COPY scripts/convert_fonts.py /tmp/convert_fonts.py
RUN python /tmp/convert_fonts.py /tmp/fonts/

# Stage 3: Slim runtime image
FROM python:3.11-slim

# Runtime system dependencies for OpenCV and CadQuery/OCCT
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libglu1-mesa \
    libx11-6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=python-builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=python-builder /usr/local/bin/ /usr/local/bin/

ENV PYTHONUNBUFFERED True

# Create necessary directories
RUN mkdir -p ./static
ADD src/ ./src/

# Copy converted fonts (includes both original OTF and converted WOFF2→OTF)
COPY --from=python-builder /tmp/fonts/ ./src/generator/fonts/

# Copy built webapp files to static directory
COPY --from=webapp-builder /app/build/ ./static/
RUN if [ -f ./static/index.html ]; then echo "index.html exists"; else echo "index.html missing"; exit 1; fi

WORKDIR /

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--timeout-keep-alive", "60"]
