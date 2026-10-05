# ── Sooppiy backend image ────────────────────────────────────────────────────
# Build context: repo root
# Runs from /app (project root) so DB_PATH=service/server/data/... resolves.

FROM python:3.12-slim AS base

# libpq5 required by psycopg[binary]
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── dependency layer ─────────────────────────────────────────────────────────
# Versions come from constraints.txt, so a rebuild of this layer (an edited
# requirements file, or a new base image evicting the cache) installs the same
# set. The check after the install fails the build if anything was installed
# that the lock does not pin at exactly that version.
FROM base AS deps

COPY service/requirements.txt service/constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip freeze > /tmp/installed.txt \
    && [ -s /tmp/installed.txt ] \
    && ! grep -vxFf constraints.txt /tmp/installed.txt

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
