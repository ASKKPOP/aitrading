# Session Handoff — Sooppiy (as of 2026-07-15)

Written so a fresh Claude session (or a different account) can continue with zero context loss.
Read this first, then [docs/README.md](../README.md) and [CLAUDE.md](../../CLAUDE.md).

---

> **2026-07-16 addendum (overnight parameter-upgrade session):** the AI-model parameter-upgrade plan ([04-ai-model-parameter-upgrade.md](04-ai-model-parameter-upgrade.md), v2 — 6-agent verified) was fully implemented (Phases 0–4, commits `f46ab32`…`0fe4317`), tested (**854 passing**), and **deployed to sooppiy.com**. New on the server: confluence engine (display + `GET /api/market-intel/confluence` agent API + Signals Board column), regime filter (advisory + `GET /api/market-intel/regime` + tile), factor-snapshot telemetry loop, historical macro calendar 2019–2025, repaired backtester metrics, breaker safety upgrade, and the opt-in per-agent exit toolkit (trailing/time stops; `exit_policy` grandfathering — existing positions untouched). **The Phase-4 walk-forward backtest returned INSUFFICIENT_EVIDENCE** ([report](../research/parameters/3-phase4-backtest-report.md)), so per the pre-registered rule the execution gates (`CONFLUENCE_GATE_ENABLED`, `REGIME_FILTER_ENABLED`, `VOL_SIZING_ENABLED`) remain **default-off / unset on the server** — no live trading behavior changed except the deliberate never-loosen-SL/TP safety fix. Re-evaluation is live-forward via the accumulating telemetry. Owner decisions pending in plan §7.

## 1. TL;DR — where things stand

- **Product:** Sooppiy — an **AI auto-trading / signal-collection platform** (NOT copy-trading, NOT real execution). All trades are **paper (simulator)**. Term of art: an **"Intelligent Automate Agent"** (never say "bot").
- **Repo:** `origin` → `https://github.com/ASKKPOP/aitrading.git` (single remote). Branch **`main`**, fully pushed (`5318e39` at handoff time).
- **Live test server:** **https://sooppiy.com** (frontend) + **https://api.sooppiy.com** (API). HTTPS is terminated by AWS; nginx on the box serves plain HTTP. **Deployed and current** with everything below.
- **Tests:** backend suite **726 passing** (`.venv/bin/python -m pytest service/server/tests/ -q`).
- **The 5 signal-collection phases are live and enabled** on the server (risk engine, psych feed, crypto quant, scanner, fusion).

---

## 2. What this session chain delivered (chronological)

Commits on `main`, oldest→newest of this arc:

| Commit | What |
|---|---|
| `0eb6c3c` | **Full AI-trading pipeline guide** — `docs/design/ai-trading-guide.html` (10 steps, 5 SVG diagrams, trader/CEO/QA views). Live at **sooppiy.com/guide.html** |
| `5dc70bf` | **Account menu + settings page + Korean default.** Sidebar shows account block on user login; new `/settings` page (account · language · per-target API config); Korean added as a language and made **default** |
| `040fbd5` | **Renamed all "bot" → "Intelligent Automate Agent"** (SDK, skill docs, dev page, Korean docs, hero kicker; renamed `demo-bot`/`qa-temp-bot` DB agents) |
| `5334765` | **Fixed missing `agent_leaderboard_exclusions` table** — profit-history recording was failing every tick with "no such table" (pre-existing bug found via server-log triage) |
| `a5d83b5` | **User login now unlocks the whole app.** Root cause: two parallel auth systems (human `userToken` vs agent `claw` token) with no link, so agent-gated menus never opened. Added `agents.user_id` + `POST /api/users/agent` (auto-provisions one simulator agent per human, $100k paper cash) + frontend auto-link |
| `7fa4131` | **Gated routes wait for the auto-link** instead of redirecting (first click after login was racing the link and bouncing to the leaderboard) |
| `5318e39` | **Recover from a stale linked-agent token.** A rotated/expired claw token stranded every agent page on 401 with no recovery. `fetchAgentInfo` now re-links on 401/403 and retries once |

### Prior arc (already on `main` before this chain, for context)
- Repositioned the whole product from copy-trading → AI auto-trading; removed all copy-trading UI/code.
- Adopted the **Signal design system** (from `signal_dashboard.html`): page `#f9f9f7`, white cards, accent `#2a78d6`, system-ui fonts, automatic dark mode. Defined in `service/frontend/src/index.css` as `:root[data-theme='signal']`; `ThemeMode='signal'` in `appShared.tsx`.
- Rebuilt the homepage (`service/frontend/src/pages/MarketingPage.tsx`) as a quiet editorial landing page, zero animation.
- Built the 5 signal phases (`11ed8d9`→`9fce006`): `risk_engine.py`, `psych_feed.py`, `quant_crypto.py`, `scanner.py`, `signal_fusion.py` + routes + tests.
- Two planning docs live: `docs/design/implementation-plan.html` (→ **sooppiy.com/plan.html**) and `docs/design/signal-framework.html` (→ **sooppiy.com/framework.html**).

---

## 3. Deployment runbook (READ — non-obvious)

### Server access
```bash
# SSH (this exact key/host — see ~/shell/sierrabiolab/dev.sh)
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202
```
- Box: CentOS Stream 10, Docker, **system nginx on :80** routing by domain (`/etc/nginx/conf.d/`). **SELinux enforcing** — always `restorecon` after copying web files.
- Backend container: **`sooppiy-backend`** on **`127.0.0.1:8101`** → nginx proxies `/api`. Managed by **docker compose** (`~/sooppiy/docker-compose.yml`, `--profile prod`), image pinned by `SOOPPIY_IMAGE` in `~/sooppiy/.env` to a dated tag. The `sooppiy-worker` container uses the **same** image variable.
- Frontend: **static files** served by nginx from **`/usr/share/nginx/sooppiy/`** (NOT from the container). `plan.html`, `framework.html`, `guide.html` also live here.
- Deploy source dir on server: **`~/sooppiy/app`**. The env file is **`~/sooppiy/.env`** — one level UP, next to `docker-compose.yml`, loaded automatically by compose. (`~/sooppiy/app/.env` does not exist; older revisions of this doc claimed it did.)
- Docker volume **`sooppiy_data`** holds the SQLite DB at `/app/service/server/data/sooppiy.db`.

### Full deploy (backend or full-stack change)

**Updated 2026-07-19 after a brief backend outage caused by the old version of this section.**
The old runbook used a raw `docker run` with `--env-file ~/sooppiy/app/.env` — **that file does not
exist**. Prod moved to **docker compose**, and the env file lives at **`~/sooppiy/.env`** (next to
`docker-compose.yml`, read automatically by compose). Doing `docker rm -f sooppiy-backend` and then a
`docker run` pointing at the missing env file leaves production **down**.

Three facts that drive the procedure below:

- **Orchestration is compose:** `cd ~/sooppiy && docker compose --profile prod up -d backend worker`.
- **The image tag is pinned in `~/sooppiy/.env` as `SOOPPIY_IMAGE`** (a dated tag, e.g.
  `sooppiy-backend:20260719-archdoc`). Nothing references `sooppiy-backend:test` — building that tag
  has **no effect**. Build a new dated tag and point `SOOPPIY_IMAGE` at it.
- **Backend and worker share `SOOPPIY_IMAGE`**, so they must be recreated **together** or they end up
  running different code.

```bash
cd /Users/desirey/Programming/src/ai-trade
TAG="$(date +%Y%m%d)-<slug>"          # e.g. 20260719-archdoc
git archive --format=tar.gz -o /tmp/sooppiy-deploy.tar.gz HEAD
scp -i ~/shell/sierrabiolab/sierrabiolab-aws.pem /tmp/sooppiy-deploy.tar.gz ec2-user@52.9.147.202:/tmp/
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 "
  set -e
  TAG='$TAG'
  cd ~/sooppiy
  # ~/sooppiy/.env is OUTSIDE app/ — wiping app/ does not touch it. Back it up anyway.
  cp .env /tmp/sooppiy.env.bak
  rm -rf app && mkdir app
  tar xzf /tmp/sooppiy-deploy.tar.gz -C app

  # 1. build the new dated image
  docker build -t \"sooppiy-backend:\$TAG\" app

  # 2. repoint SOOPPIY_IMAGE, then recreate backend AND worker together
  sed -i \"s|^SOOPPIY_IMAGE=.*|SOOPPIY_IMAGE=sooppiy-backend:\$TAG|\" ~/sooppiy/.env
  grep '^SOOPPIY_IMAGE=' ~/sooppiy/.env      # confirm before proceeding
  docker compose --profile prod up -d backend worker

  # 3. publish the SPA from the freshly built image
  #    rm -rf FIRST: if /tmp/fe-dist already exists, 'docker cp' nests the build at
  #    /tmp/fe-dist/dist/ and leaves stale top-level files -> old bundle ships to nginx.
  rm -rf /tmp/fe-dist && mkdir -p /tmp/fe-dist
  cid=\$(docker create \"sooppiy-backend:\$TAG\")
  docker cp \"\$cid\":/app/service/frontend/dist/. /tmp/fe-dist/    # trailing /. matters
  docker rm \"\$cid\"
  sudo rm -rf /usr/share/nginx/sooppiy/assets
  sudo cp -r /tmp/fe-dist/. /usr/share/nginx/sooppiy/
  sudo restorecon -R /usr/share/nginx/sooppiy                     # SELinux — still mandatory
"
```

#### Verify the deploy actually landed

Run all three. Any mismatch means the deploy is half-applied — fix it before walking away.

**Wait for readiness first.** The backend needs a few seconds after `compose up` before it answers.
Observed 2026-07-19: a functional check fired ~6s after `up` returned an empty body, then passed
5/5 once ready. Gate on the API before judging anything a failure:

```bash
until curl -s --max-time 10 https://sooppiy.com/api/market-intel/regime | grep -q '^{'; do sleep 3; done
```

```bash
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 '
  TAG=$(grep "^SOOPPIY_IMAGE=" ~/sooppiy/.env | cut -d= -f2)

  # 1. live bundle == bundle inside the image (catches the docker cp nesting trap)
  ls /usr/share/nginx/sooppiy/assets | grep -i docspage
  cid=$(docker create "$TAG"); docker cp "$cid":/app/service/frontend/dist/assets /tmp/verify-assets
  docker rm "$cid"; ls /tmp/verify-assets | grep -i docspage; rm -rf /tmp/verify-assets
  # the two hashed filenames must be identical

  # 2. backend and worker on the SAME image tag
  docker compose -f ~/sooppiy/docker-compose.yml --profile prod ps
  docker inspect --format "{{.Name}} {{.Config.Image}}" sooppiy-backend sooppiy-worker
'
# 3. functional endpoint check (from anywhere)
#    /api/market-intel/regime is public and returns JSON. NEVER check status codes alone —
#    see the SPA-fallback warning below. Assert the BODY is JSON.
curl -s https://sooppiy.com/api/market-intel/regime | head -c 80
#    -> must start with {"regime": ... . If it starts with <!DOCTYPE, the backend is NOT serving.

#    deeper: real auth round-trip (proves DB + auth, not just routing)
TOK=$(curl -s -X POST https://sooppiy.com/api/users/login -H 'Content-Type: application/json' \
  -d '{"email":"info@askkpop.com","password":"test"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
echo "len=${#TOK}"   # ~43 chars. If this errors, login returned HTML = backend down.

curl -s https://sooppiy.com/ | grep -o 'assets/index-[^"]*\.js'   # must match step 1's hash
```

> **⚠️ The SPA fallback makes status-code checks WORTHLESS — including on `/api/*` paths.**
> Verified 2026-07-19: **both** `sooppiy.com` and `api.sooppiy.com` return **HTTP 200 with
> `index.html`** for any unmatched path, and `/api/` is not exempt. Concretely:
> `curl -o /dev/null -w '%{http_code}' https://api.sooppiy.com/api/health` prints **200** even
> though **`/api/health` does not exist** — there is no health route in the codebase at all.
> A totally dead backend would still return 200 there.
>
> So: **assert on the response body, never the status code.** A real API response is JSON
> (`{"regime":...}`) or a real JSON error (`{"detail":"Authorization required"}`, which
> `/api/execution/health` returns with a genuine 401). If you get `<!DOCTYPE html`, nginx served
> the SPA and the backend never answered. Note `/api/leaderboard` and `/api/agents` also fall
> through to HTML — do not use them as liveness probes.

### Frontend-only change (faster)
```bash
cd service/frontend && npm run build && cd ../..
tar czf /tmp/fe-dist.tar.gz -C service/frontend/dist .
scp -i ~/shell/sierrabiolab/sierrabiolab-aws.pem /tmp/fe-dist.tar.gz ec2-user@52.9.147.202:/tmp/
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 '
  rm -rf /tmp/fe-new && mkdir /tmp/fe-new && tar xzf /tmp/fe-dist.tar.gz -C /tmp/fe-new
  sudo rm -rf /usr/share/nginx/sooppiy/assets
  sudo cp -r /tmp/fe-new/. /usr/share/nginx/sooppiy/
  sudo restorecon -R /usr/share/nginx/sooppiy
'
```

### Management console (administr.sooppiy.com)
- **Domain:** `administr.sooppiy.com` (Route 53 + AWS ALB terminate TLS; host nginx speaks plain HTTP).
- **Container:** `sooppiy-admin` — `nginx:alpine` on **127.0.0.1:8201**, serving the SPA build
  from **`~/sooppiy/admin-site/`** (read-only bind mounts: site dir + `~/sooppiy/admin-nginx.conf`).
- **Routing:** host `/etc/nginx/conf.d/domains.conf` block `administr.sooppiy.com` →
  `/api/` proxies to the backend (127.0.0.1:8101), everything else to 127.0.0.1:8201.
- **App behavior:** the same SPA build detects `hostname.startsWith('administr.')` and renders
  ONLY the manager console (token gate → 개요/사용자·에이전트/거래·자금/AI 자동화).
  `/admin` does NOT exist on the main domain.
- **Auth:** `admin_users` email/password with 12h sessions in `admin_tokens` (`service/server/admin_auth.py`).
  The old `ADMIN_TOKEN` env var is **dead** — setting it does nothing.
- **On frontend deploys, also refresh the admin site:**
  ```bash
  rm -rf ~/sooppiy/admin-site/* && tar xzf /tmp/fe-dist.tar.gz -C ~/sooppiy/admin-site
  # (no container restart needed — static bind mount)
  ```
  **Never swap the directory itself** (`mv admin-site.new admin-site`): the bind mount is
  pinned to the old inode, so the container keeps serving the stale bundle until
  `docker restart sooppiy-admin`. Extract *in place* as above, or restart after a swap.

### Deploy gotchas (learned the hard way)
- **`docker restart` does NOT reload env changes.** After editing `~/sooppiy/.env`, run
  `docker compose --profile prod up -d backend worker` to recreate the containers.
- **The env file is `~/sooppiy/.env`, not `~/sooppiy/app/.env`.** It sits outside `app/`, so wiping
  `app/` is safe — but back it up anyway, it holds the signal-phase flags, `SOOPPIY_IMAGE`, and real keys.
- **Never leave backend and worker on different image tags** — they share `SOOPPIY_IMAGE`; recreate both.
- **`docker cp` into an existing directory nests the copy** (`/tmp/fe-dist/dist/`) and leaves stale
  top-level files, which then get published — a NEW api serving an OLD bundle, with no error anywhere.
  Always `rm -rf` the destination first and use a trailing `/.` on the source path.
- **`restorecon` is mandatory** after copying to `/usr/share/nginx/sooppiy` (SELinux) or files 403.
- **rsync is not on the server** — use tar-over-ssh / scp.
- **Browser caching bites verification:** after a frontend deploy the browser may keep an old `index.html` → loads a stale JS bundle → "old broken behavior" persists. **Hard-refresh (Cmd+Shift+R).** Confirm the live bundle with `curl -s https://sooppiy.com/ | grep -o 'assets/index-[^"]*\.js'`.

---

## 4. Architecture notes that matter

### Dual authentication (the source of most "menu doesn't work" bugs)
- **Human users** authenticate with a `userToken` (`sooppiy_user_token` in localStorage; `/api/users/*`).
- **Agents** authenticate with a `claw` token (`claw_token` in localStorage). Agent-scoped routes live
  under **`/api/agents/me/*`** (memory, rewards, experiments) plus the shared `/api/automation/*`,
  `/api/execution/*`, `/api/runs`, `/api/risk/*` families — **not** `/api/claw/*`. (Corrected
  2026-07-20: `/api/claw/*` was never a registered prefix. Because unmatched paths return 200 + HTML,
  a status-code-only test of `/api/claw/agent` *looks* like it passes — see the SPA-fallback warning.)
- **Most menu pages are gated on the *agent* token**, so a human login alone opens almost nothing.
- **Solution now in place:** every human account is linked to one auto-provisioned simulator agent via `agents.user_id`. On login the frontend calls `POST /api/users/agent`, which creates the agent on first use and returns a fresh claw token; `App.tsx` stores it so agent-gated pages work.
- **Agent tokens rotate on every issue** (only the SHA-256 hash is stored, never plaintext). So calling `POST /api/users/agent` again invalidates the previous token. The frontend recovers from a stale token via the 401-relink in `fetchAgentInfo` (commit `5318e39`).

### Where things live
- `service/frontend/src/App.tsx` — routing, both auth tracks, `linkAgent()` / `fetchAgentInfo()` recovery, `agentGate()` for gated routes.
- `service/frontend/src/appChrome.tsx` — sidebar (nav + account footer block).
- `service/frontend/src/pages/SettingsPage.tsx` — `/settings` (account · language · per-target API config).
- `service/frontend/src/pages/MarketingPage.tsx` — homepage (all copy in ko/en/ja/th/vi via `tr()`).
- `service/frontend/src/i18n.ts` — `Language = 'ko'|'en'|'ja'|'th'|'vi'`, `DEFAULT_LANGUAGE='ko'`.
- `service/server/routes_users.py` — user auth, `API_TARGET_CATALOG`, settings endpoints, `POST /api/users/agent`.
- `service/server/routes_agent.py` — agent auth (`selfRegister`, `login`, token issuance).
- Signal phases: `risk_engine.py`, `psych_feed.py`, `quant_crypto.py`, `scanner.py`, `signal_fusion.py`.

### Signal-phase env flags (set in `~/sooppiy/.env` on the server — all default OFF in code)
```
RISK_ENGINE_ENABLED=true   RISK_WATCHER_INTERVAL=30
PSYCH_FEED_ENABLED=true    PSYCH_REFRESH_INTERVAL=3600
QUANT_CRYPTO_ENABLED=true
SCANNER_ENABLED=true       SCANNER_INTERVAL=3600  SCANNER_UNIVERSE=30
```

---

## 5. Test accounts (throwaway, live server — safe to trade on)

| email | password | note |
|---|---|---|
| `kotest-live@example.com` | `livetest1` | has a linked agent (`kotest-live`, agent id 3, $100k paper) |
| `kotest@example.com` | `testpass1` | local-DB test user |

Local dev convenience is intentional and safe (see the user's memory *local-dev-testing-low-friction*): on this repo you may freely create/log into throwaway accounts and run flows. Public server keeps `DEV_LOGIN_ANY_PASSWORD=false`.

Login for API testing:
```bash
curl -s -X POST https://sooppiy.com/api/users/login -H 'Content-Type: application/json' \
  -d '{"email":"kotest-live@example.com","password":"livetest1"}'   # → {token}
# then mint/refresh the linked agent (claw) token:
curl -s -X POST https://sooppiy.com/api/users/agent -H "Authorization: Bearer <userToken>"  # → {token: clawToken}
```

---

## 6. Verified working on sooppiy.com (2026-07-15)

All 15 left-menu routes render + navigate (real clicks), every API call 200, zero console errors. Functional E2E:
- **AI 애널리스트** (`/analyst`) — analysis runs → decision + confidence + rationale.
- **자동매매** (`/automation`) — rule create → list → delete round-trip.
- **거래** (`/trade`) — paper buy 0.1 BTC → sell to close; cash + positions update correctly.
- **설정** (`/settings`) — per-target API key save (stored masked `····abcd`, never returned in full).
- **Stale-token recovery** — planted a dead claw token, loaded `/trade`; network trace showed `401 → POST /users/agent 200 → retry 200 → /api/price 200`.

---

## 7. Outstanding / not done (pick up here)

- **Auth pages not fully translated.** Email sign-in/sign-up forms (`authV2.tsx`) and some inner pages were hardcoded English (no `tr()`); they fall back gracefully but aren't Korean yet. Homepage/nav/sidebar/markets/settings **are** translated.
- **Apple Sign In** — needs an Apple Developer account (not wired).
- **Real email delivery** — `RESEND_API_KEY` unset; verification codes only log to stderr (`API_STDERR_LOG=true` on server lets you read them via `docker logs sooppiy-backend`).
- **Real market data keys** — Alpha Vantage/FRED/FinnHub run on `demo`/dev-seed; users can add their own on `/settings`.
- **Whale / liquidation data** — paid-only; deferred to a future "Phase 6". `scanner.py` has a wired stub `fetch_whale_signals()`. The psych feed uses a labeled volatility+volume **proxy** ("추정") for shock.
- **Real-broker execution** — intentionally NOT wired; `account_type='real'` rules run analysis + record but never place orders. A real subsystem would be greenfield.
- **`/exchange`** (points→cash) not functionally tested (linked test agent has 0 points → would hit the insufficient-points path, which is correct).
- **Frontend not auto-built in CI/deploy image beyond the manual flow above** — deployment is manual (tar-over-ssh). No CI/CD to the server.

---

## 8. Working rules the user holds you to (from CLAUDE.md / global)

1. Never flatter; never just agree. State your position firmly with evidence.
2. Never gloss over errors — surface them plainly, including your own.
3. **Verify thoroughly: minimum 2 independent passes even after the first green, loop up to ~10 if uncertain.** A single passing check is never enough.
4. **Respond in English first, then a Korean mirror**, every message.
5. Default model for engineering work: **Opus 4.8** (`/model claude-opus-4-8`).
6. All documents go under **`docs/`** (never `design/` or repo root).
