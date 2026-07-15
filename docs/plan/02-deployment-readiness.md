# Deployment readiness

Status as of the AI-auto-trading reposition work (branch `feat/auto-trading-reposition`).
Local Docker dev is fully working; this is what stands between that and a real deploy.

## Ready

- **Backend image is prod-capable** — `Dockerfile` builds a slim, non-root Python 3.12
  image, runs uvicorn on `:8001`. Override `CMD` to
  `python -m uvicorn ...` (API) or `python service/server/worker.py` (worker).
- **MySQL supported** — set `DATABASE_URL` (connects via PyMySQL; there is no Postgres driver in requirements.txt — `using_mysql()` in database.py treats any `DATABASE_URL` as MySQL). SQLite is only the local fallback.
- **Dev conveniences are safe by default** — `DEV_LOGIN_ANY_PASSWORD`, `DEV_MARKET_INTEL_SEED`
  default to `false` and are additionally disabled whenever `ENVIRONMENT=production`.
  Setting `ENVIRONMENT=production` alone locks them all off.
- **Tests** — backend suite green (614 passing; the one `test_env_example` failure only
  occurs when running tests inside the container, which doesn't copy the repo-root
  `.env.example` — it passes on a normal checkout / CI).

## Gaps to close before deploy

1. **Frontend build is not in the image.** The backend serves the SPA from
   `service/frontend/dist/` (`routes_misc.py`), but the Dockerfile only copies
   `service/server/`. Either:
   - add a frontend build stage to the Dockerfile (`npm ci && npm run build`) and
     `COPY service/frontend/dist/ ./service/frontend/dist/`, **or**
   - host the built frontend separately (S3/CloudFront/Vercel) and point it at the API.
2. **Set production env** — `ENVIRONMENT=production`, a real `DATABASE_URL` (MySQL — the only wired prod driver),
   and a strong secret set (JWT/session, whatever `config.py` expects).
3. **Real API keys** (all optional but each unlocks a feature; without them the feature
   degrades gracefully):
   - **LLM provider** (`OPENAI_API_KEY` / `GEMINI_API_KEY` / … + optional `LLM_PROVIDER`)
     → real AI Analyst briefs instead of the deterministic fallback.
   - **Alpha Vantage / FRED / Finnhub** → real Financial Events data instead of the dev seed.
   - **Resend** (`RESEND_API_KEY`) → transactional email.
   - **Google OAuth** → human sign-in via Google.
4. **Run the worker separately.** In dev, `SOOPPIY_API_BACKGROUND_TASKS=true` runs the
   price/intel/automation loops inside the API. In prod, run `worker.py` as its own
   process/container and leave the API stateless.
5. **Scale the API** — run uvicorn with multiple workers (or gunicorn + uvicorn workers)
   behind a reverse proxy with TLS; `docker-compose.yml` is dev-only.
6. **Redis** (optional) — set the cache/redis URL for shared caching across instances.

## Suggested first deploy

Single VM or a small container platform: one API container, one worker container, one
managed MySQL, `ENVIRONMENT=production`, frontend built into the API image (gap #1),
TLS via a reverse proxy. Add the market-data + LLM keys once the core is up.
