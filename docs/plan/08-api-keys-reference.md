# API keys reference — Sooppiy production

Status as of 2026-07-17. Every key the platform reads, what it powers, whether it's needed,
and where to get it. Keys live only in `~/sooppiy/app/.env` on the server (never in code).
**After editing `.env` you must recreate the container** — `--env-file` is read only at
`docker run`, not on restart:

```
cd ~/sooppiy/app
docker rm -f sooppiy-backend
docker run -d --name sooppiy-backend --restart unless-stopped --env-file ~/sooppiy/app/.env \
  -e SOOPPIY_API_BACKGROUND_TASKS=true -p 127.0.0.1:8101:8001 \
  -v sooppiy_data:/app/service/server/data sooppiy-backend:test
```

---

## ✅ Set and working

| Key | Powers | Where it came from |
|---|---|---|
| `ANTHROPIC_API_KEY` | All AI: analyst briefs, trader decision, fusion, verification | console.anthropic.com |
| `EXECUTION_ENCRYPTION_KEY` | AES-GCM encryption of any stored broker credentials | Generated 2026-07-17 with the app's own `execution.crypto.generate_key_b64` |
| `SENDGRID_API_KEY` | Email alerts (fills, SL/TP, breaker, whale, watches) | sendgrid.com |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | SMS alerts | twilio.com |
| `SOSOVALUE_API_KEY` | Real BTC/ETH ETF flows (SoSoValue) | sosovalue.com |
| `COINMARKETCAL_API_KEY` | Crypto event calendar | coinmarketcal.com/en/api |
| `ETHERSCAN_API_KEY` | ETH whale transfers (exchange in/out) | etherscan.io/apis (free) |
| `ADMIN_TOKEN` | Admin/manager site auth | Set at deploy |
| `GOOGLE_CLIENT_SECRET` | Google OAuth sign-in | Google Cloud console |

## ⚠️ Set but limited — the one that needs a decision

| Key | Issue | Options |
|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | **Free tier: 25 requests/day.** News sentiment (4 categories) needs ~96/day at hourly. Set to a **6-hour** cadence (`MARKET_NEWS_REFRESH_INTERVAL=21600`, ~16/day) to fit — so news sentiment works, but updates every 6h instead of hourly. | **Upgrade to premium** (~$50/mo, alphavantage.co/premium) to restore hourly and lift the daily cap. Or leave it — 6h is fine for a slow sentiment signal. Free key from alphavantage.co/support/#api-key |

## ➖ Empty on purpose — not needed today

| Key | Why empty is fine | If you ever want it |
|---|---|---|
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `DASHSCOPE_API_KEY`, `GLM_API_KEY`, `OPENROUTER_API_KEY` | We run on Anthropic (Sonnet + Opus). These are alternate LLM providers the tiering system *can* use but doesn't need. | Add the key + set `LLM_PROVIDER`; get from each provider's console (platform.openai.com, aistudio.google.com, console.x.ai, etc.) |
| `ALPACA_KEY`/`ALPACA_SECRET`, `BINANCE_KEY`/`BINANCE_SECRET` | **No real order execution exists** — Sooppiy is a paper/simulator platform by design. | Only if a real-execution subsystem is ever built. alpaca.markets, binance.com |
| `RESEND_API_KEY` | We send email via SendGrid, not Resend. | resend.com, if switching email providers |
| `LOCAL_LLM_API_KEY` | For a self-hosted LLM; we use the hosted Anthropic API. | Only for a local model server |
| `DEV_LOGIN_ANY_PASSWORD` | Dev convenience flag; harmless in this build. | — |

---

## How to get the two you might act on

**Alpha Vantage premium** (to make news sentiment hourly): alphavantage.co/premium — the
$49.99/mo tier lifts the 25/day cap and the per-second burst limit. After buying, paste the
new key into `ALPHA_VANTAGE_API_KEY`, set `MARKET_NEWS_REFRESH_INTERVAL=3600` (hourly),
recreate the container.

**Per-source sentiment (X, Reddit, Telegram, YouTube)** — the mockup shows five sentiment
sources; we have StockTwits (free) + news headlines (Alpha Vantage). The others each need
their own key/collector: X API (paid, ~$100/mo basic), Reddit API (free tier exists),
Telegram (bot API, free, needs a channel-scraper), YouTube (Data API, free quota). This is
a build project, not just a key — scope it before committing.
