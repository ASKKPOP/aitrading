# Overnight audit — 2026-07-17

Henry asked for a full implementation check against three specs, run by 5 audit agents
plus 4 adversarial QA verifiers, with authorization to fix without confirmation until
everything passes. This is the record.

**Specs audited**
1. `~/Downloads/signal_dashboard.html` — the original Signals Board mockup (목업/DEMO data).
2. `docs/research/parameters/2-ai-trading-parameters-ko.html` — the TOP-10 decision parameters.
3. `https://sooppiy.com/docs/guide` — the live user-facing guide (its claims must be true).

---

## Fixed and deployed overnight

Every one of these is the same shape: **a value computed correctly, then dropped in a
hand-off**. None was a broken feed; all were plumbing. That pattern is the finding.

| # | Fix | Evidence it was real |
|---|---|---|
| 1 | TOP-10 params `reversal_1m_pct`, `golden_cross_state`, `sigma_24h_pct` forwarded to the model | `quant_crypto.py:161,284` computed them (BTC live: `-3.9`); `_quant_component` dropped all three, so the AI never saw mean-reversion (#10), the MA-cross trend state (#1/#2), or the 24h volatility read (#4) |
| 2 | `data_verification` + `cached_age_s` forwarded from `fuse_with_ai` to callers | We paid Opus for the D5 input check and discarded the result; the board's suspect badge and verdict-age tooltip could never fire |
| 3 | A failed AI call is now `rule-fallback`, not `rule` | `generate_text` swallows provider errors and returns `None` (`llm_client.py:270`), so a real outage wore the label meaning "AI is off by configuration". Live SOL hit exactly this |
| 4 | Kimchi block labelled `measured_on: BTCUSDT` | D5's **first live catch**: flagged ETH `suspect`/**high** — "kimchi premium computed against ~$63k prices while symbol is ETH at $1835". Correct: `cross_market.py:50-83` measures on BTC and it rides on every symbol |
| 5 | ETF headline labelled `headline_measured_on: BTC` | Same class: `sosovalue_etf` — "BTC decides the headline direction; ETH rides along" — so `direction: inflow` sat beside ETH's `-$28M` outflow |
| 6 | Whale + calibration blocks aged (D5b gap closed) | `whale_feed.py:200` sets `created_at`, `calibration.py:131` sets `generated_at`; the snapshot copied only totals/buckets. Whale totals read all-zero both when idle and when broken — the age is what tells them apart |

**Live proof of the arc:** ETH's D5 verdict went `suspect`/high → `suspect`/2×low → **`ok`, 0 high
concerns**, i.e. it would no longer block in enforce mode. The labels changed the model's
reading, exactly as intended.

Tests: **1079 passing**, two full runs, exit 0 both. Every fix mutation-checked.

---

## Needs Henry — cannot be done without you

### 1. `ALPHA_VANTAGE_API_KEY=demo` on prod — news sentiment is dead (HIGH)

Production still holds the `.env.example` placeholder. The code correctly refuses to treat
`demo` as configured, so all four news categories fail:

```
equities/macro/crypto/commodities: ALPHA_VANTAGE_API_KEY is not configured
market_news_snapshots rows: 0
```

**Impact:** news sentiment is a core signal in mockup [1] ("뉴스 감성 (24h) … 1,284건 분석").
Today the board's 뉴스 심리 tile reads "수집 중… (뉴스 스냅샷 필요)" permanently, psych spikes
are always 0, and the AI's factor snapshot has no news input at all.

**Why I stopped:** the free tier is ~25 requests/day and the loop needs ~96 (4 categories,
hourly), so this is a paid-tier decision, and I won't register accounts. Add a real key to
`~/sooppiy/app/.env` and recreate the container (`--env-file` is only read at creation).

### 2. `EXECUTION_ENCRYPTION_KEY` empty on prod (LOW today)

The container warns: *"using ephemeral key … credentials cannot be decrypted after restart"*.
Impact is nil right now because real order execution is disabled by design, so nothing is
stored. It becomes real the moment anyone saves broker credentials. I did not mint a
production secret while you were asleep.

### 3. Per-source sentiment breakdown — mockup promises 5 sources, we have 1 (decision)

Mockup [1] shows sentiment split across **X/Twitter, Reddit, news headlines, Telegram,
YouTube**. Implemented: **StockTwits only** (`analysis_sources.py:53`), plus news headlines
once #1 is fixed. X and Reddit APIs are paid/restricted; Telegram and YouTube would need
custom collectors. This is scope and cost, not a bug — your call.

---

## Still blocked (unchanged)

- **`VERIFY_ENABLED=enforce`** — needs ≥200 reviewed advisory verdicts. Verdicts *are*
  persisted (in `automation_runs.confluence_json`, confirmed live), but prod has **1 run and
  0 enabled rules**, so nothing accumulates. Needs real usage, not a config change.
- **Card 09 token unlocks** — DefiLlama went paid.

---

## Correction to earlier claims

I twice told Henry the enforce flip was blocked on enabling AI fusion. **That was wrong** —
the verifier runs on automation decisions, independent of fusion. I also claimed the verify
verdicts were never persisted; **also wrong** — `automation.py:459` writes them into the
telemetry blob, proven by a real prod run whose verdict reads `upheld / 0.6 / advisory`.
Both errors came from reading an INSERT's column list without reading the twelve lines above
it that build the payload.
