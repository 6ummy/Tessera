# syntax=docker/dockerfile:1.7
#
# Tessera Worker - Cloud Run image.
#
# Build context: REPO ROOT (not apps/worker/) so this Dockerfile can see
# packages/shared/. deploy_cloud_run.ps1 sets the context accordingly.
#
# Two-stage build:
#   1. builder - installs tessera-shared + tessera-worker + deps into /opt/venv
#   2. runtime - copies the venv + worker source, runs uvicorn as non-root
#
# Slim Python base. Runs as non-root for hardening.

# ---------------- builder ----------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build deps for any wheels that compile (pyarrow + cffi).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install tessera-shared FIRST so tessera-worker's `"tessera-shared"`
# dependency resolves by name from the local install cache instead of PyPI.
WORKDIR /build/shared
COPY packages/shared/pyproject.toml ./
COPY packages/shared/tessera_shared ./tessera_shared
RUN pip install --upgrade pip && pip install .

# Now install the worker. pip finds tessera-shared in the venv already.
WORKDIR /build/worker
COPY apps/worker/pyproject.toml ./
COPY apps/worker/tessera_worker ./tessera_worker
RUN pip install .

# ---------------- runtime ----------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user.
RUN groupadd --system tessera && useradd --system --gid tessera --home /home/tessera tessera \
    && mkdir -p /home/tessera && chown -R tessera:tessera /home/tessera

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=tessera:tessera apps/worker/tessera_worker /app/tessera_worker

USER tessera

# Cloud Run injects $PORT. Use shell form so it expands.
CMD exec uvicorn tessera_worker.main:app --host 0.0.0.0 --port "$PORT" --workers 1
