# =============================================================================
# MemoryArena Backend image (Python 3.12) — multi-stage for a slim runtime.
# Stage 0: build recipe defined; the CMD will resolve once app/main.py exists.
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
# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 appuser
COPY --from=builder /install /usr/local
COPY . .
USER appuser
EXPOSE 8000
# Stage 1 entrypoint:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
