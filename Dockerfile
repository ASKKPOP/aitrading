# ── AITRAD backend image ────────────────────────────────────────────────────
# Build context: repo root
# Runs from /app (project root) so DB_PATH=service/server/data/... resolves.

FROM python:3.12-slim AS base

# libpq5 required by psycopg[binary]
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── dependency layer (cached unless requirements.txt changes) ────────────────
FROM base AS deps

COPY service/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── final image ──────────────────────────────────────────────────────────────
FROM base

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source (keep same relative path so imports work)
COPY service/server/ ./service/server/

# SQLite data dir — overridden by DATABASE_URL in production
RUN mkdir -p service/server/data

# Non-root user
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Default: run the API.
# Override CMD to "python service/server/worker.py" for the worker process.
CMD ["python", "-m", "uvicorn", \
     "--app-dir", "service/server", \
     "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001"]
