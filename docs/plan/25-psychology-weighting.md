# Plan 25 — Weight Psychology Harder (us-stock · forex)

**Owner directive (2026-08-14):** "The platform should be changed to weight
psychology harder — psychology is a very important factor for USA stock and
foreign exchange."

**Status:** Phase A **SHIPPED** (PR #422, squash `1a45a0f1`, deployed to
prod as `sooppiy-backend:20260814-plan25-psych2` on 2026-08-14; both skills
verified rendering in the prod container and present in `trading_skills`,
enabled, correctly scoped). Phases B–D remain proposals; each ships behind
its own flag and is judged in realized-P&L terms per the owner's monitoring
law ("the ultimate goal of all analysis is profit or loss").

All file/line references are `origin/main @ 9f03a972`.

---

## 1. Where psychology actually sits today (measured, not assumed)

The single most important fact for this plan: **the famous 0.5/0.3/0.2 fusion
weights and the 0.3 psychology cap do not touch trading.** `signal_fusion.py`
is read-only, served over `GET /api/market-intel/fusion`, and its only caller
is `routes_market.py:227`. Raising `PSYCH_WEIGHT_MAX` would change a dashboard
number and not one order. Effort must go to the levers that do reach orders:

| Lever | Current psychology weight | Reference |
|---|---|---|
| Research factor screen (`WEIGHT_PROFILES`) | crypto **.20** · futures **.10** · us-stock **.05** (lowest of any component) · forex **0 — absent** | `symbol_research.py:~84-90` |
| Desk brief lines (what the deciding model reads) | crypto: F&G in regime/backdrop; us-stock: StockTwits tilt + put/call OI inside the big-trader line (48 h max age), breadth line; forex: **nothing** | `run_engine.py:3216-3266, 3598-3631` |
| E1 routing (crowd extremes → full desk) | `psych_shock` trigger is **crypto-only**; no us-stock or forex crowd-extreme trigger exists | `run_engine.py:2750-2758` |
| Regime gates | F&G-band regime + auto breaker are **crypto-scoped** | `regime.py:398-424`, `symbol_research.py:780-781` |
| Skills | zero psychology-centric skills scoped to us-stock or forex (closest: unscoped `contrarian-crowding-gate`, us-stock `breadth-context`) | `trading_skills.py` |
| Analyst desk | 1 of 4 briefs is the sentiment analyst (all markets) | `analysis_agents.py:944-990` |

Data already flowing that psychology could use **today, without new vendors**:
CNN Fear & Greed (`psych_feed.py:130`), put/call OI ratio and FINRA short-volume
ratio and StockTwits tilt (`us_stock_factors.py`), S&P-500 breadth
(`breadth_feed.py`), DXY (FRED, `cross_market.py`), Polymarket Δodds.

## 2. Position held (stated firmly) — OWNER-CONFIRMED 2026-08-14

Raise psychology's **influence and coverage** substantially — and keep the
**never-alone invariant** (psychology may steer regime, sizing context, and
attention, but crowd emotion with zero quant/sentiment corroboration may not
place an order by itself). The platform's own verified-numbers report and the
55–58 % accuracy framing are the evidence base: psychology adds real
explanatory power *in combination*; alone it is the negative-EV pattern the
owner's profit law calls garbage. This plan makes psychology loud, not solo.

## 3. The plan — four phases, impact per effort

### Phase A — Skills (owner-editable, zero code risk, ship first)
Per the standing rule *decisions become skills*: the first lever is judgment
the desk runs, not a platform gate.

1. **`us-crowd-psychology-lens`** — sites `light, trader`, markets
   `["us-stock"]`. Teaches the desk to treat the crowd block as first-class
   evidence: CNN F&G ≤ 20 / ≥ 80 = contrarian regime (fade extremes, tighten
   adds); mid-range = momentum-confirming; put/call OI and short-volume ratio
   as positioning, StockTwits tilt as retail temperature; disagreement between
   positioning and price is the signal.
2. **`fx-risk-sentiment-lens`** — sites `light, trader`, markets `["forex"]`.
   Risk-on/off is the psychology of FX: equity F&G + DXY direction define the
   regime; safe-haven logic (JPY, CHF bid in risk-off; commodity FX bid in
   risk-on); never fight a risk-off day on a carry-long thesis.

Mechanism already exists end-to-end (`skills_for_prompt` market scoping,
deterministic injection, admin Skills tab). Cost: two catalogue entries.

### Phase B — Feed the desk (small code, per-market brief lines)
3. **us-stock psych state line**: surface CNN F&G value + Δ3d in
   `position_state` for us-stock runs (mirror of the crypto F&G read),
   plus put/call percentile vs its own 90-day history. New `_us_psych_line`
   beside `_breadth_state_line` (`run_engine.py:3598`), fail-soft like every
   brief line.
4. **forex risk-sentiment inputs**: give `analysis_agents._gather_technical`
   a forex branch (today it falls to spot-price-only, `analysis_agents.py:72-79`)
   carrying F&G, DXY 5-day change, and session-volatility — the start of the
   `quant_forex` module Plan-doc §7 already argues for.

### Phase C — Research weights + routing (flagged, A/B-able)
5. **`WEIGHT_PROFILES` v2** behind `FLEET_PSYCH_WEIGHTS_V2` (default off):
   - us-stock: psych .05 → **.15**, social .10 → .05, technical .35 → .30
     (news .25, macro .15, policy .10 unchanged; Σ = 1.0)
   - forex: add psych **.15**: technical .40 → .35, macro .40 → .35,
     news .20 → .15 (Σ = 1.0)
   - crypto/futures unchanged — the directive names us-stock and forex.
6. **Crowd-extreme routing beyond crypto**: add a `psych_extreme` trigger to
   `_classify_situation` for us-stock and forex when the equity F&G is ≤ 20 or
   ≥ 80 (market-wide, ambient — same class as `psych_shock`), so crowd
   extremes convene the full desk in these markets exactly as they already do
   for crypto.

### Phase D — Measure in profit terms, then decide
7. Per-market expectancy via `pnl_audit.py` ledger replay, two-week windows
   before/after each phase; the comparison is realized P&L per closed run,
   never process health. Each phase keeps its own kill switch; Phase C's flag
   makes the weight change a clean A/B (research batches are journaled with
   their profile, so attribution is mechanical).

**Exit criteria:** Phase A/B promote by default if us-stock and forex
expectancy do not degrade; Phase C flips default-on only if the v2-weighted
batches' built runs beat v1 batches on realized P&L over ≥ 8 closed runs per
market (the platform's own `FLEET_EXPECTANCY_MIN_TRADES` standard).

## 4. Explicitly out of scope / rejected

- **Raising `PSYCH_WEIGHT_MAX` (0.3)** — dashboard-only; would change no
  trade. Cosmetic unless fusion is ever wired into the order path (it is not).
- **Letting psychology trade alone** — kept forbidden (see §2). If the owner
  wants this invariant itself removed, that is a separate decision to make
  with eyes open against the platform's own published evidence.

## 5. Risks

- StockTwits/put-call coverage is thin for small caps → the us-stock line must
  render nothing rather than a stale number (existing brief-line contract).
- Forex psychology proxies (equity F&G, DXY) are correlated regimes, not
  pair-level sentiment; the skill wording must present them as regime, not as
  a signal about the specific pair (same discipline as `breadth-context`).
- Weight changes shift which symbols get researched at all — Phase C must
  watch the survivor mix per market, not only P&L, to catch a screen that
  goes psychology-heavy and stops nominating liquid names.
