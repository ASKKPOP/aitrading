# 2026-08-07 — automation monitoring (newest first)

Ground state: owner reset the balance to **1000** and cleared all history at
2026-08-06 ~22:56Z. Fleet 28 rebuilt from scratch. This is day 1 of the new book.

---

## Cycle — 08:45Z · the arm/excursion ratio has a domain of validity

**Book:** equity **1001.6647**, profit **+1.6647 (+0.1665%)** — session high.
Realized +1.2876, unrealized +0.3770. **9/10 runs** (one retired), all on-slot,
9/9 distinct minutes. Nothing below −0.99.

### ⚠️ SECOND CORRECTION — the flaw is my metric, not the desk

983 did author a third post-clause arm (04:41 -> 05:11 -> 07:42, now 10.5x).
But **994 USDKRW is also at 10.3x**, so it is not one rogue run. What actually
separates them:

    990 ZW       exc 2.219%   arm 0.20%    0.1x    large excursion -> tight arm
    991 GC       exc 1.528%   arm 0.05%    0.0x    large excursion -> tight arm
    983 ETHUSDT  exc 0.219%   arm 2.30%   10.5x    tiny excursion  -> far arm
    994 USDKRW   exc 0.066%   arm 0.68%   10.3x    tiny excursion  -> far arm

**The ratio is large exactly where the excursion is tiny.** 994 is 1.5 hours
old; its excursion is small BY CONSTRUCTION. Anchoring its arm to 0.066% would
put the level essentially at the current price, firing on the first tick of
noise. Its actual arm sits at 0.68% — above the noise floor, below a normal
daily move. That is defensible.

**So the arm/excursion ratio has a domain of validity.** It was the right lens
for the original finding — 984, a mature position, 2.60% arm against a 0.208%
excursion, on a tape that had been running for hours. It is the WRONG lens for
a young or quiet position, and I have now over-applied it twice: once at 04:15
(claiming the clause landed on a favourable snapshot) and once at 08:15
(naming 983 a persistent outlier when the same number appears on a
1.5-hour-old run).

**Not shipped, and the clause is NOT being rewritten on this.** The right
response is to fix the MEASUREMENT: only judge arm distance by this ratio when
the excursion is large enough to be a real anchor — a sensible floor is a few
multiples of the round-trip cost, since below that the tape has not yet
expressed a range at all.

**Rule for the next session:** before calling an arm "far", check the
excursion's ABSOLUTE size and the run's age. A 10x ratio on a 0.066% excursion
says nothing.

### Correcting the 08:15 entry

The previous entry named 983 as a run-specific pattern. That reading does not
survive 994 showing the same number for the same structural reason. 983 may
still be quiet-tape rather than misjudging.

---

## Cycle — 08:15Z · correcting my own 04:15 claim about the arm clause

**Book:** equity **1001.6006**, profit **+1.6006 (+0.1601%)**. Realized
**+1.2876**, unrealized +0.3130. Fleet 10/10, **all on-slot, 10/10 distinct
minutes**. Nothing below −0.99.

### ⚠️ CORRECTION: "4 of 4 post-clause arms are reachable" was a snapshot

At 04:15Z I reported that every arm authored after the far-arm clause sat at
0.25-0.93%. With more samples that is **not the settled record**:

    983 ETHUSDT  arm 2.52%  exc 0.219%   11.5x   armed 07:42:10  post-clause
    990 ZW       arm 0.35%  exc 2.145%    0.2x   armed 05:30:57  post-clause
    991 GC       arm 0.57%  exc 1.417%    0.4x   armed 07:07:44  post-clause
    987 SOLUSDT  arm 0.47%  exc 0.000%     n/a   armed 08:10:12  post-clause

Three tight, **one far** — and it is the SAME run every time. 983 was at 14.9x
at 02:41 and 13-17x before that; it has now authored an 11.5x arm nearly five
hours after the clause went live.

**The third case does not excuse it.** 983's excursion is 0.219%, which is
**5.8x the measured round-trip fee (0.0382%)**, so "the range is below your
cost" does not apply. The main instruction applies and this run is not
following it.

**Not shipped.** One run out of ten, and arm placement is the desk's judgment,
not a platform rail. Recording it as a named watch item with numbers: if 983
authors a third far arm while the rest of the fleet arms tight, that is a
run-specific pattern worth understanding rather than a clause to rewrite.

**Lesson for me:** I measured at a moment when the sample happened to agree,
and stated it as a result. The correct claim at 04:15 was "4 arms so far, all
tight" — not "the clause landed".

### Minor observation

991 GC armed `close/1.0` — a whole-book arm — where the exit skill makes
`reduce` the default verb. Defensible for a target-reaching arm; noted, not
challenged.

---

## Cycle — 08:00Z · daily duty: the day is POSITIVE, and the shape is right

**Book:** equity **1001.6215**, profit **+1.6215 (+0.1622%)**. Realized
**+1.2897**, unrealized +0.3317. Fleet 10/10, **all on-slot, 10/10 distinct
minutes**. Nothing below −0.99.

### Daily duty — there is no minus-profit day to solve

2026-08-07 (UTC) closes the monitored stretch **positive**. But the owner's
standing instruction is to target the SHAPE, not the absence of losses, so:

| | count | total |
|---|---|---|
| winners | 5 | **+1.5183** |
| losers | 8 | **−0.2288** |

**38% win rate by count; 6.6:1 by magnitude.**

    largest win   981 SI       +0.7230
    largest loss  986 USDKRW   −0.0922      ratio 7.8:1

    winners: 981 SI +0.7230, 984 HG +0.2957, 985 ZC +0.2553,
             991 GC +0.2268, 990 ZW +0.0175
    losers:  986 −0.0922, 987 −0.0651, 983 −0.0355, 992 −0.0166,
             980 −0.0085, 982 −0.0057, 993 −0.0030, 994 −0.0022

**This is the shape the work was aimed at.** The baseline finding was *"6 of 84
closes accounted for 74% of all loss, and every one dumped 100% of book on a
sub-2% move"*. Today the worst single loss is **nine cents** and **no run has
dumped its book**. Losses are small and frequent; wins are large and
concentrated — which is the correct arrangement, not an accident of a quiet
tape.

Caveat worth keeping: one session, thirteen closed-or-open runs, on a book
seeded eight hours ago. The shape is right; the sample is not yet a claim about
edge.

### Nothing shipped

Fourth cycle in a row with no reproduced defect.

---

## Cycle — 07:45Z · stagger verified at full fleet size; three audits clean

**Book:** equity **1001.5940**, profit **+1.5940 (+0.1594%)**. Realized
**+1.2891**, unrealized +0.3048. Nothing below −0.99.

### The newborns separated exactly as predicted

    992 HYPEUSDT  07:14:52   slot :14   on-slot
    993 ZECUSDT   07:21:11   slot :21   on-slot
    994 USDKRW    07:28:16   slot :28   on-slot

**All 10 runs on-slot; distinct cycle-minutes 10/10.** This is the first test of
the stagger at FULL fleet size — it was designed and verified at 6-8 runs. Ten
runs, ten distinct slots, no collisions.

### Three audits, all clean

**pnl_audit** — ok both days; ledger validated **71/71** against the platform's
own stored `realized_pnl_usd`. The −0.11 delta on 2 flattens is the known
`adapt realized` flatten omission, in tolerance.

**ratchet_audit** — 3 in-band reduces on run 990 ZW, **all post-fix, all
survived, 0 flattened**. The shape is worth noting: **0.0270 -> 0.0135 ->
0.0068**, halving each time — the same scale-out pattern that produced 985's
best-on-book 91% retention. A second run has now found it independently.

**fill_audit** — only the single ZC flag already investigated and cleared at
03:45Z (the mark demonstrably moved between the two fills). No new flags.

### Nothing shipped

Deployed only to sync five cycles of notes into the corpus — monitoring chunks
had been stuck at 478 since the cryptobreadth deploy, and the read-obligation
starts 2026-08-08.

---

## Cycle — 07:05Z · full fleet trading; newborns share their first tick as designed

**Book:** equity **1001.5916**, profit **+1.5916 (+0.1592%)**. Realized
**+1.2785**, unrealized +0.3130. Slightly below the 07:00 reading because the
three new runs opened positions and took small initial marks (992 −0.0166,
993 −0.0110) — normal, not a leak. Nothing below −0.99.

### Cadence at 10 runs

**Distinct slots 10/10** — offsets 0, 4, 7, 9, 11, 14, 18, 21, 27, 28. But
**distinct cycle-minutes 8/10**, because 992/993/994 all cycled at
**06:59:34**, the same second.

That is the documented first-cycle behaviour, and I checked `cycle_seq` before
flagging it: **all three are `seq=1`**. A run with no `last_cycle_at` fires
immediately, and these three were created together. They separate from their
second cycle — 992 at :14, 993 at :21, 994 at :28.

(My own slot-check heuristic flagged 992/993 as "OFF-SLOT?" and passed 994 —
purely because :59 happens to sit within two minutes of 994's :58. The
heuristic is fine for steady state and useless on a first cycle.)

### The new runs are working

    992 HYPEUSDT  buy  — stop 1.3% below entry, target 2.6% above   (2:1)
    993 ZECUSDT   buy  — stop 1.9% at the prior trough, target 4%   (2:1)
    994 USDKRW    hold — "thesis weakens amid continued downtrend, so we stay flat"

Both entries carry proper 2:1 brackets anchored to structure rather than round
numbers. **994 declined to enter at all** — the desk overriding a candidate the
planner had just handed it, which is the division of labour working.

### Nothing shipped

Deliberately did not deploy: nothing to ship, and a restart would reset the
research timer (see 06:25Z), pulling bucket 496135 forward for no benefit while
the fleet is already full.

---

## Cycle — 07:00Z · #299 confirmed end to end; fleet back to 10/10

**Book:** equity **1001.6503**, profit **+1.6503 (+0.1650%)**. Realized
**+1.2970** — up from +0.8271, driven by **981 SI banking +0.2531 -> +0.7230**.
Nothing below −0.99.

### The full chain, measured

    build_universe crypto 5 -> 8                    (verified live 3x)
      -> research universe 128 -> 131
      -> batch 496134: crypto candidates 3 -> 5
      -> UNHELD selectable crypto 0 -> 2            (HYPEUSDT, ZECUSDT)
      -> planner replacement builds took them
      -> FLEET 7/10 -> 10/10

Batch 496134 landed **06:55:23Z**, against the ~06:50 I predicted from worker
uptime. The builds followed at **06:59:23-25**:

    kept ["HYPEUSDT", "USDKRW", "ZECUSDT"]
    kept ["ZECUSDT", "USDKRW"]
    kept ["USDKRW"]

New runs: **992 HYPEUSDT, 993 ZECUSDT, 994 USDKRW**. Fleet `status_reason` is
now `None` — no longer "replenishing".

**Attribution, honestly:** #299 delivered HYPEUSDT and ZECUSDT. **USDKRW is
NOT mine** — forex went 0 -> 1 selectable in the same batch through ordinary
market conditions, and my change touched only the crypto branch.

### The gate did its job alongside

Every build attempt dropped **MGC**: *"non-positive expectancy −511.16
USD/trade over 7 closed trades"*. Correct refusal — though the magnitude is
inflated by pre-reset history on a 60,000 book being applied to a 1,000 one.
The SIGN is what the gate acts on, so this is not wrong, but a future session
should not read −511 as a live-scale number.

### Why the build lagged the batch by four minutes

The last attempt before the batch was 06:54:15, using the OLD batch — where
crypto were all held, so it could only offer MGC. The next attempt at 06:59:23
saw the new batch and took three candidates immediately. Build attempts are
periodic, not batch-triggered; four minutes was the gap, not a fault.

---

## Cycle — 06:25Z · over +1.00; and my deploys are delaying research

**Book:** equity **1001.1644**, profit **+1.1644 (+0.1164%)** — **over +1.00
for the first time**. Realized **+0.8271** (from +0.6162), unrealized +0.3373.
The move came from **991 GC banking −0.0045 -> +0.2268**. Cadence **7/7
distinct minutes**. Nothing below −0.99.

### Why no new research batch — and it is my own doing

    current_batch_id() = f"research:{int(now // research_interval_seconds())}"

A **fixed hourly bucket aligned to epoch hours**, claimed once by whichever
runner gets there first. And `symbol_research_loop` sleeps
`research_interval_seconds()` **from process start**, not on a wall clock.

The log is explicit:

    [SymbolResearch] {'batch_id': 'research:496133', 'skipped': 'batch_exists'}

Sequence: batch 496133 was claimed at **05:13**. My cryptobreadth deploy
restarted the worker at **05:50**; its refresh fired ~5s later, found 496133
already claimed, and skipped. The next refresh is **05:50 + 3600s = ~06:50**,
when bucket 496134 will be free.

**So bucket 496134's batch arrives ~50 minutes later than it otherwise would**,
purely because of when I deployed. Six deploys in three hours tonight, each
resetting the timer.

**Not a defect** — a restart-resetting sleep is ordinary, and the bucket
sentinel correctly prevents duplicate LLM spend. But it is a real operational
consequence worth knowing: **a deploy late in an hour phase-shifts research to
that minute for as long as the process lives.** A future session seeing "no new
batch" should check worker uptime before suspecting the research loop.

### #299 still not testable

The payoff test needs bucket 496134, due ~06:50. Third cycle deferred, and
deferring remains correct — the ZBTUSDT verification proved the value of not
declaring early.

### Nothing shipped

Fleet 7/10, unchanged, for the 05:00 reason. Worth adding: `_do_research` calls
`_open_markets_scope()`, which **actively scopes closed markets out** of
selection — so us-stock is not merely "not built" overnight, it is excluded
from the candidate pool entirely.

---

## Cycle — 06:00Z · session high; the #299 payoff test has not run yet

**Book:** equity **1000.9454**, profit **+0.9454 (+0.0945%)** — session high.
Realized **+0.6162** (from +0.5334), unrealized +0.3290. The move came from
**981 SI banking +0.1703 -> +0.2531**.

Cadence **7/7 distinct minutes**, and every run is on its own slot — 982 (:04/
:34) last at 05:34, 990 (:00/:30) at 05:30, 991 (:07/:37) at 05:37, 987 (:09/
:39) at 05:39. Nothing below −0.99.

### #299 not yet testable

Newest batch is still `research:496133`, created **05:13:13Z — before** the
cryptobreadth deploy at ~05:50. Its crypto rows are the pre-fix three
(BTCUSDT, ETHUSDT, SOLUSDT), all already held.

Research batches run roughly hourly (03:17, 04:07, 05:13), so the first batch
built from the 8-symbol universe is due around 06:10. **No claim either way
until it lands.**

Fleet stays 7/10 for the reason established at 05:00: the unheld candidates are
us-stock and the market is closed until 13:30Z.

### Nothing shipped

---

## Cycle — 05:45Z · crypto discovery was asking for 5 while slicing for 50

**Book:** equity **1000.6511**, profit **+0.6511 (+0.0651%)**. Realized
**+0.5334**, unrealized +0.1176. Cadence **7/7 distinct minutes**. Nothing
below −0.99.

### ZBTUSDT confirmed gone — the way I said I would check

Batch `research:496133` was created at **05:13:13Z**, AFTER the 05:08 log
lines, with **19 rows instead of 20** — exactly one fewer, and ZBTUSDT is the
one missing. **Zero ZBT lines in the following three minutes.** The 05:08
fetches were a research pass already in flight around the deploy. Declining to
declare it last cycle was correct.

### The next layer down: crypto discovery pinned at five

Removing the dead symbol made the real constraint visible. Three readings:

    build_universe by market: crypto 5, us-stock 72, futures 21, forex 30

**`get_top_symbols()` DEFAULTS TO 5** — `TOP_SYMBOLS_LIMIT`, sized for the UI
widget that first used it. `build_universe` called it bare and then sliced
`rows[:50]`, so **the slice was a no-op**. The slice documents the intent; the
missing argument defeated it. This module's own docstring says the universe is
"~198 symbols" against an actual **128**.

It bit tonight: three of the five were already held, so the entire unheld
crypto opportunity set was **TWO symbols** while the fleet sat at 7 of 10 with
US equities closed.

**Fix (#299):** pass the limit the slice already asks for.

### Measured outcome — smaller than the ceiling I quoted

    before: crypto 5   universe 128
    after:  crypto 8   universe 131

**Not 20.** `_VOLUME_CANDIDATES` caps the volume ranking at 20 and the
priceable-bases filter cuts it further, so the real gain is **+3 symbols**
(ZECUSDT, ADAUSDT, HYPEUSDT). The unheld crypto set goes 2 -> 5, which is a
2.5x improvement in overnight replenishment options and still far short of the
docstring's ~198.

I deliberately did NOT raise `_VOLUME_CANDIDATES`: it would also change the
ranking the UI consumer sees, and that is a separate decision on separate
evidence.

---

## Cycle — 05:00Z · why the fleet sits at 7/10, and one dead symbol removed

**Book:** equity **1000.5312**, profit **+0.5312 (+0.0531%)**. Realized
**+0.5029** (still climbing), unrealized +0.0281 — the desk keeps converting
paper into booked. Cadence **7/7 distinct minutes**. Nothing below −0.99.

### `built: 0` on every FleetPlanner tick for 40 minutes — explained, not a defect

Fleet 28 targets 10 runs and holds 7. The newest research batch has **12
selectable theses**, so the universe is not empty. Where they go:

    7 unheld  us-stock   -> US equities CLOSED at 05:00Z; the planner
                            deliberately will not bind a slot to a symbol
                            that would idle until the session opens
    1 selectable futures -> HG, already held
    0 selectable forex
    1 unheld  crypto     -> ZBTUSDT, unpriceable

**7/10 overnight is correct behaviour**, and the slots should fill when US
markets open at 13:30Z. Nothing to fix in the planner.

### The one real defect: ZBTUSDT (#297)

**48 log failures** — 23 x `Hyperliquid symbol not listed: ZBTUSDT -> ZBT` and
23 fetch failures — across at least two days, while consuming a survivor slot
and an LLM thesis in every batch. It is not listed on the venue, so it can
never be priced and can never be built.

**It was already known.** The 2026-08-06 starvation arithmetic in
`symbol_research` counts it by name (`- ZBTUSDT unpriceable = 0 buildable`) and
the survivor cap was raised instead of removing the dead symbol. I had also
seen its error line earlier tonight and dismissed it as "harmless but noisy" —
it was not harmless.

Tonight it stopped being cosmetic: **it was the only unheld crypto candidate**,
so one dead symbol was holding the fleet's last buildable overnight slot.

`build_universe` now filters crypto through the venue's own listed set, reusing
the check `price_fetcher` already runs before every fetch — one cached call.
**Fails open in two directions**, both tested: an exception leaves the universe
intact, and an all-unlisted answer is treated as a broken read rather than an
empty venue.

Verified live 3x: ZBTUSDT absent, BTCUSDT retained.

### New observation — the crypto discovery channel is thin

With ZBTUSDT gone the crypto universe is **5 symbols** (ETHUSDT, BTCUSDT,
SOLUSDT, XRPUSDT, DOGEUSDT) and three are already held. `top_symbols` is
returning very few candidates. **Recorded, not chased** — one reading, and
overnight is the worst time to judge a discovery feed.

---

## Cycle — 04:45Z · arms are standing, not churning; 985 completed cleanly

**Book:** equity **1000.6394**, profit **+0.6394 (+0.0639%)** — session high
again. Realized +0.4967, unrealized +0.1426. Cadence **7/7 distinct minutes**.
Nothing below −0.99.

### The payoff test is still pending, and it is NOT a churn problem

No tight arm has fired yet. Before calling that "too early" I checked the
failure mode that would prevent it — the desk replacing arms every cycle so
none lives long enough to be reached:

    983  1 arm intent since 03:00     standing   1 min old
    984  1 arm intent since 03:00     standing  55 min old
    990  1 arm intent since 03:00     standing  42 min old
    987  2 arm intents (moved once)   standing   3 min old
    991  2 arm intents (moved once)   standing  35 min old

**Arms are living 35-55 minutes.** Three runs have authored exactly one arm in
an hour and three quarters. The absence of fires is the tape not reaching them,
not churn.

Two movements worth noting: **987 changed its arm from `close 1.0` to
`reduce 0.5`** — toward the exit skill's preferred verb — and 991 trailed its
level 4260 -> 4335 as price rose.

### 985 completed a clean profitable lifecycle

    status desk_retired   realized +0.2553   12 cycles

Bought, scaled out in four halving exits, kept 91% of its true high-water mark,
then **retired itself** and freed the slot. Entry through exit through
retirement, all the desk's own decisions.

### Nothing shipped

Fifth consecutive cycle with no reproduced defect.

---

## Cycle — 04:15Z · the arm clause landed — measured

**Book:** equity **1000.5947**, profit **+0.5947 (+0.0595%)** — new session
high. Realized +0.4734, unrealized +0.1211. Cadence **8/8 distinct minutes**.
Nothing below −0.99.

### Every arm authored since the clause is reachable

| run | arm | excursion | ratio | armed |
|---|---|---|---|---|
| 983 ETHUSDT | 0.93% | 0.055% | **17.0x** | 02:41 — **before** the clause |
| 984 HG | 0.88% | 2.803% | **0.3x** | 03:48 — with clause |
| 991 GC | 0.30% | 0.157% | **1.9x** | 04:08 — with clause |
| 987 SOLUSDT | 0.25% | — | — | 04:09 — with clause |
| 990 ZW | 0.59% | — | — | 04:01 — with clause |

**4 of 4 arms authored after 02:55 sit at 0.25-0.93% from the mark.** The one
surviving pre-clause arm sits at 17.0x its own excursion. The desk has moved
from authoring arms at 1.2-2.6% to 0.25-0.93%.

**984 is the clean case: it was RE-ARMED from 2.48% to 0.88%** with a fresh
`armed_at`. That is desk action, not the tape drifting under a fixed level —
the trap that made this same test misleading two cycles ago, when 984's ratio
"improved" only because its excursion grew.

**Sequence, for the record:**

    02:20  #284 "a far arm is NOT PROTECTION"  -> desk re-armed at 14.9x anyway
    02:55  #287 adds the third case (range below round-trip cost)
    03:48+ four consecutive arms at 0.25-0.93%

The first version failed because it offered a false binary; the third case is
what made it actionable. n=4 over roughly an hour — not settled, but this is
the first clear evidence that today's skill work changed behaviour.

### Nothing shipped

Fourth consecutive cycle with no reproduced defect. Deploying only to sync the
last three cycles' notes into the corpus — monitoring chunks reach it on deploy
only, and the desk is meant to be reading them.

---

## Cycle — 04:00Z · the 983 watch closes: not a defect, a boundary

**Book:** equity **1000.5033**, profit **+0.5033 (+0.050%)** — best of the
session. Realized +0.4734, unrealized +0.0297. Cadence **8/8 distinct
minutes**. Nothing below −0.99.

**Mandate confirmed reaching decisions:** the `light/crypto` block opens with
`YOUR PURPOSE IS REALIZED PROFIT`, and both new clauses are present (far-arm
`NOT PROTECTION`, and its third case `below your round-trip cost`).

### 983 — five cycles watched, and the answer is "no change"

11 run cycles, 1 trade, realized −0.0100, high-water 1.4x the round trip. The
cent is not the cost; a fleet slot and ~48 LLM decisions a day are.

**But the retire rails are gated `not has_position and trades == 0`** — flat
and never-traded only. The code states why:

> *"an open position is never abandoned on a cycle count"*

983 has traded once and holds a position, so it is **correctly excluded**.
Retiring it means CLOSING that position, which is a trading decision — the
desk's, not mine. Building a rail to force-close positions that have not moved
would take a trading decision away from the AI, which the role boundary
forbids.

**The watch item closes as "no defect".** The desk has the excursion-scale
brief and the far-arm clause describing its own situation; whether to exit is
its call. Five cycles of watching produced a clear answer instead of a change,
which is the correct outcome — not a failure to find something.

### Nothing shipped

Third consecutive cycle with no reproduced defect. Equity at its session high.

---

## Cycle — 03:45Z · all three audits run; one false positive cleared

**Book:** equity **1000.4339**, profit **+0.4339 (+0.043%)**, cross-checked and
agreeing. Realized +0.4734, unrealized −0.0396. Cadence **8/8 distinct
minutes**. Nothing below −0.99. 986 USDKRW retired, 991 GC opened.

### pnl_audit — clean

    day          ledger   adapt   delta  flat  check
    2026-08-06     0.03    0.02    0.01     0  ok
    2026-08-07     0.45    0.53   -0.08     2  ok
    ledger validated 71/71 against the platform's own stored realized_pnl_usd

The −0.08 delta with 2 flattens is the known `adapt realized` flatten omission,
within tolerance. The ledger is authoritative and matches every stored row.

### ratchet_audit — clean

4 in-band reduces, all on run 981, **all post-fix, all survived, 0 flattened.**
The breakeven ratchet (#264/#118) is doing its job: repeated reduces did not
trip a premature flatten.

### fill_audit — one flag, investigated, FALSE POSITIVE

    985 ZC  463.500000  first 00:25:59  repeat 02:56:03  gap 150m  $7.34

02:56:03 is exactly when 985 made its best-performing close, so a stale mark
there would have made the book's best win illusory. **It did not.** ZC's mark
moved between the two fills — 462.5 at 01:26, **464.0 at 02:26** — and the
window holds 15 distinct unrealized values. The price genuinely revisited
463.50.

The audit's own wording is honest about this ("evidence the mark was stuck, not
proof"). Checked rather than assumed; **985's +0.2553 is real.**

### What 985 actually did — the behaviour that works

    23:00:15  buy   0.12664 @ 461.25
    00:25:59  sell  0.06332 @ 463.50     <- half
    01:26:11  sell  0.03166 @ 462.50     <- half of the rest
    02:26:26  sell  0.01583 @ 464.00     <- half again
    02:56:03  sell  0.01583 @ 463.50     <- the remainder

Four halving exits. It kept **91% of its true high-water mark**, the best on the
book. This is `reduce`-as-default-verb working exactly as the exit skill asks.

### Nothing shipped

Three audits, one flag, and the flag was refuted by the surrounding data. No
reproduced defect.

### 983 — fourth cycle unchanged

11 cycles, 1 trade, realized −0.0100, still running. It has now been static
across four consecutive cycles. Still one cent, still a watch item.

---

## Cycle — 03:15Z · two hypotheses tested and refuted; nothing shipped

**Book:** equity **1000.4894**, profit **+0.4894 (+0.049%)**, cross-checked two
ways and agreeing. Realized +0.5275. Cadence 8/8. Nothing below −0.99. Three
positions left; the desk has closed most of the book.

### Give-back, measured properly for the first time

`peak_pnl_usd` **RE-ANCHORS to the banked total when a run goes flat** — by
design, documented, with prod evidence (run 921 was stopped 28 seconds after
opening against a stale peak). So it CANNOT measure give-back after a close. I
nearly reported the re-anchor as a bug; reading the code first stopped that.

True high-water marks, recovered from the `equity` event stream:

| run | true hwm | realized | kept |
|---|---|---|---|
| 985 ZC | +0.2806 | +0.2553 | **91%** |
| 981 SI | +0.1628 | +0.1370 | **84%** |
| 984 HG | +0.3463 | +0.2574 | **74%** |
| 980 SOLUSDT | +0.0587 | −0.0085 | −15% |
| 982 BTCUSDT | +0.0292 | −0.0057 | −19% |
| 983 ETHUSDT | +0.0122 | −0.0100 | −82% |

**Book kept 59% of its true high-water mark; the three real winners kept
74-91%,** against the prior finding of 51-66%. The banking has improved.

### Hypothesis 1 — the fee multiple explains it. REFUTED.

Measured round trip is **0.0382%** of notional. If a high-water mark below some
multiple of cost were the discriminator, the split would be clean. It is not:

    980 SOLUSDT  hwm 7.7x the round trip  ->  NEGATIVE
    981 SI       hwm 5.7x the round trip  ->  POSITIVE

### Hypothesis 2 — size tracks conviction, so weak ideas lost small. REFUTED.

    run  conf  size_scale  notional   realized
    980  0.54     0.3000     20.06     -0.0085
    982  0.56     0.3000     24.52     -0.0057
    983  0.56     0.3000     22.28     -0.0100
    981  0.54     0.3000     75.47     +0.1370   <-- same conviction, 3.5x size
    985  0.66     0.5040     58.41     +0.2553
    984  0.73     0.9504     98.84     +0.2574

981 has the SAME confidence and the SAME size_scale as all three losers and
3.5x the notional. Conviction did not separate them.

### What is actually there: conviction does not buy consistent exposure

**An identical `size_scale` of 0.3000 produced notionals from $20 to $75.** The
scale is applied to a per-run base (max_bet and leverage), so the same
conviction buys ~3.75x more exposure in futures than in crypto. A 0.54-
confidence idea is a $20 risk in one market and a $75 risk in another.

**Recorded, not fixed. n=4 at one size_scale over four hours** is not grounds
for touching sizing — and sizing is the desk's own domain. Watch whether the
asymmetry persists across markets and conviction levels before proposing
anything.

### Nothing shipped this cycle

Both candidate explanations died on the evidence. The losers cost 2.4 cents
combined against +0.65 from the winners. There is no reproduced defect to fix.

### 983, third cycle unchanged

10 cycles, 1 trade, hwm 1.4x the round trip, realized −0.0100, still running,
arm still ~14x beyond its excursion. It is the clearest dead-capital case on
the book but it is costing a cent, so it stays a watch item rather than a
justification for changing retirement rules.

---

## Cycle — 03:00Z · the dashboard was lying about profit, in both directions

**Book:** realized **+0.5327** (was +0.4042). Two runs closed ENTIRELY at their
peak — `peak == realized` for both — quoting the mandate almost verbatim:

> *"Close the entire long position now to lock the modest profit and avoid the
> automatic give-back floor that would otherwise erase it."* — 985 ZC, +0.2553
> *"Close the long position to lock the small profit after most of the earlier
> gain was given back."* — 981 SI, +0.1370

984 HG banked +0.2574 of a +0.3463 peak (74%). Cadence 8/8. Nothing below −0.99.

### My equity formula was wrong, and chasing it found a real bug

I had been reporting equity as `cash + (seed - cash) + unrealized`. That
collapses to `seed + unrealized` — **it ignores realized entirely.** True
equity was **1000.51**, not the ~1000.0 I reported for several cycles. The book
was doing better than I said. Fifth measurement error of this class today.

Chasing it found that **the platform is wrong too, three different ways:**

| path | reports | error |
|---|---|---|
| **truth** | **+0.51 (+0.05%)** | — |
| public profile `cash - seed` | **−29.04 (−2.9%)** | −29.55 |
| leaderboard SQL `cash + notional - seed` | **+30.09 (+3.0%)** | +29.58 |

**The same agent read DOWN 2.9% on one page and UP 3.0% on another.** Both
errors are exactly the leverage gap (notional − margin = 29.58 at 2×).

**Cause.** `agents.cash` has only the MARGIN deducted — the identity
`seed − margin + realized = cash` holds to 0.0001 on prod. The profile
subtracted nothing back (booking every deployed dollar as a loss); the SQL
added back the whole NOTIONAL (booking borrowed money as profit).

**Fix (#288).** A position is worth its **margin plus unrealized P&L**. At
leverage 1 that equals the old expression, so spot books do not move — pinned
by a test. The expression was inlined **four times across two files**, which is
how three versions drifted; it now lives once in `portfolio_value.py` with a
Python mirror beside the SQL.

Verified live 3×: product reports +0.4777, cross-check `realized + unrealized`
= +0.4775.

**This is the same class as #268** (an agent reading −99% on zero trades).
Anything deriving profit from `cash` alone is suspect on a leveraged book.

### 983 is still dead capital

9 cycles, 1 trade, peak = 1.0× a round trip, not retired. Its arm is still
13.7× beyond its excursion. Unchanged since 02:45 — the watch continues.

---

## Cycle — 02:45Z · the desk banked hard; my arm clause did not land

**Book:** equity 1000.15. **Realized +0.4042 — up from +0.1655 in one cycle.**
Unrealized fell +0.242 → +0.149. Cadence 8/8 distinct minutes. Nothing below
−0.99.

**That shape is the mandate working.** Equity roughly flat while realized more
than doubled and unrealized shrank: the desk converted paper gains into booked
ones and took risk off the table. Three runs banked:

| run | realized | peak | kept |
|---|---|---|---|
| 985 ZC | **+0.2201** | +0.2806 | 78% |
| 984 HG | **+0.1918** | +0.3463 | 55% |
| 981 SI | **+0.1094** | +0.1628 | 67% |

Against the earlier finding that winners gave back 34-49% of peak, keeping
55-78% is a real improvement — though it is one cycle.

### My arm clause did NOT work on its only test case

#284 went live at 02:20. Exactly one arm has been authored since — run 983 at
**02:41:59** — and it re-armed at the SAME level, still **14.9×** beyond its
own excursion:

> *"keep existing arm to trim half if price rises above 1916"*

**The clause is logically unactionable for that run, and that is my error, not
the desk's.** 983's excursion is **0.055%, exactly 1.0× the round-trip fee**.
"Move it inside the range the tape has shown" would mean arming inside the
fee — banking nothing. My clause offers a false binary (move it, or bank now)
when a third case exists: *the range is below your cost, so there is nothing to
bank and no arm can help.*

### Run 983 is dead capital

Started 22:56, **9 cycles, 1 trade**, peak $0.0122 on a $22.28 book = 0.055% =
1.0× the cost of a round trip. Realized −0.010. It cannot pay from here without
a regime change. This is the `dead-capital-and-fee-hurdle` pattern again, not
an arm problem.

### The real constraint is not the catalogue size

`MAX_BLOCK_LEN` is not a model limit — 34,000 chars is ~8,500 tokens. It is a
proxy for ATTENTION, and a poor one: compressing prose makes each lesson
terser while all 30 skills still reach every decision. Four raises and repeated
compression have been fighting the symptom.

**The answer is retrieval, not a bigger cap or better compression:** send the
skills this situation needs, with a safety core that is always present. That is
Phase 1 of docs/plan/22 and it supersedes the "prune first" rule recorded last
cycle.

---

## Cycle — 02:15Z · the desk read the ratio and trusted the arm anyway

**Book:** equity **1000.24** — best yet. Realized **+0.1655**, unrealized
+0.242. 8 runs, 6 positions. **Cadence 8/8 distinct minutes** (00, 02, 04, 09,
11, 48, 55, 57). No run below −0.99.

Realized fell from +0.2207 to +0.1655 because 986 USDKRW sold half at a loss —
*"Reduce half of the long position to limit further loss while keeping some
upside"*. Equity still rose, so this was a cut, not a leak.

### The reproduction, and it was not what I expected

**No new arm has been authored in 40 minutes** — every `armed_at` is unchanged.
The ratios moved anyway, purely because the tape moved:

| run | arm | excursion | ratio | armed at |
|---|---|---|---|---|
| 982 BTCUSDT | 1.45% | 0.205% | 7.0× | 01:34 |
| 983 ETHUSDT | 0.90% | 0.055% | **16.4×** | 23:42 |
| 984 HG | 2.08% | 0.551% | 3.8× | 00:18 |
| 986 USDKRW | 1.16% | 0.000% | n/a | 01:32 |

984 improved 6.5× → 3.8× **because its excursion grew**, not because anything
was re-armed. Ratios drift with price; only `armed_at` shows desk action.

**What the desk actually said, with the scale check in front of it:**

> *"let the existing arm (reduce half at 1916) manage upside"* — 983, **16.4×**
> *"let the existing arm protect gains"* — 982, **7.0×**

**The fact lands; the judgment does not convert.** No skill said what a large
multiple MEANS. The arm skill only asked the desk to restate an arm "once it no
longer fits the book" — which never says a far arm is not protection at all.

**Fix (#284, AI-first, skill not rail):** *at a large multiple you are
UNPROTECTED whatever you armed: move it inside the range the tape has shown, or
bank now.*

### A fact went stale for the second time

*"of 60+ arms only TWO have ever fired"* became false at **01:50:52Z** when run
981's arm fired. The count was previously "NOT ONE". The test now asserts the
current figure exactly and **rejects both superseded ones by name**, because
this particular sentence keeps ageing.

### ⚠️ The catalogue is FULL

`trader/us-stock` = **34000 of 34000, zero headroom**. All 30 skills still fit
(verified 3× on prod, none dropped) but there is no room whatsoever. **The next
skill addition must prune first.** Four times the cap has been raised; it was
not raised again.

### Still unprotected

**981 SI (1.615% excursion) and 985 ZC (1.921%)** — the two largest movers on
the book, both winners, still carry no arm. The next cycle is the test of
whether the new clause changes that.

---

## Cycle — 02:05Z · a seq collision that the design absorbed

**Book:** equity **1000.10**. Realized **+0.2207** (was +0.1648). Unrealized
+0.105. 8 runs, 6 positions, notional 132.52. No run below −0.99.
**Cadence 8/8 distinct minutes** (32, 34, 35, 39, 41, 48, 55, 57).

### A duplicate-key traceback in the worker log

```
pymysql.err.IntegrityError: (1062,
  "Duplicate entry '981-191' for key 'run_events.uq_run_events_run_seq'")
  ... trading_runs.py line 268, in _emit_event
```

**Mechanism.** `_emit_event` reads `SELECT last_event_seq FROM trading_runs`,
computes `seq + 1`, then INSERTs — **with no row lock**. Two concurrent writers
on the same run read the same value and collide. The docstring's crash-safety
argument ("a reclaiming worker re-reads last_event_seq, never a stale in-memory
counter") covers RESTART, not CONCURRENCY.

**Impact — checked, not assumed.** Run 981: **195 rows, max seq 195, zero
missing**, and no seq gaps on ANY run. Signal 523's trade is present at seq
192. The collision was on seq 191, an `equity` telemetry row, and
`emit_telemetry_event` is fail-soft for exactly that class. The critical trade
rode its own transaction and landed.

**So the invariant held** — "a committed trade may never be missing from the
journal" is intact. One equity sample was dropped.

**Not fixed this cycle: one occurrence in ~24h, benign by design.** If it
recurs the fix is `SELECT … FOR UPDATE` on the seq read, or catching
IntegrityError and retrying with a fresh seq. Expect it to recur more often as
the fleet grows — two writers per run (the cycle, and the arm executor firing
between cycles) is the collision source.

One small real cost: a fail-soft path logs a full ERROR traceback, which trains
readers to skim tracebacks. A one-line warning would be better.

### Arm ratios — the reproduction test is INCONCLUSIVE

| run | arm | excursion | ratio | armed at |
|---|---|---|---|---|
| 982 BTCUSDT | 1.27% | 0.205% | 6.2× | 01:34 (post-brief) |
| 983 ETHUSDT | 0.73% | 0.055% | 13.3× | 23:42 (pre-brief) |
| 984 HG | 2.29% | 0.350% | 6.5× | 00:18 (pre-brief) |
| 986 USDKRW | 1.18% | 0.000% | n/a | 01:32 (post-brief) |

**984's ratio improved from 11.5× to 6.5× — but the arm did NOT move.** Its
EXCURSION grew (0.216% → 0.350%) while the level stayed where it was set at
00:18. Reading that as "the brief is working" would be wrong.

**No new arm has been authored since 01:34**, so there is no new data for the
test. Do not conclude anything about the brief's effect yet.

**981 SI and 985 ZC still have no arm**, with excursions of 1.498% and 1.921% —
the two largest on the book, both winners, both unprotected.

### My fourth measurement error of the day

I read "zero events since 02:00Z" as a stall. The clock was **01:59:38Z** — my
filter was in the FUTURE. Along with the host-side glob, the null timestamp and
the missing column, the pattern is trusting an aggregate without a cross-check.
**Check the clock before filtering on it.**

---

## Cycle — 02:00Z · the first arm fired, and the book turned positive

**Book:** equity **1000.02** — positive for the first time since the reset.
Realized **+0.1648** (was +0.0567). Unrealized +0.022. 8 runs, 6 positions,
notional 141.95. No run below −0.99.

**Cadence: 8 of 8 distinct minutes** (25, 27, 32, 34, 35, 39, 41, 48). Perfect
separation, no first-cycle collision this time.

### An arm fired — the first in this fleet

```
run 981 SI  01:50:52Z  price_above 62.05 -> reduce 0.5
fill 62.075001  qty 0.305081  slippage 0.0403%  fee $0.00095
```

Accounting checked by hand: 0.305 units × (62.075 − 61.845) = $0.0702 gross,
less $0.00095 fee = **+$0.0692**, and realized moved −0.064 → +0.006, a +0.070
swing. Matches. The arm path works end to end — author, stand between cycles,
fire, execute, book.

This is the mechanism that the "60+ arms, only two ever fired" history said was
broken. It is not broken; the levels were unreachable.

### Arm distances, before vs after the scale brief

| run | arm | excursion | ratio | armed at |
|---|---|---|---|---|
| 983 ETHUSDT | 0.70% | 0.055% | 12.9× | 23:42 — **before** the brief |
| 984 HG | 2.48% | 0.216% | 11.5× | 00:18 — **before** |
| 982 BTCUSDT | 1.24% | 0.205% | **6.0×** | 01:34 — **after** |
| 986 USDKRW | 1.17% | 0.000% | n/a | 01:32 — **after** |

The two arms authored after the scale brief went live are meaningfully closer
than the two authored before (6.0× vs 11.5–12.9×). **Two data points is not
reproduction — no change shipped this cycle.** Measure again next cycle before
concluding the brief changed behaviour.

### Unprotected winners

**981 SI and 985 ZC have no arm standing.** 981's just fired and was consumed;
985 banked +0.177 at 01:26 and did not re-arm. 985 has the largest excursion on
the book (**1.92%**) and is the largest winner. The scale brief already tells
both of them "No level is armed" — whether they act is the desk's call, and the
next cycle shows whether they do.

### A measurement bug of my own

I first reported "NO ARM" on every run. That was my query selecting specific
columns and omitting `armed_order_json`, so every run read as unarmed. The
decisions plainly showed active arming, which is what caught it. **Third
measurement bug of this class today** — a host-side glob through `docker exec`,
a null timestamp, and now a missing column. Read the decisions as a
cross-check before trusting an aggregate.

---

## Cycle — 01:45Z · arms were a unit-conversion bug

**Book:** equity 999.87 vs seed 1000 (flat). Realized +0.0567, unrealized
−0.132. 8 runs, 6 positions, notional 175.42 on 87.65 margin.

**Floor rule:** no run below −0.99. Nothing cleaned. The desk retired run 988
on its own reasoning ("price is already below the recent swing low") and the
fleet replaced it with 989 ZW.

### The finding

The desk noticed its own give-back and held anyway:

> *"Thesis still valid with ample downside buffer, but momentum is weak and the
> small gain has already been given back, so we hold the long position and keep
> the existing arm at 6.89 for a partial profit take."* — run 984, 01:18Z

That is the mandate working (it named the give-back) and the arm failing. Why:

**Peak reaches the desk in DOLLARS — "Best this run has reached: $0.10" — but
an arm is a PRICE LEVEL.** The conversion was never given. A desk told "$0.10"
cannot know that was two tenths of one percent of its position.

Measured live, every standing arm against the largest move its own tape made:

| run | arm distance | peak excursion | ratio |
|---|---|---|---|
| 983 ETHUSDT | 0.74% | 0.055% | **13.4×** |
| 984 HG | 2.60% | 0.208% | **12.5×** |
| 982 BTCUSDT | 0.46% | 0.205% | 2.2× |
| 981 SI | 0.50% | 0.297% | 1.7× |

Four of four beyond their own tape's range, two by more than twelvefold. This
is the mechanism behind the long-running **"60+ arms authored, only two ever
fired"** — a missing unit conversion, not a failure of judgment.

**Fix (#277, AI-first):** `_excursion_scale_line` states the excursion as a
percentage of price and, when a level is armed, how many times further it sits.
Fact only; moving the arm stays the desk's call. Live and rendering on 5 runs:

> *Scale check: the furthest this has travelled in your favour is 0.21% of
> price (peak $0.10 on a $49.42 position). Your standing arm sits 2.48% away —
> 11.9× that.*

### A wrong turn, corrected

I first concluded the excursions were too small to clear fees. **Checked
instead of assumed, and it was false.** Measured fee: **0.0265% per side,
0.053% round trip.** 983's 0.05% excursion genuinely was unbankable (1.0× fee),
but 981 (5.6×), 982 and 984 (3.9×) were comfortably bankable. Do not repeat the
wrong version.

### Give-back is still the shape

Peak → current total: 981 +0.112 → −0.128, 982 +0.025 → −0.005, 983 +0.012 →
−0.043 — **all three gave back more than their entire peak.** 984 +0.103 →
+0.022.

The counter-example that works: **985 ZC banked +0.138 of a +0.281 peak and is
still +0.217.** It is also the largest excursion on the book (1.92% of price)
with **no level armed** — which the new brief now says out loud.

**Watch next cycle:** whether arms tighten toward the tape's actual range now
the desk can see the ratio. Run 981 has already re-armed to 0.15% away — 0.5×
its excursion, i.e. inside the range. One data point.

---

## Cycle — 01:15Z · desk corpus (RAG) live

Owner: *"RAG keep all analysis and monitoring for this session and sooppiy AI"*.

`desk_memory` + ingest daemon live (#271–#275). Corpus holds monitoring chunks,
the desk's own decisions, and run outcomes; it rides the ~30s scheduler tick,
throttled to 30 min, wrapped so it can never fail a trading tick.

Four problems found by checking rather than assuming:

1. **The corpus kept only half of what it is for** — 16 decisions, zero
   monitoring chunks, because `/app/docs` is not in the image.
2. **`.dockerignore` excludes both `docs/` and `*.md`** — a `COPY docs/reports/`
   fails to build. Mounted read-only from the deployed tree instead.
3. **`scripts/deploy.sh` never updates `$REMOTE/docker-compose.yml`** — compose
   changes must be applied on the box by hand.
4. **A no-op ingest took 26–33s** — one SELECT per chunk, 442 round-trips
   against the trading database. `known_shas()` made it **0.2s**.

**Corrections to my own reading:** a partial corpus count read mid-ingest is
not an interrupted run; and `ls glob | wc -l` through `docker exec` expands on
the host, not in the container. Both of my first readings were wrong.

---

## Cycle — 00:15Z · profit mandate and 30-minute staggered cadence

Owner: *"We must be make solution for get a profit (It's our destiny and
purpose)"*, *"MUST BE THINKING DEEPLY and do not make change lost profit"*,
*"Sooppiy AI analysis each run 30 min (make time gap each)"*.

Shipped (#269): the mandate is now the first line of every decision prompt;
`RUN_INTERVAL_CAP_MIN=30`; per-run slots on an absolute grid.

**A relative elapsed test can never break lockstep** — once a full interval has
passed the slot has always advanced too, so the two conditions collapse into
one and every run keeps its inherited phase forever. One early fire, floored at
half an interval, snaps a run onto its slot.

**A first cycle always fires immediately** (no `last_cycle_at`), so a newly
built run shares a minute with whatever else is due. Check `cycle_seq` before
calling that a stagger failure.

---

## Open

- Marketing pages fail every deploy: `astro: command not found`. Last step,
  after backend/worker/SPA are live, so nothing is broken — but marketing has
  not rebuilt today.
- `$ZBT-USD` logs a delisted-symbol error each research sweep. Harmless, noisy.
- `adapt realized` still omits `run:N:flatten` closes, so daily P&L understates
  losses exactly on the worst days. Must be fixed before any retrieval weights
  are trusted (docs/plan/22).
