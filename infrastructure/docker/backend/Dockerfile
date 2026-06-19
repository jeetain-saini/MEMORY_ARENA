# =============================================================================
# MemoryArena Backend image (Python 3.12) — multi-stage for a slim runtime.
# Build context is ./backend (see docker-compose.yml).
# =============================================================================

# ---- Builder ---------------------------------------------------------------
FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install --prefix=/install .

# ---- Runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
# curl is used by the container HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser
COPY --from=builder /install /usr/local
COPY . .
USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
