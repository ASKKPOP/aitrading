# Plan 27 — US-stock intraday range discipline ("buy the low zone, sell the high zone")

**Owner ask (2026-08-18, verbatim):** "Is there any USA stock algorithm that
two time buy or sell — buy lowest price of the today, and sell highest?"
followed by "implement" and "plan first and verification 5 agents and then
implement."

**Honest reframe (stated to the owner, accepted):** buying THE daily low and
selling THE daily high is unknowable prospectively. The buildable neighbor is
an **intraday range/mean-reversion discipline**: enter long in a
statistically-likely LOW zone, exit in a likely HIGH zone, at most two
round-trips per day, only where measured expectancy after fees is positive.

## 1 · Why this fits the measured evidence

- XOM 1426 (2026-08-18): the desk **sold the dip** and the sequencing cost
  −$0.582 = 83% of the run's potential (+$0.701 → +$0.119). Two-agent
  verified.
- The noise-churn class (reduce-inside-own-stop, early-in-horizon) is the
  documented recurring loss author on winners AND losers (1417, 1426).
- Fleet-33's winning shape (bank strength in halves, never dump dips) is the
  behavioral target; this plan gives it intraday-timing teeth.
- Known microstructure: intraday extremes cluster near the open and close
  (U-shaped intraday volatility) — the effect this plan must MEASURE on our
  own symbols, not assume.

## 2 · The experiment (binding: implement only on its result)

### H1 (distribution)
For the R20 tech roster + S&P-100 names the platform trades, the daily LOW
falls in the first 60 minutes (13:30–14:30Z) and the daily HIGH in the last
60 minutes (19:00–20:00Z) — or the mirrored down-day pattern — materially
more often than the uniform-time null (each ≈ 15% per hour bucket).
**Falsifier:** extreme-time distribution statistically indistinguishable
from uniform across buckets.

Data: Yahoo 1m candles (5-day window per symbol — the platform's own
fetcher path, interval "1m"/range "5d"), ~30 symbols → ~150 symbol-days.
Thin but sufficient for a first distribution read; state n plainly.

### H2 (the tradeable rule, daily-OHLC backtest — no intraday needed)
Rule R(k, m), evaluated per symbol-day from daily OHLC over 1 year:
- **Entry:** limit-buy at `open × (1 − k)`. Filled only if `low < limit`
  (strict, conservative); fill price = limit.
- **Exit:** limit-sell at `open × (1 + m)` if `high > limit` (strict);
  otherwise market-on-close at `close`.
- Fees: platform rate `fees.fee_rate("us-stock") = 0.00005` per side
  (plus a slippage haircut of 2 bp per side — deliberately harsher than
  the measured 0.088% arm-executor slippage scaled to liquid large-caps).
- Grid: k, m ∈ {0.25%, 0.5%, 0.75%, 1.0%, 1.5%}; report the FULL grid,
  never only the best cell (R6 lesson: narrow-band positives are noise).
- Sizing: $250 notional (our capped scale) — expectancy reported per-trade
  in $ and %.

**Ship gate (all required):**
1. Per-trade net expectancy > 0 at the 90% bootstrap lower bound on the
   full-grid-median cell's neighborhood (not a lone cell), n ≥ 300 fills.
2. Sign survives removing the largest single winning day (owner outlier
   rule).
3. Sign survives a fee ×2 stress.
**If any gate fails, the verdict is published as the result and NOTHING
ships — negative-expectancy logic never ships (the garbage rule).**

### Lookahead/pitfall guards (R6/R8 precedent)
- Entry limit is derived from OPEN only; exit limit from OPEN only; fills
  use strict inequalities against low/high — no same-bar peeking beyond
  OHLC semantics.
- Ambiguity rule: if BOTH limits were touchable, assume the WORST ordering
  (entry filled, exit NOT filled, exit at close) — biases against the rule.
- Gap days: if `open < limit_entry` already (gap down through the zone),
  skip the day (no chasing).
- Survivorship: the roster is today's membership — acknowledged bias,
  second-order at 1y horizon; stated in the result.
- No `__pycache__`/live-feed leaks: script runs on the prod worker
  container against the platform's own cached fetchers, read-only.

## 3 · Implementation IF the gate clears (AI-first order)

1. **Skill (the desk stays the author, §7b):** a `trader/us-stock` clause —
   "TIME YOUR ZONES: enter on weakness into a pre-stated zone below the
   open, bank into strength near your target zone; never market-chase an
   entry, never sell a dip that is inside your own stop distance" — wired
   with the measured numbers. Budget: prune first (catalogue at capacity,
   §10 trap), wiring test mandatory (brief-line lesson).
2. **No new platform executor in phase 1.** Entries remain desk-authored at
   cycle time (the 30-min cadence samples the open hour 2–3 times); the arm
   executor already covers exits between cycles. A resting-limit-entry
   mechanism is explicitly out of scope until the skill's live effect is
   measured (2+ sessions).
3. **Post-ship re-measurement (binding):** the churn-class counterfactual
   (dip-sells and their cost) and entry-fill quality (entry price vs open,
   vs day range) per session, reported at the 24h sweep; a skill that moves
   nothing is reported FAILED.

## 4 · Boundaries kept

- Monitor-only session: no fleets/runs/trades are created to test this;
  the backtest is offline replay on cached data.
- Gates (expectancy, R15, maturity) untouched. Extreme-config warning
  unchanged. Risk configs never edited.
- The 5-agent verification (owner order) reviews THIS plan before any code.

---

# v2 — POST-VERIFICATION AMENDMENTS (binding; 5-agent review 2026-08-18, 5× APPROVE-WITH-CHANGES, 0 REJECT)

Consolidated from V1 statistics · V2 methodology · V3 integration ·
V4 owner-law · V5 profit-adversary. Where they conflict with §1–§4 above,
these amendments WIN.

## A · Hypothesis corrections
1. **H1 null = arcsine / simulated random walk, not uniform** (extremes
   cluster at open/close for ANY driftless walk — uniform is auto-pass).
   Inference clustered by calendar day (~30 symbols × same 5 days ≈ 5
   effective observations). **H1 is descriptive and NON-GATING: it
   contributes nothing to the ship decision, and no skill wording may
   depend on it** unless it survives against the arcsine null.
2. **H1's 1m data is NOT served by any cached platform path** (the 1m/5d
   fetch exists only inside a private single-price helper). The script
   makes its own chart calls: paced ≥23s apart (~12 min for 30 symbols),
   run OUTSIDE NYSE hours, fetch ONCE → persist to scratch → all analysis
   offline. Same pacing for the ~30 daily-candle calls (the days=365
   cache key misses the research engine's warm days=60 entries).

## B · H2 fill-model corrections
3. **Ambiguity rule replaced** (the old one killed the m-axis and was
   optimistic on strong closes): when both limits were touchable, exit
   price = **min(close, exit_limit)**. The daily-OHLC backtest is
   thereby the PESSIMISTIC variant (limit exit never assumed better than
   close) — labeled as such in the result.
4. **Gap rule re-anchored**: skip the day if `open ≤ prior_close × (1−k)`
   (gap-down through the zone — no knife-catching); the old open-anchored
   rule was vacuous.
5. **Data hygiene**: drop the current partial trading day's bar; drop any
   row with None open/high/low; unadjusted OHLC is fine (all quantities
   are same-day ratios) but H1 bucketing never compares levels across an
   ex-date.
6. **Mechanism gap stated and stressed**: H2's limit fills are an UPPER
   BOUND on the live 30-min-sampled desk (entries are market orders at
   cycle marks; arms are exits-only; there is no true MOC). The backtest
   adds a **cycle-sampled variant** — entry only if a 30/60-min sample
   point sits inside the zone, entry at that sample price — and the ship
   gate must hold on BOTH the limit and cycle-sampled variants. The 2bp
   slippage haircut is SOFTER than the one measured live figure (0.088%
   arm slippage) — the fee×2 stress therefore ALSO doubles slippage, and
   §3.3's live fill-quality metric is the binding sim-to-live control.

## C · Ship-gate corrections
7. **Drift control (chief false-positive vector)**: the gated quantity is
   the rule's expectancy MINUS the same-symbol-days open→close baseline
   (beta-matched). Report the down-market / flat / up-market subsample
   split; a rule that only wins in the up subsample fails.
8. **Day-level block bootstrap** (fills cluster on market-wide dips; iid
   over fills is invalid). **The shipped (k,m) cell is pre-registered as
   the gated cell** — gate-on-median-then-ship-best is forbidden.
9. **Published auto-REJECT triggers, binding even if the headline gate
   passes**: (a) top decile of symbol-days > 50% of net profit, or
   removing the top 3 days flips the sign; (b) sign flips between the two
   half-year subsamples; (c) profit predominantly from the MOC leg (that
   is drift capture, not "sell the high zone"); (d) baseline miss per
   amendment 7; (e) post-ship live entry-fill quality does not reproduce
   the backtested variant's fills.

## D · Skill-scope corrections (V5's deepest cut)
10. **The entry half is CONDITIONED or dropped.** The roster is
    momentum-selected (mom_5d/mom_20d ranking) — fading dips on
    trend-selected names fights the selection signal and collides with
    the no-adds-into-losers rail (#79). The measured evidence (XOM
    churn −$0.582; 1417) supports the EXIT-discipline half. Therefore:
    the skill's exit half ("bank strength; never sell a dip inside your
    own stop distance, early in your own horizon") ships on the churn
    evidence + a passing H2; the ENTRY half ships only if the H2 result
    itself is entry-driven AND is conditioned on "desk thesis long AND
    price above the desk's own stated invalidation."
11. **Rail-geometry check before wiring numbers**: the surviving (k,m)
    cell's implied R:R must clear the order-params R:R floor (2:1) — a
    cell the rails would clamp is not shippable as skill numbers. R21 /
    ratchet exits are the rails working and are NOT counted as skill
    failures in §3.3's re-measurement.
12. **"≤ 2 round trips/day" is encoded in the skill text** and counted in
    the §3.3 re-measurement (it was load-bearing prose before).
13. Correction of record: the trader/us-stock skills budget is 48,000
    with ~4,014 chars headroom (measured on main) — the "at capacity,
    prune first" note in §3.1 is stale; the binding constraint is the
    desk's attention, not bytes. Fractional-share sizing stays a
    simulator fact — skill text must not promise broker-side fractional
    routing.

## E · Execution constraints
14. Fetch window: outside 13:30–20:00Z. One fetch pass, then offline.
    The script runs `docker exec -w /app/service/server`, read-only to
    the DB; cache writes by `get_daily_candles` are accepted as the one
    shared side effect (they are ordinary warm entries).

---

# v3 — EXPERIMENT RESULT (2026-08-18 ~23:30Z) · **VERDICT: REJECTED — NOTHING SHIPS**

Data: 30 symbols (R20 tech roster + 7 fleet-traded non-tech), 1y daily +
60d 30-minute + 5d 1-minute bars, fetched once, paced, off-hours.
Pre-registered primary cell k=0.5%, m=1.0%. Pessimistic fills, prior-close
gap skip, fees 0.5bp + 2bp slippage per side.

## The numbers (primary cell)

| variant | n fills | rule net /trade | excess over open→close baseline | LB90 (day-block) | ×2-cost net |
|---|---|---|---|---|---|
| limit (1y daily) | 3,989 | **−27.7bp (−$0.69)** | +30.1bp | +27.9bp | −32.7bp |
| cycle-sampled (60d 30m) | 662 | **−0.6bp (−$0.01)** | +127.1bp | +119.1bp | −5.6bp |

## Why REJECTED despite the "excess" gate passing

**The garbage rule outranks the gate arithmetic: the rule's ABSOLUTE
expectancy is negative in both variants** (−$0.69/trade limit; ≈$0 to
negative cycle-sampled, and negative under the ×2 cost stress). The
pre-registered gated quantity (excess over the drift baseline) passes —
but only because conditioning on a fill (price −0.5% below open)
SELECTS weak days, on which the open→close baseline loses even more
(~−58bp). "Loses less than buying the open on down days" is not an
edge; shipping it would ship negative-expectancy logic. The drift
control did its anti-bull-year job and simultaneously exposed this
inverse selection effect — exactly the class of false positive V5
warned the gate could manufacture. The grid's rising "excess" with
deeper k is the same artifact (deeper fills select weaker days).

MOC-leg diagnostics confirm: 86–88% of fills exit at close, and the MOC
leg carries the entire loss (limit leg +822bp total vs MOC −1,926bp) —
the rule is structurally "catch a falling open, ride it to a losing
close" on a momentum-selected roster, as V5 predicted.

## H1 (descriptive, non-gating) — and it REFUTES the folk premise

Against the arcsine null [.33/.17/.17/.33], observed quartile-of-day
distributions (n=1,800 symbol-days @30m; 150 @1m):
LOW [.66/.09/.07/.19], HIGH [.62/.09/.09/.20]. **BOTH extremes cluster
in the FIRST quartile far beyond random-walk expectation.** The "high
comes late" half of the buy-low-early/sell-high-late story is refuted
on this tape — the open sets both extremes most days. The only
defensible descriptive lesson is: the open hour is where the day's
extremes print; market-chasing entries there is maximum-adverse-
selection territory. That aligns with the already-licensed
exit-discipline/churn track, which continues under its own evidence
rules (XOM −$0.582 etc.) — NOT licensed by this experiment.

## Disposition

- No skill ships from Plan 27 (per D10, the exit half required a
  passing H2; H2 failed).
- The churn/exit-discipline lesson track continues separately on its
  own accruing evidence.
- Dead theories recorded by name so no future session re-runs them:
  **"intraday limit-fade on momentum-selected US large-caps"
  (negative absolute expectancy, inverse-selection excess artifact)**
  and **"daily high prints late"** (refuted vs arcsine).
- Data and fetch scripts cleaned from the box and scratchpad
  (temp-artifact rule); this section is the durable record.
