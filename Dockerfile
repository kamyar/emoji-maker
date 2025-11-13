# Build stage for webapp
FROM node:18 as webapp-builder
WORKDIR /app
COPY webapp/package*.json ./
RUN npm install
COPY webapp/ ./
RUN npm run build

# Python application stage
FROM python:3.11

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# PIP & Poetry
RUN pip install --upgrade pip
COPY poetry.lock pyproject.toml ./
RUN pip install poetry==1.6.1
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev --no-interaction --no-ansi --no-root

ENV PYTHONUNBUFFERED True

# Create necessary directories
RUN mkdir -p ./static
ADD src/ ./src/

# Copy built webapp files to static directory
COPY --from=webapp-builder /app/build/ ./static/
# Ensure index.html is copied as index.html
RUN if [ -f ./static/index.html ]; then echo "index.html exists"; else echo "index.html missing"; exit 1; fi

WORKDIR /

# Use CMD instead of ENTRYPOINT for better signal handling
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--timeout-keep-alive", "60"]
