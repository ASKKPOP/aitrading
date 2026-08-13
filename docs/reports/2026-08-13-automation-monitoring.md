# Automation monitoring — 2026-08-13 (overnight into the first full us-stock session)

Session context: seven deploys landed between 2026-08-12 20:30Z and 2026-08-13 06:11Z
(#393 #394 #396 #397 #400 #403 #404 #405). This note records the findings in
retrieval-ready form — each heading is one lesson the desk can recall.

## The finding — a "flat" brief while your own history says you traded is SUSPECT (SOL −$69.56)

Run 1099 held a losing SOL short and was told "Position: 0 units (flat)" for four
hours because a rounded-to-zero ghost row shadowed the real book. Believing it, the
desk re-opened its short six times — $9,189 stacked against a $1,580 budget — and the
max-loss rail flattened all six lots for −$69.56 realized. The platform defect is
fixed (one book per run, aggregated reads), but the desk-side lesson stands: when the
position brief reads flat while your own recent decisions say you sold or shorted,
treat the flat read as suspect and do NOT size a fresh entry as if starting clean.
Repeated identical entries on an unchanged thesis are adds, and adds into a losing
position must be earned by the position working — never by the book looking empty.

## us-stock: the open IS the trade — a plan acted on at the bell beats the same plan 30 minutes late

Most participants transact at the US open; the first 30 minutes carry the day's
highest volume and range, and gap continuations or fades resolve there at the best
liquidity of the session. The scheduler now fires every us-stock desk within a minute
of 13:30 UTC with the pre-open analysis already done. When holding a plan into the
open: act on it in the opening window rather than waiting for confirmation that
arrives after the move; when flat at the bell on a mover thesis, the first orderly
pullback that holds is the entry, taken on resumption — chasing the first vertical
minutes buys someone's exit.

## us-stock: read the 2-day mover footprint before any entry or exit (mom_2d_pct, volume_ratio)

Your thesis carries mom_2d_pct (the symbol's 2-day move) and volume_ratio (latest
volume vs its own normal) — the reason the symbol was selected. A large 2-day move
WITH elevated volume is an institutional footprint: size that cannot enter or exit in
one print, so the flow tends to continue across days — trade in its direction and do
not fade it by reflex. A large move on thin volume is a drift nobody funded: no
continuation bet. High volume with a NARROW range is absorption — direction undecided,
stand aside until the range breaks. Two consecutive outsized up-days mean the next
vertical push is late: wait for the pullback. If price falls back through the level
where the big volume appeared, the footprint failed — exit the idea, do not argue.

## us-stock and everywhere: a young position moving against you INSIDE the ordinary day is noise, not evidence

The book's largest measured losses are full exits made minutes after entry on moves
smaller than the symbol's ordinary daily range: KAITO was fully covered 30 minutes
after entry on a −0.9% wiggle for −$10.14 and the tape then went the thesis's way.
When the position is young and the adverse move is inside one ordinary day, a full
close realizes fees on a wiggle. If exiting anyway, state why a FULL close beats a
HALF reduce; when your component scores disagree with your headline confidence,
trust the scores. Holding through noise is not stubbornness when the thesis is
intact — dumping on noise is the measured leak.

## Holding against your own reading is the invalidation signal (ZEC −$5.55)

A short was held for three consecutive cycles while the desk's own report read
"technical buy, news 10 bullish vs 1 bearish" — the position bled to a forced retire.
When the technical signal and the news balance BOTH oppose the held side for two
cycles running, a silent hold is not an available action: reduce, or explicitly
re-underwrite the thesis with fresh evidence in the report. At three straight
contradicted cycles the platform reduces half by itself; being ahead of that rail is
the desk's job.

## Sleepy symbols lose by idling; movers earn their slot (GLD −$300/trade class)

Trend-blend picks with no short-term range (GLD, SLV-class names) burned twelve
30-minute cycles holding, idle-retired without a trade, and GLD's account history ran
−$300.66 per closed trade over seven trades before the expectancy gate blocked it.
A 30-minute desk needs symbols with real 2-day range: prefer the mover the selection
gave you, and when a symbol produces nothing but holds for a session, the slot is
better handed back early than defended out of habit.

## Scaled-out winners must CLOSE their tail, not halve it forever

Four correct "cover half" decisions on a winning short decayed the book to a $4.45
remainder that could never pay its own round trip, then consumed desk cycles
babysitting dust. When a reduce would leave a remainder below the manage-worthy
floor (about $25), take the full close — the compiler now enforces this, but the
desk deciding it first is always cleaner: bank the tail with the second-to-last
reduce instead of leaving a crumb.

## Fleet mechanics verified live this session (for the operator, not the desk)

Replenish now holds the defined slot count at all times (market clock never blocks a
build; only AI verdicts — fee, expectancy, swing-history, funding — leave a slot
empty). Research supply scales to fleet demand per market (cap 40). The us-stock
survivor pool widened from 4 to 24 theses in one batch and fleet 31 grew 2→16 slots
in a day; fleet 32 recycled its SOL slot within the hour of the max-loss stop. The
liquidation-defense daemon, orphan sweep (ghost cleanup verified: 1 deleted), young-
dump flag, contradiction rail, dust rail, and bell-aligned scheduling are all live
and journalled — measure them in run_events before tuning anything.

---

# Monitoring loop log (newest first)

## Cycle 1 DEPLOYED + VERIFIED 3× — #406 live (2026-08-13 07:39Z)

Merged `155e8572` (#406), deployed **`sooppiy-backend:20260813-day-block-trio`**
via scripts/deploy.sh (rollback: `20260813-rag-usstock-lessons`). Migrations
at 0050 head; all three static roots republished; health 200s.

**Verification (3 passes, all green):**
1. **In-image:** both containers on the new tag, 0 tracebacks;
   `due_run_ids` source carries the 2026-08-13 owner comment and no
   `240 if`; `_big_trader_line` renders from LIVE prod data (XOM 0.47 /
   MSFT 0.46 / TMO 0.53 short-volume, StockTwits tilts, put/call omitted
   while the feed serves NULL — null-honesty working); the tape clause is
   in the live `trader/us-stock` catalogue (39,187 of 48,000).
2. **Event rate:** fleet 31 repeat gate events **90 in the 27 min before
   deploy → 0 after**, while `fleet_events`/`run_events` MAX(ts) stay
   current (streams alive — the silence is the fix, not a dead loop).
3. **Shape:** exactly ONE re-gate pair at 07:27:53–58 (first attempt after
   the worker restart — the process-local memo starts empty, the fail-safe
   direction), then only ~60s `fleet_status` ticks. 10 ticks in 10 min.

**Watch next cycles:** first session decisions from 11:30Z (pre-open
shoulder) should show the `Big-trader tape` line in effect — judge desk
usage per the swing time-constant (days, not cycles); gate-event volume
should stay ~2 pairs/15 min max while the pool is exhausted; a new
research batch must break the memo immediately (fingerprint changes).

## 24-HOUR VERIFICATION SWEEP (15:37Z) — five fixes re-proven; the day's losing SHAPE named

**Fix re-proofs against the full day (all held):**
1. **Regate back-off (#406-era churn → #410 PR set):** hourly fleet-31
   gate events 240/hr for seven straight hours pre-deploy → **≤20/hr
   ever since** (92–96% cut, sustained 8 hours). PROVEN.
2. **putcall walk (#409):** batches 06/07/09Z were 0-for-56 non-null →
   11/13/15Z are **28/28 each**. PROVEN sustained.
3. **at_time anchor (#407):** all 10 us-stock composes since 11:33 carry
   anchored deadlines — SBUX 1154 built 12:36Z (closed) → at_time
   21:30Z = 13:30 open + 8h exactly. PROVEN across the day.
4. **Vary-on-refusal (#410):** cooldown rows written on both fleets'
   untraded retires; replacements varied (PFE/EURCHF/NZDUSD/INTC/NFLX —
   fresh names entering, ping-pong absent since deploy). PROVEN.
5. **Ordinary-day authoring (#411):** deployed 15:30 — NO verdict yet;
   next sweep measures authored stop_pct / typical move on new entries.

**Not a defect (investigated):** UBER 1134's two identical 0.654 sells
15s apart = the ARMED reduce (74.90) firing, then the position stop
(~74.84) collecting the remainder — two protective layers stacked at one
level, both correct. A desk-coordination nuance, not a malfunction.

**The 24h SHAPE (per closing leg, agents in scope):**
- **Agent 6 / fleet 31: 19 legs, win rate 53%, median win +0.13 vs
  median loss −0.55 — losers run ~4× winners. Worst-6 legs = 94% of all
  loss. Per-leg expectancy −0.21.** The banking mandate produces fast
  small wins (TMO's 5 partials, PFE at the bell) but loss-trims happen
  at ~4× the size — the desk reacts to profit faster than to pain. No
  whole-book desk dumps (the one full close was the SLV watcher-stop,
  #411's target). Biggest legs: SLV −1.82 (noise stop), JPM −1.35,
  ORCL −1.13 (mid-session chop trims).
- Agent 59 / fleet 33: 24 legs, 42% win rate, everything fee-scale
  (net −0.35); small caps behaving (CBRS +0.19 banked, SPCX stopped
  −0.33, QNT untraded).
- pnl_audit 08-13: ledger −145.82 platform-wide, DRIFT −13.88 = the
  known benign entry-fee class (25+ newborns) — agents 6/59 own only
  −9.16 / −0.74 of it; the rest is out-of-scope fleet 32.

**Adversarial notes:** (a) "disciplined trims" is TRUE but insufficient —
exit discipline alone did not buy positive expectancy; the losing shape
is now precisely the 4× win/loss size inversion. DO NOT stack a new
lesson yet: #411 just changed the stop layer mid-session — measure one
full session under it first, then judge whether a loss-tempo lesson is
still needed. (b) Tape citations 0/~95 is a WEAK usage signal (the
report field is one sentence); the pre-registered session-end decision
stands, but the better long-term measure is decision/tape correlation
over days. (c) Fleet 31 slid 16→14/25 as cooldowns bench refused
symbols — the intended tradeoff; universe supply remains the owner-level
constraint (unchanged since cycle 100).

**§7 promotion panel (fleet 31, day 2):** closed legs 19 · hit rate
52.6% (Wilson 90% ≈ 0.34–0.71, n far below the 30-leg checkpoint) ·
net realized −9.16 (0.09% of budget; DD trivial) · worst single
overnight-gap loss: none yet · setups-taken vs seen: gates refusing
negative-expectancy names as designed.

## Cycle 12 — choppy mid-session; four desk trims red (15:35Z)

Agent 6 −5.34 → **−9.16**: JPM −1.35, ORCL −1.13, XOM −0.55, IBM −0.37,
all desk `losing_close` trims (NO SL/TP watcher closes since #411's
deploy — the watcher class is quiet). Wins this window: CBRS +0.19
(fleet 33 small-cap banking!), AUDCHF +0.03. Agent 59 −0.74. Reading:
mid-session chop against mostly-long books; each leg small, no dumps —
the SHAPE verdict (per-leg expectancy, full-close share) belongs to the
24h sweep, not a 30-min window. No new ship candidate this cycle.
Post-#411 stop-authoring sample: none yet (deploy ~15:30; next decision
round lands after this note). Tape citations 0 (~95 decisions). Image
current, 0 TB, docs 200.

## Cycle 11b — #411 DEPLOYED + VERIFIED 3× (~15:3xZ)

Merged `c7b1bff0`, deployed **`20260813-ordinary-day-authoring`**
(rollback: `20260813-vary-on-refusal`). Verified: both containers on the
tag, 0 tracebacks; the line renders live from prod candles (SLV ±1.52%,
UBER ±1.90%, MSFT ±1.51%); wiring confirmed in BOTH prompt paths inside
the image. **Post-ship watch:** newly authored stops on us-stock day
runs should move toward ≥ ~1.0 ordinary day (or the desk should say why
tighter) — measure authored stop_pct / typical_daily_move on new entries
over the coming sessions; SL/TP-watcher full-closes on sub-0.6-od stops
should stop recurring.

## Cycle 11 — SL/TP watcher identified; §8(a) trigger met, fix in CI (14:39–15:1xZ, PR #411)

Busy half hour: 21 decisions / 14 trades / 1 armed_exit. Wins banked
AUDCHF +0.06, MSFT +0.50; trims/trailing-locks SPCX −0.34, ADBE −0.13,
MSFT −0.17 (fleet 33 small caps behaving — SPCX stopped small, QNT
still untraded). Agent 6 −5.34, agent 59 −0.91.

**Watch RESOLVED — the null-client_order_id full-book sell path is the
SL/TP WATCHER** (worker log: "SL/TP watcher closed position 340 (SLV
us-stock @ 58.355, stop_loss)"). It executes the desk's own AI-authored
entry stop at position level. Protection correct; the defect is
upstream: **stops authored inside routine noise** — SLV 0.84% vs 1.52%
ordinary day (0.55 od), UBER 0.94% vs 1.90% (0.50 od) — §8(a)'s exact
trigger, met at n=2, −5.35 combined = the largest recurring loss shape
on fleet 31.

**Fix (PR #411, §8(a)'s own prescription):** `_ordinary_day_line` states
the median daily move + the unit lesson in BOTH prompts at AUTHORING
time (the exit-size line only rendered after adverse drift). fail-before
5/5, unwire mutation caught, 4,061 green. Deploy on CI.

Tape citations: still 0 (~80 decisions). Session-end test stands.

## Cycle 10 — session flowing; #410 replacement-side proof complete (14:09Z)

27 decisions / 7 trades / 1 armed_exit in the half hour. Banking legs
small and disciplined: losing closes TMO −0.003, USDCHF −0.046, XOM
−0.60 — all trims, no dumps. Agent 6 −3.91, agent 59 −0.44.
**Vary-on-refusal fully proven:** after CVX/WMT cooled down, the
replacements built DIFFERENT symbols (fleet 31 → PFE 1156, fleet 33 →
EURCHF 1155). Watch closed on both sides (cooldown write + variation).
Tape citations: 0 of ~60 decisions today — the session-end zero test
(≈20:00Z cycle) decides the skill nudge. Watch note: a $5-notional TMO
sell leg — if reduce-remainders under the ~$25 manage-floor recur, the
dust-tail rule (#396 class) needs a look on the day block.

## Cycle 9 — first session under the full stack: bell-fire, first bank, #410 proven n=2 (13:38Z)

- **Bell-fire:** 20 decisions across both fleets within 9 min of the
  13:30Z open; 6 entries — fleet 31 bought PFE/SLV/ADBE/MSFT, fleet 33
  bought UBER.
- **First banked win of the day block:** PFE bought 26.31 at the bell,
  half sold 26.49 minutes later — agent 6 improved −4.54 → **−3.80**
  (+0.74 realized). Buy-the-open, bank-the-pop: the intended shape.
- **#410 vary-on-refusal PROVEN live, n=2, within minutes of deploy:**
  1117 CVX (fleet 31) desk-retired untraded 13:34:48 → cooldown row 65
  (until 08-14T01:35, source_run_id stamped); 1132 WMT (fleet 33) → row
  66. Behavioral watch CLOSED — replacements must now vary; verify the
  next builds pick different symbols.
- Tape citations: still 0 of ~34 decisions today, now including real
  entries. If the full session ends at 0, the next AI-first step is a
  small `follow-the-flow` clause asking the desk to CITE the tape when
  it bears on the action (cheap, makes usage observable) — evidence
  threshold met by a full-day zero, not before.
- Image current, 0 TB, docs 200, agent 59 −0.48.

## Cycle 8b — #410 DEPLOYED + VERIFIED (13:16Z, 14 min to the bell)

Merged `8680caa4`, deployed **`20260813-vary-on-refusal`** (rollback:
`20260813-putcall-walk`). Verified: both containers on the tag, 0
tracebacks, vary-on-refusal wired in the running worker, events flowing.
Behavioral proof pending tape: the NEXT untraded desk-retire must write a
`fleet_symbol_cooldowns` row and the replacement must carry a different
symbol — check next cycles (UBER/WMT/SBUX runs 1152/1153/1154 are the
likely candidates at their first session look).

## Cycle 8 — retire-churn found and fixed: vary-on-refusal (12:39–13:1xZ, PR #410)

Health: image current, 0 TB, docs 200, agents 6/59 realized unchanged.
Tape citations still 0 (counting continues).

**Found: same-symbol rebuild churn on refused theses.** UBER: desk
retired it UNTRADED as unexpressable ("invalidation level sits at the
current price"); replacement rebuilt UBER from the same thesis 20 seconds
later; the rebuild re-reached the identical verdict in 4 minutes — UBER
is on its 4th run (3 consecutive desk-retires), WMT on its 3rd, SBUX on
its 3rd. The desks are RIGHT; the platform re-asks the identical
question every ~30 min, burning builds + LLM calls. Cooldowns existed
for idle_retired / losing stop_event / synthetic_liquidation —
`desk_retired` was simply missing from the list.

**Fix (PR #410):** desk_retired with ZERO trade legs writes the
idle-class symbol cooldown (vary-on-refusal); `_ever_traded` fails
closed so a traded bank-out never benches its symbol. fail-before 2/2,
mutation (inverted gate) caught by both tests, 4,056 green. Deploy on CI.

## Cycle 7 — second shoulder round, no entries yet (12:08Z)

18 fleet-31 decisions on the 30-min clock; zero trades from fleet 31
(shoulder correctly queues entries to the session). Fleet 33: one forex
AUDCHF sell, agent 59 −0.45. **Tape-usage first sample: 0 of 18 decision
reports cite short-volume/put-call/flow language** — too early to call
(shoulder holds, short report field); keep sampling through the session
per the days-not-cycles rule. Image current, 0 TB, docs 200.

## Cycle 6 — shoulder wake-up: all three fixes proven on the live tape (11:38Z)

- **Shoulder works:** all 18 fleet-31 desks decided within ~9 min of the
  11:30Z shoulder. First reads are sane (SLV buy conf 0.54 w/ ~1.1% stop;
  T hold citing no viable 2:1 R:R).
- **#409 CLOSED-VERIFIED end-to-end:** the scheduled 11:12:54Z factor
  batch wrote non-NULL `putcall_oi_ratio` — recorder, not just probe.
  The tape line now carries all three fields into the session.
- **#407 anchor watch CLOSED-VERIFIED on live composes:** 1150 WMT
  (11:33Z, 72h) → at_time 08-16T13:30Z = next open + 72h; 1151 UBER
  (96h) → 08-17T13:30Z. ✅ 1145 SBUX (07:41Z, pre-fix) carries the old
  wall-clock 15:41Z — the documented one-more-early-retire class; it
  still gets 2h11m of session. Nuance noted, not a defect: an anchored
  deadline can LAND while closed (08-16 is a Sunday) — the retire then
  fires flat or queues its flatten to the open per §2.5.
- Image current, 0 tracebacks, agents 6/59 unchanged.

**Remaining watches:** desk USAGE of the tape once session decisions
carry reports (judge over days); fleet 33 small caps at the open;
pre-fix runs' early retires (expected, count them).

## Cycle 5 — quiet, pre-shoulder (2026-08-13 11:13Z)

Image `20260813-putcall-walk`, 0 tracebacks, docs 200, agents 6/59
unchanged (−4.54 / −0.41), gate pairs 4 since 11:00 (back-off holding),
no new composes. Shoulder opens 11:30Z — next cycle should show the
swing desks' first decisions with the full tape (short-volume + putcall
+ tilt) in their briefs.

## Cycle 4b — #409 DEPLOYED + VERIFIED 3× (2026-08-13 ~11:2xZ)

Merged `64fb6d70`, deployed **`sooppiy-backend:20260813-putcall-walk`**
(rollback: `20260813-open-time-deadline`). Verification: (1) both
containers on the tag, 0 tracebacks; (2) **live re-probe returns real
ratios where the whole day was None** — MSFT 0.894, XOM 0.4554,
JPM 0.9559; (3) walk source present in the running image. The next
6-hourly factor batch should write non-NULL `putcall_oi_ratio`, and the
Big-trader tape line then renders all three fields — confirm at the next
batch (~15:4xZ) and in the first session decisions.

## Cycle 4 — putcall root-caused and fixed (2026-08-13 10:39–11:0xZ)

Steady otherwise: image current, 0 tracebacks, docs 200, agent 6 −4.54 /
agent 59 −0.41 unchanged, back-off holding (2 gate pairs this window),
no new composes (anchor watch still open for the first us-stock build).

**putcall_oi_ratio dark → ROOT-CAUSED live and shipped (PR #409).** The
watch's trigger met (2+ consecutive dark batches). Traced in the prod
container: chain fetch fine (MSFT 105 calls / 96 puts) but **every front-
expiry contract carries openInterest 0** — the front rolled to a fresh
weekly (exp 08-14) and OCC publishes OI next morning, so the front-only
read is honestly-null ALL day while real positioning sits one expiry out.
Fix: walk to the first expiry with nonzero call OI (fetcher already takes
`expiry_epoch`; ≤3 extra fetches; still None when nothing published).
fail-before red, mutation (refetch-front) caught, 4,054 green. Merge +
deploy + live re-probe of MSFT pending CI.

## Cycle 3 — quiet pre-open cycle (2026-08-13 10:08Z)

Image `20260813-open-time-deadline`, 0 tracebacks, docs 200. Agent 6
realized unchanged (−4.54), agent 59 −0.41 — no new losses overnight
(market closed; only forex runs 1130/1143/1147 decided, small books).

- **Regate back-off holding:** fleet 31 gate pairs down to 3 in 29 min
  (was ~62) — slightly above the 1-per-15-min floor, consistent with the
  pool fingerprint changing on fresh research batches. Keep watching.
- **at_time anchor watch:** only compose since deploy is 1148 HYPEUSDT
  (crypto) → +48h wall, correct for 24/7. First us-stock compose still
  pending — check next cycles.
- **pnl_audit DRIFT −6.03 (3 flattens):** the known-benign entry-fee
  class — ~25 newborn runs built 08-12/13 carry entry-side fees the adapt
  stream never sees (main handoff #257 note). Not chased. Bulk of the
  day's red is fleet 32 (out of scope).
- **putcall_oi_ratio still dark** since 04:18Z. If the ~10:48Z batch is
  NULL again, trace `_fetch_yahoo_option_chain` from the prod container.

## Cycle 2 — scope extension + the night-notification defect (2026-08-13 ~09:00–10:00Z)

**Owner: add henry.j@eklotho.com for US stock → DONE.** Fleet 33 in scope
(baseline in §7a of the n-slot handoff); crons re-armed two-fleet
(`5d805817` 30-min, `92bfc187` sweep).

**Owner: "why working now (not market time)?" / "make clean this time" /
the 12:10 AM email — run 1128 CBRS.** Diagnosis: nothing traded and no AI
ran overnight (only market-closed pre-gate skips). The 24/7 safety scan
retired the run on `at_time` — a 6h thesis horizon stamped as WALL hours
at 01:09Z burned entirely against a shut NYSE; the slot then rebuilt the
same symbol (owner's own keep-N rule — correct). The "청산" wording was
boilerplate: $0 traded, no position.

**Race note (parallel sessions, same mandate):** this session built the
cumulative-open-hours fix (#408: 5 fail-before tests, mutation caught,
4,052 green) while the parallel session shipped #407 (anchor at_time to
the NEXT open) first — #408 CLOSED as superseded, rationale on the PR.
#407's anchor+wall semantics is the better read for multi-day thesis
horizons (48h ≈ 2 sessions, not 7+). This session deployed merged main as
**`20260813-open-time-deadline`** and verified live: both containers on
the tag, 0 tracebacks, `_horizon_anchor("us-stock")` → 13:30:00Z while
closed / crypto → now, compose wired. Residual WATCH (not shipped without
evidence): sub-session horizons composed near the close still anchor to
now — the ORCL/CAT class.

## Cycle 1 SHIP — owner confirmed all four asks (2026-08-13 ~07:3xZ)

Owner reply, verbatim intent: (1) "yes 30 min — change plan 23"; (2)
big-trader record-only "must be make solutions"; (3) replenish churn
"solving"; (4) "do R1 — build the day block following big traders."

**Shipped in one PR (branch `feat/day-block-big-trader`):**

1. **Cadence** — the dead `cap = 240` swing special-case removed from
   `due_run_ids` (it never slowed a run: compose stamps
   `interval_minutes: 30` per the owner's 08-12 spec and the cap is a
   ceiling — `min(240, 30) = 30` all along). Plan 23 §10.1 amended with a
   dated note. Session dormancy, overnight stop dormancy, G sizing,
   overnight cap, §7 gates all unchanged.
2. **`_big_trader_line`** (run_engine) — latest `us_stock_factor_snapshots`
   row rendered into BOTH decision prompts: FINRA short-volume ratio,
   put/call OI, StockTwits tilt. Null-honest (missing field omitted), 48h
   age cap (FINRA T+1 + weekend), us-stock only, fail-soft. Skill:
   level-read clause appended to `follow-the-flow` (#405) — teach only
   what the line shows, no deltas the desk cannot see. Wiring tests for
   both paths + mutation check (light-path unwire caught by exactly the
   wiring test).
3. **Regate back-off** (fleet_supervisor) — the per-slot
   `_LAST_EMPTY_ATTEMPT` 300s cooldown was WORKING; the churn was nine
   slots each re-asking the identical per-POOL question (9 × 72 expiries
   × 2 events ≈ the observed 1,342). New per-fleet memo keyed on
   (candidate-pool fingerprint, backtest-gate config), window
   `REPLACEMENT_REGATE_MIN` (default 15 min); an unchanged pool that gated
   to nothing is skipped silently; any pool or gate-config change regates
   immediately. ⚠️ First attempt broke `test_fleet_backfill` — the memo
   outlived a gate-config flip; fixed by putting gate config INTO the
   fingerprint. The existing cooldown discovery repeats the standing
   lesson: **verify a mechanism is absent before building it** — the gap
   was cross-slot dedupe, not a missing cooldown.

**Verification:** fail-before 3 groups (cadence flip, 8 big-trader tests,
5 back-off tests) all red on unmodified code → **4,047 passed / 0 failed**
full suite after; ruff F401/F811/F821/F841 clean; skills budget test green
(MAX_BLOCK_LEN 48000); mutation check 1/1. Deploy + 3× live verification
tracked below when the PR lands.

---

## Cycle 1 (new loop) — 2026-08-13 05:46Z

**Loop restart under a new owner mandate (2026-08-13, verbatim intent):**
monitoring is for **user info@askkpop.com** (user 5, agent 6); analyze
each run on /automation — (1) working per plan? (2) losses/profits and WHY,
checking/modifying the RUN AI reading algorithm; (3) what we missed; (4)
how-it-works + plan-16 docs healthy; (5) suggestions + strong
recommendations, then solve directly. Cadence **every 30 min, 6AM–7PM**
(interpreted as **US Eastern** — the US-stock trading day; a KST reading
would put every cycle outside the session with nothing new to report.
Stated to the owner; adjust on their word). Additionally: *"make plan: US
stock day trading, buy/sell each 30 min, MUST follow big traders — it's
key"* → recommendation R1 below.

**State anchor:** DB NOW 2026-08-13 05:46:16Z · image
`sooppiy-backend:20260813-lot-blindness` · worker tracebacks (12h): 0 ·
main = `85e2d3fd` (#404).

### The monitored fleet exists — fleet 31 (the event §7 of the n-slot handoff was waiting for)

- **Fleet 31**, agent 6 (info@askkpop.com), archetype **swing**, us-stock
  only, target 25 slots, **replenishing:16/25**, budget $10,001.51 (seed
  10,000). Built by the owner at user level 2026-08-12 ~15:13Z. Also live
  but OUT OF SCOPE: fleet 32 (agent 5 = user 4 yoojinbe) and fleet 33
  (agent 59 = user 23).
- **P&L attribution matters:** `pnl_audit` shows 08-12 −23.53 / 08-13 (to
  05:46Z) −72.98 platform-wide, but **agent 6's share is only −4.54**
  (fleet 31 −3.81 + fleet 29 remnants −0.73). The −91.85 sits on agent 5
  (fleet 32, futures/forex/crypto) — different user, not this loop's scope.

### (1) Working per plan — mostly YES

- **All 16 running swing runs correctly stamped**: `archetype: "swing"`,
  `swing_g_frac` 0.031–0.099 (all ≥ 0.03 floor), `analysis_window`
  pre 120 / post 120 min. Session dormancy WORKS — zero decision cycles
  overnight (last decisions ~21:46–22:00Z, none since; §2.5 satisfied
  in the dormancy direction).
- **Run 1095 TMO is the exemplar**: buy 0.167 @ 601.15, then five banked
  partial wins (+0.04/+0.14/+0.11/+0.12/+0.07 = **+0.46 realized**), and
  the **first armed_exit fire on a us-stock symbol** — `price_above 603 →
  reduce 0.5`, executed, slippage **+0.0174%** (`run:1095:arm:10`,
  19:29:46Z). Buy-bank-arm is exactly the intended shape.
- **Rails fired small and correctly**: 1091/1092/1093/1096 died to
  `stop_event:trailing_lock` at −0.21/−0.13/−0.33/−0.04 — trims, not dumps.
- **Fees are percentage-scale** (e.g. 0.005 on a $100 fill) — the flat-fee
  hurdle that killed early fleets does not apply here.
- **Docs healthy**: /docs/how-it-works 200, plan-16 HTML 200, /automation
  200.

### (2) The losses and why

- **1081 UBER −3.53 (78% of fleet-31 red).** Cycle-8 buy 4.78 @ 77.81
  (conf 0.73, `hot_issue` trigger), then a **full-book sell 12 minutes
  later** @ 77.07 (−0.94%) with `client_order_id: null` — a stop-path
  execution, not a desk cycle. Desk retired the run 2h later at conf 0.53.
  The known killer shape (full dump on a sub-1% move) at small scale.
  **WATCH: identify the null-client_order_id sell path** (risk watcher /
  stop executor) and whether the authored stop sat inside ordinary range
  (§8(a) of the main handoff — judge in ordinary days).
- Everything else red is fee-scale dust (−0.01…−0.33).

### (3) What we missed — defects found this cycle

1. **Swing cadence never actually slowed: `interval_minutes: 30` is
   stamped at compose, and the 240 in `due_run_ids` is only a CEILING**
   (`interval_min = min(cap, cfg.interval_minutes)`). So the "240-min
   swing clock" (plan 23 Phase B) never engages — runs think every ~26–30
   min. n=16, structural, reproduced in code + tape (1095: 15 decisions in
   6.5h). ⚠️ This coincidentally MATCHES the owner's new day-trade ask, so
   the FIX IS A DECISION, not a patch: either compose stamps 240 for swing,
   or the owner blesses 30-min thinking as a distinct **day archetype**
   (R1). Do not silently change either way.
2. **"Follow big traders" is record-only.** `us_stock_factor_snapshots`
   is fresh (6-hourly; FINRA `short_volume_ratio` + `stocktwits_tilt`
   populated; `putcall_oi_ratio` intermittently NULL — last non-null
   04:18Z, watch the feed) — but **grep proves 0 references in
   `run_engine` or `fleet_planner`**. The desk cannot see the one signal
   the owner calls key. → R1.
3. **Replenish churn against an exhausted pool**: 671 `swing_gate` + 671
   `backtest_gate` + 333 `fleet_status` events in <6h for fleet 31 alone —
   ~9 empty slots retried every ~60s tick, re-dropping the same candidates
   (QNT/CBRS/SPCX `swing_history_thin`; NVDA −200.50, MRK −292.03 per
   trade). Universe starvation (the cycle-100 class) now with event-table
   bloat attached (~5k rows/day/fleet). Fix candidate (needs nothing from
   the desk): back off replacement attempts while the candidate set is
   unchanged, and/or don't attempt us-stock builds while the session is
   closed. Evidence: reproduced 1,342×.
4. **Orphan positions held**: agent 6 carries run-less CRM (~$124) +
   USDKRW dust ×2; `OrphanReclaim` sees them (`held: 3`) and holds by
   design. Dead capital against a $10k book — watch, don't force.

### (5) Recommendations

- **R1 (STRONG, the owner's own ask): a US-stock DAY block that follows
  big traders.** Make the accidental 30-min cadence intentional: a `day`
  archetype (30-min think clock, flat-or-reduced into the close, no
  overnight G pricing), and AI-first wiring of the big-trader tape the
  platform already records — a brief line (FINRA short-volume tilt,
  put/call OI, unusual volume) + a skill clause teaching the desk to trade
  WITH institutional flow and never against a heavy short-volume tape.
  Perception first, then measure on our own tape per §6 gates.
- **R2:** replenish back-off (defect 3) — pure platform hygiene.
- **R3:** keep the §7 promotion counters running from fleet 31's tape
  (closed legs to date: ~9 fleet-31 closes; panel starts accumulating).

**Actions this cycle:** cycle note + n-slot handoff §7 updated; loop
crons armed (30-min 6AM–7PM ET + daily sweep); no code shipped (both fix
candidates need either owner decision (cadence) or a quiet-hours window
(churn back-off) — R2 queued for evidence-complete ship next cycles).
