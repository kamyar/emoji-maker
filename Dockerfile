# Stage 1: Build webapp
FROM node:18 as webapp-builder
WORKDIR /app
COPY webapp/package*.json ./
RUN npm install --legacy-peer-deps
COPY webapp/ ./
RUN npm run build

# Stage 2: Runtime app image
FROM europe-west1-docker.pkg.dev/kamy-me/emoji-maker/base:latest

ENV PYTHONUNBUFFERED True

RUN mkdir -p ./static

# Convert WOFF2 fonts to OTF in its own cacheable layer. The later source copy
# merges with this directory without deleting converted OTF files.
COPY src/generator/fonts/ ./src/generator/fonts/
COPY scripts/convert_fonts.py /tmp/convert_fonts.py
RUN python /tmp/convert_fonts.py ./src/generator/fonts/

COPY src/ ./src/
COPY --from=webapp-builder /app/build/ ./static/
RUN if [ -f ./static/index.html ]; then echo "index.html exists"; else echo "index.html missing"; exit 1; fi

WORKDIR /

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--timeout-keep-alive", "60"]
