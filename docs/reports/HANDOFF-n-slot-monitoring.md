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
| cadence | 30-min cap (`RUN_INTERVAL_CAP_MIN`) | **30-min analysis** through open−2h→close+2h shoulders; dormant outside (owner spec 2026-08-12; was 240-min) |
| order policy | per cycle | **session-only fills · entries ≥60 min apart · exits exempt** (`entry_spacing_minutes` / `analysis_window` snapshot stamps) |
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
3. **Cadence** (owner spec 2026-08-12 — supersedes the 240-min contract) —
   swing runs analyze on a 30-min clock from 2h before the open to 2h after
   the close, and are DORMANT outside that window: zero cycles overnight and
   on weekends (not even `market closed` skips — `due_run_ids` never
   dispatches them). ORDER legs are the rail to watch, not cycle spacing:
   entry signals (`side` buy/short) on one run must sit ≥60 min apart, every
   fill must land inside the NYSE session, and `order_policy` gate_skips
   ("analysis shoulder — orders resume at the open", "entry spacing") are
   the proof the rails engaged. Exits are exempt from spacing by design.
   A swing run cycling at 30-min WITHOUT these stamps in its snapshot
   (`entry_spacing_minutes`, `analysis_window`) predates the change —
   composed before deploy — and still trades under the old 240 contract.
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

## 7e. 🔒 OWNER RULES (2026-08-13) — TWO-SUBAGENT MONITORING + THE OUTCOME LAW

Owner, verbatim:

> "Do not make excuses, do not delude yourself into thinking your
> analysis is always correct, and do not justify losses with flawed
> logic; instead, always analyze the reasons behind the outcome of every
> trade. The ultimate goal of all analysis is profit or loss; conduct
> your analysis with that in mind."

Origin: the same day, a −169.54 running loss was reported as "improved"
on a +0.21 delta — the exact self-delusion the law forbids. Binding
procedure for every cycle/sweep with tape to analyze:

1. Dispatch **TWO subagents in parallel**: **Agent A** — every
   AI-authored trade outcome (desk cycles, panel finals, armed exits)
   with the REASON behind each result; **Agent B** — every
   algorithm-authored outcome (SL/TP, locks, max_loss, at_time,
   adapt-retire, flattens, sizing/selection) the same way. A description
   without a reason is not analysis; an excuse is not a reason.
2. The main session **fully cross-checks** both reports against the law:
   reject findings that excuse a loss, assume their own correctness, or
   lack a per-trade reason. Where A and B disagree, chase it — the
   disagreement is the finding.
3. Verdicts in PROFIT-OR-LOSS terms first; process health second. A
   small favorable delta on a large loss is NOT improvement and must
   never be reported as one.

## 7d. ⚠️ ACTIVE: GitHub Actions BILLING BLOCK (since 2026-08-13 22:53Z)

Every CI job dies in ~4s with zero steps: "recent account payments have
failed or your spending limit needs to be increased." OWNER-ONLY fix
(GitHub Billing & plans). Until cleared: run full local CI equivalents
and confirm this signature before any merge (global CI-outage rule).
Also OPEN owner action: Settings-page AI for users 4 (yoojinbe) and 23
(henry.j) — without it their panels are rule-fallbacks and the #414
guard keeps their orders on light-tier AI verdicts only.

## 7c. 🔍 DEEP MONITORING — TWO AXES (owner 2026-08-13 ~22:20Z)

Owner: *"deep monitoring 1. Sooppiy AI agent clear for make plus profit,
2. other algorithm."* Every sweep (and any cycle with enough tape)
attributes P&L to its AUTHOR:

- **AXIS 1 — the AI's own decisions:** desk-cycle exits
  (winning/losing_close adapts), panel-authored orders
  (order_discussion finals), armed exits (the AI's standing orders).
  The question: is the AI's judgment net-positive ON ITS OWN?
- **AXIS 2 — every other algorithm, each on its own line:** SL/TP
  watcher, trailing/breakeven locks, max_loss floors, at_time retires,
  adapt-retire ladder, overnight cap, sizing/selection (research
  ranking, backtest gate). ⚠️ Honesty rule: a flatten COLLECTS what the
  book accumulated under holding — attribute the collector and the
  accumulator separately before blaming either.

**Baseline attribution (since 08-12, first pass 2026-08-13 22:20Z):**

| fleet | AXIS-1 desk exits (legs) | AXIS-2 flattens (legs) | reading |
|---|---|---|---|
| 33 | **+8.27** (41) | −0.70 (5) | AI clearly plus-profit — the model case |
| 31 | −5.84 (38) | −0.84 (7) | AI exits slightly red (chop-trim day 1); #411/#413 target exactly this — re-measure over sessions |
| 32 | −35.32 (103) | **−124.99** (13) | both axes red PRE-fixes; tail = adapt_retired −83.37 + max_loss −69.56 (the #404 ghost-book). Watch whether the new architecture bends it |

Panel night-1: 8 discussions, 2 confirmed-stronger, 6 reversed-to-hold.
Count reversals per session; panel-starvation is an owner conversation
with numbers.

## 7b. 🔒 OWNER RULE (2026-08-13, STRONG, all trading orders) — THE AI IS THE FINAL AUTHOR

Owner, verbatim intent across five messages: *"Must be final discussion
for contract or order by sooppiy AI — NOT any programming logic. It's
strong rules for all trading order. Must be full scan full analysis; if
we have order by programming, we must be change to Sooppiy AI. By AI it
is main; programming decision is optional."*

Shipped in response (PR #412):

1. **Order discussion** (`run_engine._order_discussion`): every
   order-producing proposal from the cheap tier (buy/sell/retire-with-
   book) convenes the full 4-analyst + trader discussion, whose decision
   REPLACES the proposal wholesale — no code arbitration. Holds convene
   nothing. Fail-open on panel infra errors. Env `ORDER_DISCUSSION`
   (default on).
2. **Stop-hit routing** (`stop_router.py` + risk_engine + run_engine):
   a stop/target HIT on a live FLEET run convenes an immediate emergency
   discussion (due-now dispatch, forced full route, STOP HIT brief line)
   instead of the watcher's auto-close; the watcher closes ONLY as the
   fail-safe (`STOP_DESK_TIMEOUT_S` 180s, desk silent) — "AI main,
   programming optional" literally. A desk ruling suppresses
   re-litigation for `STOP_RENOTE_MIN` (30). **Manual users' SL/TP is a
   promise and executes exactly as before — fleet runs only.**

Still programmatic BY DESIGN (each executes a decision the AI itself
authored earlier, or is owner-approved safety): armed exits, trailing/
breakeven locks, max_loss floors, at_time retires, overnight cap,
liquidation defense, fleet breakers. Next conversions (one at a time,
each live-verified before the next): trailing/breakeven fire → desk
ruling; at_time expiry → desk ruling. Do NOT convert in bulk.

**Per-cycle watches for this rule:** `order_discussion` events (proposed
vs final — count reversals; the panel changing verdicts is the feature
working); `stop_hit` route triggers + whether desk rulings beat the
180s fail-safe (log line "SL/TP hit routed to desk" vs "TIMED OUT");
LLM spend per day (panel calls ≈ order-producing cycles + stop hits —
if it explodes, tell the owner before tuning anything).

## 7a. ▶️ THE FLEET EXISTS — fleet 31, loop LIVE (2026-08-13 05:46Z)

- **SCOPE = THREE USERS (owner 2026-08-13 ~22:10Z), each with a focus
  market:** yoojinbe@gmail.com (user 4, agent 5, fleet 32 — **CRYPTO**),
  info@askkpop.com (user 5, agent 6, fleet 31 — **US STOCK**),
  henry.j@eklotho.com (user 23, agent 59, fleet 33 — **CRYPTO + FOREX**).
  Fleet 32 baseline at entry into scope: 10 slots ~$100k, archetype
  short, market scope NULL (trades all markets: 5 futures / 2 crypto /
  2 us-stock / 1 forex at baseline), **realized since 08-12: −169.75**,
  worst legs SOLUSDT −69.56 (the #404 ghost-book incident, platform side
  fixed), SPCX −35.98, KAITOUSDT −22.71 — its crypto slots are where the
  catastrophic tail lived; that is the focus. Open book modest (~$3.6k,
  slightly green). Note: focus labels are the OWNER'S watch priorities,
  not the fleets' scopes — report per focus market but never ignore the
  rest of a fleet's book.
- **SCOPE EXTENDED (owner 2026-08-13): henry.j@eklotho.com (user 23,
  agent 59, fleet 33) is monitored for US STOCK.** Fleet 33: archetype
  `short`, scope ["us-stock","forex"], 10 slots, budget ~$100k, profit
  target 10%. Its us-stock runs cycle on the 30-min clock and skip with
  `gate_skip: market closed` overnight (cheap pre-gate skips, no LLM
  spend — by design; the short archetype has no `analysis_window`
  zero-dispatch dormancy). ⚠️ Standing watch: it trades the THIN-HISTORY
  small caps the swing gate refuses (QNT 48 bars, CBRS 62, SPCX 42) —
  `swing_symbol_check` is swing-only and manipulation.py is crypto-only,
  so no small-cap screen covers us-stock shorts. Judge by tape evidence
  before proposing any gate.
- **WATCH (from #407/#408, 2026-08-13):** `at_time` now anchors to the
  next open (#407, deployed `20260813-open-time-deadline`) — new composes
  while closed must show at_time ≥ next open + horizon. Residual shape:
  a SUB-SESSION horizon composed near the close anchors to now and can
  still burn its life overnight (the ORCL/CAT class). If reproduced, the
  increment is open-time counting for sub-session horizons only (#408,
  closed superseded, has the tested walk to start from).
- **Fleet 31 = the owner-built swing fleet for info@askkpop.com** (user 5,
  agent 6): us-stock only, target 25 slots, budget/seed $10,000, built
  2026-08-12 ~15:13Z. This is the fleet this playbook governs. Fleets 32
  (user 4) and 33 (user 23) are other users — out of monitoring scope.
- **New owner mandate (2026-08-13):** cycle every **30 min, 6AM–7PM**
  (read as US Eastern — the us-stock session; KST would put every cycle
  in the dormant window). Per cycle: working-per-plan / losses+why (check
  the RUN AI reading algorithm) / what we missed / docs health
  (how-it-works + plan-16) / suggestions, then solve directly. Plus a
  standing feature ask: **a US-stock DAY block, buy/sell each 30 min,
  that FOLLOWS BIG TRADERS ("it's key")** — see R1 in the 08-13 cycle
  note before designing anything.
- **Findings from 2026-08-13 cycle 1 — ALL FOUR OWNER-CONFIRMED and
  shipped the same day (read the 08-13 cycle note for the evidence):**
  (1) cadence — owner: "yes 30 min, change plan 23" ⇒ the dead
  `cap = 240` swing special-case in `due_run_ids` is REMOVED (it never
  slowed a run; compose stamps `interval_minutes: 30` per the 08-12 spec)
  and plan 23 §10.1 carries the amendment. (2) big-trader factors were
  RECORD-ONLY (0 refs in the decision layer) ⇒ `_big_trader_line` now
  renders FINRA short-volume / put-call OI / StockTwits tilt (null-honest,
  48h age cap, us-stock only) into BOTH prompts, with the level-read
  clause added to `follow-the-flow`; wiring tests per the standing rule.
  (3) replenish churn (~1,342 repeat gate events <6h = 9 slots × 300s
  cooldown expiries × 2) ⇒ per-fleet regate memo keyed on
  (pool fingerprint, gate config), window `REPLACEMENT_REGATE_MIN`
  (default 15 min) — complements the per-slot `_LAST_EMPTY_ATTEMPT`
  cooldown, which was working as designed. (4) run-less CRM/USDKRW
  positions on agent 6 are HELD by OrphanReclaim by design — watch. Also:
  `run_events`/`fleet_events` payload column is **`payload`** — the
  `payload_json` in §2's SQL is STALE; errors are silent under 2>/dev/null.
- First tape: fleet-31 realized −3.81 (UBER −3.53 = one stop-path
  full-book sell on a −0.94% move, `client_order_id: null` — identify
  that path). TMO +0.46 with 5 banked partials and the **first us-stock
  `armed_exit` fire** (slippage +0.0174%). Trailing-lock deaths all
  ≤ −0.33. §7 promotion counters started (~9 closed legs).

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
