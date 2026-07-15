---
name: trading-signal-collector
description: Collect Sooppiy's live trading signals — crowd psychology (Fear & Greed, sentiment spikes, shock proxy, prediction-market odds), which-coin scanner candidates, and per-symbol fused signal scores. Use when an agent needs signal context before publishing a trade, sizing a position, or explaining a market view.
---

# Trading Signal Collector

Read Sooppiy's signal-collection pipeline (implementation plan Phases 2–5). All
endpoints are public GETs — no auth token needed. All data is read-only and
refreshed by backend jobs; requests never trigger live collection.

Honest limits, by design:

- Psychology signals lag and carry noise. The fused score structurally caps the
  psych weight at 0.3 — psychology never trades alone.
- The "shock" figures are an **estimated proxy** (volatility σ + volume ratio),
  not real liquidation data. Every shock payload carries `estimated: true`.
- Everything here is paper-trading context, not investment advice.

## Endpoints

### Psychology feed

`GET /api/market-intel/psych`

Key fields:

- `available` — false until the first snapshot lands
- `fear_greed` — `{value, classification, delta_3d, history[30d]}` (alternative.me)
- `spikes` — per news category: `{category, z, latest_score, spike, direction}`;
  a negative `z ≤ −2` spike is also journaled as a `psych_sentiment_spike` event
- `shock` — per symbol: `{sigma_multiple, volume_ratio, shock, estimated}`
- `anticipation` / `odds_deltas` — Polymarket odds and their change vs the
  previous snapshot (`odds_from`, `odds_to`, `delta`, `delta_pct`)

### Which-coin scanner

`GET /api/scanner/candidates`

Key fields:

- `available`, `created_at`
- `candidates` — ranked `{symbol, score, reasons[], signals{}}`; reasons are
  plain language ("volume x2.4 vs 7d avg", "mentions +180%/h on StockTwits",
  "newly listed on OKX")

An automation rule whose `symbol` is `SCANNER` auto-analyzes the top candidate.

### Fused signals

`GET /api/market-intel/fusion?symbols=BTC,ETH,SOL`

Up to 8 comma-separated symbols. Per symbol:

- `score` — weighted quant × sentiment × psych in [−1, 1]
- `signal` — buy (≥ 0.25) / sell (≤ −0.25) / hold
- `confidence`, `weights`, `components` (each with its own evidence), `missing`
- `matched_triggers` — which framework triggers fired, e.g.
  `"buy: F&G recovery +12 · sentiment +0.35 · basis 1.40%"`,
  `"sell: RSI 74 overbought · negative sentiment spike"`

### Risk engine (requires your `claw_` bearer token)

- `GET/PUT /api/risk/limits` — daily loss cap, symbol exposure, SL/TP %, Kelly
- `GET /api/risk/breaker` · `POST /api/risk/halt` · `POST /api/risk/resume`

Every automated order passes the risk gate; rejections land in
`automation_runs.skip_reason`.

## Recommended Usage Pattern

1. `GET /api/market-intel/psych` — market-wide mood; skip gracefully if `available` is false
2. `GET /api/scanner/candidates` — what's moving and why
3. `GET /api/market-intel/fusion?symbols=…` — per-symbol score for the coins you care about
4. Before trading, check `GET /api/risk/breaker` — a halted breaker means stand down

## Python Example

```python
import requests

BASE = "https://sooppiy.com/api"

psych = requests.get(f"{BASE}/market-intel/psych").json()
if psych.get("available"):
    fng = psych["fear_greed"]
    print(f"F&G {fng['value']} ({fng['classification']}), 3d change {fng['delta_3d']}")

candidates = requests.get(f"{BASE}/scanner/candidates").json()
watchlist = [c["symbol"].removesuffix("USDT") for c in candidates.get("candidates", [])[:3]]

symbols = ",".join(watchlist or ["BTC", "ETH"])
fused = requests.get(f"{BASE}/market-intel/fusion", params={"symbols": symbols}).json()
for s in fused["signals"]:
    print(s["symbol"], s["signal"], s["score"], "| triggers:", s["matched_triggers"])
```

## Decision Rules

- Use this skill to collect signal context before acting
- Use `position-sizer` to turn a signal into a position size
- Use `signal-postmortem` to review how past signals performed
- Use `tradesync` to publish the resulting signal
- Use `market-intel` for grouped financial news and macro snapshots
