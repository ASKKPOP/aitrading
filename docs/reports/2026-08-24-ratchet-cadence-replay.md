# Breakeven-ratchet lock-cadence replay (pre-registered experiment, solution lever #2)

2026-08-24. Pure computation on archived 1m candles — no prod writes, no trades.
Gates the ranked solution #2 of reading #50 (docs/reports/2026-08-22-automation-monitoring.md).
Replay code and machine output live beside the dataset (untracked, like this
report): `docs/reports/data/ratchet-replay-candles/replay_v2.py` /
`replay_v2_out.json`. Data: `docs/reports/data/ratchet-replay-candles/`.

## Pre-registered hypothesis and refutation rule

**H:** the ratchet's realized losses are the 64s-poll/300s-mark discretization; a
lock evaluated on ≤60s marks — or held as a resting price level — converts
−overshoot fires to ≈$0 net while preserving the rail's saves (LTC 1556-class).

**Refutation (pre-registered):** if ≥30% of fires under either counterfactual exit
MORE negative than live, or the aggregate delta ≤ $0, the cadence hypothesis is dead.

## Verdict (headline)

**The hypothesis SPLITS. The ≤60s-marks half is REFUTED. The resting-price-level
half SURVIVES, with a stated slippage sensitivity.**

- **Counterfactual A (60s lock evaluation, exit at the sampled mark): REFUTED on
  both pre-registered axes.** Aggregate delta **−$0.34** (≤ $0) and **3/9 fires
  (33%) exit more negative than live** (1335 −$0.006, 1712 −$0.60, 1721 −$1.01).
  The basis-free estimator (vs simulated-live on the same tape) is worse still:
  4/9 episodes negative. Mechanism: the crossing 1-minute bars range 0.14–0.51%
  against a 0.09–0.10% floor cushion — the overshoot is price velocity through
  the cushion, not the 300s mark gap. A finer *sampled* clock still fires one
  sample late, and on V-shaped crossings (1712) the coarse clock's luck can even
  beat the fine one.
- **Counterfactual B (resting price-level stop at the lock level): SURVIVES.**
  Level-fill aggregate **+$3.00**, **0/9 worse than live**; strip-largest (1392,
  +$1.22) leaves **+$1.78, 0/8 worse** — sign survives the strip. Robust to
  arming cadence (arming restricted to the 300s grid: +$1.77…+$2.70 across all 5
  phases, 0 worse). The three 08-23 fires (−0.577/−0.507/−0.137) all convert to
  **−$0.0002** (the level IS breakeven + round-trip fee by construction).
- **Slippage sensitivity (B):** aggregate stays positive until stop slippage
  reaches ~**45%** of the crossing minute's full range (~**24%** with 1392
  stripped); the worse-count never exceeds 2/9 (22%, < the 30% kill line) at ANY
  slip up to a full candle range. Crossing-minute ranges were 0.00–0.51%; 24% of
  the worst = ~12 bps of adverse slip tolerated even under the stripped
  aggregate. On OKX-liquidity perps at ~$500 notional this margin is wide, but it
  is the load-bearing assumption and is stated as such.
- **1556 LTC save preserved under every variant:** all counterfactuals exit
  00:51–00:59Z vs live 01:09:57Z — before the adverse move — at ≈+$0.00 vs live
  −$0.30 (and vs the reading-#43 no-ratchet counterfactual −$2.30, i.e. the save
  improves from $1.72 to ≈$2.30). Verified: B's stop is struck at 00:51 and the
  A-grid fires 00:51–00:59 in all phases.
- Per the pre-registration in reading #50 item 2 ("ship only if aggregate delta
  > 0 surviving strip-largest AND the LTC-class save is preserved"): **B
  qualifies; A does not.** Any Plan 28 rail experiment should target a resting
  price-level lock (intrabar stop fill), not a faster sampled clock.

## Refutations produced (named, per the experimental-mindset rule)

1. **H-cadence-60s** ("60s sampled marks ≈ $0 net") — **DEAD.** −$0.34 aggregate,
   33% of fires worse than live; on fast crossings the first 60s sample is
   already deep past the floor (1721: 23:30 close 0.43% past it → −$1.15 vs
   live's lucky −$0.14 poll catch at 23:29:49).
2. **H-archive-equals-prod-feed** — **DEAD** (v1 dead-end, documented below):
   12/12 spot-checked prod fills fall OUTSIDE the corresponding OKX 1m candle's
   low–high. Absolute replay against prod USD thresholds is invalid; v1 falsely
   concluded 1392 could never arm.
3. **H-1417-is-cadence** — **DEAD.** 1417's fire is authored by the
   phantom-baseline bug (since fixed by R21), fires 9s after the desk's own
   partial cover at an unchanged mark; any cadence exits within ±$0.02–0.10 of
   live. Its −$0.33 leg is NOT recoverable by lever #2 (and is already
   prevented by R21).

## Extracted code semantics (authority: worktree `service/server/run_engine.py`, branch docs/phase1-reading-51)

The task brief's line refs (~L890/~L969) match THIS worktree, not the stale
`feat/i18n-followups` checkout (which predates the ratchet entirely).

- `_breakeven_ratchet_enabled` **L883-887** — `BREAKEVEN_RATCHET` default ON.
- `_breakeven_arm_usd` **L890-918** — arm = max(current |qty|, largest book ever
  held) × **current mark** × `BREAKEVEN_FEE_RATE` (default 0.001) × 2 ×
  `BREAKEVEN_ARM_FEES` (default 1.0). Re-evaluated every scan at the current
  mark — **not latched** (the reading-#48 un-arm quirk).
- `_run_max_abs_qty` **L921-966** — anchor from `run_events` trade replay.
- `_breakeven_floor_hit` **L969-1033** — fires when
  `(current_total − baseline) ≤ exit_fee_usd`, gated on
  `(peak_total − baseline) ≥ arm_usd`.
- Call site **L1211-1258** — `_be_fee` = |qty| × mark × 2 ×
  (`BREAKEVEN_FEE_RATE` env or `fees.fee_rate(market)` = **0.00045** crypto);
  baseline = `peak_realized_usd` (R21: realized frozen at the peak epoch).
- `compute_run_pnl` (~L740s) — `total` = realized (ALL leg fees inside, entry
  fee included) + **gross** unrealized at `positions.current_price`; marks
  refresh every `POSITION_REFRESH_INTERVAL` (default/prod **300s**); scans ~64s
  but read the same stale mark. `_flatten_run` fills the exit **at the last
  mark** — fire mark price = fill price (verified on every episode below).
- `_ratchet_peak_pnl` — peak is a max over the SAME sampled marks (stale peak:
  reading #48 measured tick +$2.33 recorded as +$1.01 on 1721).

**Era reconstruction from the census arithmetic** (arm ÷ exit_fee):
- ratio **2.000** → fee term = ONE leg at flat 0.001 and the pre-baseline
  condition on run TOTAL: runs **1335, 1358, 1367, 1392** (08-17 → 08-18T00:27).
- ratio **8.889** → **1417** (08-18T12:23): round-trip per-market fee term
  (0.0009) already in; arm anchored to the 4× full book after partial covers;
  pre-R21 baseline (the bug fire).
- ratio **2.2222** → round-trip 0.0009 term + excursion baseline: **1489, 1556,
  1710, 1712, 1721** (08-19 on).

**Semantics verification (3 independent passes):** (1) all 10 census `arm`
values reproduce to 4 decimals as anchor_qty × fire-mark × 0.002 (this also
proves 1367's position was the FULL 0.69102 short and 1417's anchor the full
195.17); (2) all 10 `total@fire` values reproduce from C + X(exit_px) with
actual charged fee 0.00045/leg — including recovering 1335's prior-short banked
realized **C = +$0.0806**, which matches the code comment's independently
recorded "own excursion 0.342192" to 4 decimals; (3) the resulting live nets
reproduce the code comment's 1335 **−0.141443** exactly and the 08-23 trio
−0.577/−0.507/−0.137 → day **−$1.222** = pnl_audit. Fee assumption: actual
charged fee 0.00045/leg (crypto, FEE_PER_MARKET) for all 10 episodes — proven
by pass (2), which is inconsistent with 0.001/leg charging on every episode.

## Data-integrity finding (changes the method)

The archive README claims a fill-price cross-check PASS. **Re-verification
refutes it: 12/12 spot-checked prod fills (entries and exits) fall OUTSIDE the
low–high of their fill-minute OKX candle**, offset by a systematic 0.03–0.16%
(e.g. 1710 entry 52.35 vs candle 52.21–52.27 — the +0.15% drift reading #48
itself logged; 1556 entry 46.974 vs 47.05–47.07). The platform traded on its own
feed's marks; OKX history carries a basis against them of the same order as the
0.09% floor cushion, so absolute replay is invalid (it falsely killed 1392's
arm: needed ≥516.04 prod-space, archive max high 515.93).

**Method fix (v2):** difference-in-difference on the same tape. Each episode is
rebased to the archive's own entry price (entry-minute open); BOTH the live 300s
cadence (5 grid phases, since the poll phase is unknown) and the counterfactuals
are simulated on the same series. The basis cancels in deltas; simulated-live is
validated against the actual fire minute and net per episode. The system is
homogeneous of degree 1 in price, so rebasing scales all USD amounts by ≈1±0.002
(1335's cash C is the exception and is kept as cash — $0.0002-scale error).

Validation result: simulated-live phase ranges bracket the actual fire minute
and actual net in 8/9 episodes (e.g. 1710 sim −0.374…−0.779 vs actual −0.577;
1721 sim −0.132…−1.607 vs actual −0.137; 1712 sim −0.158…−1.267 vs actual
−0.507). Exception: 1556 (sim −0.092…−0.167, actual −0.300; sim fires ~10 min
earlier) — feed basis on LTC that night; flagged in its row.

## Method (variants and bounds)

All variants replicate the era-faithful fire logic above; only the mark cadence
or execution changes. Net = X(exit) − entry fee − exit fee at 0.00045/leg.

- **live-sim**: marks = closes of every 5th minute, phases 0–4.
- **A60** (central): marks = every 1m close; exit at the crossing close — what a
  60s poll realistically does.
- **A_best**: intrabar detection, exit AT the floor price (peak from favorable
  extremes — earliest arming).
- **A_worst**: intrabar detection, exit at the crossing candle's adverse
  extreme; floored by A60 where A60 is worse.
- **B**: stop resting at the floor price from the first armed 1m evaluation;
  exit at the level (best) or level + s × crossing-candle range, s ∈ [0,1]
  (slip bound), capped at the candle extreme. Robustness re-run with arming
  restricted to the 300s grid.
- Floor price per era: post-fix short E/(1+0.0009), long E/(1−0.0009); pre-fix
  from the run-total equation including C (one-leg 0.001 term).

## Per-episode results (USD, archive-rebased; delta = cf − actual live net)

| run | live net | live-sim range (5 phases) | A60 (t, net, Δ) | A bounds [worst, best] | B level (Δ) | B cross t vs live fire | notes |
|---|---|---|---|---|---|---|---|
| 1335 | −0.1414 | −0.148…−0.305 | 02:25 −0.1478 (−0.006) | [−0.1478, −0.0608] | −0.0608 (+0.081) | 02:00 vs 02:23 | pre-era; banked C=+0.0806 means even a perfect floor exit nets −0.06 on this position (bug semantics, fixed since) |
| 1358 | +0.0025 | +0.000…+0.008 (3/5 fire) | 08:27 +0.0126 (+0.010) | [+0.0042, +0.0154] | +0.0154 (+0.013) | 08:26 vs 08:28 | pre-era one-leg term > actual round trip → small positive fires |
| 1367 | −0.1140 | −0.123…+0.008 | 13:31 +0.0083 (+0.122) | [+0.0083, +0.0287] | +0.0287 (+0.143) | 12:57 vs 13:35 | full 0.691 short (census qty col is the split-fill half) |
| 1392 | −0.9602 | −1.255 (1/5 fires in window) | 00:20 +0.0338 (+0.994) | [+0.0338, +0.2609] | +0.2609 (+1.221) | 00:20 vs 00:27 | LARGEST contributor; pre-era C puts the long's floor above entry; 4/5 sim phases censored by window end — treat with care |
| 1417 | −0.3281 | n/a | n/a | n/a | n/a | n/a | **EXCLUDED — not a cadence loss.** Phantom-baseline fire (R21 bug, fixed); clean semantics never fire on this tape; bug-faithful cadence variants land within ±0.02–0.10 of live |
| 1489 | −0.0202 | −0.003…−0.015 | 02:57 −0.0029 (+0.017) | [−0.0060, −0.0000] | −0.0000 (+0.020) | 02:57 vs 03:16 | flat crossing candle (range 0) — zero slip risk |
| 1556 | −0.3005 | −0.092…−0.167 | 00:51 −0.1669 (+0.134) | [−0.2415, +0.0001] | +0.0001 (+0.301) | 00:51 vs 01:09 | **save preserved** — every variant exits ≥18 min before live, long before the −$2.30 no-ratchet path |
| 1710 | −0.5774 | −0.374…−0.779 | 12:16 −0.5766 (+0.001) | [−0.5766, −0.0002] | −0.0002 (+0.577) | 12:16 vs 12:19 | 0.27% crossing bar ≫ 0.09% cushion: 60s clock does NOT help; level does |
| 1712 | −0.5074 | −0.158…−1.267 | 16:12 −1.1089 (**−0.601**) | [−1.1089, −0.0002] | −0.0002 (+0.507) | 16:12 vs 16:14 | 0.51% crossing bar; V-shape — the 300s clock's late samples caught the recovery, 60s fired into the spike |
| 1721 | −0.1372 | −0.132…−1.607 | 23:30 −1.1496 (**−1.012**) | [−1.8110, −0.0002] | −0.0002 (+0.137) | 23:30 vs 23:29 | 0.43% crossing bar blew through the floor inside one minute; live's 23:29:49 poll was phase luck |

## Aggregates (n = 9 cadence-attributable fires; 1417 excluded)

Live total (these 9): **−$2.756** (all 10 incl. 1417: −$3.084).

| estimator | aggregate Δ | worse than live | strip largest (1392) | strip largest negative (1721) |
|---|---|---|---|---|
| A60 (60s sampled, central) | **−$0.342** | **3/9 = 33%** | −$1.336, 3/8 = 38% | +$0.670, 2/8 = 25% |
| A worst bound | −$1.090 | 3/9 | −$2.084 | — |
| A best bound (=level fill) | +$3.000 | 0/9 | +$1.778 | — |
| **B level fill** | **+$3.000** | **0/9** | **+$1.778, 0/8** | — |
| B slip 10% of crossing range | +$2.258 | 1/9 | +$1.037 | — |
| B slip 25% | +$1.161 | 2/9 | −$0.060 | — |
| B slip 50% | −$0.278 | 2/9 | — | — |
| B slip 100% (full range) | −$1.128 | 2/9 = 22% | — | — |

Basis-free secondary estimator (cf − simulated-live phase average, same tape):
A60 **+$0.62 but 4/9 episodes negative** and the sign is carried entirely by
1392 (+1.29; stripped: −$0.66) → A fails here too. B level fill **+$3.97, 9/9
positive**.

Per the owner rule on outliers: A60's full-sample verdict (refuted) FLIPS to
mildly positive when the largest negative (1721) is stripped — but the
pre-registered rule is evaluated on the full sample, both kill conditions
triggered, and the worse-fraction axis (33%) does not depend on the aggregate's
outlier. B's verdict survives its own strip (1392) on both axes at level fill.

## Caveats (all of them)

1. **OKX-vs-prod-feed basis** (0.03–0.16%): handled by rebasing + diff-in-diff;
   absolute USD levels carry it, deltas do not (to first order). The archive
   README's fill-range PASS claim is wrong and should be corrected.
2. **1392** is the largest positive contributor and its era arithmetic (C in the
   floor) is bug-semantics-faithful but no longer current; 4/5 live-sim phases
   were window-censored. B's verdict is reported with and without it.
3. **B's execution model does not exist on the platform today** — the simulator
   fills at marks, not at resting levels. Shipping B means building an intrabar
   stop-fill path (or per-position fast marks for open positions only), and the
   realized slippage is the one free parameter this experiment cannot measure
   from 1m candles. Survival threshold: ~45% (~24% stripped) of the crossing
   minute's range.
4. **Sub-minute price action is invisible**: A_best/B-level assume the level is
   touchable; a true gap through the level inside one minute would fill worse —
   bounded by the slip table.
5. **Peak-arming interaction**: B assumed 60s arming; re-run with 300s arming
   stays +$1.77…+$2.70 with 0 worse (7 window-censored no-fire cases across 45
   run-phases, all late-arming artifacts of the +30 min window).
6. n = 9 (10 minus the non-cadence 1417); one week of fires, all crypto, all
   one fleet generation. The forward metric if B ships: per-fire net vs the
   −overshoot baseline, measured on the same pnl_audit ledger.

## Bottom line

The discretization diagnosis of reading #48 was right about the loss mechanism
but wrong about the cheap fix: **a faster sampled clock does not buy the money
back — only execution AT the level does.** The Plan 28 rail item should be
re-scoped from "60s lock evaluation" to "resting price-level lock (intrabar
stop fill at breakeven+fee), slippage-measured", which this replay clears at
+$1.78…+$3.00 on the week's tape with zero episodes made worse and the
1556-class save intact.
