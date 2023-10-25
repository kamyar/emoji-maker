FROM python:3.11

# PIP & Poetry
RUN pip install --upgrade pip
COPY poetry.lock pyproject.toml ./
RUN pip install poetry==1.6.1
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev --no-interaction --no-ansi --no-root

ENV PYTHONUNBUFFERED True

ADD src/ ./src/
ADD static/ ./static/
# VOLUME [ "/tmp" ]

ENTRYPOINT uvicorn src.main:app --host 0.0.0.0 --port 8000
