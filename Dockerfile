# ── Sooppiy backend image ────────────────────────────────────────────────────
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

# ── frontend build (deployment gap #1: the API serves the SPA from
#    service/frontend/dist via routes_misc — the image must contain it) ───────
FROM node:20-bookworm-slim AS frontend

WORKDIR /fe
COPY service/frontend/package.json service/frontend/package-lock.json ./
RUN npm ci
COPY service/frontend/ ./
RUN npm run build

# ── final image ──────────────────────────────────────────────────────────────
FROM base

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source (keep same relative path so imports work)
COPY service/server/ ./service/server/

# Monitoring analysis — desk_memory_ingest chunks these into the desk corpus.
# Without them the corpus keeps only the AI's own decisions, which is half of
# what it is for: the findings, traps and verdicts learned about this desk
# live in these notes and would otherwise never reach prod.
COPY docs/reports/ ./docs/reports/

# Built SPA — served by the API's routes_misc fallback from service/frontend/dist
COPY --from=frontend /fe/dist ./service/frontend/dist/

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
