# Session handoff — 2026-07-17

For the next Claude session (possibly a different account). Read this first, then
[docs/README.md](../README.md) and [CLAUDE.md](../../CLAUDE.md). Everything below is verified
as of this date, not remembered.

---

## 0. Who the user is, how to talk to them

- The user is **Henry** (Henry Desirey; git author; org owner `info@askkpop.com`). Address him
  as **"Henry"** — never 사장님/boss/honorifics, **including in the Korean half of replies**
  (Korean business register pulls toward 사장님 — check the Korean text before sending).
- **Reply in English first, then a Korean mirror.** Every response.
- House rules (non-negotiable): never flatter; state your position firmly with evidence even
  against his opinion; surface errors plainly including your own; **verify ≥2× (up to 10)
  before reporting** — one green check is never enough.

## 1. What this project is (read twice)

Sooppiy is a **signal & paper-trading platform**, NOT a broker execution engine. Agents
publish signals; positions are tracked by polling prices. **There is no real order routing —
that is by design, never a bug.** Feature work assuming real execution will be wrong.

- Backend: FastAPI, Python 3.12, `service/server/` (13 `routes_*.py` + workers/services).
- Frontend: React + Vite + TS, `service/frontend/src/` (big files: `AppPages.tsx`,
  `SignalsBoardPage.tsx`, `AutomationPage.tsx`).
- Prod: **https://sooppiy.com** (live). Origin: `github.com/ASKKPOP/aitrading.git` (single remote).

## 2. How to work here

**Local tests** (from repo root; use `uv`-created `.venv`, no system python3.12):
```
.venv/bin/python -m pytest service/server/tests -q
```
Current: **1119 passing.** Always run twice with an explicit exit check — a shell pipe once
swallowed pytest's exit code and 2 failures shipped:
```
.venv/bin/python -m pytest service/server/tests -q 2>&1 | tail -1; echo "EXIT=${pipestatus[1]}"
```

**Discipline that caught real bugs this session:**
- **Mutation-test every fix** — flip the fixed line back and confirm a test fails. Two of my
  own tests were fake (passed with the bug present); only mutation testing exposed them.
- **Write bug-fix tests against the OLD code first** and watch them fail there — that proves
  the exploit, not just the fix.
- **Read the whole function before concluding something is missing.** I raised 3 false alarms
  today (user-token 401s, verdicts-not-persisted, enforce-blocked-on-fusion) — all from
  reading part of a file. The best real findings came from diffing *produced vs forwarded*.

**Deploy runbook** (SSH key: `~/shell/sierrabiolab/sierrabiolab-aws.pem`, host
`ec2-user@52.9.147.202`):
```
# BACKEND: archive HEAD -> scp -> extract into ~/sooppiy/app -> rebuild image -> recreate container
git archive --format=tar HEAD | gzip > /tmp/src.tar.gz
scp -i <key> /tmp/src.tar.gz ec2-user@52.9.147.202:~/sooppiy/src.tar.gz
ssh -i <key> ec2-user@52.9.147.202 '
  cd ~/sooppiy/app && tar xzf ~/sooppiy/src.tar.gz service/server
  docker build -q -t sooppiy-backend:test . 
  docker rm -f sooppiy-backend
  docker run -d --name sooppiy-backend --restart unless-stopped --env-file ~/sooppiy/app/.env \
    -e SOOPPIY_API_BACKGROUND_TASKS=true -p 127.0.0.1:8101:8001 \
    -v sooppiy_data:/app/service/server/data sooppiy-backend:test'
```
**Gotchas that will bite you:**
- Container name is `sooppiy-backend`; app dir `~/sooppiy/app`; image built from repo-root
  Dockerfile (source is BAKED IN — a deploy means a **rebuild**, not a bind-mount).
- `--env-file` is read **only at `docker run`**, never on restart. Change `.env` → recreate.
- **Back up `.env` first**: `cp .env .env.bak-$(date +%Y%m%d-%H%M%S)`.
- **FRONTEND is served by nginx from `/usr/share/nginx/sooppiy`**, NOT the container. A backend
  deploy does not ship UI. Frontend deploy: `npm run build` → tar `dist/` → extract **in place**
  (never `mv`-swap — bind-mount inode trap) → `restorecon -R` (SELinux) → `systemctl reload nginx`.
  Verify by fetching the exact `index-*.js` chunk `https://sooppiy.com/` references.
- zsh **globs `?`** in URLs — quote every curl URL with a query string.

## 3. Current production state (verified 2026-07-17)

**Flags in `~/sooppiy/app/.env`:**
- `AI_FUSION_ENABLED=true` — AI fusion is LIVE (Opus decision tier). Board verdicts are AI-weighted.
- `DATA_VERIFY_MODE` unset → **advisory** (D5 input verification runs, reports, never blocks).
- `VERIFY_ENABLED` unset → **advisory** (D3 decision verifier runs, never blocks).
- `MARKET_NEWS_REFRESH_INTERVAL=21600` (6h — fits Alpha Vantage free tier).
- `DOCS_OWNER_EMAILS` unset → default `info@askkpop.com` (owner-only docs).

**Models:** brief = `claude-sonnet-5`, decision = `claude-opus-4-8` (set via `LLM_MODEL_BRIEF/
DECISION` in `.env`; source values are fallbacks). Measured: Haiku produced high-severity
FALSE data-verify faults 4/4 → don't use it for verify/decision.

**Cost:** with fusion on, each board fusion is ~2 Opus calls (fuse + D5 verify) per symbol per
900s cache. Rough worst case ~$34/day with a dashboard open continuously. Junk-symbol
amplification is closed (structural hold, no model call; cache bounded to 64).

**Keys:** see the owner-only doc `sooppiy.com → Docs → API Keys (owner)` (or
`docs/plan/08-api-keys-reference.md`). All critical keys set. Alpha Vantage is free-tier
(25/day) — news sentiment partially alive (equities category); premium (~$50/mo) restores hourly.

## 4. What this session did (headlines)

Plan 06 (full-concept build) is **complete**; then two audits (5-agent + 4-QA, and a
guide-vs-code deep scan) found and fixed real issues. Notable fixes, all live:
- **P-1 hole closed:** the LLM used to author the execution `entry` price, which set the
  denominator of every notional risk cap — a unit slip (60 vs 60,000) opened 1000× size through
  a gate that said ALLOWED. Now the model advises (`suggested_entry`); fills at live price.
- **A League of Legends match was moving BTC's signal:** Polymarket anticipation was top-volume
  with no topic filter (esports/elections/football). Now crypto/macro topic-filtered
  (`ANTICIPATION_TOPICS`), one signed Δodds per market (it could not read bearish before).
- **AI-native fusion (D4/D5) end-to-end:** AI weighs the factor snapshot itself; D5 verifies the
  INPUTS (ages/contradiction/anomaly). Board shows a source badge (AI / rule / rule-fallback /
  ⚠ inputs suspect). Psych cap 0.3 now enforced on the AI path too.
- **Config profiles** (Plan 06 C3 last feature); **owner-only API-keys doc**; **guide accuracy**
  (STEP 5 fusion, VIX→F&G mapping note, backtest pooled-DD collision bug); **kimchi tile i18n**
  for th/vi.
- Durable records: `docs/plan/07-overnight-audit-2026-07-17.md`, `08-api-keys-reference.md`.

## 5. Next work

### Actionable now (no blocker — pick these up)
1. **3σ shock/volatility chart** (mockup gap): `psych_feed.shock_history()` exists but no
   endpoint/chart renders it. Add a route + a board chart. Data is real (OKX liquidations).
2. **Events tile shows only the next event** — the calendar has `recent` + a full list; surface
   the hot-issues list the mockup promised (low).
3. **Consult chat asks for `"rsi"`** — a key `quant_crypto` never emits, so the advisor sees
   null. Confirmed by the overnight audit; wire the real field (medium).
4. **`sigma_daily_pct` never reaches the risk gate** — vol-sizing is dead code; turning it on
   reportedly rejects 100% of buys. Investigate before enabling (medium).
5. **Whale/ETF/calibration** blocks: only the ETF print is date-aged; add per-block `as_of` if
   you extend staleness checks (low, my own noted debt).

### Blocked on Henry (a decision or a key — do NOT do these unprompted)
- **Flip `VERIFY_ENABLED=enforce`** — gated on ≥200 reviewed advisory verdicts. Verdicts ARE
  persisted (`automation_runs.confluence_json`), but prod has ~2 runs / 1 enabled rule, so they
  don't accumulate. Needs real usage, not a config change. Do not flip early.
- **Alpha Vantage premium** (~$50/mo) to make news sentiment hourly + all 4 categories.
- **Per-source sentiment** (X/Reddit/Telegram/YouTube) — mockup promised 5 sources; only
  StockTwits + news headlines exist. Paid APIs + custom collectors = a build project.
- **Per-country premiums** (JP/TH/VN) — deliberately not built; kimchi is the only clean one.
- **SMS end-to-end test** — needs Henry's phone number (Twilio keys are set).

### Externally blocked
- **Card 09 token unlocks** — DefiLlama went paid; documented key options, no free source.

## 6. Safety invariants — never regress these (P-1)

The architecture's core rule: **the AI decides signals; deterministic CODE enforces limits.**
An LLM must never talk its way past a stop-loss. Concretely, all enforced in code:
- Fills at the live price, never the model's number (§4).
- `risk_engine.evaluate_order` gate can only shrink/reject; portfolio caps (60% equity, 8
  positions) default-on; breaker + daily-loss caps.
- Psychology never trades alone (structural hold) and psych weight ≤ 0.3 on both fusion paths.
- `config_profiles` import re-validates through `RiskLimitsIn` — a pasted profile can't carry a
  limit the editor would reject.
Any change touching these needs tests that fail if the invariant is removed.
