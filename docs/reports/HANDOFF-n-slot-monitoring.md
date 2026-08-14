# Handoff — N-slot fleet monitoring: crypto short block + US-stock swing block

> ## ⚠️ REPO MARKDOWN IS THE ONLY DURABLE STATE
>
> Same rule as `HANDOFF-automation-monitoring.md` (read that file for access,
> the ship pipeline, and every SQL trap — they all apply here and are NOT
> repeated). This file is the authority for the **two-block N-slot fleet**:
> what to watch per block, what counts as evidence for a FIX, and what gate
> must clear before any EXTEND. When memory and this file disagree, this
> file wins.
>
> ### 🔒 OWNER RULE (2026-08-11) — MONITOR ONLY, NEVER OPERATE
>
> **Trials, fleets, runs, and trades are created BY THE USER through
> sooppiy.com only.** A monitoring session never creates a fleet, never
> starts or stops a run, never places or closes a trade, and never edits
> `risk_limits` / `positions` / run configs. The session's whole output is:
> observe → diagnose → (when reproduced evidence demands it) ship a code or
> skill fix to prod → keep observing. The owner said it twice:
> *"I don't want testing from this session, stop"* and
> *"must be made by user and we can monitoring only."*

**Created 2026-08-12**, when the swing block (Plan 23 phases A–E, #382–#388)
and the pre-live trio (per-market broker routing, FINRA short-volume,
book-level overnight cap) completed. The owner will build their own swing
fleet at user level via sooppiy.com; from that moment this playbook governs
the loop.

---

## 1. The two blocks — what runs where

| | crypto SHORT block | US-stock SWING block |
|---|---|---|
| `fleets.archetype` | `short` (default) | `swing` |
| markets | crypto (+futures/forex per fleet) | **us-stock only** |
| cadence | 30-min cap (`RUN_INTERVAL_CAP_MIN`) | **240-min** cap (per-archetype) |
| leverage | fleet setting (spot/futures) | **pinned 1.0** |
| tier | per fleet gates | **Professional / Enterprise only** |
| horizon | intraday, give-back defense | 1–2+ days, holds overnight by design |
| sizing | vol-parity slot funding | **gap-sized: max_bet = R/G**, R = 1% of fleet budget |
| universe gate | research pool + manipulation screen | `swing_symbol_check` (≥180 bars, ≥$10, ADV20 ≥ $50M) + earnings guard |
| session logic | 24/7 | NYSE calendar: queued flattens, overnight stop dormancy |
| book rail | trailing lock / breakeven ratchet | **+ overnight cap: Σ(notional×G) ≤ 2.5% equity** (×0.6 Friday), last-20-min window, reduce-not-dump |

Archetype is stamped into each run's `config_snapshot_json` at compose time
(`archetype`, and for swing `thesis.swing_g_frac`). **Read the snapshot, not
the fleet row**, when judging a live run — the snapshot is what the run
actually trades under.

## 2. Per-cycle checks — SWING block

Run these on top of the normal cycle (main handoff §4). All `run_events`
filters use the full ISO form (`ts >= "2026-08-12T00:00:00Z"`).

1. **Universe gate honesty** — fleet events carry dropped candidates with
   reasons: `swing_history_thin`, `swing_price_low`, `swing_adv_thin`,
   `swing_data_unavailable`, `earnings_window`. A swing fleet that keeps
   dropping everything is either a dead feed (`swing_data_unavailable`
   dominant → check the daily-candles source) or a research pool that isn't
   producing us-stock theses (check `research_theses` market mix). Both are
   FIX candidates; neither is a reason to hand-pick symbols.
2. **G sanity** — for each running swing run, `thesis.swing_g_frac` in the
   snapshot should be ≥ 0.03 (the floor). A missing stamp is tolerated by
   the cap pass (floors at `SWING_G_FLOOR`, overstating risk = safe) but is
   still a defect — report it.
3. **Cadence** — ~~swing runs must NOT cycle at 30-min spacing~~
   **STALE, corrected 2026-08-14:** the owner's 2026-08-12 spec (see
   `fleet_planner.py` ~line 1155, "decouple LOOKING from ACTING")
   changed swing to **30-min analysis cycles with 60-min minimum entry
   spacing** — 30-min cycling is now CORRECT. The check is instead: no
   two ENTRIES on one swing run < 60 min apart (verified PASS 2026-08-14
   on SLV/MSFT/JPM tape).
4. **Overnight cap events** — fleet event `overnight_cap`; the reduce trades
   carry `client_order_id` prefix `fleet:{fleet_id}:overnight-cap:`. Verify:
   fired only in the last ~20 min before close, reduced the LARGEST
   notional×G contributor, never a full dump. Frequency matters: a cap that
   fires daily means sizing upstream is too big — that is a compose/G fix,
   not a cap tune.
5. **Session-queued flattens** — a stop/retire decided while NYSE is closed
   must queue and execute at the open, not error. Look for the queued marker
   in `run_events` and confirm execution at the next session open.
6. **Overnight gap outcomes** — the block's designed risk. For every
   position held overnight, compare open price vs prior close; a gap beyond
   G that fires the (dormant-overnight) stop at the open is the system
   WORKING. Log every gap loss — the §7 promotion criterion is that the
   WORST SINGLE overnight-gap loss stays < 5% (it proves the gap sizing
   works).
7. **Factor loop freshness** — `us_stock_factor_snapshots` should gain rows
   ~6-hourly for held/candidate symbols: `putcall_oi_ratio`,
   `short_volume_ratio` (FINRA, T+1 — a 1–3 day lag over weekends/holidays
   is normal, NULL forever is not), `stocktwits_tilt` (bare symbol, no `.X`).
   NULLs are honest (feed couldn't see) — never backfill by guessing.

```sql
-- swing runs + their snapshot archetype/G (prod MySQL)
SELECT r.id, r.symbol, r.status,
       JSON_UNQUOTE(JSON_EXTRACT(r.config_snapshot_json, '$.archetype')) a,
       JSON_EXTRACT(r.config_snapshot_json, '$.thesis.swing_g_frac') g
FROM trading_runs r JOIN fleets f ON r.fleet_id = f.id
WHERE f.archetype = 'swing' AND r.status = 'running';

-- overnight-cap reduces, last 3 days
SELECT ts, run_id, event_type, LEFT(payload_json, 200)
FROM run_events
WHERE ts >= "2026-08-09T00:00:00Z"
  AND payload_json LIKE '%overnight-cap%' ORDER BY ts;
```

## 3. Per-cycle checks — CRYPTO short block

Unchanged from the main handoff, plus the manipulation defense (#374, #380):

1. **Detector events** — `manipulation.py` verdicts on small-caps; the three
   skills (`pump-ignition-veto`, `stop-hunt-discipline`,
   `manipulated-book-hygiene`) should appear in decision prompts for crypto
   runs; hot-issue triggers fire on ignition shapes.
2. **Mode coverage** — all three automation modes carry the defense: thesis
   prompt `manipulation_shape` (Full Auto), planner `_screen_manipulated`
   (Simple), run-create `manipulation_advisory` (Agent 1-symbol). A mode
   whose events never show any of the three has regressed.
3. **Vol-parity + directional brake** — slot funding scales by realized vol;
   ≤ ceil(n/3) same-direction adds. Watch for the brake blocking a genuinely
   diversifying add (report, don't tune on n=1).

## 4. Gateway routing — both blocks (pre-live trio)

Once the owner connects real gateways, every cycle verify routing honesty:

- `broker_accounts`: multiple active rows are LEGAL (connect deactivates
  same-broker only). Alpaca/IBKR carry us-stock; the 8 crypto venues carry
  crypto; anything else supports nothing (fail-closed).
- An order whose market no active broker supports must land on the **paper
  ledger** — check `broker` on the execution record. A crypto order filled
  via Alpaca (or vice versa) is a SEV-1 mis-route: stop-the-line fix.
- A `live` rule for market M with no M-capable gateway must refuse with
  `NOT_CONFIGURED` — surfaced to the user, never silently simulated.

## 5. FIX loop — what counts as evidence

The main handoff's rules bind: reproduced evidence (never n=1), AI-first
(design the fix as a skill/prompt lesson the desk acts on; platform gates
only where the desk cannot be the actor), full ship pipeline to prod,
verify ≥2× live. Swing-specific calibration:

- **Time constant is DAYS, not cycles.** A swing run sees ~2 decisions per
  session. "2+ cycles before judging" for the short block ≈ 1 hour; for
  swing it is ≈ 1–2 trading days. Do not tune swing skills on a single
  session's tape.
- **A gap loss is not a defect.** The block prices gap risk via G; a stop
  gapped through at the open is the designed cost. The defect shapes are:
  gap losses exceeding their §7 share, sizing that ignored G, or a stop
  raised overnight (dormancy regression).
- **Judge by the SHAPE** (win/loss distribution, give-back, full-dump
  share), never by any single trade — owner rule: "We can not fix 100%."

## 6. EXTEND gates — nothing scales without clearing these

The §7 promotion pipeline (docs/plan/23) is the only path. Report progress
at every checkpoint; the DECISION is the owner's.

| stage | gate (Plan 23 §7, verbatim numbers) |
|---|---|
| paper trial | minimum to a decision: **60 closed trades AND two full earnings seasons (~6 months), whichever is later**. Kill checkpoints at 30/60/90 closed trades (no continuous peeking): kill if Wilson 90% UPPER bound of hit rate < 0.50, or cumulative net expectancy negative beyond fee noise at 90% confidence, or paper DD > 20% |
| promotion (ALL required) | bootstrap LB90 of per-trade net expectancy > 0 · Wilson LB90 of hit rate > 0.50 **or** PF ≥ 1.3 with bootstrap 10th pct ≥ 1.0 · paper max DD < 15% · **worst single overnight-gap loss < 5%** |
| probation | 1 live slot, minimum size; full scaling waits for 150+ combined trades |
| timebox | **unconditional kill at 12 months** without promotion — negative-expectancy logic never ships (the garbage rule) |

Every checkpoint reports the full panel (n, hit rate + CI, expectancy, PF +
bootstrap, avg win/loss, max DD, worst gap loss, and setups-seen vs
setups-taken — the last detects fail-closed gates silently starving the
trial).

Extend candidates that WAIT for data (do not build early):

- `short_volume_ratio` / `putcall_oi_ratio` / `stocktwits_tilt` as research
  INPUTS — only after the recorded snapshots show a measurable relationship
  to next-day outcomes on our own tape. Recording ≠ using; Gate 0 already
  proved the generic PEAD edge does not clear fees (memory:
  plan23-swing-block-gate0).
- More swing slots / more fleets — only through the §7 table above.
- Paid positioning feeds — excluded until a gate is cleared (owner decision,
  Plan 23 v2).

## 7. State at creation (2026-08-12)

- Swing block SHIPPED through #388 (UI: 전략 유형 selector, 6 langs,
  Professional/Enterprise gate). Pre-live trio in flight on branch
  `worktree-manipulation-detection` (this PR).
- **No swing fleet exists yet.** The internal trial (fleet 30, agent 58,
  user 22) was fully stopped at the owner's order with ZERO positions ever
  opened, then **deleted entirely at the owner's order 2026-08-12** (full
  FK graph removed in one transaction: 160 run_events, 145 fleet_events,
  3 slots, 2 candidates, runs 1077/1078, fleet 30, subscription, agent 58,
  user 22 — verified zero orphans, owner account untouched). The owner
  also stopped their own fleet 29.
- Next expected event: the owner builds a swing fleet at user level via
  sooppiy.com. First session after that: run §2 checks, start the closed-
  trade counter for the §7 checkpoints, and note the fleet id HERE.

## 8. Live fleets (noted 2026-08-14, cycle loop restart)

The owner-built fleets arrived 2026-08-12/13. Monitoring covers THREE user
accounts (owner directive 2026-08-14): henry.j@eklotho.com (user 23),
yoojinbe@gmail.com (user 4), info@askkpop.com (user 5).

| fleet | user | agent | archetype | scope | slots | budget |
|---|---|---|---|---|---|---|
| **31** | info@askkpop (5) | 6 | **swing** | us-stock | 25 | $10k |
| **32** | yoojinbe (4) | 5 | short | crypto/futures/forex/us-stock | 10 | $100k |
| **33** | henry.j (23) | 59 | short | us-stock + forex | 6 | $100k |

Fleet 31 is THE swing block trial — §2 checks and the §7 closed-trade
counter apply to it. Owner directive 2026-08-14: do NOT actively monitor
us-stock runs outside NYSE session hours (13:30–20:00Z).
