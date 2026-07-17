# Overnight audit — 2026-07-17

Henry asked for a full implementation check against three specs, run by 5 audit agents
plus 4 adversarial QA verifiers, with authorization to fix without confirmation until
everything passes.

**Result:** 94 agents, **20 findings confirmed, 2 refuted**. Nine fixed, tested, deployed
and verified live overnight. Suite went 1075 → **1111 passing**. Zero exceptions in prod.

**Specs audited**
1. `~/Downloads/signal_dashboard.html` — the original Signals Board mockup (목업/DEMO data).
2. `docs/research/parameters/2-ai-trading-parameters-ko.html` — the TOP-10 decision parameters.
3. `https://sooppiy.com/docs/guide` — the live user-facing guide (its claims must be true).

---

## The two that mattered most

### A League of Legends match was moving the BTC signal (high, 3/4 QA)

`_gather_anticipation()` asked Polymarket for top markets **by volume, with no topic
filter**, so the *crypto* anticipation signal was fed by whatever the world was betting on.
Live, all ten markets were non-crypto:

```
Will Belete Molla be the next Prime Minister of Ethiopia?
Will Argentina win the 2026 FIFA World Cup?
LoL: Hanwha Life Esports vs T1 (BO3)        <- Δ0.08, above the 0.05 threshold
```

A ≥0.05 swing on any of them added +0.25 to the psych component and printed *"odds
re-rating LoL: Hanwha Life vs T1 0.355→0.435"* on the board as a **trade rationale**. QA
measured BTC's entire fused score magnitude coming from the esports match. The psych dict
also feeds the AI snapshot, so it reached the Opus verdict too.

Fixed: filtered to crypto/regulatory/macro topics; returns `[]` when nothing relevant is
live (missing is honest, substituting noise is not). Live now: Fed rate decisions and
Bitcoin price markets only.

**My own test caught a bug in my fix:** plain substring matching let `"eth"` match
**Eth**iopia — which would have passed the Ethiopian markets straight through the new
filter. Matching is on word boundaries.

### The LLM authored the fill price, defeating every notional limit (high, 4/4 QA)

The trader prompt asked the model for `"entry":number|null` and the code replaced it only
when *falsy*. So:

```
automation.py:401   quantity = size_usd / entry     <- model's number
risk_engine.py:464  exposure + quantity * price     <- the SAME model's number
```

Both sides use it, so the arithmetic always reconciles to exactly `size_usd` and every cap
reports **ALLOWED** — while the position opened is off by whatever factor the price was off
by. An entry of 60 instead of 60,000 opens 1000× the intended size, cleanly, through a gate
that says yes. No malicious model required; LLMs slip units routinely.

This is the exact P-1 violation the architecture exists to prevent, hiding in the one input
nobody classified as a limit: **every cap is denominated in price, so whoever sets the price
sets the denominator of the whole risk stack.**

Fixed: the model's price is commentary (`suggested_entry`); execution always fills at the
live price. The 6 tests were written against the OLD code first and 4 failed there — they
prove the exploit, they don't just assert the fix.

---

## All nine fixes deployed

| # | Fix | Why it was real |
|---|---|---|
| 1 | Anticipation filtered to crypto/macro topics | esports/elections/football were moving crypto signals |
| 2 | Anticipation can now be bearish | Both outcomes of a binary market were emitted and only `delta >= +0.05` tested — so **any** movement always read bullish. Proven: "BTC above $60k?" Yes collapsing 0.70→0.55 fired **bullish** via the No side |
| 3 | P-1: model no longer authors the fill price | see above |
| 4 | Junk symbols cost 0 Opus calls | Public unauthenticated endpoint: `?symbols=ZZQQ9` bought 2 Opus calls + 21s. With quant=None and sentiment=None the invariant forces `hold` anyway — so the model is no longer asked. Cache bounded (64, LRU) |
| 5 | Psych cap enforced on the AI path | The board promised "psych weight structurally capped"; that was true only of the rule path. A verdict declaring `psych > 0.3` is now discarded. Board text corrected to what is actually guaranteed |
| 6 | TOP-10 params forwarded | `reversal_1m_pct` (#10), `golden_cross_state` (#1/#2), `sigma_24h_pct` (#4) computed and dropped. The live model rationale now cites *"reversal_1m -4.37%"* — it reasons with data it could not see before |
| 7 | D5 verdict + verdict age forwarded | We paid Opus for the input check and discarded it |
| 8 | `rule-fallback` vs `rule` | A real model outage wore the label meaning "AI is off" |
| 9 | Temperature refusal learned once | prod logs showed 400s:200s exactly **1:1** — every call wasted a round-trip (~2x latency on a 20s path). Now 1:5 |

Plus, from before the audit: kimchi/ETF headline labelled BTC-measured, whale/calibration
blocks aged.

Every fix mutation-checked. Two of my own tests were caught being fake by mutation testing.

---

## Needs Henry

### 1. `ALPHA_VANTAGE_API_KEY=demo` — news sentiment is dead (HIGH, 4/4 QA)

Prod still holds the `.env.example` placeholder, so all four categories fail and
`market_news_snapshots` has **0 rows**. News sentiment is a core mockup signal; the board's
뉴스 심리 tile reads "수집 중…" permanently and the AI gets no news input.

Free tier is ~25 req/day against ~96 needed (4 categories, hourly) → **paid-tier decision**.
I don't register accounts. Add the key to `~/sooppiy/app/.env` and recreate the container
(`--env-file` is only read at creation).

### 2. Per-source sentiment breakdown — mockup promises 5 sources, we have 1 (decision)

Mockup shows X/Twitter, Reddit, news, Telegram, YouTube. Implemented: **StockTwits only**.
X and Reddit APIs are paid/restricted; Telegram/YouTube need custom collectors. Scope + cost.

### 3. `EXECUTION_ENCRYPTION_KEY` empty (LOW today)

Prod warns it uses an ephemeral key. Harmless now (real execution disabled by design);
matters the moment anyone stores broker credentials. I won't mint a production secret
unilaterally.

### 4. Should the kimchi premium inform non-BTC signals at all? (decision)

It is a BTC-measured market-wide gauge. I labelled it rather than strip it, because whether
it should reach an ETH signal is a trading-domain judgment, not mine.

---

## Confirmed but NOT yet fixed (ranked)

| Finding | Sev | Note |
|---|---|---|
| Guide documents fixed 0.5/0.3/0.2 fusion; prod is AI-weighted | high | **I made this false by enabling fusion.** Guide content needs regenerating |
| Guide claims psych-led trading "outright impossible" | high | Now true again after fix #5, but wording overclaims the mechanism |
| Guide test count stale and self-contradictory (says 859 and 708; actual 1111) | low | |
| Rule-based fallback decision labelled with the Opus model that never produced it | med | same class as fix #8 |
| Automation confluence reads `technical`, always None | med | |
| `sigma_daily_pct` never reaches the risk gate — vol sizing is dead code | med | turning it on reportedly rejects 100% of buys |
| Consult chat asks for `"rsi"`, a key quant_crypto never emitted → advisor always sees null | med | |
| 24h shock/volatility chart with 3σ bars never built | med | `shock_history()` exists, no endpoint |
| Fundamentals (#9: ROE/EPS/valuation) not implemented | low | |
| Bid-ask spread / liquidity order-size cap (#3) not implemented | low | |
| Hot-issues list — board shows only the next event, drops the other 7 | low | |

---

## Corrections to my own earlier claims

- I twice said the `enforce` flip was blocked on enabling AI fusion. **Wrong** — the verifier
  runs on automation decisions, independent of fusion.
- I claimed verify verdicts were never persisted. **Wrong** — `automation.py:459` writes them
  into the telemetry blob; a real prod run reads `upheld / 0.6 / advisory`.
- I raised an alarm that logged-in users get 401 on agent routes. **Wrong** — the app carries
  two tokens deliberately.

All three came from reading part of a file and concluding from it. The audit's best findings
came from doing the opposite: diffing what is produced against what arrives.
