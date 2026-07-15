# Signal expansion gap analysis — research cards 07–16 vs the platform

**Date:** 2026-07-15 (overnight session). **Input:** `AI트레이딩_신호요소_확장리서치.md` (10 proposed signal sources beyond the existing 6 cards).
**Method:** full audit of the existing signal stack (market_intel / psych_feed / quant_crypto / scanner / signal_fusion / automation), then per-card feasibility triage: build now (free or existing-key data), env-gate for later (paid data), or already covered.

## Verdict summary

| Card | Research proposal | Platform status BEFORE | Status AFTER tonight | Data source |
|---|---|---|---|---|
| **07** 거시 일정 (FOMC·CPI·NFP) | Scheduled volatility events; block entries around releases | ❌ Absent (FRED gave latest *levels*, no calendar) | ✅ **Built** — `market_events.py`, `GET /api/market-intel/events`, fusion evidence, opt-in automation guard | Static verified calendar (Fed 2026–27 FOMC, BLS CPI 2026, BLS NFP convention) — zero API |
| **08** ETF 자금 흐름 | Real IBIT/FBTC daily net flows | ⚠️ Proxy only — `estimated_flow_score = price_change × volume_ratio` over the 8 spot-BTC-ETF tickers, flagged `is_estimated` | ✅ **Built (2026-07-15 follow-up)** — `sosovalue_etf.py`: real aggregate daily/5d/cumulative dollar flows for the US BTC+ETH complexes via the SoSoValue free-tier API (`SOSOVALUE_API_KEY`); summary `is_estimated:false`, per-ETF rows stay estimated (free tier is complex-level) | SoSoValue (free tier) |
| **09** 토큰 언락 | Unlock calendar, ~90% downside pressure, 30d pre-pricing | ❌ Absent | ⏸ **Deprioritized (2026-07-16)** — DefiLlama moved `/emissions` behind its paid API; a CoinMarketCal key was tried but their gateway 403s until a plan subscription is attached, and the owner decided it isn't worth the friction: unlocks only matter for vesting altcoins, while the platform centers on BTC/ETH/SOL (no unlock schedules). Revisit if alt coverage deepens | DefiLlama Pro or CoinMarketCal key (subscribed) |
| **10** 상장·상폐 | Listing pump&dump, delisting dumps | 🟡 Half-covered — scanner already diffs OKX new SWAP listings per scan | 🟡 Unchanged — delisting notices would need exchange announcement feeds | OKX instruments (free) |
| **11** 청산 캐스케이드 | Real liquidation feed + heatmap | ⚠️ Proxy only — psych_feed "shock" = hourly σ + volume ratio, flagged `estimated` | ✅ **Built (2026-07-15 follow-up)** — OKX `/public/liquidation-orders` (keyless, verified live) aggregated per hour (count, notional, long/short split) into psych shock; `estimated:false`, cascade flag at `LIQ_SHOCK_NOTIONAL_USD` (default $5M/1h). Heatmap/backfill still CoinGlass-only | OKX public (free) |
| **12** OI·펀딩·CVD | Positioning: open interest, funding, long/short | 🟡 Funding + basis existed; **OI hardcoded to "0"**, no long/short | ✅ **Built** — OKX `open-interest` + rubik `long-short-account-ratio` into `quant_crypto` (score factors: L/S ≥2.0 risk, ≤0.5 contrarian) and fusion payload | OKX public (free, verified live: BTC OI $1.93B, L/S 1.26) |
| **13** 거래소 넷플로우 | Exchange in/outflow as sell-pressure lead | ❌ Absent | 📋 Documented only — needs CryptoQuant/Glassnode (paid) | `CRYPTOQUANT_API_KEY` when subscribed |
| **14** 스테이블코인·스마트머니 | Stablecoin flows + labeled whale wallets | ❌ Absent (`scanner.fetch_whale_signals` stub returns `[]` — the designed extension point) | 📋 Documented only — Nansen/Arkham/Amberdata are paid | stub ready |
| **15** 예측시장 확률 | Polymarket odds as leading probability | ✅ Already exists — psych_feed "anticipation" tracks top-10 Polymarket odds deltas; full Gamma+CLOB integration | ✅ No work needed | Polymarket (free) |
| **16** DXY·김치 프리미엄 | Dollar correlation + Korea spread | ❌ Absent (only UUP-ETF momentum as a dollar proxy) | ✅ **Built** — `cross_market.py`, `GET /api/market-intel/cross`: kimchi premium (Upbit KRW-BTC vs OKX through USD/KRW) + FRED broad-dollar index | Upbit + open.er-api (free); FRED needs `FRED_API_KEY` |

**Net:** 3 cards built end-to-end tonight (07, 12, 16), 1 already existed (15), 1 half-existed (10), 2 remain honest proxies pending paid data (08, 11), 3 documented with the exact key needed (09, 13, 14).

## What was built tonight (verified)

### Card 07 — `market_events.py`
- Static calendar: 16 FOMC decisions (2026+2027, verified against federalreserve.gov), 12 CPI releases (BLS 2026), 6 NFP dates (Jul 2 + Aug 7 confirmed; Sep–Dec first-Friday convention). Times stored in ET, converted DST-correctly via zoneinfo (Jul FOMC → 18:00Z, Dec → 19:00Z — unit-tested).
- `GET /api/market-intel/events` → next events with countdown, recent, active release window (±60 min, env-tunable via `EVENT_WINDOW_BEFORE/AFTER_MINUTES`).
- Fusion: evidence line when <24h to an event or window active; `event_window` field added to fusion output.
- Automation: `EVENT_GUARD_ENABLED=true` (default **off**) skips new entries inside a release window, journaled as `skip_reason`. Implements the research's "block entries ±release" strategy. Fail-open.

### Card 12 — positioning in `quant_crypto`
- `crypto_feed.fetch_open_interest` (OKX `/public/open-interest`) and `fetch_long_short_ratio` (OKX rubik, keyless).
- New analysis fields: `open_interest_ccy/usd`, `long_short_ratio`; new score factors: L/S ≥ 2.0 → −1 (crowded long, squeeze risk), ≤ 0.5 → +1 (contrarian). Fusion quant component now carries both; Signals Board shows `OI $X.XXB · L/S n.nn` per coin.

### Card 16 — `cross_market.py`
- Kimchi premium: Upbit KRW-BTC ÷ USD/KRW vs OKX BTC-USDT spot; verdicts overheated (≥ +3%) / neutral / discount (≤ −0.5%), thresholds env-tunable. Verified live: −1.2% (discount regime).
- Dollar index: FRED `DTWEXBGS` level + 1d change when `FRED_API_KEY` set; explicit null+reason otherwise.
- Gated `CROSS_MARKET_ENABLED` (default off, same convention as psych/scanner phases). Served via the shared market-intel cache.

### Also shipped alongside (request A)
Three-tier user modes on the Automation page (`sooppiy_automation_mode`): **간편** (coin + risk preset → one button; presets 안정 4h/0.75/$200 · 균형 1h/0.65/$500 · 공격 30m/0.55/$1,000), **표준** (key fields + inline recommendations), **전문가** (all fields + event-guard note). Signals Board gained Next-Macro-Event and Kimchi-Premium tiles.

## Priority queue for the remaining gaps

1. **Card 08 upgrade (real ETF flows)** — highest signal-per-effort once a key exists. CoinGlass REST has per-ETF daily flows; land behind `COINGLASS_API_KEY` and replace `is_estimated` with real data (keep proxy as fallback).
2. **Card 11 upgrade (real liquidations)** — same CoinGlass key unlocks liquidation history + heatmap; would replace the σ-proxy in psych_feed's shock and give fusion a real cascade trigger.
3. **Card 09 (unlocks)** — DefiLlama free API; build `token_unlocks.py` with a 30d-lead flag per scanner candidate. Most useful if the platform expands beyond majors (unlock schedules matter for alts, not BTC/ETH).
4. **Cards 13/14 (netflow, smart money)** — blocked on paid subscriptions (CryptoQuant, Nansen). `scanner.fetch_whale_signals` is the prepared integration point.

## Layering (research doc §통합 관점 → implementation mapping)

1. Scheduled-event filter (07) → `events` endpoint + `EVENT_GUARD_ENABLED` ✅
2. Flow direction (08·13·14) → estimated ETF proxy only; real flows pending keys ⚠️
3. Microstructure trigger (11·12) → funding/basis/OI/L-S live ✅; liquidation still proxy ⚠️
4. Cross-check (15·16) → Polymarket odds ✅ + kimchi/DXY ✅

> ⚠️ Research use only — not investment advice. All figures are snapshots; thresholds (±3% kimchi, L/S 2.0/0.5, ±60min windows) are env-tunable and should be revisited with backtests.
