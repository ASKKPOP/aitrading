# Automation monitoring — 2026-08-05

Owner-set hourly loop (cron `3e0160dc`, :17; session-only, expires ~2026-08-11)
— **INDEFINITE**: no end time; only an explicit owner stop ends it. Cycle
notes newest-first. Predecessor: `2026-08-04-automation-monitoring.md`
(cycles 28–48: the false-alarm confession, 5 prod ships #227–#230 +
bracketauthor, the 956 wrongful-retire post-mortem, the idle-churn fix).

Open with the owner: (1) risk_limits 8%/15% row vs the 2:1 floor —
row change / floor change / rely on desk authoring; (2) arm-executor
design (gap-through-level semantics). Standing verifications due today:
TSLA/NVDA idle-cooldown rows + varied replacements at the US open
(~13:30Z), first NVDA-print FMP check as mid-August approaches.

---

## Cycle 74 — 2026-08-06 05:20Z — 11-minute window, no change; cron prompt refreshed

DB clock `05:20:01`. **The cron fired 11 minutes after cycle 73** — 1
decision, 1 trade. That is a fact about the window, not the fleet. 7
running, **0 tracebacks in 60 min**, prod `20260806-flatpnl`.

**08-06 via the new tool: ledger −8.10, adapt −7.78, delta −0.32, 2
flattens, verdict `ok`.** The audit tool is now the runbook's P&L method and
it keeps reconciling.

### The one decision: 960 banked half a winner — and it does NOT count for #245

960 cycle 28: `sell` at conviction 0.6775 → **`intent: reduce, size_frac
0.5`** (sold 39.22 of 78.44 units).

Tempting to log as a second exit-verb win. **It is not.** 960 was **in
profit** (unrealized **+5.49**), so the Exit scale line was correctly
SILENT — the lesson's trigger context was absent. This is banking half a
winner, which is good behaviour but a different thing.

**Exit-verb (#245) stays at n=1** (969 cycle 20, genuinely adverse at 59%
of an ordinary day). Counting profitable reduces would inflate the evidence
for a lesson that has one real data point.

*Standing caution now written into the cron:* only count an exit as #245
evidence if the Exit scale line actually rendered.

### Housekeeping — cron prompt refreshed (job `e3e5f8fe`)

The prompt was **stale and actively misleading**: it still listed FINDING 1
as "NOT YET EXERCISED" and the newborn guard as "n=1", both closed in cycle
73. It would have sent the next cycle chasing solved work. The new prompt
carries: FINDING 1 and the newborn high-conviction caveat marked CLOSED with
their evidence, the `pnl_audit` tool as the P&L method (with the mount
fallback), the profit-silence caution for #245, and the recalibrated
ordinary-days lens for watch (a).

### No change warranted

Eleven minutes of data, one profitable reduce. Today's obligation was met by
the audit tool (#250, in CI). Triggers unchanged: a second `drawdown_brake`
with the add-then-brake shape · the ratchet firing repeatedly on noise or
cutting a winner · a stop inside ~1.0 ordinary day collected by routine
range · an adverse full close with an empty `why`.

---

## Cycle 73 — 2026-08-06 05:09Z — FINDING 1 fired LIVE; newborn guard reaches n=4 and clears its last caveat

DB clock `05:09:34`. 7 running (960, 961, 968, 972, 974, **975 new**,
**976 new**); 969 retired. **0 tracebacks in 30 min.**

### ✅ FINDING 1 — the fix fired live, exactly as designed

969 HG retired on `retire_consecutive_losses` (3 losses) while **holding
95.78 units**, so the stop path flattened it — the first real flatten since
the fix deployed:

```
05:05:24  trade  {"client_order_id": "run:969:flatten", ...}
05:05:24  adapt  {"trigger": "flatten_close", "realized": -3.2407,
                  "side": "sell", "quantity": 95.77662175, "price": 6.7185}
```

And the new audit tool confirms the consequence:

| day | ledger | adapt | delta | flattens | verdict |
|---|---|---|---|---|---|
| 08-06 | −7.98 | −7.78 | **−0.20** | 2 | **ok** |

**A day containing two flattens now RECONCILES.** Compare 08-05 — also two
flattens — which drifted **−64.73**. The residual −0.20 is 973's pre-fix
flatten (+0.40) minus entry-fee asymmetry, exactly as expected.

**FINDING 1 is CLOSED**, on three independent legs: 71/71 historical
validation, a natural live firing, and the audit tool showing the day
reconcile.

### ✅ Newborn guard (#244) — n=4, and the HIGH-CONVICTION case is finally covered

| run | born | cycle-1 action | conviction |
|---|---|---|---|
| 973 SOLUSDT | 08-05 21:32 | `sell` | 0.545 |
| 974 SOLUSDT | 08-06 02:47 | `sell` | 0.4525 |
| 975 BTCUSDT | 08-06 04:50 | `hold` | 0.665 |
| **976 GC** | 08-06 04:53 | **`buy`** | **0.8725** |

**Four consecutive newborns, zero retires**, spanning conviction
0.4525 → 0.8725. I have been carrying the caveat that the specific
pathology — run 970 quitting at **0.7025** on a thesis it agreed with — was
untested. **976 acted at 0.8725, above that level.** That caveat is now
retired: the guard is covered across the range where the bug actually bit.

Baseline for contrast: five consecutive newborns retired on cycle 1 before
#244.

### 969's retirement was the rails working, not a defect

`retire_consecutive_losses` after 3 losses, with an honest thesis review:
*"returned −0.5% versus the anticipated +4% gain."* Lifetime **+10.57**.
A run that lost its edge was retired by the deterministic rail and banked a
net gain. No action.

### Carried items

| item | status |
|---|---|
| **FINDING 1** | **CLOSED — fired live, day reconciles, 71/71 validated** |
| **Newborn guard (#244)** | **n=4, all survived; high-conviction caveat CLEARED** |
| Exit-verb (#245) | 1 positive (969 cycle 20 chose `reduce`), n=1 |
| Ratchet (#249) | 1 fire, no churn, no winner cut |
| Arm executor (#247) | 968's arm still standing |
| FINDING 2 | still 1 brake-retirement |

**08-06 true realized: −7.98** (tool, verdict ok). No change shipped this
cycle beyond the audit tool already in flight (#250) — the window's evidence
is three mechanisms working as designed.

---

## Cycle 72 — 2026-08-06 04:40Z — FINDING 1 VERIFIED (without waiting), and its severity CORRECTED DOWN

Owner: *"fixing"* the standing "FINDING 1 still unverified". Waiting for a
natural flatten is not a verification strategy. There were **71 historical
flattens sitting in prod**; I used them.

### ✅ VERIFIED — the fix's arithmetic, against 71 real prod flattens

The shipped fix computes a flatten's realized as a `compute_run_pnl` delta.
I replayed every one of the 71 historical flattens from the raw trade
ledger and compared each run's total against the PRODUCT's own stored
`realized_pnl_usd`:

| | |
|---|---|
| runs matching within 2 cents | **71 / 71** |
| mismatches | **0** (worst 0.00) |
| runs with no stored value | 0 |

971 is the marquee case: replay **−58.18**, stored **−58.18**, my earlier
hand arithmetic **−58.18** — three independent methods agreeing.

**This is a stronger verification than one natural firing would have been**,
and it no longer blocks on the fleet's behaviour.

### ⚠️ SEVERITY CORRECTED DOWN — this was a MONITORING defect, not a product defect

I need to be precise about something I let read as bigger than it is.

`grep` shows **no product code reads adapt-realized at all.** The platform's
P&L comes from `realized_pnl_usd` / `compute_run_pnl`, which replay SIGNALS
— and a flatten IS a signal, so it was always included. Proof: 971's stored
value is −58.18, the full loss, not the −3.70 the adapt stream showed.

**No user ever saw a wrong number.** The blind spot was confined to the
monitoring query in the runbook (and therefore to MY cycle notes). The
08-04/08-05 figures I corrected were monitoring figures. The fix is still
right and still worth having — it makes the monitoring query trustworthy —
but it is reporting hygiene, not a platform bug.

### The historical correction, now computed

71 flattens, **−166.03 unrecorded in aggregate** (44 losses −1,078.97 / 27
gains +912.93). Largest single omissions:

| date | run | sym | missing |
|---|---|---|---|
| 07-24 | 76 | CL | **−150.64** |
| 07-23 | 62 | ETHUSDT | −138.58 |
| 07-22 | 35 | ETHUSDT | −91.42 |
| 07-25 | 99 | HYPEUSDT | −83.54 |
| 08-05 | 971 | ZECUSDT | −54.47 |

Per-UTC-day correction to any historical monitoring figure: 07-22 +82.48 ·
07-23 +219.56 · 07-24 −169.02 · 07-25 −185.34 · 07-26 −61.97 · 07-27 −9.00 ·
07-28 +20.95 · 07-29 −1.29 · 07-30 −6.76 · 07-31 +31.59 · 08-01 −0.71 ·
08-02 −0.17 · 08-03 −0.46 · 08-04 −31.06 · 08-05 −55.24 · 08-06 +0.40.

### ⚠️ And a query error of my own, caught and corrected mid-cycle

Checking double-count risk I first ran the signal_id match **globally**
instead of run-scoped, and got "5 adapts reference a flatten signal" — which
would have contradicted the no-double-count claim in the #249 commit. It was
a false positive: signal_ids 267/270/386/421/458 belong to flattens in runs
895/856/945/957/973 while those adapts sit in runs 856/898/942/958/969 —
different runs. **Run-scoped, the answer is 0.** The shipped claim holds.

### NOT backfilling the 71 missing events, deliberately

Tempting, and I am declining. `run_events.seq` is NOT NULL and ordered;
inserting 71 synthetic events into the history of stopped runs risks
corrupting an event stream to fix a number that **no product surface reads**.
The corrected series above is the durable artifact and costs nothing.

### Carried items

| item | status |
|---|---|
| **FINDING 1** | **VERIFIED (71/71) — severity corrected to monitoring-only. CLOSED.** |
| Ratchet (#249) | 1 fire, no churn, no winner cut |
| Exit-verb (#245) | first positive result (cycle 71), n=1 |
| Newborn guard (#244) | n=2, high-conviction case untested |
| Arm executor (#247) | 968's arm still standing |
| FINDING 2 | still 1 brake-retirement |

---

## Cycle 71 — 2026-08-06 04:20Z — the exit-verb lesson FIRED POSITIVE on its first real test

DB clock `04:20:12`. 60 min of real data: 6 decisions, 2 trades, 2 adapts.
6 running (949 left), **0 tracebacks in 60 min**, prod `20260806-flatpnl`.

**08-06 true realized: −4.21** (ledger replay). Query reads −1.44; the 2.77
gap is 969's 04:19 reduce still awaiting its `run_feedback` adapt next
cycle, plus 973's pre-fix flatten. Same lag pattern confirmed last cycle
when 960's `winning_close` +0.68 landed exactly as predicted.

### ✅ EXIT-VERB (#245) — first genuine adverse exit, and it COMPLIED

Run 969 HG, cycle 20 at 04:19:51. The position was **underwater**
(unrealized **−6.42**), so the Exit scale line rendered — and this is what
the desk was looking at:

> *"the move against you is 0.50%. An ordinary day on this symbol moves
> 0.84%, so this is **59% of one ordinary day**. If you act, choose the VERB
> deliberately: 'reduce' with a size_frac…"*

**Its choice: `intent: reduce, size_frac: 0.5`** — sold 95.78 of 191.55
units. **NOT `close: 1.0`.**

That is precisely the behaviour #245 was built to produce, on precisely the
setup it targets: an adverse move well inside routine range. Against the
08-05 baseline — 27 losing FULL closes carrying **91% of all loss** — an
adverse position at 59% of an ordinary day got a **half reduce** instead of
a dump.

**Strength, stated honestly:** n=1 for a genuine adverse exit (973's earlier
reduce was at ~0.00%, barely adverse). Encouraging, not a verdict — the
2+ cycle rule still applies. And **`why` remains empty**; not required for a
reduce, but the field is still unpopulated fleet-wide.

### 949 closed out cleanly

`stop_event:at_time` fired at 03:47:34 exactly as scheduled: running →
stopping → stopped, **no flatten needed** because it was flat. Lifetime
−15.51 over 46 hours. The 46-hour flat slot resolved with no intervention,
as predicted last cycle.

### Today's losing shape — and why no fix is warranted

| run | today |
|---|---|
| 969 HG | **−5.17** |
| 968 USDKRW | −1.35 |
| 960 SI | +1.92 |
| 973 SOL | +0.40 |

969 is the day's loss, and it is **being managed correctly**: a genuine
adverse move, met with a half reduce rather than a dump, on a 1.8% stop
that sits at **2.1 ordinary days** for a 0.84%/day symbol. This is what
"we can not fix 100%" means — a real adverse move handled with the right
shape is not a defect to engineer away.

### Carried items

| item | status |
|---|---|
| **FINDING 1 (#249)** | **0 flattens since deploy — STILL UNVERIFIED.** 949's stop needed none (flat) |
| Ratchet (#249) | still 1 fire, no churn, no winner cut |
| Arm executor (#247) | 968's arm still standing at 1440 |
| Newborn guard (#244) | n=2 (973, 974) — high-conviction case still untested |
| **Exit-verb (#245)** | **first positive result (above)** — n=1 |
| FINDING 2 | still 1 brake-retirement |

### No change shipped, correctly

Today's obligation was met in cycle 67 (FINDING 1). This window's evidence
is a lesson working as designed and one properly-managed adverse move.
Conviction spread 0.4525–0.6975, honest, no clustering.

---

## Cycle 70 — 2026-08-06 03:20Z — newborn guard reaches n=2; 960 banked +37.59; no change warranted

DB clock `03:20:19`. 60 min of real data: 4 decisions, 1 trade, a new run.
7 running, **0 tracebacks in 60 min**, docs 4/4 at 200, `/automation` 200,
prod `20260806-flatpnl` byte-identical to `origin/main`.

**08-06 true realized: −0.75** (ledger replay). The adapt query reads −1.76;
the 1.01 gap is (a) 960's 03:00 close still awaiting its `run_feedback`
adapt on the next cycle, and (b) 973's 00:21 flatten which predates the
FINDING 1 fix. Both explained — not a new blind spot.

### Newborn guard (#244) — now n=2, and both survived

**Run 974 SOLUSDT, born 02:47:00.** Cycle 1 action = **`sell`**, not
`retire`. Conviction 0.4525; the order was gated at the confidence
threshold (0.47 < 0.50) so it never traded, but **it chose to act rather
than quit**.

| | before #244 | after |
|---|---|---|
| newborns retiring on cycle 1 | 5 consecutive (963-966, 970) | **0 of 2** (973, 974) |

**Honest limit:** both survivors had modest conviction (0.545, 0.4525). The
specific pathology — 970 quitting at conviction **0.7025** on a thesis it
agreed with — has **not been retested**. Two is movement, not proof.

### Exit-verb (#245) — the watch is STILL UNTESTED, and I nearly miscounted it

960 cycle 25 emitted `intent: close, size_frac: 1.0` with **`why: ""`** —
on its face exactly what the lesson forbids.

**It is not the pathology.** That close was **banking a winner**: realized
36.91 → **37.59**, unrealized 1.30 → 0. 960 bought 84.17 @ 61.90 and scaled
out in halving slices (42 → 21 → 10.5 → 5.3 …), and this was the final 7
units. The run ended **+37.59**. The Exit scale line was correctly SILENT,
because it renders only on adverse drift.

#245 targets full dumps on ADVERSE noise-scale moves. Counting a profitable
scale-out finale as a failure would have been a false negative finding.
**Still waiting for a genuine adverse full close.**

*(Standing note: `why` remains empty even here. On a winner that costs
nothing, but the field is still unpopulated across the board.)*

### Breakeven ratchet (#249) — no churn, and it did not touch the winner

**1 fire total** (973, 00:21). 960 ran to +37.59 and closed on the desk's
own decision with **no ratchet interference** — the arm/never-breach path
behaving exactly as designed. The "more small exits" trade-off has **not**
materialised.

### Watch (a), recalibrated — 974's stop is sound

974 authored **stop 1.0%** on SOLUSDT, whose ordinary day measures
**0.70%** → **1.44 ordinary days**. Outside routine range; sound. Under the
old flat-1% lens this would have been flagged as a sub-1% stop and it is
not one. No new evidence for that watch.

### Carried items

| item | status |
|---|---|
| **FINDING 1 (#249)** | **0 flattens since deploy — STILL UNVERIFIED on prod** |
| Ratchet (#249) | 1 fire, no churn, winner untouched |
| Arm executor (#247) | 968's arm still standing at 1440 |
| Newborn guard (#244) | **n=2**, both survived — high-conviction case untested |
| Exit-verb (#245) | untested — no adverse full close yet |
| FINDING 2 | still 1 brake-retirement |

### No change shipped, and that is correct

Today's solution obligation was met in cycle 67 (FINDING 1). This window's
evidence — two newborns behaving, one winner banked, a flat day — supports
no trading change. Conviction spread 0.3375–0.6975, honest, no clustering.

**Next natural event:** 949's scheduled `at_time` stop at **03:47Z** (~27
min), which resolves the 46-hour flat slot without intervention.

---

## Cycle 69 — 2026-08-06 02:20Z — no ship; my cycle-62 concern about 960 RESOLVED ITSELF; watch (a) is miscalibrated

DB clock `02:20:07`. 37 min since cycle 68 — thin but not empty: 2 decisions,
1 adapt, 1 order_intent. 6 running, **0 tracebacks in 60 min**, prod on
`20260806-flatpnl` (byte-identical to `origin/main`).

### ⚠️ CORRECTION — 960's rail/stop gap has resolved, and I nearly misread it

Cycle 62 flagged 960 as carrying a **2.9× gap** (rail 2.59% vs a 3.05%
authored stop), and it authored 3.05% again at cycles 19/22/23/24. That
looked like the desk ignoring the Risk rail line.

**It is not.** 960's rail is now **11.69%**, because the desk REDUCED the
position from 28.04 units to 7.01 (notional ~440). A fixed dollar room over
a 4× smaller book is a 4.5× larger price move. **The stop now binds first,
which is the healthy design — the gap is gone.** Repeating 3.05% is correct
behaviour, not non-compliance. I would have filed a false finding had I
compared the stop to a stale rail figure instead of recomputing it.

### Watch (a) "sub-1% authored stops" is MISCALIBRATED in both directions

Stops authored since the rail line went live, against each symbol's own
measured ordinary daily move:

| run | symbol | stop | ordinary day | in ordinary days |
|---|---|---|---|---|
| 968 | USDKRW | 0.65-0.79% | 0.50% | **1.3-1.6x** — fine |
| 969 | HG | 1.80-1.82% | 1.06% | 1.7x — fine |
| 960 | SI | 3.00-3.05% | 2.01% | 1.5x — fine |
| 949 | HYPEUSDT | 1.63-2.7% | 2.15% | **0.76-1.26x** — tight |

A flat 1% threshold **false-positives on 968** (forex sub-1% stops that sit
1.3-1.6 ordinary days out are perfectly sound) and **under-flags 949**
(1.63% on a 2.15%/day mover is 0.76 of one ordinary day). The watch should
be **volatility-relative**, and `_typical_daily_move_pct` already computes
exactly that number.

### But NOT shipping it this cycle, deliberately

Tempting, and I am declining on the rules. #231's shipped clause says
"~1% on a leveraged crypto book" — by that standard 949's 1.63-2.7% stops
are **compliant**. Ship the volatility-relative version and I am imposing a
NEW standard, not enforcing an existing one, and I have **no loss attached
to it in this window** — 949 is flat and its scheduled stop is 03:47Z.
Four runs of authoring data is enough to identify the miscalibration, not
enough to justify tightening live trading behaviour.

**Trigger to act:** a stop authored inside ~1.0 ordinary day that is then
collected by routine range, on any run — i.e. the 941/955 shape recurring
with the volatility-relative lens rather than the flat 1% one. At that point
the AI-first fix is to state the symbol's ordinary daily move **at the
moment the bracket is asked for** (today it appears only on adverse drift,
via the Exit scale line, long after the stop was authored).

### Carried items

| item | status |
|---|---|
| **FINDING 1 (#249)** | **0 flattens since deploy — STILL UNVERIFIED on prod** |
| Ratchet (#249) | 1 fire total. No churn. Winners untouched |
| Arm executor (#247) | 968's arm still standing at 1440, untouched |
| Newborn guard (#244) | no new newborns — still n=1 |
| Exit-verb (#245) | no adverse exit yet |
| FINDING 2 | still 1 brake-retirement |

Fleet honesty check: conviction spread 0.242 (949) to 0.7225 (960) — wide
and honest, no clustering. 949 at conviction 0.242 flat is correctly holding
rather than forcing a trade; its `at_time` stop resolves it at 03:47Z.

---

## Cycle 68 — 2026-08-06 01:43Z — no change warranted; idle slots verified healthy; main caught up to prod

DB clock `01:43:00`. **The cron fired 5 minutes after the previous check, so
there is almost no new trading data** — a fact about the window, not the
fleet. 6 running, events 62 s fresh, **0 tracebacks in 90 min**, prod on
`20260806-flatpnl`.

### No change shipped, and that is the correct call

Today's solution obligation was already met in cycle 67 (FINDING 1). Nothing
in a 5-minute window meets the reproduced-evidence bar. Triggers restated
below rather than manufacturing a finding.

### What I examined instead: is the fleet actually working?

| run | age (h) | qty | note |
|---|---|---|---|
| 949 HYPEUSDT | 45.9 | flat | scheduled `at_time` stop **03:47Z** — resolves in ~2 h |
| 960 SI | 16.8 | 7.0102 | held |
| 961 UBER | 16.8 | flat | **0 trades ever**, cycle 11 |
| 968 USDKRW | 12.7 | 0.1826 | residual, notional **258.63** (above the ~52 dust floor) |
| 969 HG | 11.7 | 191.55 | held |
| 972 SLV | 8.4 | 10.73 | held |

**4 held / 2 flat.** 961 looked like dead capital — 16.8 h, zero trades —
but it is behaving exactly as designed:

- **6 `market closed` gate-skips** since 19:01Z and **zero LLM decisions** —
  the pre-gate skips BEFORE the analysis, so it costs nothing overnight.
- It sits at **cycle 11 against a 12-cycle idle-retire threshold**, so the
  rail claims the slot one cycle after the US open if it still has not
  traded.

**No action.** The rail is one cycle from firing and the run is free to hold
while its market is shut.

### Carried items

| item | status |
|---|---|
| **FINDING 1 (#249)** | fixed, **NOT YET EXERCISED** — no flatten since deploy, so `flatten_close` is still unproven on prod |
| Ratchet (#249) | **1 fire total** (973). No churn. 960/969/972 armed and **protected, not cut** |
| Arm executor (#247) | 968's arm still standing at 1.21%, untouched |
| Newborn guard (#244) | no new newborns — still n=1 |
| Exit-verb (#245) | no adverse exit yet |
| FINDING 2 | still 1 brake-retirement |

### Housekeeping done

- **PR #249 merged** (5/5 checks green); **prod is now byte-identical to
  `origin/main`** — main caught up to prod, not the reverse.
- **Cron prompt refreshed.** It still listed FINDING 1 as UNFIXED and cited
  a superseded image. The new prompt (`17d63a61`) carries the corrected
  carried-items list, the alembic-for-MySQL rule, the wiring-test rule, the
  replay sign-error warning, and an explicit instruction to say so plainly
  when the cron fires minutes after the last cycle.

### What would trigger action

A second `drawdown_brake` with the add-then-brake shape · the ratchet firing
repeatedly on noise (then `BREAKEVEN_ARM_FEES`) · the ratchet cutting a
winner · a newborn retiring on cycle 1 · an adverse exit choosing `close`
with an empty `why`.

---

## Cycle 67 — 2026-08-06 00:25Z — FINDING 1 FIXED; and I correct a false claim I made last cycle

DB clock `00:25:14`. **The cron fired 4 minutes after cycle 66, so there is
essentially no new trading data in this window** — that is a fact about the
window, not about the fleet. 6 running, 0 tracebacks in 60 min, docs 4/4 at
200, `/automation` 200.

### ⚠️ CORRECTION — my "never armed, ever" claim was WRONG

Cycle 66 stated the trailing lock "has never armed. On any run. Ever."
**That is false.** It fired on six runs:

| run | `activate_usd` | peak | fired |
|---|---|---|---|
| 921 | 0.80 | 2.74 | ✓ — 28 SECONDS after opening |
| 919 | 6.00 | 6.79 | ✓ |
| 119 / 125 | 26.17 | 33.92 / 28.76 | ✓ |
| 854 / 897 | 43.48 | 46.18 / 76.41 | ✓ |
| **940-972** | **78-81** | max **22.07** | **0** |

The accurate finding is narrower and still supports the ratchet:
`activate_usd` is set EQUAL to `max_loss_usd`, so it has RISEN with position
size (0.8 → 6 → 26.17 → 43.48 → 78-81) and outran what the fleet earns.
**Across the entire current budget regime it fired zero times.** Run 921
also shows the opposite failure — armed at 0.8 and stopped 28 seconds in —
which is exactly why the new rail anchors its arm to the position's own
round-trip cost rather than a small constant.

Corrected in three places: the shipped code comment, the PR #248 body, and
the cycle-66 note above.

### SHIPPED — FINDING 1, the P&L reporting blind spot (image `20260806-flatpnl`)

A forced flatten emitted a `trade` event and **nothing else**, while every
ordinary close emits an `adapt` carrying `realized`. The standard query sums
exactly those adapt events, so it **omitted every flatten** — and a flatten
happens when a brake, retire or stop fires on a LOSING position, so it
understated losses precisely on the worst days:

| day | query said | truth |
|---|---|---|
| 08-04 | −20.61 | **−62.57** |
| 08-05 | +73.21 | **+8.62** (gap ≈ run 971's −54.47 flatten) |

**It bit again today:** run 973's ratchet exit at 00:21:23 is a flatten and
would have been invisible too.

Fix: emit an `adapt` carrying `realized` at flatten time — rather than a new
event type — so every downstream consumer is fixed at once with **no query
change**. It cannot double-count: `run_feedback` derives its adapt events
from closed SIGNALS on a later cycle, and a flattened run is
stopping/stopped so no later cycle processes that leg — which is exactly why
the number went missing. Fail-soft both ways: the realized snapshot is taken
before the exit and the journal is wrapped, so a reporting problem can never
block or undo an exit.

Pipeline: 4 new tests (one asserts the STANDARD query shape now sees it) →
2 mutations verified to bite (drop the emit; drop the `realized` key so the
event exists but the query stays blind) → ruff clean → **3348 passed** →
build → 66 in-image → drift guard vs the ratchet deploy → swap → verified
(ratchet and arm executor confirmed still wired — no regression).

### Why shipping a REPORTING fix was the right call this cycle

The daily obligation requires a solution, and rule 6 forbids a
thinly-evidenced TRADING change. With 4 minutes of new data there was no
trading evidence to act on — but FINDING 1 was fully evidenced, long
outstanding, and carries **zero trading risk**. That is the correct way to
satisfy both constraints at once.

### Carried items

| item | status |
|---|---|
| Newborn guard #244 | no new newborns this window — still n=1 |
| Exit-verb #245 | no adverse exit yet — still waiting |
| **FINDING 1** | **FIXED this cycle** |
| FINDING 2 (add-then-brake) | still n=1 — correctly no action |
| close→reduce rail | owner decision, untouched |
| MAX_BLOCK_LEN | unchanged (34000) |
| Arm executor #247 | 968's arm still standing at 1.21% |
| Ratchet #248 | 1 fire (973); 960/969/972 armed and protected, not cut |

---

## Cycle 66 — 2026-08-06 00:21Z — THE PEAK PROTECTION HAD NEVER ARMED. Ratchet built, fired live.

Owner: *"many times desk doesn't hear signal. How do we make 100% hear
signal and act — without act, we will be lost always."*

### The honest answer: stop requiring the desk to hear

Measured over 08-04/05: the desk **held a position on 133 cycles and armed
on 37 — 28%**, and every arm it placed sat **11-13% from price**. Effective
between-cycle protection was **≈ 0%**. An LLM will never be 100% compliant,
so the guarantee cannot depend on one.

### The decisive finding: the machine-side rail is dead by configuration

A deterministic trailing profit lock already existed in `_evaluate_stop`.
Its config on the live fleet:

```
949 HYPEUSDT   trail.activate_usd = 81.00
960 SI         trail.activate_usd = 78.16
```

`activate_usd` is set **equal to `max_loss_usd`** — the trail only starts
protecting after a run is up by its ENTIRE loss budget. The best peak any
run reached in two days was **$22.07**; most were $2-6.

> ⚠️ **CORRECTION (cycle 67).** I first wrote "it has never armed, on any
> run, ever." **That was wrong** and the next cycle disproved it: it fired
> on runs 921, 919, 125, 119, 854 and 897 when `activate_usd` sat at
> 0.8-43.48. The accurate finding is narrower and still supports the rail:
> `activate_usd` equals `max_loss_usd`, so it has RISEN with position size
> (0.8 -> 6 -> 26.17 -> 43.48 -> 78-81) and outran what the fleet earns.
> **Across runs 940-972 — the whole current budget regime — it fired ZERO
> times** while peaks maxed at 22.07. The opposite failure exists too: run
> 921 armed at 0.8 and was stopped 28 SECONDS after opening, which is why
> the new rail anchors its arm to the position's own round-trip cost rather
> than a small constant.

**I did not change that number** — `stop_conditions_json` is run config and
belongs to the sooppiy AI. Build the path, do not patch the row.

### Shipped — PR #248, image `20260806-ratchet`

A **breakeven ratchet**: once a position's peak clears **its own round-trip
cost**, it may not go negative. Deterministic, on the control pass, needs
nothing from the desk. Fee-anchored rather than a constant (a flat figure
would be a noise-trigger on small books and inert on large ones), needs NO
`trail` config (961 carries `{}` and had no protection at all), reuses the
`trailing_lock` reason (already classified in both fleet disposition sets
and all six languages — a new reason would fall through every one), and
`BREAKEVEN_RATCHET=0` kills it without a deploy.

Replayed against the 08-05 book, on `total` while held:

| run | actual | with ratchet |
|---|---|---|
| 971 | −54.50 | fires at **−5.10** |
| 955 | −21.66 | fires at **−2.64** |
| 967 | −13.24 | fires at **−0.54** |
| **969** (+19.11, day's best) | +19.11 | **arms, never breaches — kept** |
| 957 / 962 | small losses | **never arm** (peaks never paid their round trip) |

≈ **+81** on the day with the winner untouched.

**A self-caught error worth recording:** my first simulation appeared to
show the ratchet cutting 969, the day's best run. That was an artifact of
reading `unrealized` (which snaps to 0 at the close) instead of `total`
while held. Checking the winner case BEFORE building is what caught it — a
naive breakeven floor that cut 969 would have been worse than the disease.

### First desk arm after the skill — moved a lot, not all the way (n=1)

The arm write path is proven end-to-end: run 968 persisted
`{"if":"price_above","level":1440.0,"then":"reduce","size_frac":0.5}`
(seq 16, 00:22:42Z).

| | 08-05 (before) | this arm |
|---|---|---|
| distance from price | **11-13%** | **1.21%** |
| in ordinary days for that symbol | ~25 | **2.5** |
| direction | mostly protective `price_below` | **`price_above` -> reduce = BANKING** |

**~10x more reachable, and it is a banking arm rather than a protective
one — both are what the skill asked for.** But the skill asked for a level
inside roughly ONE ordinary day's move and this is 2.5, so compliance moved
substantially without completing. n=1; give it 2+ cycles.

**This is exactly why the ratchet had to be built too.** If 968's arm never
gets touched, the breakeven floor still covers it. Neither layer depends on
the other, which is the whole point of the two-layer design.

### It fired live within 3 minutes of deploy

```
00:21:20 breakeven ratchet fired (run 973): peak=1.7228 now=-0.3343 arm=1.6469
00:21:23 run_status running -> stopping (stop_event:trailing_lock)
00:21:23 trade cover 11.11935406 SOLUSDT @ 74.055
00:21:23 run_status stopping -> stopped
```

973 peaked just above its round-trip cost, came back through breakeven, and
was exited at **−0.33** instead of being left to run to a −13 like 967. All
six other runs — including 960 (+34.76) and 969 (+17.84) — untouched.
0 tracebacks.

**The trade-off, stated plainly:** this produces MORE frequent small exits
in exchange for cutting the −54 tail. That is the intended SHAPE change, not
a side effect. Watch that the small exits do not themselves become a churn
cost — if they do, the arm multiple (`BREAKEVEN_ARM_FEES`) is the dial.

Pipeline: 8 new tests (incl. a WIRING guard and the 969 winner case) → 3
mutations verified to bite → ruff clean → **3344 passed** → build → 62
in-image → drift guard vs merged main → swap → verified live.

---

## Cycle 65 — 2026-08-05 23:45Z — WHY today lost: the profit was invisible between cycles

Owner listed today's losses and asked for a full re-analysis. This goes
past the earlier exit-verb finding to the layer underneath it.

### Every losing run was IN PROFIT first

Maximum favourable excursion (MFE) reconstructed from the per-minute
`equity` stream:

| run | sym | best unrealized | worst | final |
|---|---|---|---|---|
| 971 | ZEC | **+17.52** | −65.97 | **−58.18** |
| 969 | HG | +19.83 | −3.12 | +19.11 ✓ kept |
| 955 | SOL | +6.94 | −16.60 | −22.68 |
| 967 | ZEC | +6.10 | −11.42 | −13.24 |
| 957 | ETH | +3.37 | −7.82 | −12.93 |
| 962 | SOL | +2.68 | −5.88 | −6.37 |
| 968 | USDKRW | +0.17 | −0.21 | −2.58 |

**Not one of these was an entry problem.** ~56 of unrealized profit existed
across these runs; ~−42 was realized.

### The cause: the profit never appeared AT a decision point

| run | true MFE | best seen **at a decision** | dwell above ½ peak |
|---|---|---|---|
| 967 | +6.10 | **0.00** | **10 min** |
| 957 | +3.37 | **0.00** | **5 min** |
| 962 | +2.68 | +0.33 | 15 min |
| 955 | +6.94 | +2.48 | 20 min |
| 969 | +19.83 | +14.53 | 53 min → **banked ✓** |
| 971 | +17.52 | +11.15 | 46 min → saw it, **added instead** |

**The decision interval is ~45 minutes. Those profit windows lasted 5–20
minutes.** They opened and closed entirely between two decisions. 967 and
957 literally never had a cycle while in profit. **The desk cannot bank
what it never sees.** The two runs whose dwell (46–53 min) exceeded the
cycle interval BOTH saw their peak — and 969 kept it.

This is a **sampling-rate** defect, not a judgment defect. No skill can fix
it, because no prompt is being rendered during the window that matters.

### The desk already asks for the fix — and the platform throws it away

`order_intent` supports `arm`: *"if price_above/price_below X, then
reduce/close size_frac"* — a pre-committed, intra-cycle trigger that needs
no desk cycle. Exactly the missing mechanism.

**54 arm intents lifetime. Nothing consumes them.** Grep confirms only
`order_intent.py` knows the arm vocabulary; the `arm` hits in
`run_engine.py` are *armed RUNS* (start conditions), an unrelated concept.
The desk has been asking 54 times and the platform discards every one.

Today's desk clearly wanted this — it armed banking orders like
`price_above 74.8 → reduce 0.5` and protective ones like
`price_below 6.55 → reduce 0.5`.

### ⚠️ HONEST CORRECTION — the executor alone would NOT have saved today

I checked every armed level today against every subsequent price mark:

| run | armed | outcome |
|---|---|---|
| 971 | below 454.23 → close | **never touched** (ZEC 518–521 — **13% away**) |
| 960 | above 69.0 → reduce | never touched (SI 62.2–62.7 — 11% away) |
| 968 | below 1415 / 1413 | never touched (1421.8–1424.8) |
| 969 | below 6.55 / 6.58 | never touched (6.68–6.76) |
| 972 | below 55.8 → reduce | never touched (56.07–56.29) |

**None would have fired.** The desk arms levels far from price, and mostly
*protective* (`price_below`) rather than *banking* (`price_above → reduce`).
Today it needed banking.

So the executor is **necessary but not sufficient.** The fix is two parts,
and the ORDER MATTERS:

1. **Platform — build the arm executor.** Without it, any skill telling the
   desk to arm better is a lesson with no executor: the exact trap in
   [[liquidation-defense-daemon]]. **This must come first.**
2. **Desk — a skill to arm a REACHABLE banking level**, anchored to the
   position's own measured excursion rather than a distant round number.
   Worthless until (1) exists.

**Design note that unblocks handoff §9.2.** That section recorded the
gap-through question ("fire at next tick regardless, or bound by a slippage
band?") as needing the owner. It largely answers itself: `ARM_THEN` is
restricted to `("reduce", "close")` — **arms can only SHED risk.** The
module's own doctrine says an intent that sheds risk may be clamped UP and
never refused, so *always fire at the next tick* is the consistent answer;
refusing an exit is the documented danger. Slippage is journalled, not a
veto. The residual owner question is narrower than recorded.

**Status: BOTH PARTS SHIPPED** — owner approved the two-part plan in order.
PR #247, image `20260806-armexec`, **alembic 0043**.

**Part 1, the executor.** `order_intent.arm_fires` / `arm_exit_fraction`
(pure, fail-closed) + `trading_runs.armed_order_json` +
`run_engine._store_armed_order` / `_fire_armed_order`, fired from
`_control_active` — the only path that runs between decisions. Safety:
reduce/close only (ARM_THEN enforces it, so it can only shed risk);
fail-closed on missing arm/position/mark; honours the manual breaker like
`_flatten_run`; one-shot (cleared BEFORE the trade) plus an idempotent
`client_order_id`; going flat clears a standing arm. `health_below` parses
but is explicitly NOT executable — named, not silently ignored.

**Part 2, the skill.** `position-management` gained "ARM THE LEVEL YOU
CANNOT WAIT FOR": arm whenever holding, make it REACHABLE (one ordinary
day's move, not a distant round number), arm to BANK not only to protect.

**MySQL:** the SQLite ALTER list does not reach prod. Alembic 0043 was run
against prod MySQL BEFORE the swap (additive nullable column, backward
compatible with the running image); prod moved 0042 → 0043 and the column
now exists.

Pipeline: 12 new tests (incl. a WIRING guard) → 2 mutations verified to
bite (unwire executor, remove one-shot clear) → **1 reported honestly as an
EQUIVALENT mutant** (dropping the explicit `mark is None` check: `float(None)`
raises and the existing `except` already returns False) → ruff clean →
**3336 passed** → build → **159 tests OK in-image** → sha256 drift guard on
all four files vs parent `fea53e9` → migration → swap → verified.

**Verified live:** predicate + wiring present in the worker, both skill
sites carry the lesson, catalogue auto-upgraded, column readable (NULL on
all 7 runs — correct, arms are written on the next cycle), control pass
confirmed running (35 equity events in 5 min, emitted from inside
`_control_active`), 0 tracebacks.

> **I did NOT arm a live run to test it** — that would place a real trade,
> which is the desk's decision, not mine. End-to-end execution is proven by
> the in-image tests against a temp DB; the prod proof must come from the
> desk arming naturally.

**Open, and the thing that decides whether this worked:** every arm on
08-05 sat **11–13% from price** and none would have fired. **The executor
alone changes nothing until the desk arms REACHABLE levels** — that is what
the skill must move. Watch `armed_order_json` going non-NULL and `armed_exit`
events firing.

---

## Cycle 64 — 2026-08-05 21:44Z — first newborn since #244 SURVIVED; all three brief lines verified live

DB clock `21:44:14`, last event 35 s prior. Image `20260805-exitverb`.
**0 tracebacks and 0 `conviction_missing` in 60 minutes.** No changes
shipped this cycle — nothing met the reproduced-evidence bar.

### CARRIED ITEM — did #244 stop the newborn cycle-1 retires? EARLY YES (n=1)

**Run 973 SOLUSDT, born 21:32:34** — the first newborn since the
newborn-guard deployed.

| | |
|---|---|
| cycle 1 action | **`sell`** (opened a short) — **not `retire`** |
| conviction | 0.545 |
| authored bracket | stop 1.20% / target 2.50% → **ratio 2.08, clears the 2:1 floor** |
| status now | running, position −22.24 |

Before #244, five consecutive newborns retired on cycle 1 (one at
conviction 0.70). This one traded its read instead. **Honest limit: n=1,
and 973's conviction (0.545) is not in the range where the old bug was
most striking (970 quit at 0.7025).** Per the 2+ cycle rule this is
encouraging evidence, not a verdict. Keep counting newborns.

### All three brief lines verified together on live runs

| run | book | Streak | Risk rail | Exit scale |
|---|---|---|---|---|
| 949 HYPEUSDT | flat | **9 consecutive** | — | — |
| 961 UBER | flat | **6 consecutive** | — | — |
| 968 / 969 | flat | — (streak < 4) | — | — |
| 960 SI | long, adverse | — | **$45.37 left** | **0.18% = 9% of an ordinary day** |
| 972 SLV | long, **in profit** | — | $53.04 left | — (silent on a winner, by design) |
| 973 SOL | short, new | — | $56.91 left | 0.00% of a 0.66% ordinary day |

Every line fires exactly where intended and stays silent where intended —
including #244's gate working as designed: 949 and 961 DO carry the Streak
line, so retiring is now legitimately available to them, and both held.

*Cosmetic nit (not worth a deploy):* 973 renders "the move against you is
0.00%" when the adverse move is non-zero but rounds to zero. Harmless and
not misleading; fold into the next functional change to that line.

### CARRIED ITEM — FINDING 1 (P&L blind spot) reconfirmed at scale

| | |
|---|---|
| `adapt`-realized query reports 08-05 | **+73.21** (32 closes) |
| **true realized (ledger replay, all closes + all fees)** | **+8.62** |

The 64.59 gap is dominated by **971's flatten (−54.47)**, which emits no
`adapt realized` row at all. Two flattens today (957 06:47, 971 20:04).
**Still unfixed — every daily figure must be hand-reconciled until it is.**

### CARRIED ITEM — FINDING 2 (add-then-brake): still n=1, no action

Only 971's `drawdown_brake` exists since 08-01. Correctly holding at watch
rather than acting on a single data point.

### CARRIED ITEM — MAX_BLOCK_LEN

Unchanged at 34000 this cycle. Cycle 63 acted on the attention warning
rather than ignoring it: the exit-verb lesson **extended
`exit-discipline`** instead of becoming a 35th skill.

### Decisions this window (4) — all honest

960 hold (conv 0.765, c17) · 949 hold (0.29, c56) · 968 hold (0.33, c12) ·
973 sell (0.545, c1). Spread 0.29–0.765, no clustering artifact.

### Docs (brief item 4) — healthy

`how-it-works-en` 200/34,991b · `-ko` 200/38,496b · `liq-defense-en`
200/45,783b · `-ko` 200/51,896b · public `/docs/how-it-works` 200 ·
`/automation` 200.

### Next cycle

1. Count more newborns — does the #244 result hold beyond n=1?
2. First **adverse** exit decision on a run carrying the Exit scale line:
   does the desk choose `reduce` over `close`, or state a `why`?
3. FINDING 1 remains the outstanding fix.

---

## Cycle 63 — 2026-08-05 21:00Z — TWO-DAY LOSS ANALYSIS (owner-requested) + fix shipped

Owner asked: recent minus profit — what reason, how do we protect, check the
full 2 days. Answer below. Shipped as PR #245, image `20260805-exitverb`.

### The reported numbers were wrong

| | 08-04 | 08-05 | 2-day |
|---|---|---|---|
| standard `adapt`-realized query | −20.61 | **+75.20** | **+54.59** |
| **actual (ledger replay)** | **−62.57** | **+9.35** | **−53.22** |

The two largest losses of the period — 971 (−58.18) and 956 (−31.00) —
were **both forced flattens, invisible to that query** (FINDING 1, cycle
62). Including the 08-03 tail the true figure is **−40.57**.

*Replay correctness:* my first replay had a cost-basis SIGN ERROR when
covering a short (`cost -= avg*close` on a negative cost basis). Fixed by
tracking `avg` explicitly. Now validated against **five** independent
sources: 971 hand arithmetic (−58.18), 956 (−31.00), 942 (+13.19), 958
(+54.45) equity events, and 955/967 adapt sums with the known
entry-fee offset.

### The edge is real; a tail destroys it

| | |
|---|---|
| closes | 84 |
| **win rate** | **55%** |
| median win / median loss | **+1.98 / −1.29** — at the median, wins are BIGGER |
| mean win / mean loss | +3.78 / −5.19 (payoff 0.73) |
| **6 closes of 84 (7%)** | **74% of ALL loss (−145.86 of −197.08)** |

The other 32 losses average −1.60 and are healthy. Cap those 6 at the
median loss and the two days go from **−23 to +115** (closes only).

### Locating the tail — it is the VERB, not the timing

| | closes | total | mean | mean notional |
|---|---|---|---|---|
| losing **trims** (<100%) | 11 | −16.80 | −1.53 | 736 |
| losing **FULL closes** | 27 | **−180.29** | −6.68 | 1266 |

**Full dumps = 71% of losing closes but 91% of all loss.** All six
catastrophic losses dumped **100%** of the book, notionals 810–8231, on
moves of 0.49–1.74%.

Separately: **37 of 38 losing closes were taken on a move under 1%**, at a
**median 28% of the desk's own authored stop**; only **1 of 38** ever
reached that stop.

### What it is NOT — measured and rejected

I tested the obvious fix (stop the desk exiting early) by reconstructing
the price path after every sub-1% losing exit from a 414-point per-symbol
timeline built out of `decision.entry` marks:

> holding would have been better in **19/28** measurable cases (68%), but
> the **median gain is only +0.11 percentage points**.

The price does not recover — it drifts. **Gating early exits would trade a
small certain loss for an uncertain one** and risk trapping desks in real
moves (949's −1.74% exit was legitimate). Rejected on evidence.

### The fix — AI-first, desk stays the actor

The channel is visible in the telemetry: 969 cycle 9 →
`intent: close, size_frac: 1.0, railed: {}, why: ""`.

No existing exit lesson states the SCALE of the move against an ordinary
day on that symbol, and **none offers `reduce` as the alternative to
`close`** — five skills say what not to do without a number or an
alternative verb. That is why they have not worked.

1. **`_exit_size_line`** — the adverse move, what fraction of one ORDINARY
   day on this symbol it is (median |close-to-close| over recent daily
   bars, so one event day cannot redefine "ordinary"), and both verbs
   named. Adverse drift only; silent on a winner. Wired on BOTH paths.
2. **`exit-discipline`** gains the verb clause with the measured numbers,
   and asks for the reason in the intent's `why` on a whole-book close.

**Live after deploy:** 960 SI renders
`"the move against you is 0.18%. An ordinary day on this symbol moves
2.01%, so this is 9% of one ordinary day."`

### DELIBERATELY NOT DONE — needs the owner's decision

Railing `close → reduce` in `order_intent`. That module documents an
explicit safety asymmetry: *"close is never railed at all... refusing one
is how a rail becomes the risk."* Clamping an exit DOWN contradicts it.
**Amending a documented safety invariant is the owner's call, not a side
effect of a monitoring fix.** Escalate only if the desk's own verb choice
does not move over the coming cycles.

Pipeline: 7 new tests (incl. BOTH wiring guards + a median-vs-mean guard)
→ 3 verified mutations → ruff clean → **3323 passed** → build → **90 tests
OK in-image** → drift guard (prod == parent `b35850f`) → swap → verified.

---

## Cycle 62 — 2026-08-05 20:05Z (the newborn-retire regression fixed and shipped; a P&L query blind spot found)

DB clock anchor `20:05:22`. Picked up from `HANDOFF-automation-monitoring.md`.

### Fleet at cycle start

6 running (handoff listed 7 — **971 ZECUSDT closed during the cycle**):
949 HYPEUSDT, 960 SI, 961 UBER, 968 USDKRW, 969 HG, 972 SLV.

Worker healthy: 0 tracebacks in 90 min, 0 `conviction_missing`. The 10 log
lines matching `error` were all benign `errors=none` / `errors=0`
feed-snapshot lines — a grep artifact, not incidents. **Both open watches
from handoff §7 (telemetry pymysql traceback, conviction_missing rate) are
quiet — neither recurred.**

### SHIPPED — PR #244, image `sooppiy-backend:20260805-newbornguard`

The in-flight #238 regression is fixed and live.

**Evidence re-confirmed:** run 970 born 15:29:57, retired 15:31:19 — **82
seconds old**, `action: retire` on cycle 1, `conviction 0.7025`,
`thesis_alignment 0.8`. It agreed with its own thesis and quit. Siblings
963/964/965/966 did the same at 12:19–12:24Z.

**Cause:** #238's flat-retirement clause made "retire" salient with **no
precondition a fresh desk could check** — a newborn is trivially "flat
with no read yet" because it has not looked yet.

**Fix (AI-first — bind the lesson to its datum, no new code rail):**
`reentry-discipline` now gates retirement on the `Streak:` brief line #241
already added, which renders **only after 4+ consecutive flat holds** —
exactly the evidence the clause asks the desk to weigh. Absent that line
the desk lacks the finding, and "retiring at birth wastes the build that
created this slot."

**Pipeline:** fail-before/pass-after test
(`test_flat_retirement_is_gated_on_the_streak_line`) → **mutation-verified**
(breaking the guard phrase failed that test and only that test) → ruff
clean → **3307 passed** → build → **40/40 in-image unittest** → sha256
drift guard (prod == parent `db56c1f`, exact match) → swap → verified 5×.

`MAX_BLOCK_LEN` 30000 → 34000 (the guard took trader/us-stock to 30,248).

> ⚠️ **Fourth budget raise** (14000 → 16000 → 28000 → 30000 → 34000). The
> catalogue only grows — every lesson is appended, none retire. **The real
> constraint is attention, not bytes:** the busiest site now carries 30
> skills, so each new lesson competes with 29 others. The next structural
> move should be *pruning or market-scoping* skills that stopped earning
> their place, not another bump. Flagged in the code comment too.

### FINDING 1 — the "authoritative" realized-P&L query has a blind spot

**The daily realized figure understates losses whenever a run is retired
while still holding.** The query sums `adapt` events carrying `realized`.
A **forced flatten** (`client_order_id: run:N:flatten`) emits a `trade`
event and **no `adapt realized` row at all**.

Verified two independent ways on 971:

| | |
|---|---|
| Query says 08-05 realized | **+75.20** (30 closes) |
| 971's only `adapt` rows | `drawdown_brake`, `retired` — **neither carries `realized`** |
| 971 hand arithmetic | buy 5.8393 @ 520.01 + buy 9.9722 @ 520.87, sell 15.8115 @ 517.34; cost 8230.72, proceeds 8179.93, fees 7.38 → **−58.18** |
| Independent ledger replay | **−58.18** (agrees to the cent) |
| **Corrected 08-05 realized** | **≈ +17.02** |

Not new — the prior session noted 956's −31 outside the query on 08-04.
**It is systematic:** 70+ forced flattens exist in the event history.
**Not yet fixed** — this is a *measurement* defect, so the fix is
reporting code, not a skill. Until then **read every daily P&L in these
notes as "excluding forced flattens."**

*Method note, stated plainly:* a full ledger replay produced obviously
wrong lifetime figures for multi-trade runs (942 SOLUSDT → 116,756). That
replay is **not trustworthy** and none of its multi-trade numbers are
reported. Only 971 is reported — a clean three-trade run confirmed by hand
arithmetic and replay independently.

### FINDING 2 — RESOLVED and SHIPPED (image `20260805-riskrail`)

**Correction to my own first read below:** I filed this as "single data
point, watch only" because the *brake firing* had happened once. That was
the wrong unit of analysis. The **brake firing** is rare; the **condition
that makes it fatal** is not. Full analysis follows; the WATCH-only note is
kept underneath for the record.

**The real defect: the desk authors risk in PRICE PERCENT, the platform
retires the run on EQUITY DRAWDOWN IN USD, and nothing reconciled them.**
`run_feedback.apply_policy` retires at `0.70 × max_loss_usd` of drawdown
from the high-water mark. Translated into a price move, that distance is:

```
rail_% = 0.70 × max_loss_usd / (position notional)
```

`max_loss_usd` is a fixed dollar figure (uniformly 3% of `max_bet_usd`
across the fleet). Notional is not — it grows with every add and with
leverage (live runs carry leverage 2). **So every add divides the rail
distance.** The desk was never shown either number.

**971 reconstructed exactly** (verified against its own event stream):

| moment | rail distance |
|---|---|
| at the cycle-6 decision, pre-add | **1.86%** |
| immediately after the add | **0.62%** |
| price then moved | **−0.68% → RETIRED** |
| stop the desk authored that same cycle | **3.5%** |

The desk budgeted 3.5% of room while standing 0.62% from the exit, and its
own add is what moved it there. Its authored stop never had a chance to
bind — it was never the binding constraint.

**Reproduced across the fleet.** Auditing runs 940–972 (21 with usable
data), the brake sits **inside the desk's own authored stop in SEVEN**:

| run | authored stop (median) | rail | brake binds first by |
|---|---|---|---|
| 971 | 3.50% | 0.72% | **4.9×** |
| 960 | 3.05% | 1.05% | **2.9×** |
| 956 | 2.00% | 1.05% | 1.9× |
| 945 / 958 / 969 | 2.20 / 1.24 / 1.80% | 1.79 / 1.05 / 1.56% | 1.2× |
| 942 | 1.65% | 1.59% | 1.0× |

Median across all 21 is 0.6× — i.e. *normally* the desk's stop is tighter
and binds first, which is the healthy design. **The failure is the tail,
and the tail was invisible.** 960 was carrying a 2.9× gap live while this
was being written.

**Solution shipped (AI-first, two parts):**

1. **Perception plumbing — `_brake_distance_line`** (`run_engine.py`). Code,
   because the desk genuinely *cannot* compute this: it has no access to
   `peak_total_pnl`, `max_loss_usd`, or total notional. Renders the
   remaining equity room and that room as a price move at the current
   position size. Wired on **both** decision paths beside
   `_hold_streak_line`. Reads `retire_drawdown_frac` from `run_feedback`
   so it can never drift out of sync with the rail it describes. Fact
   only; fail-soft to `""` on a flat book, stale mark, or missing stop.
2. **Judgment — `risk-reward-structure`** gains the reconciliation clause:
   check the rail against your authored stop, and treat an add as a
   **tightening of the rail**, not merely more exposure. *Extended the
   existing skill rather than adding a 35th*, deliberately consistent with
   the attention warning above.

**Live on prod after deploy:**
```
960 SI    rail 2.59%   (authored stops have been 3.05% — the gap is now visible to it)
972 SLV   rail 8.82%   (comfortable)
949/961/968/969  flat  → no line, as designed
```

> **The most important verification finding:** unwiring the light path
> **passed the entire suite — 3313 tests.** A brief line that renders
> correctly but is never concatenated into the prompt is a no-op, the same
> class as the `liquidation-defense` "flag with no executor" lesson. Both
> wiring sites now have a dedicated test, and all three mutations were
> confirmed to bite (unwire-light, unwire-full, drop-the-drawdown-term).
> **Any future brief line must ship with a wiring test.**

Pipeline: 7 new tests → 3 verified mutations → ruff clean → **3315 passed**
→ build → **82 tests OK in-image** → sha256 drift guard (prod == parent
`6492d14` on both files) → swap → verified on live runs.

#### FIRST BEHAVIORAL OBSERVATION — no change yet (1 cycle, not a verdict)

Run 960 SI, cycle 17 at **20:58:26Z** — the first decision whose prompt
carried the Risk rail line (composed block verified at 20:49Z).

| | |
|---|---|
| rail shown to it | **2.59%** |
| stop it authored | **3.05%** (its habitual value, unchanged) |
| invalidation it named in its report | **"$60"** = entry 62.21 → **−3.55%** |
| action | hold, conviction 0.765 |

**The desk read the rail and still planned around a level outside it.** Its
stated invalidation at −3.55% will never be reached: the rail retires the
run at −2.59% first. This is precisely the failure the clause targets, and
on cycle 1 it did not bite.

Two candidate reasons, both worth testing over the next cycles:
1. **It was a HOLD, not a size/add decision.** The clause says "reconcile
   the two every time you size or add" — a hold may simply not be a strong
   trigger, and the desk restated a habitual stop rather than authoring a
   fresh one.
2. **Attention dilution** — the clause is one paragraph inside a 30-skill,
   30KB block. This is the concern flagged above about the fourth budget
   raise, and this observation is the first evidence FOR it.

Per the standing rule, a fresh skill gets **2+ cycles** before judgment. But
if the next rail-carrying decisions also show authored stops outside the
rail, the escalation is NOT another clause — it is either (a) putting the
reconciliation into the light prompt's own bracket instruction, where the
desk is actually asked for stop_pct, or (b) pruning the catalogue so the
lesson is not competing with 29 others.

---

### FINDING 2 (original WATCH-only note, superseded above)

971 is the **first `drawdown_brake` retirement since at least 08-01** —
one occurrence, so logged, **not acted on**.

- Cycle 1 (15:32Z) bought 5.8393 ZEC @ 520.01.
- Cycles 2–5 held (conviction 0.60–0.73).
- **Cycle 6 (19:19Z) added 9.9722 units @ 520.87** — position went
  **2.7×**, on a legitimate read (conviction 0.7325, price above entry —
  adding to a winner, not a loser).
- 45 min later the brake fired: `drawdown 64.28` vs `max_loss 85.26`.
- Final **−58.18 on a −0.62% price move**.

**The shape:** at post-add notional (~8,230) a **1% adverse move consumes
~96% of the run's entire loss budget.** The desk sized the add from
conviction with no visibility that adding moved its own brake from ~1.7%
away to ~0.6% away — *inside routine ZEC daily range*. This is the
noise-floor lesson (#231) restated at the **size** level rather than the
**stop** level: the brake became a noise-trigger. Without the add the same
move leaves the run near −20 against an 85.26 budget — **alive**.

If a second brake-retirement shows the same add-then-brake shape, the
AI-first fix is a skill teaching the desk to price its add in *"how far is
my brake now, in percent"* terms — which likely needs a brief line
supplying the number, the way #241 supplied the Streak count.

### Confirmed working

- **Docs (brief item 4):** all four render authenticated —
  `how-it-works-en` 200/34,991b, `how-it-works-ko` 200/38,496b,
  `liq-defense-en` 200/45,783b, `liq-defense-ko` 200/51,896b. Public
  `/docs/how-it-works` and `/automation` 200; `/api/health` 200.
  *Correction to prevent a future false alarm:* unauthenticated
  `/api/guide/doc/*` returns **401 by design** (`_require_login` in
  `routes_guide.py`) — the member gate, **not** a regression.
- Event stream live (last event 54 s before the check), 0 tracebacks
  post-swap, catalogue auto-upgraded (`updated_by='seed-upgrade'` 20:17:29Z).
- Confidence spreads healthy (0.60–0.73 across 971's seven cycles).

### Standing watches

| Watch | Status |
|---|---|
| (a) sub-1% desk stops | none authored this cycle |
| (b) arm intents, no executor | unchanged — blocked on owner design input |
| (c) confidence-cluster honesty | healthy |
| (d) fabricated rationales | clean |
| (e) `risk_limits` 8%/15% row | untouched, report-only |
| telemetry pymysql traceback | **no recurrence** |
| `conviction_missing` rate | **0 in 90 min** — baseline |

### Next cycle should

1. Watch newborn desks **2+ cycles** before judging #244 (fresh-skill
   rule): do new runs now survive cycle 1?
2. Fix the forced-flatten P&L blind spot (FINDING 1) — reporting integrity.
3. Watch for a second `drawdown_brake` with the add-then-brake shape.

---

## Cycle 61 — 2026-08-05 10:44Z (the streak fact moved 949 — just not toward retire; 960 braked and reviewed honestly)

DB clock 10:44:57Z. Window 09:54→10:44: 325 events, 0 tracebacks.

- **949's first read WITH the streak line (09:58): its first non-hold
  in 13 cycles** — a sell attempt at conf 0.48, gated by its bumped
  0.6 threshold; cycle 42 then held at 0.295. The fact changed
  behavior (from passive holding to attempting expression), but not
  yet to retirement. No further escalation: its scheduled `at_time`
  stop is **2026-08-06 03:47Z** — the slot resolves naturally in ~17h,
  and the AI-first ladder (clause + perception) has been fully
  delivered. The desk decides; the schedule backstops.
- **960 SI: the machinery composed well under pressure** —
  `drawdown_soft_brake` fired (adds halved), thesis review honest in
  correct units ("down 0.61% … hasn't breached the $60 invalidation"),
  hold at 0.62 with the bracket intact. −35 at read ≈ 1.4× a typical
  banked win — inside loss-aging bounds with a stop at −3%.
- **962 SOLUSDT born** (10:17, 955's slot line) — first read hold 0.45.
- **New small watch: `conviction_missing: true` ×3 in 2h** (959 c9 with
  confidence 0.0, +2 more) vs ~1/day baseline — LLM verdict parse
  failures. If the rate climbs next cycle, investigate llm_client
  timeouts vs prompt-parse.
- Ledger 08-05 unchanged: **+33.77**. Fleet 7 (949, 953, 954, 959,
  960, 961, 962).

Watches: (a)–(e) unchanged; + conviction_missing rate.

---

## Cycle 60 — 2026-08-05 09:34Z (949's real gap found: the desk cannot COUNT its own streak — streak brief shipped as #241)

DB clock 09:34:15Z. Window 09:01→09:34: 176 events, 0 tracebacks.

- **949 cycle 40: hold at conviction 0.2975** — 9th flat cycle, 2nd
  read with the clause verifiably in context. Diagnosis: the clause
  conditions on "several consecutive cycles," but each cycle's prompt
  shows only that cycle — **the desk has no way to perceive its own
  streak**. A lesson without its datum cannot fire.
- **Shipped PR #241** (AI-first: perception, not decision):
  `_hold_streak_line` joins the position/earnings/breadth briefs on
  both prompt paths — flat book + 4-plus trailing consecutive holds
  renders "Streak: you have been flat with no action for N consecutive
  cycles." Fact only; judgment stays in the skill. Fail-before ×3,
  mutation-killed, 3,286 tests green. (The background deploy job died
  silently on a GitHub API hiccup — re-ran the chain foreground.)
  Merged `e25da32`, image `20260805-holdstreak` live 09:52Z, verified
  3×: in-image module tests E=0; **the live 949 line renders "Streak:
  you have been flat with no action for 12 consecutive cycles"**; both
  containers swapped, events flowing, 0 tracebacks. 949's next read
  sees the fact.
- **960's bracket is HEALTHY**: stop 60.02 (−3.05%), target 65.98
  (+6.58%), R:R 2.16, noise-clear; margin health 0.99. Position −16 at
  read — properly bracketed risk, loss-aging is the watch.
- **961 = UBER** (us-stock), gated until the 13:30Z open.

Watches: (a)–(e) unchanged. Day remains +33.77.

---

## Cycle 59 — 2026-08-05 09:01Z (958 retired itself AT THE TOP; its replacement re-entered silver full-size and is already −14)

DB clock 09:01:11Z. Window 08:29→09:01: 161 events, 0 tracebacks.

- **958 self-retired at conviction 0.445** (08:52, retire verb) — after
  a ≈ +55 life. Its read: thesis_alignment 0.4, entry 0.3 — silver
  extended, thesis expressed, nothing left to do. This is the WIN-side
  mirror of 955's loss-side retire: the desk handing back a spent
  thesis instead of overstaying it. The flat-retirement clause (live 26
  minutes earlier) says exactly this; whether cause or coincidence,
  the behavior matches the teaching.
- **960 born as the SI replacement** (08:53) and entered FULL-SIZE on
  cycle 1: buy 84.17 @ 61.905 (conviction 0.7575, ~$5.2k notional) —
  above 958's exit prices, and already **−14.3** at read (61.735).
  A fresh thesis paying up for an extended move. NEXT-CYCLE CHECK: its
  authored bracket (stop/target), and whether loss-aging discipline
  shows if the hole deepens.
- **961 born 08:56** — no first decision yet; identity next cycle.
- 959's +0.6511 landed. Day: **+33.77** (15 closes). 949's clause-test
  read (~09:12) lands next cycle.

Watches: (a)–(e) unchanged.

---

## Cycle 58 — 2026-08-05 08:29Z (958's bank lands at +25.06; the whole fleet is flat; day +33.12)

DB clock 08:29:00Z (30-second window — the firing chased the deploy
verification; gap 08:04→08:28 back-filled by query).

- **958's full-position bank landed: +25.0647** (cycle-56 estimate
  +24.8). Day ledger: **+33.12** (14 closes) — the first solidly green
  day since 08-03, and the win/loss shape points the right way: largest
  win +25.06 vs largest loss −1.33 today.
- 959 closed its USDJPY long @ 157.747 (+0.5 net pending) at 0.49 —
  quick clean forex scalp. **The entire fleet is now flat**: 5 runs
  (949, 953, 954, 958, 959), zero open positions.
- 949 cycle 39 (08:27:45, seconds after the flatretire swap): hold at
  conviction 0.265 — 8th flat sub-0.35 cycle. The clause asks for
  "several consecutive cycles" judgment, and this was its first read
  with the clause; 2-cycle bar before judging (next reads ~09:1x).
- 0 tracebacks.

Watches: (a)–(e) unchanged. Due today: us-stock desks at 13:30Z open
(953 post-print behavior under the new post-print clause; PLTR desk
day 2 of +29.5%).

---

## Cycle 57 — 2026-08-05 08:04Z (949's retire-reluctance confirmed at cycle 38 — flat-retirement clause shipped as #238)

DB clock 08:04:41Z. 22-minute window: 104 events, 0 tracebacks, one
decision — which was the case-confirming one.

- **949 cycle 38: hold at conviction 0.28** (thesis_alignment 0.2),
  flat, 7th consecutive sub-0.35 cycle, retire verb unused again. The
  2-cycle bar is met; no rail applies (idle-retire = never-traded only;
  decay/collapse rails = held positions only).
- **Shipped PR #238** (AI-first): `reentry-discipline` closes the loop
  it opened — "when standing flat has itself become the read … a desk
  with no read is not waiting, it is occupying capital another thesis
  could use. The retire verb exists for exactly this." Fail-before,
  mutation-killed, 3,283 tests green. Backend CI queue-bound at note
  time; merge+deploy chained in a guarded background job (hard-aborts
  on any hash/CI mismatch) — completed DEPLOY-DONE at ~08:26Z and
  **verified 3× at 08:28Z**: both containers on `20260805-flatretire`,
  clause renders on both sites, seed-upgrade fired on the live row,
  events flowing (MAX ts 4s behind NOW), 0 tracebacks. 949's next
  flat reads are now the clause's live test.
- Book: 959 USDJPY +0.6, all else flat. Ledger unchanged +8.06 landed,
  958's +24.8 still pending adapt.

Watches: (a)–(e) unchanged.

---

## Cycle 56 — 2026-08-05 07:42Z (the fleet prunes itself clean; 958 banks +24.8 in 44 minutes)

DB clock 07:42:09Z. Window 06:34→07:42: 368 events continuous, 0
tracebacks.

- **957 adapt-retired** (06:46, 3 consecutive losses, 24h ETH cooldown,
  flatten −1.33). Review honest in correct units ("−0.14% return …
  falling short of the anticipated 2% downside"). That makes THREE
  retires in ~3 hours — 944 thesis_invalidated, 955 desk_retired (the
  skill-driven one), 957 consecutive_losses — each by a different
  mechanism, each with a rationale matching its data. The fleet is
  pruning dead short-theses instead of feeding them.
- **958 re-entered silver full-size and banked the whole position**:
  buy 84.42 @ 61.72 (conviction 0.7675, momentum 0.9), sell ALL @
  62.02 44 minutes later ≈ **+24.8**. Its day total heads toward ≈ +55.
  Note the style change: whole-position exit rather than laddering —
  its call, and with silver this extended, defensible.
- **949 is now the visible gap**: flat, conviction 0.24–0.29 for ~6
  cycles, but it HAS traded in its life so idle-retire (never-traded
  rail) can't collect it, and the retire verb — offered every flat
  cycle — goes unused. If it stays sub-0.35 flat through next cycle,
  this becomes a case: retire-verb reluctance on an exhausted thesis
  (candidate skill clause, AI-first per the standing rule).
- 959 USDJPY long +0.3, holding at ~0.5 conviction. Ledger 08-05:
  +8.06 landed (13 closes), 958's +24.8 pending → day ≈ +33. Fleet 5
  running.

Watches: (a) none; (b) arms 36; (c) 0.25–0.68 spread clean; (d) clean;
(e) open.

---

## Cycle 55 — 2026-08-05 06:34Z (first behavior change under the new skills: 955 chose RETIRE over a third same-direction attempt; 958 completed a +30 life; ledger gap reconciled to the cent)

DB clock 06:34:31Z. Window 04:24→06:34: 985 events continuous, 0
tracebacks.

### The skills are visibly working

- **955 self-retired via the retire verb** (06:31, `desk_retired`,
  conviction 0.31). After two losing closes short (−3.32, −17.6) its
  cycle 22/23 sell reads were gated; on cycle 24 — with
  `reentry-discipline` in its prompt — it did NOT attempt a third
  same-direction entry: it handed the slot back. First live instance of
  the taught pattern replacing the churn pattern.
- **944 retired via thesis_invalidated** (04:49) with an honest,
  correct-units review: "net loss despite a high win rate — the
  anticipated downward move did not materialize." 24h BTC cooldown.
- **958 completed its silver life flat at ≈ +30**: banked legs of
  +2.78/+1.79/+1.37 this window, the final exit via the WATCHER at
  61.43 (the trailing rail selling the top tick of the move so far).
  Entry 59.65 → exits laddered to 61.43, six banks, every one on a
  fresh high, zero losing legs. This is the ledger shape the catalogue
  teaches, demonstrated end to end.

### The 944 reconciliation (owed from last cycle): bookkeeping, not a leak

adapt-realized sum −14.79 vs equity −17.457: gap = **2.663** = exactly
the sum of the three ENTRY-side fees (1.30 + 0.817 + 0.546). adapt
`realized` nets only exit-side fees; the equity ledger charges both
sides. Resolved to the cent — no leak.

### Rest of window

- 959 USDJPY entered long 10.27 @ 157.671 (conf 0.58 > 0.5 gate,
  cycle 2) — +0.5 at read. 957 covered half its ETH short (≈ −1.3
  pending), holds 0.217. 949 HYPE conviction sank 0.42 → 0.24 while
  flat — a desk running out of thesis; retire-watch.
- Ledger 08-05: **+9.39** (12 closes). Fleet 7 running.

Watches: (a) no sub-1% authoring this window; (b) arms 36; (c)
0.25–0.62 spread clean; (d) clean — both retire rationales match data;
(e) open.

---

## Cycle 54 — 2026-08-05 04:24Z (958 keeps laddering silver; 959 USDJPY born; 944 flat)

DB clock 04:24:28Z. 9-minute window: 87 events, 0 tracebacks.

- **958 SI banked leg 5** @ 61.035 on another fresh high (+5.77 landed,
  +2.8 pending; run realized ≈ +24 and counting). Every reduction has
  been on a new milestone — within the exit-discipline clause. Holds
  2.01 (+2.8). The one desk showing the right ledger shape, compounding.
- **959 USDJPY born 04:21** (forex, gate 0.5 — first forex desk since
  the fee-infeasible purge; its thesis passed the build hurdle). First
  read: buy at 0.42, honestly gated. Watch its fee-vs-move math.
- 944 covered its final BTC residual @ 64108 (04:05, ≈ +0.2 gross) —
  flat, cycling. Run life realized −17.46 over 12 trades.
- Ledger 08-05: +3.30 (8 closes). Book: SI +2.8, ETH short −0.2.
- First decisions under the FULL 34-skill set land from ~05:00 (the
  04:2x reads ran on prompts built at deploy boundary).

Watches: (a) no new sub-1% authoring; (b) arms 36; (c) 0.42–0.73 spread
clean; (d) clean; (e) open.

---

## Inter-cycle ship — 2026-08-05 04:15Z (the case library's untaught patterns → #233; owner's AI-FIRST rule saved to memory)

Owner asked what monitored cases could still be made into desk knowledge,
then set the standing rule: **"from now all monitoring and get required
fix or modify then thinking for solving by sooppiy AI first"** — saved to
memory (`decisions-become-skills`, strengthened). Reconciled the
monitoring case library against the catalogue; three observed patterns
had no skill. Shipped as PR #233 (`74a30bc`, image `20260805-caselib`,
live 04:13Z):

- **`loss-aging` (NEW, light+trader)** — 949 HYPE: −4.6 → −8.9 → −14.5
  across ~12h of individually-defensible holds, then capitulation at the
  worst price. Holds on an aging loss now carry escalating named burden
  of proof; "would I open this position now?"; three deteriorating
  cycles with no action = a decision by default.
- **`reachable-exits` + entry-churn clause** — 956's four identical
  refused brackets: two refusals ⇒ re-derive or stand down.
- **`earnings-preview` + post-print clause** — SPCX's +9.4% gap resets
  the map; pre-print levels stale; neither chase nor reflex-fade.

Verified 3×: image unittest EXIT=0; all three clauses render live
(loss-aging/entry-churn on light, post-print on light/us-stock);
seed + 2× seed-upgrade rows; events flowing; 0 tracebacks. **34 skills.**

---

## Cycle 53 — 2026-08-05 03:35Z (2-minute window right after the #232 deploy)

DB clock 03:35:50Z. 17 events, 0 tracebacks, no decisions yet under the
new skills — the first post-#232 reads land next cycle.

- Ledger 08-05 now **−11.31** (6 closes — 955's stop-out and 957's cuts
  all posted; matches cycle 52's ≈ −11 projection).
- Book all green at read: 958 SI +11.5 (silver running), 957 ETH +0.4,
  944 BTC +0.27.

---

## Inter-cycle ship — 2026-08-05 03:34Z (owner redirect: "must be thinking and act by sooppiy AI" — the −57 day's lessons land as desk skills, #232)

After the −57 decomposition, the owner approved fixes 1/2/3 and then
redirected: no hard platform gates — the sooppiy AI must think and act;
and losses cannot be fixed to 100%. The in-flight code-rail build was
dropped; the lessons shipped as skills instead (PR #232, `a825d66`,
image `20260805-deskskills`, live 03:31Z):

- **`reentry-discipline` (NEW, light+trader)**: two losing closes in one
  direction on one symbol within a day flip the burden of proof —
  re-entry needs materially NEW evidence; "feeling more confident is not
  new evidence; the entries that lost were also confident." (955/957's
  short→cut→short→cut pattern.)
- **`exit-discipline` + ledger-SHAPE clause**: bank early and small ⇒
  cut early and small; a loss several times the typical banked win has
  already spent those wins. (Five banked wins surrendered to two
  oversized losses.)

The 1/2/3 solution map (all desk-side now): (1) noise stops → #231;
(2) same-direction re-entries → #232; (3) 8/15 defaults → #228's
authorship clause (the AI authoring its own bracket makes the default
row irrelevant). Verified 3×: image unittest EXIT=0; both skills render
live both sites (11,320/22,769 chars); seed + seed-upgrade rows
confirmed; events flowing; 0 tracebacks. 33 skills in catalogue.

---

## Cycle 52 — 2026-08-05 02:28Z (WATCH (a) FIRED: second sub-1% stop-out — skill shipped as #231; the rail design goes to the owner)

DB clock 02:28:51Z (ship completed 02:51Z). Window 01:44→02:28: 334
events continuous, 0 tracebacks.

### 955's SOL short: collected by its own 0.65% stop

- The 01:14 entry authored `stop_pct 0.65, target_pct 1.3` — and the
  rails' notes show the desk originally authored a **negative target**
  (−3.07) that was rescued to the bare 2:1 minimum. Tightest legal
  bracket, maximally noise-vulnerable.
- 01:59:25: cover 30.5 @ 74.069, `client_order_id: null` (the watcher,
  not a cycle) — a **+0.74% wiggle**, inside SOL's routine hourly
  range, realized ≈ **−17.6**. Second casualty of the class after 941's
  −8.045 (949's 0.95% authoring sat between them, unexecuted).
- **Acted per the pre-registered watch — shipped PR #231** (`245d52e`,
  image `20260805-noisefloor`, live 02:49Z): risk-reward-structure
  (light+trader) now names the too-NEAR failure mode: "a stop inside
  the symbol's routine per-cycle range is a noise-trigger, not
  protection… walk away rather than shrinking the stop to fit."
  Verified 3× (image unittest EXIT=0; clause renders both sites live;
  seed-upgrade fired; events flowing, 0 tracebacks).
- **Why no code rail tonight**: order_params' monotone rule forbids
  loosening an authored stop (the module raises TARGETS, never stops),
  and refusing these entries risks recreating the 956 refusal-churn
  class. The design choice — volatility-aware stop floor vs
  rr_floor-style refusal — is the owner's call; it interacts with the
  open 8/15-row question (both are bracket-geometry sanity).
- Watch (a) evolves: now watching for sub-1% authoring persisting
  DESPITE the skill (2-cycle bar applies before judging it).

### The window otherwise

- 958 SI's +4.5448 landed (predicted +4.59 ✓); it HELD its 16.1
  remainder at 0.65 conviction without a milestone-less 4th reduction —
  inside the exit-discipline clause. +7.0 at read.
- 957 cut half its ETH short @ 1876 (≈ −4.0 pending) at conviction
  0.355 — small, fast, honest. 944's +0.5861 landed; residual −0.3.
- Ledger 08-05: **+10.71** (4 closes) before 955's −17.6 and 957's −4
  land — expect ≈ −11 after they post.

Watches: (a) FIRED + acted, evolved as above; (b) arms 36; (c)
0.30–0.65 spread clean; (d) clean; (e) open — now joined by the
stop-rail design question.

---

## Cycle 51 — 2026-08-05 01:44Z (957 re-enters; 955's fresh short already −11 against)

DB clock 01:44:11Z. 20-minute window: 153 events, 0 tracebacks.

- 957 re-shorted 0.869 ETH @ 1866.7 (conf 0.58 > bumped 0.55, size
  0.75× per its adapt tightening) — the loop shrinking its bets after
  the −5.69 cut, as designed. −2.7 at read.
- **955's SOL short moved −11.3 against it in 30 minutes** (73.525 →
  73.896, +0.5%). Its 0.65-conviction entry is being tested
  immediately. Its book, its exits — but this is the position to watch
  next cycle; the trailing/stop rails and cycle-18 read arrive before
  02:15Z.
- 949 held at 0.3025 conviction (risk_context 0.25) — flat and honest.
  953 SPCX +9.4% hot_issue re-fire (daily basis), desk flat.
- Book: SI +2.1, SOL −11.3, ETH −2.7, BTC +0.06. Ledger 08-05: +5.58.

Watches: (a)–(e) unchanged.

---

## Cycle 50 — 2026-08-05 01:24Z (955's brake released at 0.65; 958 ladders a third time; +5.58 on the day)

DB clock 01:24:26Z. 15-minute window (early fire): 116 events, 0
tracebacks.

- **955's post-loss brake released correctly**: after five gated sell
  reads (0.45–0.56 vs its bumped 0.60), the desk's conviction reached
  **0.65** and the entry went through — short 30.5 SOL @ 73.525. That
  is the adapt loop doing exactly what it's for: not blocking forever,
  blocking until the read strengthens.
- **958's +4.7384 landed** (cycle-49 prediction ≈ +4.6 ✓), then it
  banked another half @ 59.935 (+4.59 pending) on a fresh price high.
  Ladder: 64.5 → 32.2 → 16.1, each reduction on further progress —
  within the exit-discipline skill's "fresh milestone" clause so far;
  will flag if it reduces again without one.
- Book: 958 SI long +3.9, 955 SOL short −3.8, 944 residual +0.3.
  Ledger 08-05: **+5.58** (2 closes).

Watches: (a)–(e) unchanged; TSLA/NVDA cooldown check still due at the
open.

---

## Cycle 49 — 2026-08-05 01:09Z (day roll; 958 SI born and laddering; 08-04 closes at −20.61)

DB clock 01:09:48Z. Window 23:41→01:09 (spans midnight): 642 events
continuous, 0 tracebacks.

- **958 SI (silver futures) born 23:49** — traded on cycle 1 (long 64.5
  @ 59.65, conf 0.68), then **banked half on cycle 2** @ 59.80 (conf
  0.73, ≈ +4.6 pending). Second consecutive post-#230 build to act
  immediately. Holds 32.2 long, +7.6 at read.
- **08-04 closed at −20.61 realized** (36 closes). The honest shape of
  the day: −14.47 HYPE capitulation + −5.69 957 fast cut + small cut
  losses, against many small banks. (956's −31 sits in equity, not in
  the adapt ledger — its flatten wasn't adapt-journaled.)
- 957's −5.6881 adapt landed (cycle-47 estimate was −6.5 — 0.8 off on
  fee/qty detail; noted for calibration honesty).
- **944 laddered its BTC short down**: +0.8415 landed (predicted ≈+0.9),
  then covered half again @ 63921 (+0.65 pending). Residual 0.0024
  short (+0.5). Textbook ladder exit on a small book.
- 955's sell reads (0.55, 0.56) still gated by its bumped threshold;
  949 flat at 0.385–0.4725. Honest holds.
- 08-05 ledger opens **+0.84**.

Watches: (a) no stop-outs; (b) arms 36; (c) 0.40–0.73 spread clean;
(d) clean; (e) open. TSLA/NVDA cooldown check due at the open.
