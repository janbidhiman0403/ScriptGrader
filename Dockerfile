# syntax=docker/dockerfile:1

# ---- Build stage: install dependencies into a venv, keeps the final ----
# ---- image free of build tools (gcc etc. needed by some wheels).    ----
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt gunicorn==26.0.0

# ---- Runtime stage: copy only the venv and app code, no build tools ----
FROM python:3.12-slim AS runtime

# opencv-python-headless still needs these shared libs at runtime even
# though it doesn't need a compiler.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=app:app app/ ./app/
COPY --chown=app:app static/ ./static/
COPY --chown=app:app gunicorn_conf.py ./

RUN mkdir -p /app/data && chown app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["gunicorn", "app.main:app", "-c", "gunicorn_conf.py"]
