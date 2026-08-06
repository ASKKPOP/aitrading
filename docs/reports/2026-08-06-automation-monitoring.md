# Automation monitoring — 2026-08-06 (UTC day)

**Loop RESUMED by the owner 2026-08-06 ~05:47Z** — new cadence: **30-minute
cycles** (cron `6f554382`, `13,43 * * * *`) + the unchanged **24-hour
verification sweep** (cron `947fea0d`, 08:07 local = 15:07Z, KST day
boundary). Both session-only; re-arm per HANDOFF §1. Predecessor:
`2026-08-05-automation-monitoring.md` (cycles 49–74 — note: cycles 62–74,
which fell on UTC 08-06, were appended there before the roll; this file
starts at cycle 75).

Owner's standing questions each cycle: working per plan? losses and WHY
(RUN AI reading)? what we missed? how-it-works + plan-16 docs healthy?
Suggestions + shipped solutions.

---

## Cycle 101 — 2026-08-06 20:29Z (prod DB clock) — THE DIAGNOSED PROBLEM NOW HAS A VISIBLE COST

⚠️ **A cycle was missed.** 70 minutes since cycle 100 — the ~19:43 firing
did not land because the session was mid-investigation. Documented
idle-only cron limitation (§1), not a new fault.

**1. Working per plan?** The platform, yes — `20260806-floorstatus`,
**0 tracebacks**, docs 200/200. **The fleet, no: it is now 2/10.**

**2. Losses and WHY.** Ledger **−93.67 → −97.83** (−4.16), fully
attributed:

| run | event | realized |
|---|---|---|
| 978 ETHUSDT | `adapt_retired / consecutive_losses` 19:40, then flatten | −0.14 (final **−6.38**) |
| 977 GC | sell 0.495024 @ 4298.100098 at 20:01:20 | **−4.01** |

978 was the third run today retired by the **consecutive-losses rail** —
after 975 and 979. The rail keeps working; it is the only thing reliably
closing losers.

**3. The structural finding from cycles 97–100 now has a measurable
outcome.**

**The fleet has gone from 8 runs this morning to 2**, and the replenish
loop cannot refill it:

| | |
|---|---|
| fleet target | 10 |
| running | **2** (972 SLV +1.43 flat, 977 GC +0.81) |
| cooldowns blocking crypto/futures | SOLUSDT, HG, BTCUSDT, SI, **ETHUSDT** (new) |

Each retire adds a 24-hour cooldown, which removes that symbol from a
universe of ~12 — so **the fleet's own losses shrink the pool it needs to
recover from.** That is the compounding shape behind the diagnosis, and
it is now visible in the run count rather than only in the logs.

**✅ Cycle 100's prediction confirmed.** I wrote: *"ZBTUSDT is selectable
again, so the unpriceable skip loop from cycle 97 should resume."* It
did — skips went **276 → 365**, latest 20:01:30.

**4. Docs.** Both 200.

**5. Shipped: nothing.** The diagnosis is complete (cycle 100) and the
remedy — widen the research universe or lower the fleet target — is a
design decision. What changed today is the **urgency**: this is no longer
an idle-slot inefficiency, it is a fleet emptying itself.

*Watch:* if 972 and 977 close without replacements, the fleet reaches
**0/10** and stops trading entirely.

---

## Cycle 100 — 2026-08-06 19:19Z (prod DB clock) — ROOT CAUSE REFINED, AND CYCLE 99 PARTLY CORRECTED

**1. Working per plan?** Yes. `20260806-floorstatus`, **0 tracebacks**,
docs 200/200, ledger **−93.67**. **Fleet down to 3 runs** (972 SLV, 977
GC, 978 ETHUSDT) from 8 this morning.

**961 UBER idle-retired at 19:05:59** — the run that never traded. It hit
its 12 worked cycles and the rail collected it. **Exactly what cycle 94
predicted**: *"a us-stock run can hold a slot 31+ hours before the rail
can even consider it."*

**2. Losses.** −0.57 this beat, immaterial.

**3. A new batch reproduced the pathology within 30 minutes — with ZERO
buildable candidates.**

`research:496122` arrived. Applying the filters:

| status | symbols |
|---|---|
| cooldown | SOLUSDT, HG, BTCUSDT |
| running | GC, ETHUSDT |
| unpriceable | **ZBTUSDT (back again)** |
| negative expectancy | NVDA, SNOW |
| **buildable** | **none** |

496121 and 496122 share **7 of 8** selectable symbols. Across eight
consecutive batches (496115→496122) the universe is a fixed rotation —
CHFJPY, ETHUSDT, HG, NVDA and SNOW appear in **all eight**.

**4. ⚠️ CORRECTING MYSELF MID-INVESTIGATION.** I found that batch 496122
holds **12** theses but only **8** are `selectable`, and that the four
excluded — DIS, PYPL, CHFJPY, USDKRW — were precisely the ones neither
running nor cooling. I was forming the conclusion *"the filter excludes
the usable symbols."* **That reading is wrong, and checking the reason
killed it.**

`selectable = ev_pct > 0 AND expressible AND feasible`. The four:

| symbol | score | why excluded |
|---|---|---|
| **DIS** | **0.983** (2nd best) | us-stock **SHORT** — a spot-only book cannot express it |
| PYPL | 0.582 | long, +EV, fails the **R:R feasibility** floor (3.0% move) |
| CHFJPY | 0.422 | short, 1.0% move — same R:R floor |
| USDKRW | 0.323 | short, 1.0% move — same |

**Every exclusion is legitimate.** `selectable` is doing its job, and
"score" was never the criterion — DIS outscores six selectable symbols
and is still correctly refused.

**THE REFINED ROOT CAUSE.** Cycle 99 said *"research and the cooldown
list are not coordinated."* True, but not the binding constraint. The
sharper statement:

> **The research universe — roughly 12 symbols per batch, heavily
> repeated across batches — is too small to sustain a 10-slot fleet.
> The fleet's own holdings (3) plus its 24-hour cooldowns (5) plus
> structural infeasibility (one un-shortable spot thesis, three
> sub-R:R moves) consume the entire batch. Nothing is left over.**

It is not one broken component. It is a **universe-size problem**: every
gate is correct, and correct gates over a 12-symbol rotation leave zero.

**5. Docs** 200/200. **Shipped: nothing.** The fix is to widen what
research covers, or to shrink the fleet's target — both are the owner's
call, and neither is a patch. Coordinating research with cooldowns
(cycle 99's suggestion) would help at the margin but **cannot create
symbols that are not in the universe**.

*Prediction to check next cycle:* ZBTUSDT is selectable again, so the
unpriceable skip loop from cycle 97 should resume.

---

## Cycle 99 — 2026-08-06 18:49Z (prod DB clock) — ✅ ROOT CAUSE FOUND: RESEARCH PROPOSES WHAT THE FLEET JUST RETIRED

**1. Working per plan?** Yes. `20260806-floorstatus`, **0 tracebacks**,
docs 200/200, ledger **−93.10**, 4 runs live.

**2. Losses.** −0.21 this beat, immaterial.

**3. ✅ THE TOP ITEM IS SOLVED — full causal chain, verified read-only.**

Cycle 98 narrowed it to *"the filter is between thesis and candidate."*
It is `symbol_research.select_targets`, and here is the whole chain:

**Step 1 — only ONE batch is ever eligible.** `select_targets` takes the
*newest* batch with live selectable theses and reads **only that batch**:

```sql
SELECT batch_id FROM research_theses WHERE selectable = 1
AND expires_at > ? ORDER BY batch_id DESC LIMIT 1
```

So "200 theses across 21 symbols today" was never the pool. The pool is
one batch.

**Step 2 — that batch holds 8 theses.** `research:496121`:
SOLUSDT, HG, BTCUSDT, NVDA, ETHUSDT, SNOW, GC, AVGO.

**Step 3 — 5 of those 8 are symbols the fleet definitionally cannot
use:**

| symbol | why unusable |
|---|---|
| SOLUSDT, HG, BTCUSDT | in 24h cooldown — **this fleet retired them today** |
| ETHUSDT, GC | currently running |

**Step 4 — 3 remain** (NVDA, SNOW, AVGO), and the backtest gate correctly
refuses NVDA (−200.50 USD/trade over 9 trades) and SNOW (−72.43 over 6).

**Confirmed by direct read-only call:**
`select_targets(agent 6, depth=10, exclude=∅, all six markets in scope)`
→ **3 rows: NVDA, SNOW, AVGO.** Depth 10 was requested. Market scope and
the exclude set are both eliminated as causes.

**THE ROOT CAUSE, stated plainly: research and the cooldown list are not
coordinated. The fleet retires a symbol on a loss, the symbol enters a
24-hour cooldown, and research keeps proposing that same symbol — so the
usable pool collapses to whatever is left.** 63% of the newest batch was
unusable before the gate even looked.

This is not the backtest gate misbehaving, not cooldowns being wrong, and
not thin research. Each part is doing its job; **they are not talking to
each other.**

**4. Docs.** Both 200.

**5. Shipped: nothing — and this one genuinely needs a decision, not a
patch.** The obvious fix (feed the busy/cooldown set into research
targeting so it proposes usable symbols) is a change to how the platform
chooses what to research. That is a design decision with real
consequences — it would bias research away from recently-traded symbols
permanently — and it is not mine to make unilaterally at 18:49 on a day
that has already taken five ships.

**→ RECOMMENDATION for the owner:** pass the agent's busy + cooldown set
into `symbol_research`'s target selection so a batch is not 63% dead on
arrival. Second-order option: let `select_targets` fall back to older
still-unexpired batches when the newest yields too few eligible rows —
smaller change, keeps research untouched.

*#264 still blocked* — Security runners unavailable after a third rerun.

---

## Cycle 98 — 2026-08-06 18:19Z (prod DB clock) — THE FLEET THREAD, PULLED

**1. Working per plan?** Yes. `20260806-floorstatus`, docs 200/200,
ledger **−92.89 unchanged**, 4 runs live.

**One traceback** — a **MySQL deadlock (1213)** on a single equity
heartbeat for run 978 at 18:10:04. `emit_telemetry_event` **caught it and
logged a warning**, which is the intended fail-soft behaviour for
telemetry; no cycle broke and the next heartbeat wrote. **One occurrence
in 57 days of MySQL uptime and 46.5M queries** — recorded as a singleton,
not a pattern.

**2. Losses.** None this beat.

**3. ✅ Cycle 97's prediction confirmed within 30 minutes — and it
retires the fix I declined to ship.**

I wrote yesterday-hour: *"Fixing (a) would stop the futile build attempts
and make the reason honest, but it would NOT fill a single slot — the
gate would simply report `kept: []`."*

**That is now literally the log:**

```
18:19:07  backtest_gate  kept: []
          dropped: NVDA −200.50 USD/trade, SNOW −72.43 USD/trade
```

ZBTUSDT aged out of the pool on its own (skips stopped at **276**), the
gate reports `kept: []`, and the fleet is **still 3/10**. **Declining the
priceability patch was correct** — it would have changed the log line and
nothing else.

**4. What the thread actually leads to — and it is NOT cooldowns.**

I expected the 24-hour symbol cooldowns from today's retires to explain
the empty slots. **They do not.** Measured:

| | count | |
|---|---|---|
| symbols researched today | **21** | 200 theses |
| in active cooldown | 5 | BTCUSDT, HG, SI, SOLUSDT, ZECUSDT |
| busy (already running) | 3 | ETHUSDT, GC, SLV |
| **available** | **13** | AVGO, BICOUSDT, CHFJPY, DIS, HYPEUSDT, LABUSDT, NG, NVDA, RIVN, SNOW, USDJPY, USDKRW, ZBTUSDT |
| **actually reaching the gate** | **2** | NVDA, SNOW |

**Thirteen symbols are available and two are offered.** The bottleneck is
between "thesis exists" and "candidate presented to the gate" — not
research supply (200 theses/21 symbols today), not cooldowns, and not the
gate itself, which is correctly refusing two proven money-losers.

Also relevant: **no `fleet_candidates` row has been created since
08:53:59** — 9.5 hours.

**5. Shipped: nothing, and I am stopping at the honest boundary.** What
filters the other ~11 symbols is in the replacement-candidate selection
path (the gate events carry `context: "replacement"`). Reading that
properly is a code investigation, not a monitoring beat, and I would
rather hand forward a sharp question than a half-read answer at the end
of a long session.

**→ TOP ITEM, now much sharper than cycle 97:** *13 available symbols, 2
offered. Find the filter between thesis and candidate in the
`"replacement"` path.* Cooldowns, research supply and the backtest gate
are all **eliminated** as causes.

*#264 still blocked* — Security runners unavailable after a third rerun.

---

## Cycle 97 — 2026-08-06 17:49Z (prod DB clock) — 🚨 THE FLEET HAS BEEN STUCK AT 3/10 FOR 4.5 HOURS

**1. Working per plan?** The runs, yes — **0 tracebacks**, docs 200/200,
ledger **−92.89 unchanged**, one event in the whole beat (978 hold).
**The fleet, no.**

**2. Losses.** None this beat. But **capital is idle**, which the P&L does
not show.

**3. 🚨 THE FINDING — fleet 27 is `replenishing:3/10` and has built
NOTHING for 4h31m.**

`[FleetPlanner] tick: {'claimed': 1, 'researched': 0, 'built': 0,
'supervised': 1}` on every tick. The cause is a deterministic loop:

```
backtest_gate   kept: ["ZBTUSDT"]
                dropped: NVDA  −200.50 USD/trade over 9 closed trades
                         SNOW   −72.43 USD/trade over 6 closed trades
candidate_skipped  slot N, ZBTUSDT:
   "no price available for ZBTUSDT (crypto) — an unpriceable symbol
    cannot be traded or stop-checked"
```

**Every empty slot draws the same sole survivor, and that survivor cannot
be priced.** Measured: **271 skips between 13:18:38Z and 17:49:51Z**,
across slots 2, 3, 6, 8, 9…

**ZBTUSDT is genuinely untradeable, not a casualty of the freeze.**
Verified directly: `Hyperliquid symbol not listed: ZBTUSDT -> ZBT`, while
BTCUSDT (64599.5) and SOLUSDT (73.1165) price fine.

**Two separable problems, and I want to be precise about which is which:**

**(a) An ordering defect.** `fleet_planner` runs a chain of build-time
feasibility checks — `thesis_expired`, `symbol_busy`,
`_thesis_fee_infeasible`, `_bucket_expectancy_block` — each with the
explicit rationale *"decide once, before the run exists."* **Priceability
is not among them**; it fails later, at run creation
(`routes_runs.py:462`). This is a **seventh instance** of the documented
infeasible-at-build class.

**(b) The real reason the slots stay empty — candidate SUPPLY.** The pool
is **three symbols**. One is untradeable, and the other two were dropped
on measured negative expectancy. **Fixing (a) would stop 271 futile build
attempts and make the reason honest, but it would NOT fill a single
slot** — the gate would simply report `kept: []`.

**4. Docs.** Both 200.

**5. Shipped: nothing, deliberately — and the reasoning matters.** The
priceability filter is well-evidenced (271×) and low-risk, but it is a
**partial** fix: it removes waste and restores honest reporting without
addressing why 7 of 10 slots have no viable candidate. Shipping the easy
half at the end of a long session would leave the fleet exactly as idle
while looking addressed. **Research is proposing symbols the exchange
does not list** — that is the thread to pull, and it deserves a fresh
look rather than a rushed patch.

**→ TOP NEW ITEM.** Recommended order: (i) add priceability to the
build-time feasibility chain beside `_thesis_fee_infeasible`; (ii)
investigate why the candidate pool is 3 and why research emits unlisted
symbols at all.

*Also:* **#264 still blocked** — Security workflow runners still
unavailable after a third rerun. CI's have recovered. Not merging on red.

---

## Cycle 96 — 2026-08-06 17:19Z (prod DB clock) — ⭐ #257 FIRED, EXACTLY AS PREDICTED

**1. Working per plan?** Yes. `20260806-floorstatus` (tag compared),
**0 tracebacks**, 4 runs live, docs 200/200.

**2. Losses and WHY.** Ledger **−92.89, unchanged**. DRIFT narrowed
−32.04 → **−10.67** as the lagged adapts landed (979's −19.2239 at
17:11:35). Two runs closed, neither adding new loss:

- **968 USDKRW −3.34** on `stop_event:conviction_collapse` (17:00:49)
- **979 SI −31.17** on `adapt_retired / consecutive_losses` (17:11:35),
  the loss already booked at 16:30

Only 978 ETHUSDT still holds a position.

**3. ⭐ `pending_close` FIRED FOR THE FIRST TIME — #257's open
verification is CLOSED, positive.**

Open since cycle 84. The sequence on 968 is textbook:

| time | event |
|---|---|
| 17:00:15 | decision cycle 38, `sell`, conviction 0.275 |
| 17:00:16 | desk `reduce` 0.5 → trade signal 499 |
| 17:00:47 | equity: realized −3.351328 → **−3.346403** (**+0.0049**) |
| 17:00:48 | control pass fires `conviction_collapse` → `stopping` |
| **17:00:48** | **`adapt: pending_close` signal 498, realized +0.0049** |
| 17:00:49 | flatten leg → #249's `flatten_close` +0.0046 |
| 17:00:49 | `stopped` |

**The +0.0049 matches the equity delta to the cent**, and the flush ran
**before** the flatten leg existed as a signal — so #257 and #249 both
journalled, with no overlap. That is the design working exactly as
written.

**And it validates cycle 89's structural prediction word for word.**
That cycle argued the silence was not a failure:

> *"#257's non-null case requires a stop fired by the CONTROL pass
> (at_time, max_loss, trailing_lock, profit_target, idle/fee retire)
> while a close from the last decision cycle is still un-ingested."*

`conviction_collapse` is a control-pass stop, and it fired **32 seconds**
after the desk's reduce — before any next cycle could ingest it. Exactly
that shape.

*Worth noting:* the captured amount is **positive** (+0.0049). The flush
recovers wins as well as losses; the hole was never loss-specific.

**4. Docs.** Both 200.

**5. Shipped.** Nothing new. **#264 still blocked** — the Security
workflow's runners remain unavailable (`"The job was not acquired by
Runner of type hosted"`), while CI's have recovered (Frontend and Backend
both pass). Not merging on red. Its correction stands published:
`ratchet_audit`'s raw *"post-fix 10 survived"* contains **2 float-dust
rows**; the honest figure is **8**.

---

## Cycle 95 — 2026-08-06 16:49Z (prod DB clock)

**1. Working per plan?** Yes. `20260806-floorstatus` (tag compared),
**0 tracebacks**, 6 runs live, docs 200/200.

**2. Losses and WHY.** Ledger **−92.90, unchanged** this beat — no closes
since 16:30. A quiet half-hour after a costly one.

**The fleet is now almost entirely flat.** Only 2 of 6 runs hold a
position:

| run | symbol | realized | position |
|---|---|---|---|
| 968 | USDKRW | −3.35 | 0.005706 |
| 978 | ETHUSDT | −5.67 | 0.322224 |
| 979 | SI | **−31.17** | flat |
| 977 | GC | +5.04 | flat |
| 972 | SLV | +1.43 | flat |
| 961 | UBER | 0.00 | never traded |

979's `peak_pnl_usd` re-anchored −0.26 → −31.17 on going flat — the same
documented `_ratchet_peak_pnl` behaviour seen on 972 last cycle, not a
new loss.

**3. What we found — CI recovered PARTIALLY, and #264 is still held.**

The GitHub hosted-runner outage has cleared for the **CI** workflow:
Frontend now passes (2m55s) and Backend passes (17m7s). It has **not**
cleared for the **Security** workflow — all three jobs re-ran and failed
again with the identical annotation:

> `The job was not acquired by Runner of type hosted even after multiple
> attempts`

**#264 remains unmerged.** My diff is Python-only, adds no dependency and
no secret, so the practical risk of merging is nil — **but "the check
never ran" is not "the check passed", and I am not substituting my own
judgment for the gate.** The correction it carries is already published
(cycle 94: post-fix survived is **5**, not 6), which was the part that
mattered. Retry next cycle.

**4. Docs.** Both 200.

**5. Shipped.** Nothing — #264 blocked on infrastructure, and no new
evidence this beat.

*Watches:* the restated trigger (*lifetime peak never exceeds its own
round-trip cost AND held past ~4h*) stands at **n=2** (975, 979); both
are now closed out, so a third instance needs a fresh run.
`armed_exit` 2, `pending_close` 0 unchanged.

### Addendum, 17:06Z — two things moved during the verification pass

**(a) A rail fired that I have not seen fire before.** 968 USDKRW stopped
at **17:00:49** on **`stop_event:conviction_collapse`** at −3.34 — the
dark-shipped rail that closes a held position whose desk has read
conviction below the floor for N straight cycles. First observed firing
in this monitoring run. It behaved correctly: 968 had been holding a
losing forex book for hours.

**(b) The #264 defect is now inflating the number MORE, exactly as
expected.** `ratchet_audit` reports **"post-fix 10 survived"**. Two of
those rows are float dust from full closes:

```
972  2026-08-06T15:55:25   arm after 0.0000
977  2026-08-06T16:30:17   arm after 0.0000   <-- new this beat
```

**The honest count is 8 genuine post-fix survivals**, not 10 — of 9
genuine in-band rows, 8 post-fix survived and 1 (976) pre-fix FLATTENED.
**The over-report grows every time a run goes flat**, which is precisely
why #264 matters and why I am publishing the corrected figure alongside
the tool's raw output rather than waiting for the merge.

Fleet is down to 5 running.

---

## Cycle 94 — 2026-08-06 16:19Z (prod DB clock) — ⚠️ A NUMBER I REPORTED WAS WRONG

**1. Working per plan?** Yes. `20260806-floorstatus`, **0 tracebacks**,
6 runs live, docs 200/200. **The thaw is holding** — GC 4310.40 → 4295.30,
SI 61.535 → 61.450, USDKRW 1421.88 → 1423.68, ETH 1916.80 → 1909.20, all
moving between reads.

**2. Losses and WHY.** *(Corrected at 16:44 — the ledger moved while
this cycle's PR work was in flight, and the first draft of this line said
"unchanged".)* Ledger **−71.53 → −92.90**, a **−21.37** beat:

| time | run | leg | realized |
|---|---|---|---|
| 16:30:19 | **979 SI** | sell 20.714 @ 61.174999 vs 62.099998 entry | **−19.22** |
| 16:30:17 | 977 GC | sell 0.0824 @ 4284.700195 | −2.14 |

972 SLV also fully exited at **55.180099** — a real price, not the frozen
56.07 — banking **+1.43**. Its `peak_pnl_usd` re-anchored 8.63 → 1.43 on
going flat: documented `_ratchet_peak_pnl` behaviour, not a loss.

**979 is now −31.17, and this is the sweep's own prediction playing out.**
Ninety minutes ago the sweep flagged it as *"the 971 shape happening
live — NOT ARMED, best −0.26, needs 10.21, and −9.63 open right now."*
SI fell **−1.49%** from its entry and it has lost −31.17.

**But my trigger was mis-specified, and I would rather say so than claim
a hit.** I wrote the trigger as *"notional > ~$4k, peak under ~10% of one
ordinary day, held > 4h."* 979 is **$2,573** notional — it **misses on
size** while matching the two criteria that matter:

| | 975 | 979 |
|---|---|---|
| lifetime peak | +2.84 (on $4,739) | **−0.26 — never in profit at all** |
| held | 7h18m | **7h50m** |
| notional | $4,739 | $2,573 ❌ |
| final | −38.26 | −31.17 |

**Notional is not the discriminator; "the peak never meaningfully cleared
zero" is.** The trigger is restated accordingly: *a run whose lifetime
peak never exceeds its own round-trip cost and is still held past ~4
hours.* Both 975 and 979 satisfy that; it is now n=2.

The desk is not misbehaving here. 979 reduced at 15:41 and again at
16:30 — correct partial exits. It has been told *"NOT ARMED — needs
$10.21, your best is −$0.26"* every cycle since #263 went live at 15:18.
**The loss is an entry that was never right, held long** — the same
conclusion the sweep reached for 975, now with a second instance.

**3. ⚠️ A NUMBER I HAVE BEEN CITING WAS WRONG.** `ratchet_audit` reported
**"post-fix 6 survived"** for #251. **The honest figure is 5.**

972 halved a 42.92-unit SLV book six times. Its final **full close** left
**1.47e-08** units of float dust — above the absolute `1e-12` guard in
`reduce_steps`, and functionally zero. That flat close was counted as a
*reduce* whose post-reduce arm was ~0, which satisfied the in-band test
trivially and produced a seventh row:

```
972  2026-08-06T15:55:25   arm after 0.0000   peak 1.43   arm full 4.7372
```

An absolute epsilon cannot express "essentially nothing left" for a book
whose size is unknown in advance. **PR #264** makes the guard relative
(`_FLAT_FRACTION` 1e-6): 972's residual is 1.1e-08 of its book and is
excluded; a genuine 50% reduce is 0.5 and is kept.

**This is the FOURTH time live data has caught a defect in one of these
audit tools that its own unit tests passed** — after #253's
flatten-timestamp and duplicate-status-row traps and #261's seq-vs-time
ordering. Every one came from fixtures using tidy round numbers where
prod has float residue and repeated timestamps.

**Corrected evidence: 5 genuine post-fix in-band survivals** against
976's single pre-fix FLATTENED. #251's direction is unchanged; its
magnitude is one weaker than I reported.

**#264 is NOT merged — CI is down.** `"The job was not acquired by Runner
of type hosted even after multiple attempts"` and `"Failed to resolve
action download info"` on four jobs. **The backend suite itself passed
(✓ Run pytest, ✓ Complete job)**; the others never got runners. I am not
merging on red checks. Local: fail-before 1/1, mutation 2/2, 3544 pass,
ruff clean. Re-check next cycle.

**4. What we checked and cleared.** 961 UBER has run **32 cycles over 31
hours with zero trades**, which looks like an idle-retire failure. **It is
not.** `_closed_market_cycles` correctly discounts 23 closed-market ticks,
leaving **9 worked cycles against a limit of 12**. Checked, not assumed.
(The runs the query flagged "past the limit" all hold positions, so the
idle rail does not apply to them.) It does mean a us-stock run can hold a
slot 31+ hours before the rail can even consider it — structural, and
already recorded as the dead-capital cost.

**5. Docs** 200/200. **Shipped:** #264 authored and verified locally,
merge blocked on the GitHub outage.

*Watches:* `fill_audit` frozen at 10 repeats / $12,655.93 — it stopped
growing the moment prices moved, exactly as cycle 93 predicted.
`conviction_missing` 6 of 95 (6.3%); `armed_exit` 2; `pending_close` 0.

---

## Cycle 93 — 2026-08-06 15:52Z (prod DB clock) — 🔓 THE FEED THAWED, AND THE BILL CAME DUE

**1. Working per plan?** Yes. `20260806-floorstatus`, **0 tracebacks**,
6 runs live, docs 200/200.

**2. 🔓 THE FREEZE IS OVER — after roughly eight hours.** Every Yahoo
ticker is fresh again, measured at 15:54:06Z:

| ticker | price | age |
|---|---|---|
| SPY | 768.6 | **0m** |
| BTC-USD | 64683.97 | **0m** |
| SLV | 55.265 | **0m** |
| USDKRW=X | 1422.87 | **0m** |
| SI=F | 61.53 | 10m |
| GC=F | 4308.3 | 10m |

It ended around 15:41–15:44Z. GC had been frozen since 07:57:40.

**3. The sweep's central claim was tested by events within minutes — and
it held.** Ninety minutes ago I wrote that the frozen feed *"distorts
bookkeeping, not the outcome."* **The thaw proves it.** Every price that
arrived was lower, and the concealed losses landed at once:

| run | frozen mark | real mark | move | book | revealed |
|---|---|---|---|---|---|
| 979 SI | 62.099998 | 61.535 | **−0.91%** | 20.714 | **−11.70** |
| 972 SLV | 56.07 | 55.395 | −1.20% | 1.341 | −0.91 |
| 977 GC | 4320.700195 | 4310.400 | −0.24% | 0.082 | −0.85 |
| 968 USDKRW | 1428.310059 | 1421.880 | −0.45% | 0.006 | −0.04 |
| | | | | **total** | **−13.49** |

**979 realized −11.56 on a single leg at 15:41:23** — a `reduce` 0.5 at
61.544998 against a 62.099998 entry — the instant it could see the truth.
Its realized went **−0.39 → −11.95**. It was the run flagged in the sweep
as the live 971 shape, and it was underwater the whole time.

**A note on which way the distortion ran.** Because every frozen price was
*higher* than reality and the desk was long, the **fills made at stale
prices were FAVOURABLE** — the $12,655.93 of frozen-price notional was
sold better than the market allowed. The distortion did not cost money on
those legs; it deferred it onto whatever stayed open. That is the more
precise version of "bookkeeping, not outcome", and it is worth stating
because the naive reading — "stale fills lost us money" — is wrong.

**4. Docs.** Both 200.

**5. Shipped.** Nothing, and nothing is called for: the condition
resolved itself upstream. What the episode leaves behind is evidence, not
a defect to patch — the platform's blindness to upstream staleness
(`mark_age_ok` measuring our fetch time) is unchanged and remains the
owner's call, now with a measured cost attached.

*Watches:* `fill_audit` will stop growing now that prices move; the
$12,655.93 figure is the closed record of the episode.

---

## ⏱️ 24-HOUR SWEEP (cron-fired) — 2026-08-06 15:46Z (prod DB clock)

The early sweep at 15:20Z built the ledger and shipped #263. This one does
what that one did not: **shape statistics against the §7 baseline, both day
boundaries, the regression check, and a live re-proof of every fix.**

### (5) True P&L, flatten-reconciled, both boundaries

| window | result |
|---|---|
| UTC 08-05 | **+7.09** |
| UTC 08-06 | **−70.36** |
| KST 08-05 (04T15:00Z→05T15:00Z) | closing-leg net −4.11 (wins +91.43 / losses −85.68) |
| KST 08-06 (05T15:00Z→06T15:00Z) | closing-leg net **−101.69** (wins +38.58 / losses −130.11) |

### (6) SHAPE vs the §7 baseline (55% win rate; 6/84 closes = 74% of loss)

Measured **per closing leg**, the way the baseline was measured:

| metric | UTC 08-05 (prior) | UTC 08-06 | baseline |
|---|---|---|---|
| win rate | 57% | **39%** | 55% |
| median win | +3.52 | **+0.40** | — |
| median loss | −0.90 | **−2.87** | — |
| **full closes' share of loss** | **92%** | **19%** | 74% |
| worst 6 legs' share | 93% | 69% | 74% |

**This cuts both ways and I am not going to report only the good half.**

**The exit-verb work landed decisively.** Whole-book closes carried **92%**
of all loss on 08-05 and **19%** today — well below even the 74% baseline.
That is the single largest shape improvement of the week, and #245/#253/#262
are what changed it.

**And the day still lost far more.** The loss moved out of the tail and into
the body: median win collapsed **+3.52 → +0.40** while median loss worsened
**−0.90 → −2.87** — a **7.2:1 adverse ratio** at a 39% hit rate. Per-leg
expectancy went from **+1.62** to **−1.60**.

### The confound I tested — and rejected

Four of seven runs were pricing off a frozen feed, so the honest move was to
split the day by feed health before blaming anything:

| bucket | legs | win rate | median win / loss | net |
|---|---|---|---|---|
| **crypto (LIVE feed)** | 7 | **14%** | +0.40 / **−4.69** | **−40.30 (61%)** |
| yahoo-served (FROZEN) | 26 | 46% | +0.48 / −2.20 | −26.00 (39%) |

**61% of the day's loss is in the markets whose prices are real.** The frozen
feed is *not* the explanation for the damage — it distorts the bookkeeping,
not the outcome. And **975 BTCUSDT alone is −38.26: 95% of the live-feed loss
and ~54% of the entire day.**

**975's shape:** a $4,739 notional whose lifetime peak was **+2.84** — 0.06%
of notional, or **6.5% of one ordinary day** in its favour — held 7h18m and
exited in four partial legs. **It was never right.** Not an exit failure; an
entry that never worked, held long. The exit machinery behaved correctly
throughout (partial verbs, and the arm fired for the first time ever).

### (2) Re-proof of every fix, in the running container

All twelve confirmed live by source inspection inside `sooppiy-worker`:
#251 max-book anchor · #253 arm-verb · #262 motionless carve-out · #262
corrected fire-count · #254/#255 exposure audit (`RATCHET_TS 2026-08-06T01:45`)
· #257 flush wired · #259 both briefs on both prompt paths · #260 Data Honesty
clause · #260/#261 `fill_audit` · #263 floor-status · `pnl_audit`.

### (3) Watch triggers

| watch | state |
|---|---|
| (i) trailing_lock | 2 fires today, **both pre-fix era** (973 00:21, 976 05:40); `ratchet_audit` post-fix **2 survived, 0 flattened** |
| (ii) armed_exit | **2 — the first ever**; 0.16 and 0.75 ordinary days → 1h44m and 4h32m |
| (iv) newborn cycle-1 retires | none |
| (v) drawdown brake | 1 (975 12:24) — **NOT** add-then-brake; 975 never added. Untriggered |
| (vii) conviction_missing | 6 of 92 = **6.5%** (was 9.4%) |
| #257 `pending_close` | 0 — structural (cycle 89), not a failure |
| frozen feed | `fill_audit` 10 repeats / **$12,655.93** |

⚠️ **A trap worth recording:** my ad-hoc SQL counted 4 `trailing_lock` fires
where `ratchet_audit` correctly reports 2 — the hand-written query matched
**both** status rows, exactly the double-count bug the tool was built to
avoid. *Use the tool.*

### (7) The day's solution — and where I stop

**Shipped this window: #263**, which addresses precisely the 13/13 finding —
not one of the ten losers could ever have armed the floor. That is the day's
solution and it is already live on all five open runs.

**Beyond that, no further change is evidenced today, and I am saying so
rather than shipping on n=1.** 975 is a single instance of "large notional,
never right, held long". The retire rail did eventually catch it
(`consecutive_losses`).

**Triggers being watched, any one of which acts:**
1. A **second** run with 975's shape — notional > ~$4k, lifetime peak under
   ~10% of one ordinary day, held > 4h.
2. Full-close share of loss climbing back above ~40%.
3. Median-win : median-loss staying worse than 1:2 for a **second** day —
   one day is a market, two is a mechanism.
4. The frozen feed (owner decision, unchanged).
5. #257's non-null case: a control-pass stop with an un-ingested close.

---

## ⏱️ 24-HOUR VERIFICATION SWEEP — 2026-08-06 15:20Z (prod DB clock) — SHIPPED #263

The 15:07Z sweep cron did not fire — the session was mid-deploy on #262,
the documented idle-only limitation. Run here instead.

### The 24h ledger

| UTC day | ledger | adapt | delta | flattens |
|---|---|---|---|---|
| 08-04 | −62.57 | −20.61 | −41.96 | 2 |
| 08-05 | **+7.09** | +71.82 | −64.73 | 2 |
| 08-06 | −70.36 | −47.59 | −22.77 | 5 |

**22 runs closed** in the KST-day window (08-05 15:00Z → 08-06 15:00Z):
10 losers totalling **−191.33**, 4 winners totalling **+94.01**, and **8
runs that produced exactly 0.00** while holding slots.

### The SHAPE — and it is adversarial about my own week

I shipped #249/#251/#254/#255 around the breakeven floor and reported
#251 "proven live" this morning. **The sweep asked a question I had
not: could that floor have protected the runs that actually lost the
money?**

The split is **13 of 13**:

| | runs | |
|---|---|---|
| **losers** | 971 975 955 944 949 957 967 962 976 973 | peak **<** arm → **the floor could never have armed** |
| **winners** | 969 960 958 | peak **≥** arm → covered |

The floor arms only once a run's peak clears its own round-trip cost, and
**that threshold scales with book size — so the protection arms last
exactly where it would save most.**

**Run 971 is the case that makes it concrete:** a 15.81-unit ZEC book
needed a peak of **$16.36**, reached **$16.15**, then lost **−$58.18**.
**It missed its own protection by 1.3%** — and it was the largest single
loss in the window.

**This is not the tautology it first looks like.** Four of the ten losers
had *positive* peaks — 971 +16.15, 976 +7.22, 975 +2.84, 973 +1.72 — and
still sat under their thresholds.

Secondary shapes worth recording:
- **Winners give back 34–49% of peak** (969 20.71→10.57, 960 42.84→28.47).
  Only 958 banked at its peak (54.45→54.45).
- **8 of 22 runs (36%) produced nothing at all** — five ZEC `desk_retired`
  zeros plus three `idle_retired`.

### Shipped — PR #263 (`918416d`, image `20260806-floorstatus`)

The desk is already shown its peak. It has **never** been shown where
protection begins, so it cannot know it is uncovered — the same shape as
#241/#244/#245. `_floor_status_line` states it and nothing else; the
judgment lives in the skills and both verbs (bank, arm) already exist. It
uses the **same #251 max-book anchor as the floor itself**, so a reduce
cannot quietly lower the bar the desk is reading.

**Live on all five open runs immediately, and the split is useful:**

| run | status |
|---|---|
| 972 SLV | **ARMED** (peak 8.63 > 4.75) |
| 977 GC | **ARMED** (peak 21.08 > 11.38) |
| 968 USDKRW | NOT ARMED (best −2.08, needs 4.74) |
| 978 ETHUSDT | NOT ARMED (best 0.83, needs 4.94) |
| **979 SI** | NOT ARMED (best −0.26, needs 10.21) — **and −9.63 open right now** |

**979 is the 971 shape happening live.** It is unprotected, and as of this
sweep it is told so every cycle.

No skill text touched — `trader/us-stock` has 60 characters left (#262).

**Verified:** fail-before 7/7, mutation 4/4 (incl. unwiring and reverting
to the current-book anchor), 3543 pass, ruff clean; in-image 7/7 OK;
renders on all 5 open runs through the real `_position_state_line` path;
0 tracebacks; docs 200/200.

### Re-proving the week's other fixes against live data

- **#251** — still "post-fix 2 survived, 0 flattened". Holds.
- **#253/#262 arm verb** — 9 `reduce` : 1 `close` since #253.
- **#257** — `pending_close` still 0; cycle 89 established this is
  structural (`adapt_retired` self-drains), not a failure.
- **#259 reachability** — the two arms that fired were 0.16 and 0.75
  ordinary days out, taking 1h44m and 4h32m. Direction supported, n=2.
- **#260/#262 frozen-mark** — the feed is still frozen; `fill_audit` 10
  repeats / $12,655.93.

### Noted, not acted on

`_position_state_line` can render *"you are holding 350% of that
high-water mark"* (978: unrealized 2.90 vs peak-total 0.83). Pre-existing,
out of this scope, and worth a look when the catalogue is next opened.

---

## Cycle 90 — 2026-08-06 14:49Z (prod DB clock) — SHIPPED #262

**1. Working per plan?** Yes. 6 runs live, **0 tracebacks**, docs 200/200.

**2. Losses and WHY.** Ledger **−59.14 → −58.26**, a **+0.88 GAIN**.
DRIFT narrowed to −9.79 as 978's lagged adapts landed (fourth
consecutive confirmation of that explanation).

**3. Reproduced — the arm lesson was overriding the frozen-mark clause.**

Since #260's Data Honesty clause went live at 12:07, the desk authored
**three** arms:

| symbol | armed | feed | outcome |
|---|---|---|---|
| ETHUSDT | 12:07:32 | **live** | **FIRED** 13:51:38 |
| GC | 12:29:05 | frozen 4h+ | can never fire |
| USDKRW | 14:45:08 | frozen | can never fire |

**n=2 on frozen marks, with a clean n=1 control that worked.** The cause
is a conflict between two skills: the clause says *"set no stop, target
or arm off"* a motionless price, while the arm lesson says *"Whenever you
hold a position, arm the level"* — unconditional, imperative, and in the
skill that is actually about arming. **The desk followed the nearer
instruction.** A caveat parked in a different skill loses to a local
imperative.

**Also: the lesson had become factually false.** It asserted *"64 arms
placed here, NOT ONE ever fired"* — untrue since 13:11:19 yesterday…
untrue since **today** at 13:11:19 (975) and 13:51:38 (978). A lesson
that states a fact must not go on stating it once it is untrue.

**Shipped PR #262** (`4730d20`, image `20260806-armcarve`): the exception
now lives inside the arm lesson, and the evidence line states the real
count plus the two measured distances (0.16 and 0.75 ordinary days).

Budget: the carve-out overflowed `trader/us-stock`, so room came from
compressing the lesson's own backstory and dropping "arm" from the Data
Honesty list — that case now lives in the arm lesson, so the duplication
was mine to remove. **No `MAX_BLOCK_LEN` bump.**

⚠️ **`trader/us-stock` is now 33,940 of 34,000 — 60 characters.** The
catalogue needs pruning, not more shaving.

**Verified:** fail-before 3/3, mutation 4/4 (incl. restoring the false
claim), 3536 pass, ruff clean; in-image 49/49 OK; live on both sites with
`execution-plan-check` retained on trader; DB rows `data-honesty` and
`position-management` both `seed-upgrade` at 15:18:17; 0 tracebacks;
docs 200/200.

**4. Unchanged.** Feed still frozen — 972 filled SLV at 56.07 again at
14:27:19 (mid-session) and 977 filled GC at 4320.700195 at 14:44:38.
`fill_audit` now **10 repeats across 4 symbols, $12,655.93**.

---

## Cycle 89 — 2026-08-06 14:19Z (prod DB clock)

**1. Working per plan?** Yes. `20260806-fillorder` (tag compared), **0
tracebacks**, 6 runs live, docs 200/200.

**2. Losses and WHY.** Ledger **−55.02 → −59.14** (−4.12).

**975 BTCUSDT retired at −38.26** — the day's largest loser — on
`adapt_retired / consecutive_losses` at 13:55:02, then flattened its
0.00730544 remainder at 64391 (−3.71). **The adaptation rail caught it**:
three losing closes in a row triggered the retire, with a 24-hour symbol
cooldown. That is the rail working, not failing.

978's armed exit contributed −0.40 (sold 0.3222 @ 1906.3 against a 1906.7
entry — a **−0.02%** move; essentially the fee).

**3. What we found.**

**⭐ A SECOND `armed_exit` fired** — 978 ETHUSDT at 13:51:38, `armed_seq
8`, `price_above 1905.2 → reduce 0.5`, mark 1906.3, **slippage
+0.0577%**. Both fires to date are on **crypto**, the only live-feed
symbols; **zero** on Yahoo-served ones. The "dead on arrival" claim from
cycle 86 now holds at **2/2**.

**Calibration for #259, now n=2 and consistent:**

| run | arm distance | time to fire |
|---|---|---|
| 975 BTCUSDT | 0.685% = **0.75** ordinary days | **4h32m** |
| 978 ETHUSDT | 0.174% = **0.16** ordinary days | **1h44m** |

The closer arm fired ~2.6× faster — the relationship #259's re-anchor
predicts. **But note neither fired inside one cycle**: even at 0.16
ordinary days it took ~2.3 cycles. The re-anchor is directionally
supported; two points do not make a curve, and if the goal is a fire
before the next look, arms may need to be closer still.

**🔍 WHY #257 HAS NOT FIRED — a structural answer, not a silence.**
975's retire went through `run_cycle`'s feedback pass, which calls
`ingest_outcomes` **first** (emitting `losing_close` for signals 484 and
485 at 13:55:02) and only then `retire_run`. By the time
`_control_stopping` ran, nothing was pending — so the flush correctly
emitted nothing.

**#257's non-null case requires a stop fired by the CONTROL pass**
(`at_time`, `max_loss`, `trailing_lock`, `profit_target`, idle/fee
retire) **while a close from the last decision cycle is still
un-ingested** — precisely what runs 960 and 976 were. The
`adapt_retired` path **self-drains**. That is not a broken fix, and the
silence should not be read as one.

**DRIFT narrowed −35.58 → −15.11** as 975's lagged adapts landed
(−15.6895, −5.2225, −3.711). Third consecutive confirmation of the lag
explanation.

**The feed is still frozen** — GC/SI/SLV/USDKRW byte-identical; only
crypto moves. `fill_audit` unchanged at 8 repeats / $12,149.41.

**4. Docs.** Both 200.

**5. Shipped.** Nothing. `conviction_missing` 6/83 (7.2%); `armed_exit`
**2**; `pending_close` **0**; `ratchet_audit` still "post-fix 2
survived".

---

## Cycle 88 — 2026-08-06 13:49Z (prod DB clock) — 🚨 FREEZE CONFIRMED CONCLUSIVELY

**1. Working per plan?** The platform, yes — `20260806-fillorder` (tag
compared), **0 tracebacks**, 7 runs live, docs 200/200. **The prices it
trades on, no.**

**2. Losses and WHY.** Ledger **−50.98 → −55.02** (−4.04), nearly all
978 ETHUSDT: bought 1.2888970 @ 1906.7, `reduce` 0.5 at 1901.1 →
`(1901.1 − 1906.7) × 0.6444485 − 0.5513 = −4.16`. A **−0.29%** move,
partial verb, book still open. Right shape again. 972 SLV +0.12.

**3. 🚨 THE FREEZE IS CONCLUSIVE — and it is now filling orders inside a
LIVE market session.**

The US regular session opened at 13:30Z. Twenty minutes in, queried from
the prod container at 13:50:09Z:

| ticker | Yahoo price | age of Yahoo's OWN data |
|---|---|---|
| SLV | 56.07 | **1070 min (17.8 h)** |
| UBER | 68.18 | **1070 min** |
| **SPY** | 769.79 | **1070 min** |
| BTC-USD | 64786.2 | 370 min |

**SPY is the most liquid ETF in the world and cannot go 17.8 hours
without a print during market hours.** BTC-USD's age grew from 282 min
(12:22) to 370 min (13:50) — **1:1 with the wall clock**, so the data is
not lagging, it is completely static. `marketState` is absent from the
payload entirely.

**The US open changed nothing**, which kills the last alternative
explanation: this is not session semantics, not the Alpha Vantage rate
limit (different provider), and not our clock (verified against an
external `Date` header, chrony synced). **Yahoo is serving this host a
frozen snapshot on every ticker.**

**And the consequence escalated this beat.** 972 filled **SLV at 56.07 at
13:41:30 — eleven minutes into an active US session**, against a
17.8-hour-old price. Earlier frozen fills were at least outside regular
hours; this one was not. **Four of the seven live runs are currently
priced off that snapshot** (GC, SI, SLV, USDKRW); only the three
Hyperliquid-served crypto runs have real marks.

**The desk is behaving correctly within its remit.** #260's clause
endorses reduce/close on a frozen mark, and 972 did exactly that — a
`reduce`. What the desk cannot control is the *price it gets*. This is
now entirely a platform/provider matter.

**4. Docs.** Both 200.

**5. Shipped — nothing, and I want the reasoning on the record.** Every
remedy is one of: (a) halt the Yahoo-served markets — trading-halting,
not mine to do unattended; (b) switch provider — needs a decision and
credentials; (c) record the upstream timestamp without gating — needs an
alembic column and changes no behaviour. **The evidence is now conclusive
enough that (a) or (b) is a decision that can be made immediately.**

*Unchanged:* `fill_audit` 8 repeats / $12,149.41; `ratchet_audit` still
"post-fix 2 survived"; `conviction_missing` 6/79 (7.6%); `armed_exit` 1;
`pending_close` **0**.

---

## Cycle 87 — 2026-08-06 13:19Z (prod DB clock) — ⭐ TWO FIRSTS

**1. Working per plan?** Yes. `20260806-fillorder` (tag compared), **0
tracebacks**, 7 runs live, docs 200/200.

**2. Losses and WHY.** Ledger **−30.11 → −50.98**, a **−20.87** beat —
the day's largest, and **all of it is run 975**.

| time | leg | price | realized |
|---|---|---|---|
| 05:37:34 | buy 0.0730544 | 64870 | (entry) |
| 13:10:32 | desk `reduce` 0.6 → 0.0219163 | 64183 | **−15.69** |
| 13:11:19 | **armed exit** `reduce` 0.5 → 0.0073054 | 64184 | **−5.22** |

BTC fell **−1.06%** from entry. Both exits used the **partial verb**; the
book still holds 0.0073054. **Right shape, losing outcome** — the same
class as cycle 83, not a #245 dump. Fees across 975's life are **4.04 of
the −34.55, 11.7%**.

**3. ⭐ FIRST — the arm executor fired. Ever.**

64+ arms had been authored and **not one had executed**. At **13:11:19**
run 975 fired `run:975:arm:6`:

```
{"armed_seq": 6, "if": "price_below", "level": 64220.0, "then": "reduce",
 "size_frac": 0.5, "mark": 64184.0, "qty": 0.00730544,
 "slippage_pct": -0.0561, "executed": true, "skip": null}
```

End-to-end proof: predicate fired, size taken as 50% **of the remaining**
book, idempotent `client_order_id`, telemetry with slippage — and
**slippage of only −0.056%** past the level.

**It fired on BTCUSDT — the one symbol whose feed is live.** That is a
direct confirmation of cycle 86's "dead on arrival" claim: the only arm
that *could* fire, did. Every Yahoo-served arm remains inert.

**A calibration data point for #259:** this arm was **0.75 ordinary days**
away when set and took **4h32m** — roughly six cycles — to reach. #259
re-anchored the reachability lesson from "one ordinary day" to "your next
look, ~45 minutes"; this is the first live measurement supporting that
direction. n=1.

**4. ⭐ FIRST — #251 is now PROVEN live, with discriminating evidence.**

The post-fix sample has been **n=0 since cycle 77**. It is no longer:

| run | reduced | arm after | peak | arm full | era | outcome |
|---|---|---|---|---|---|---|
| 975 | 13:10:32 | 1.8755 | 2.84 | 9.3777 | post-fix | **survived** |
| 975 | 13:11:19 | 0.9378 | 2.84 | 9.3778 | post-fix | **survived** |
| 976 | 05:40:01 | 5.6799 | 7.22 | 11.3597 | pre-fix | **FLATTENED** |

Both post-fix reduces landed **inside the discriminating band**. Under
the OLD anchor the arm would have been 1.8755 and 0.9378, both **below**
the peak of 2.84 → the breakeven floor **would have armed**; 975's total
P&L was far below breakeven → it **would have fired and flattened the
remainder**. Under the new max-book anchor the arm is 9.3777 > peak 2.84
→ never arms. **#251 demonstrably prevented two forced flattens today**,
and 975 still holds its 0.0073054 remainder because of it.

That is the exact 976 shape, twice, with the opposite outcome — the
comparison the audit was built to make.

**5. What is unchanged.** The feed is still frozen (GC/SI/SLV/USDKRW
byte-identical; BTCUSDT 64503→64222, ETHUSDT 1902.90→1895.20 moving).
`fill_audit` **8 repeats, $12,149.41**. `conviction_missing` 6/76 (7.9%).
`pending_close` still **0** — #257 remains untested on a non-null case.
DRIFT widened to −31.54 on 975's two closes awaiting their next-cycle
adapts — the documented lag, already validated in cycle 84.

**Docs.** Both 200. **Shipped:** nothing — this beat produced evidence,
not a defect.

---

## Cycle 86 — 2026-08-06 12:49Z (prod DB clock)

**1. Working per plan?** Yes. `20260806-fillorder` (tag compared), **0
tracebacks**, 7 runs live, docs 200/200, events current.

**2. Losses and WHY.** Ledger **−30.17 → −30.11** (+0.06). DRIFT −10.60.
No closes; nothing to attribute.

**975 emitted `drawdown_soft_brake`** at 12:24:35 (size_mult 1.0 → 0.5).
**Watch (v) is NOT triggered** — I checked the shape rather than assuming
it: 975 bought once (05:37:34) and reduced once (10:54:43), **no adds**.
FINDING 2 is specifically the add-then-brake shape, and this is not it.

**3. What we missed — and two n=1 reads on fixes shipped 40 minutes ago.**

**The freeze is unchanged and now 4h52m on GC.** Yahoo-served marks are
byte-identical to 30 minutes ago (GC 4320.700195, SI 62.099998, SLV
56.07, USDKRW 1428.310059) while BTCUSDT moved 64457→64503 and ETHUSDT
1901.90→1902.90. The split diagnosed in cycle 85 holds exactly.

**A systemic consequence worth naming:** an arm can only fire when the
mark crosses its level, so **every arm on a Yahoo-served symbol is
currently dead on arrival** — that is 4 of the 7 live runs. It also
explains part of the 64-arms/0-fires record independently of the
distance question.

**#260's clause is live; the desk did one thing it endorses and one it
forbids.** Both mark-check lines were rendering:

| run | line the desk saw | action | verdict |
|---|---|---|---|
| 968 USDKRW | SAME price, 19 reads (~22 min) | **reduce** 0.5 at 12:28:35 | ✅ the clause's carve-out — the one act that still makes sense |
| 977 GC | SAME price, 60 reads (~69 min) | **armed** price_above 4345 at 12:29:05 | ❌ the clause says *"set no stop, target or arm off it"* |

**n=1 each way, 22 minutes after deploy.** Far too early to read either
as signal. Recorded as data.

**The arm-verb tally is starting to look real, with a caveat.** 968
replaced its `close 1.0` (1447) with **`reduce` 0.5 (1445)**. Post-#253:
**9 `reduce`, 1 `close` = 10% full-book** against a **45%** pre-fix base
rate. Nominal binomial p ≈ **0.023** for ≤1 close in 10 under the null —
**but the arms are not independent draws**; several are the same handful
of runs restating. Encouraging, not established.

*Watches:* `conviction_missing` **6 of 72** (8.3%); `armed_exit` **0**;
`pending_close` **0** (#257 still untested on a non-null case);
`fill_audit` now **7 repeats, $12,141.26** (968's 12:28:35 reduce filled
at the frozen 1428.310059).

**4. Docs.** Both 200.

**5. Shipped.** Nothing. The one change worth making — judging staleness
against the upstream's own timestamp — still halts the fleet the moment
it lands, because the marks are stale right now.

---

## Cycle 85 — 2026-08-06 12:19Z (prod DB clock) — 🔍 FROZEN-FEED CAUSE FOUND

Seven minutes after cycle 84, so no meaningful new trading data. Spent the
beat narrowing the standing owner decision instead — and the answer is
**not** what cycle 82 implied.

**1. Working per plan?** Yes. `20260806-fillorder` (tag compared), **0
tracebacks**, 7 runs live, docs 200/200, events current. Ledger **−30.17**
and DRIFT **−10.66**, both unchanged.

**2. Losses.** No closes this beat; nothing new to attribute.

**3. 🔍 THE FINDING — the frozen feed is UPSTREAM STALENESS, and the
platform is blind to it by design.**

Yahoo's chart response carries its own timestamps. Queried directly from
the prod container at 12:20:26Z:

| ticker | Yahoo's price | age of Yahoo's OWN data |
|---|---|---|
| GC=F | 4320.7 | **290 min** |
| SI=F | 62.1 | **290 min** |
| USDKRW=X | 1428.31 | **280 min** |
| SLV | 56.07 | **980 min** |
| **BTC-USD** | 64786.2 | **280 min** |

**BTC-USD trades 24/7 and cannot be 4h40m without a print.** The last
1-minute *candle* is equally old on every ticker, so this is not a
`regularMarketPrice`-outside-the-session artefact — I tested that
hypothesis and it is refuted. **Yahoo is serving ~4.8-hour-old data to
this host across the board.**

The split matches exactly: **every Yahoo-served market is frozen**
(futures, forex, us-stock — GC, SI, USDKRW, SLV) and **every
Hyperliquid-served market is live** (crypto — our BTCUSDT reads 64457
while Yahoo's stale BTC-USD says 64786).

**Host clock verified before trusting any of this**: `date -u` matches
Google's `Date` header to the second, chrony synced, stratum 4. The ages
are real.

**Why the platform cannot see it:** `mark_age_ok` measures **our fetch
time**, not the data's own timestamp — and Yahoo *gives* us that
timestamp, which `_get_yahoo_chart_price` discards. A stale upstream
answering 200 OK is therefore indistinguishable from a live one.

**⚠️ CORRECTION to cycle 82.** That note reported the Alpha Vantage rate
limit (*"25 requests per day"*) alongside the freeze, which implied a
link I had not established. **It is not the cause.** Alpha Vantage serves
Market Intel; the price path is Yahoo. Reporting the two together was
suggestive and wrong, and the AV limit is a separate (real) issue.

**4. Docs.** Both 200.

**5. Shipped — nothing, and the reason is specific.** The minimal fix is
to record Yahoo's own timestamp and judge staleness against it. But the
natural form of that — gating on true staleness — **would halt the fleet
the moment it shipped**, because the marks are stale right now. That is
not a change to make unattended. It also likely needs a new column
(alembic + prod upgrade).

**→ The owner decision is now specific rather than vague:** (a) is Yahoo
degrading/caching for this host's IP, and is a different provider needed
for futures/forex/us-stock? (b) should the platform record and act on the
upstream's timestamp — warn, or block?

---

## Cycle 84 — 2026-08-06 12:12Z (prod DB clock)

**1. Working per plan?** Yes. `20260806-fillorder` stable (tag compared),
**0 tracebacks**, 7 runs live, docs 200/200, `ratchet_audit` clean.

**2. Losses and WHY — nothing new; a prediction came true instead.**
Ledger **−30.05 → −30.17** (−0.12, negligible).

The real movement was in the **adapt** column: **−9.65 → −19.51**, which
narrowed DRIFT from **−20.53 to −10.66**. Those are exactly the lagged
adapts cycle 83 said were missing, landing on the next cycle:

| run | when | realized |
|---|---|---|
| 975 | 11:39:01 | −11.5084 |
| 977 | 11:43:34 | +1.6457 |
| 979 | 11:54:59 | −0.1286 |

Cycle 83 attributed the −20.53 to "closes that had not yet emitted their
next-cycle adapts — the documented lag, not a new hole." **That
explanation is now confirmed by the numbers arriving.** Worth stating
because it is the rarer outcome: a prior conclusion held up.

**3. What we missed — and an honest read on #257.**

**974 SOLUSDT `idle_retired` at 11:06:28 — the first run to stop since
#257 deployed — and it emitted NO `pending_close`. That is correct, and
it is also not a test.** 974 ran **12 cycles over 8h19m with zero
trades**, so `leg_outcomes` had nothing to return. The call *did*
execute — the run transitioned through `_control_stopping`, and the flush
is wired at its top (verified by source inspection inside the running
image, twice) — but the null case and the "didn't run" case produce the
same observable. **#257's non-null path remains untested live**, and I am
not going to count 974 as evidence.

**The freeze is not resolving — it is lengthening.** GC has now printed
`4320.700195` for **4h15m** and SI `62.099998` for **3h54m**; USDKRW and
SLV are also static. BTCUSDT and ETHUSDT move. `fill_audit` still reports
**$12,124.96** at stalled prices.

*974's cost, noted not acted on:* 12 multi-agent cycles and a capital
slot for 8h19m to produce nothing. That is the documented dead-capital
shape and the idle-retire rail fired at its configured limit — working as
designed, not a defect.

**4. Docs.** Both 200.

**5. Shipped.** Nothing. Two PRs landed two minutes before this beat;
what they need now is live cycles, not another change.

---

## Inter-cycle ship — 2026-08-06 12:10Z — owner asked to cover the FILL side; PRs #260 + #261

Owner: *"can we cover?"* on cycle 83's finding that trades are executing at
frozen marks. Two parts, AI-first order, image `20260806-fillorder`.

### Part 1 — the lesson I owed

**#259 shipped an observable with no lesson.** `_mark_freshness_line` gave
the desk the FACT of a motionless tape and **no skill attached any
judgment to it.** Data Honesty already teaches *"if a needed input is
missing or stale, treat it as a reason for caution"* — a frozen price is
precisely the case it missed, because it does not look stale at all. It
looks like a healthy quote, **and it still fills.**

The clause now refuses OPEN/ADD and level-setting on a motionless price,
and carves out reduce/close as the one act that still makes sense.

### Part 2 — the record the desk cannot keep

`fill_audit` splits realized P&L into earned vs booked-against-a-stalled
tape. Signature: two fills on the SAME symbol at the SAME price to full
float precision, separated by real time. **Live prod, first run:**

| run | symbol | price | gap | notional |
|---|---|---|---|---|
| 977 | GC | 4320.700195 | 181m | 712.21 |
| 979 | SI | 62.099998 | 172m | 2,572.69 |
| 968 | USDKRW | 1428.310059 | 136m | 32.60 |
| 960 | SI | 62.320000 | 45m | 2,444.25 |
| 979 | SI | 62.099998 | 36m | 5,145.39 |
| 960 | SI | 62.099998 | 35m | 1,217.81 |

**$12,124.96 of notional transacted at a stalled price**, across 3
symbols — and correctly silent on BTCUSDT and ETHUSDT, which move.

### The budget was measured, not bumped

The clause overflowed `trader/us-stock` by **166 chars** and **silently
dropped `execution-plan-check`**, a 667-char safety skill. That
combination sits at **~33,890 of 34,000** while every other site/market
pair has 3,700–30,800 spare. Room came from compressing this catalogue's
own arm lesson (mine, #253/#259) — **not** a fifth `MAX_BLOCK_LEN` raise
— and the ceiling is now documented at the constant.

### Three defects in my own work, all caught before or at verification

1. **The skill test was appended AFTER `if __name__ == "__main__"`** and
   was never collected. Fail-before caught it.
2. **Its guard would have passed vacuously** if Data Honesty ever left a
   site. Now asserts the skill's presence unconditionally.
3. **`fill_audit` paired fills in `seq` order** — and `run_events.seq` is
   **per-run**, so a cross-run scan interleaved them out of time order.
   The first live run printed run 960's 08:18:07 fill as the "repeat" of
   run 979's 08:54:26 one — **a repeat predating its first**. Fixed in
   **#261** (`ORDER BY ts, seq`) with a regression test that seeds two
   runs whose seq order reverses their time order. The corrected total
   rose from $6,979.57 to $12,124.96.

**That is the THIRD time live data has caught a defect in one of these
tools that its own unit tests passed** (#253's flatten-timestamp and
duplicate-status-row traps were the first two). Fixtures are tidy; prod
is not.

**Verified:** fail-before real on both PRs, mutation 6/6, 3534 pass, ruff
clean; in-image 14/14 fill_audit + 47 skills OK; frozen judgment renders
on all four sites and `execution-plan-check` is back on trader; DB rows
`data-honesty` and `position-management` both `seed-upgrade` at 12:07:00
(durable); 0 tracebacks; docs 200/200. Verified twice.

⚠️ **Still the owner's call:** the CAUSE. Alpha Vantage rate-limited at 25
req/day; the feed answers "Successfully fetched" with a stale quote. And
whether a frozen mark should ever BLOCK a fill — deliberately not built,
because that halts trading.

---

## Cycle 83 — 2026-08-06 10:58Z (prod DB clock)

**1. Working per plan?** Yes. Fresh `20260806-deskeyes` stable — **0
tracebacks** in either container since deploy, 8 runs live, docs 200/200,
`ratchet_audit` EXIT=0, events current to the second.

**2. Losses and WHY — the biggest single-beat drop today, and it came
from a CORRECTLY-shaped decision.** Ledger **−20.18 → −30.05**.

**975 BTCUSDT took −11.51 on one reduce**, the whole of the move:

| | |
|---|---|
| 05:37:34 | buy 0.0730544 BTC @ **64870**, fee 2.1326 |
| 10:54:43 | sell 0.0365272 @ **64584**, fee 1.0616 |

`(64584 − 64870) × 0.0365272 − 1.0616 = −11.51` ✓, and with the entry fee
the run stands at −13.64 on a $4,739 notional.

**This is not a #245-shaped loss.** The desk used the **partial verb**
(`reduce` 0.5, conviction 0.63), on a losing position, after 5h17m — the
exact discipline the skills teach. The price simply went **−0.44%**
against it. This is the "we can not fix 100%" case: right shape, losing
outcome.

Worth noting rather than acting on: **fees are 3.194 of the 13.64 = 23%
of the loss.** Round trip is ~0.09% against a BTCUSDT ordinary day of
0.915%, so the hurdle is ~10% of a normal day — not dominant here, but it
compounds with every reduce.

Also 977 GC banked +1.65 and 968 +0.14. DRIFT widened to −20.53 purely
because 975's and 977's closes had not yet emitted their next-cycle
adapts — the documented lag, not a new hole.

**3. What we missed — a consequence of the freeze I had not stated.**

**Trades are EXECUTING at frozen marks.** 977 exited GC at
**4320.700195** — the identical price it has printed for 70+ minutes. The
freeze is therefore not only a decision-quality problem, it is a **fill-
price** problem: the book is being marked, and now transacted, at a
number that is not moving. The +1.65 it booked is measured against that
stale price.

*First post-#259 decision:* 977 cycle 8 at 10:58:41 (deploy was 10:56:42)
chose `reduce` 0.5 at conviction 0.80 and did **not** re-arm — while
holding a standing arm the new line now shows it (price_below 4285,
reduce 0.5, set 43 min earlier). That is exactly the intended response to
`_standing_arm_line`, but it is **n=1 and I cannot see the prompt**, so
it is recorded as data, not as proof the line worked.

*Watch (vii):* `conviction_missing` **6 of 64** decisions today (9.4%, up
from 7.7%). *Watch (ii):* `armed_exit` still **0** fleet-wide.

**4. Docs.** Both 200.

**5. Shipped.** Nothing this beat — #259 landed two minutes before it and
needs live cycles to judge, not another change on top.

---

## Inter-cycle ship — 2026-08-06 10:56Z — owner asked for solutions to cycle 82's items 3 and 5; PR #259

Owner: *"try to make solution for 3,5."* Both shipped in one PR
(`a6f752f`, image `20260806-deskeyes`). Both are the same shape as
#241/#244/#245 — **the desk judged against something it cannot perceive**
— so both are AI-first: facts into the brief, judgment left to the desk.
**Neither halts trading.**

### Item 3 — a fresh timestamp is not a fresh price

`_mark_freshness_line` counts trailing `equity` events whose `unrealized`
is unchanged and states it. Deliberately **not** a gate: I raised in
cycle 82 that a value-staleness rail *halts trading*, and quiet markets
are real — so the desk gets the observable and stays the actor.

Conservative by construction: `unrealized = (mark − avg) × qty`, so an
add or reduce moves it even under a frozen mark and **resets** the count.
It can under-report a freeze, never invent one.

**Live render immediately found more than I had measured** — SLV, a
us-stock, is frozen too, so this is not a futures/forex problem:

| run | line rendered |
|---|---|
| 968 USDKRW | SAME price for **38** straight reads (~44 min) |
| 972 **SLV** | SAME price for **60** straight reads (~69 min) |
| 977 GC | SAME price for **60** straight reads (~69 min) |
| 979 SI | SAME price for **60** straight reads (~69 min) |
| 975 BTCUSDT | *(silent — it moves)* ✅ |

The detector fires exactly where a freeze was measured and stays silent
on the one symbol that is trading. That discrimination is the evidence
it works.

### Item 5 — 64 arms, zero fires, and the yardstick was the wrong clock

I verified the executor first, so the fix would land on the real cause:
`arm_fires()` 5/5 correct tested live in the image, `_fire_armed_order`
provably reached, and **no level ever crossed**. So the levels, not the
code.

**The skill contradicted itself.** It told the desk *"your cycles are
roughly 45 minutes apart"* and, in the same breath, to place the level
*"inside roughly one ordinary day's move"* — **two horizons ~30× apart**.
The desk followed the yardstick it was given. Re-anchored to the clock
the arm actually runs on, with the 64/0 evidence stated in the lesson.

**And one claim in it was simply false.** *"Each cycle's arm replaces the
last"* — `_store_armed_order` runs only on `intent == "arm"`, so a reduce
or hold cycle leaves the arm standing. Corrected to what the code does,
and `_standing_arm_line` now shows the desk the arm it already has. Live
proof of why that was needed: **975's arm had been standing 137 minutes
unrestated**, and 968's `close 1.0` 89 minutes.

Skill text was **tightened to fit the existing budget** rather than raise
`MAX_BLOCK_LEN` a fifth time — the same call as #253.

**Verified:** fail-before 16/16, mutation 6/6 (incl. both unwirings and a
revert to the day-yardstick), 3519 pass, ruff clean; in-image 13/13 then
the full 46-test skills suite OK; both lines wired on **both** prompt
paths; skill text live on both sites with the old yardstick gone; DB row
`position-management` shows `seed-upgrade` at 10:56:42 (durable, not just
in the image); 0 tracebacks; docs 200/200. Verified twice.

⚠️ **Still open for the owner:** the *cause* of the freeze. Alpha Vantage
is rate-limited at 25 req/day and the feed answers "Successfully fetched"
with a stale quote. That is a provider/tier decision, not a code one.

---

## Cycle 82 — 2026-08-06 10:19Z (prod DB clock) — 🚨 FROZEN MARKS

**1. Working per plan?** Containers healthy on `20260806-prunebackups`
(tag compared per the new trap — unchanged since 09:45), docs 200/200,
**0 tracebacks**, `ratchet_audit` EXIT=0. But see below: healthy
processes are running against a **frozen tape**.

**2. Losses and WHY.** 08-06 ledger **−20.18** (was −19.21). The −0.97
decomposes exactly: 978 ETHUSDT's entry fee **−1.1059** plus 968's reduce
**+0.14**. That is component (a) — entry-side fees — the by-design term,
not a trading loss.

**3. 🚨 THE FINDING: futures and forex marks have not moved in over two
hours, and the staleness guard cannot see it.**

| symbol | last change | frozen for | value |
|---|---|---|---|
| GC | 07:57:40 | **2h26m** | 4320.700195 |
| SI | 08:18:07 | **2h05m** | 62.099998 |
| USDKRW | — | ~40m+ | 1428.310059 |
| BTCUSDT | continuous | — | moves 64564–64936 ✅ |

Evidence chain, each step checked rather than assumed:

1. **Marks are FRESH by timestamp** — `price_updated_at` = 91s old on all
   four. So `mark_age_ok` passes.
2. **`_maybe_emit_equity` only emits on a CHANGED total or a heartbeat.**
   979 produced 36 consecutive samples with identical unrealized, 977
   produced 8. The value genuinely did not move.
3. **Three SI trades printed at exactly 62.099998** across 08:18→08:54,
   and SI had been stepping normally before that (62.55 → 62.47 → 62.32
   → 62.10).
4. **Calling `get_price_from_market` directly returns the same frozen
   numbers** — GC 4320.7, SI 62.1 — and logs *"Successfully fetched"*.
5. **Alpha Vantage is fully rate-limited**: *"our standard API rate limit
   is 25 requests per day"*, hitting equities, macro, crypto and
   commodities refreshes.

**The guard measures the wrong thing.** `mark_age_ok` checks the
*timestamp* of the last fetch, not whether the *value* changed. A feed
that keeps answering with a stale quote refreshes the timestamp every
90s and is therefore invisible to every staleness check in the engine.

**4. Docs.** Both 200.

**5. What this explains — watch (ii), answered.**

**64 arms authored, ever. `armed_exit` events: 0. Not one has ever
fired.** I verified this is *not* a dead executor:

- `order_intent.arm_fires()` returns True on all should-fire cases and
  False on all should-not (5/5 correct, tested live in the image).
- `_fire_armed_order` is provably reached — `_maybe_emit_equity` sits
  after it in `_control_active`, and equity events are flowing.
- **No arm level has ever been crossed.** Reconstructing price from
  equity events, all four standing arms remain 0.48–0.88% short:
  968 0.877%, 975 0.533%, 977 0.826%, 979 0.483%.

So the executor is sound and the levels were never reached — and on GC,
SI and USDKRW they *could not* be reached, because the price is not
moving at all.

Standing arms, all reachable-by-the-skill except 968:

| run | verb | ordinary days |
|---|---|---|
| 979 SI | reduce 0.5 | 0.24 ✅ |
| 977 GC | reduce 0.5 | 0.61 ✅ |
| 975 BTCUSDT | reduce 0.5 | 0.62 ✅ |
| 968 USDKRW | **close 1.0** | **2.65** ❌ |

*Also noted:* `_store_armed_order` is called **only when
`intent == "arm"`**, so a cycle that reduces or holds leaves the previous
arm standing. 968 executed a reduce at 10:12:40 and its 09:27 `close 1.0`
arm still stands. The code comment says "each cycle's arm replaces the
last" — that is true only of arming cycles.

**Shipped: nothing, deliberately.** Stated plainly because the owner is
asleep: the natural fix — a *value*-staleness guard — would **halt
trading** when it fires, and shipping a trading-halting rail unattended
is not a call I should make alone. The root cause may also be an API
tier/key decision (Alpha Vantage exhausted; memory already carries a
"watch FMP tier thinness" item) which is the owner's, not mine.

**→ TOP OPEN ITEM FOR THE OWNER.** Two separable decisions: (a) the data
provider/tier, (b) whether a frozen-value guard should pause runs, warn,
or only be reported by a read-only detector like `ratchet_audit`.

---

## Cycle 81 — 2026-08-06 09:49Z (prod DB clock)

Owner is asleep from this beat; the loop continues on cron `688d79c1`
(`13,43 * * * *`) plus the 24h sweep `d869c56a` — both confirmed armed.

**1. Working per plan?** Yes. 8 runs live, `20260806-pendflush`, docs
200/200, **0 tracebacks** over 22m, `ratchet_audit` EXIT=0.

**2. Losses and WHY.** 08-06 ledger **−19.21**, unchanged for a third
consecutive beat — no closes since 08:54. DRIFT −9.56, unchanged and
already explained (#257 is forward-only; both affected runs are
`stopped`). **#257 has not yet been exercised live** — no run has entered
`stopping` since it deployed. That remains the open verification.

**3. What we missed.** Nothing new. **The named watch from cycle 80 is
NOT tripped.** One new arm this beat, and it is a clean one:

| run | verb | distance |
|---|---|---|
| 979 SI | `reduce` 0.5 @ 62.4 | 0.483% = **0.24** ordinary days |

That is well inside the skill's ≤~1 ask. Post-#253 tally is now **5 arms
— 4 `reduce`, 1 `close` = 20% full-book** (down from 25% by dilution, not
by evidence) against the 45% pre-fix base rate. n=5.

Reachability across every post-#253 arm keeps 968 as the *sole* outlier:

| run | ordinary days |
|---|---|
| 979 SI | **0.24** |
| 975 BTCUSDT | **0.75** |
| 975 BTCUSDT | 1.28 |
| 968 USDKRW | 2.03 |
| 968 USDKRW | 2.65 (the `close 1.0`) |

Four of five arms are at or near the ask. 968 is the only run drifting on
both verb and distance — still **n=1**, so the #253 clause stays closed.

**4. Docs.** Both 200.

**5. Shipped.** Nothing. No reproduced evidence; the watch is holding.

**⚠️ A PARALLEL SESSION DEPLOYED MID-CYCLE.** The verification pass found
the containers on `20260806-prunebackups`, not the `20260806-pendflush` I
deployed at 09:26 — another session shipped **#258** (backup pruning) on
top of #257 at ~09:45. Checked rather than assumed, and it is clean:

- `_flush_pending_close_adapts` still wired, still before the flatten
- `ratchet_audit.RATCHET_TS` and `audit_exposures` both present
- `run_engine.py` and `ratchet_audit.py` sha256 **match `origin/main`
  exactly** — nothing of #255/#257 was clobbered

The other session built from fresh main, which is exactly what the
parallel-worktree rule asks for. **Never infer this from a green health
check — an image tag changing under you is invisible unless you compare
it.** `pending_close` adapt events fleet-wide: **0**, confirming #257 is
still unexercised live.

---

## Cycle 80 — 2026-08-06 09:30Z (prod DB clock)

**1. Working per plan?** Yes. 8 runs live, both containers on
`20260806-pendflush`, docs 200/200, **0 tracebacks** since the deploy,
`ratchet_audit` EXIT=0, events current to the second.

**A false alarm I checked before raising it.** `[TradingRuns] tick` was
**absent from the entire worker log** after the 09:27:38 restart, which
reads like a stalled control loop. It is not. `tasks.py:795` prints that
line **only when `dispatched` or `armed_started` or `stopping_finished`
is truthy** — silence means nothing was due. Positive proof the loop is
alive: `_maybe_emit_equity` is called from `_control_active`, on the same
tick as `_control_stopping`, and equity events are landing at 09:31:10.
So the path #257's flush sits on is confirmed running. Recorded as a trap
— a future session could easily mis-call this a dead worker.

**2. Losses and WHY.** 08-06 ledger **−19.21**, unchanged; no realized
movement this beat. `pnl_audit` DRIFT persists at −9.56 exactly as
predicted — #257 is forward-only and both affected runs are already
`stopped`.

**3. What we missed — the first post-#253 counter-example.**

Cycle 79 reported 3 post-#253 arms, all `reduce`, and called it *not yet
significant*. That caution was right: **968 armed `close 1.0` at 09:27:18.**
Post-#253 tally is now **4 arms — 3 `reduce`, 1 `close` = 25% full-book**
against a 45% pre-fix base rate. n=4. **The clause has not eliminated
full-book arms**, and nothing here is significant either way.

**The instance is worse than the verb alone.** 968 *replaced its own
better arm*:

| time | verb | level | distance |
|---|---|---|---|
| 08:42:25 | `reduce` 0.5 | 1442.6 | 1.000% = **2.03** ordinary days |
| 09:27:18 | `close` 1.0 | 1447.0 | 1.309% = **2.65** ordinary days |

It moved the level **further away** *and* **escalated the verb** in one
cycle — on a run that has never been in profit (realized −3.59, peak
−2.08). Watch (ii) asks ≤~1 ordinary day; both are beyond it.

**But this is 968-specific, not systemic** — the split matters:

| run | arm | ordinary days |
|---|---|---|
| 975 BTCUSDT | reduce | 1.28 |
| 975 BTCUSDT | reduce | **0.75** (moved CLOSER) |
| 968 USDKRW | reduce | 2.03 |
| 968 USDKRW | close | 2.65 |

975 is doing exactly what the skills ask — partial verb, and it tightened
its own level on the second pass. Only 968 drifts.

*Watch (vii):* `conviction_missing` = **4 of 52** decisions today (7.7%).

**4. Docs.** Both 200.

**5. Shipped.** **Nothing, deliberately.** One counter-example on one run
is not reproduced evidence, and the standing daily-solution duty never
licenses a thinly-evidenced ship. Logged as a named watch: **a second
run authoring an unreachable full-book arm re-opens the #253 clause.**

---

## Inter-cycle ship — 2026-08-06 09:28Z — owner asked for a solution to the pnl_audit DRIFT; PR #257

Owner: *"make solution for pnl_audit는 여전히 08-06 DRIFT … 알려진 미수정
adapt-flatten 누락 문제입니다."*

**First finding: it is NOT mostly the known flatten gap.** Decomposing the
day's −9.56 delta to the cent:

| component | USD |
|---|---:|
| (a) entry-side fees, by design | −3.2027 |
| **(b) adapt NEVER emitted** | **−6.6894** |
| (c) 973's pre-#249 flatten | +0.3967 |
| (d) 08-05 close landing on 08-06 | −0.0644 |
| **sum** | **−9.5598** = observed |

#249's emission fix **is working**: 3 of today's 4 flattens emitted
`flatten_close` adapts (969, 976, 960); only 973 predates the deploy.

**(b) is a different, unfixed defect — and #249's own comment states its
mechanism while fixing only one instance of it:**

> "run_feedback derives its own adapt events from closed SIGNALS on a later
> cycle, and a flattened run is stopping/stopped, so no later cycle ever
> processes this leg"

True of the flatten leg — and equally true of **every other close still
pending when the run stops**. Run 960 reduced at 08:18:07 (−4.3752) and
stopped at 08:53; run 976 reduced at 05:40:01 (−2.3142) and was flattened
at 05:40:02. Neither ever reached the adapt stream. **The same failure shape
twice: a number journalled only "next cycle" is lost precisely when there is
no next cycle — which is precisely when the run died.**

**Fix (PR #257, image `20260806-pendflush`, main `4041812`).**
`_flush_pending_close_adapts` at the **top** of `_control_stopping`, before
all three terminal branches and before the flatten leg exists as a signal.
Emits, never adapts — a terminal run's `size_mult` ladder is moot, so it
deliberately skips the claim fence `save_state` needs (a stopping run is
unclaimed; the write would be discarded). Idempotent by construction: the
watermark is read back out of the run's *own* adapt events, so the bounded
flatten retry cannot double-journal.

**NOT an AI-first fix, deliberately.** The desk cannot emit the platform's
record of what the desk already did — the "code only where the desk cannot
be the actor" case, stated rather than skipped.

**Verified:** fail-before 7/7, mutation 4/4 (incl. unwiring, and moving the
call after the flatten), 3504 pass, ruff clean; in-image 7/7 then the full
82-test `test_run_engine` OK; wiring confirmed live from the image twice;
0 tracebacks; docs 200/200. **Read-only replay proves it would have caught
exactly the two lost legs: run 960 signal 475 = −4.3752, run 976 signal 469
= −2.3142** — the decomposition's (b) to four decimal places.

⚠️ **The fix is forward-looking.** Today's −6.69 is already lost (both runs
are `stopped`, and `_control_stopping` only visits `stopping`), so the
08-06 DRIFT line will not change retroactively.

⚠️ **Open, not shipped:** even after this, component (a) — entry-side fees,
which the ledger charges on the opening leg and the adapt stream never sees
— will keep the delta non-zero, ~−3.20 on a 4-newborn day against a $5.00
tolerance. On busy days the alarm will still fire benignly. Deciding whether
to model (a) in the tolerance is a separate call; **do not chase it as a bug**.

---

## Cycle 79 — 2026-08-06 08:53Z (prod DB clock)

Fired 59 seconds after cycle 78's final verification, so this is a short
beat with one genuine observable and **nothing to ship**.

**1. Working per plan?** Yes. 8 runs live (979 SI newborn 08:53), both
containers on `20260806-band2`, docs 200/200, **0 tracebacks** in both
containers over 60m. `ratchet_audit` EXIT=0.

**2. Losses and WHY.** 08-06 ledger **−14.58**, unchanged since 08:49 —
no new realized loss this beat.

**960 SI closed +28.47** (peak 42.84), the day's best run, on
`stop_event:at_time` — its 24h horizon expiring exactly one day after
birth (08-05 08:53 → 08-06 08:53). **Not** a rail fire. It did reduce
0.5 at 08:18:07 and is worth checking against the band: book 39.22 →
19.61 at mark 62.10 gives arm-full **4.87** and arm-after **2.44**
against a peak of **42.84**. The peak cleared *both* arms by ~9×, so the
floor was armed under old and new code alike and simply never reached —
correct behaviour, and **non-discriminating**, exactly as the auditor
reports (0 in-band rows for 960).

**3. What we missed.** Nothing new. The post-#251 discriminating sample
is still **n=0** and the in-band table still reads one row (976,
pre-fix, FLATTENED).

*The one observable:* since #253 deployed at 07:51:01 the desk has taken
**7 decisions — 3 arms, all `reduce` 0.5; 3 executed reduces; 1 hold.
Zero `close 1.0`, zero full exits.** Against the measured pre-fix base
rate of **45% full-book arms**, three consecutive partials carries
p ≈ 0.55³ ≈ **0.17** under the null. Suggestive, **not significant** —
the base rate would predict ~1.4 full-book arms in three. Keep counting;
do not call it working yet.

*Noted, not alarming:* 968 USDKRW carries `peak_pnl_usd` = **−2.08**. A
negative peak can never satisfy `peak >= arm > 0`, so the breakeven floor
is simply inert on that run — which is the intended shape for a position
that has never been in profit.

**4. Docs.** how-it-works 200, liquidation-defense 200.

**5. Shipped.** Nothing. No reproduced evidence called for a change, and
a quiet beat is the correct outcome one hour after two ships.

⚠️ `pnl_audit` still reports 08-06 DRIFT (ledger −14.58 vs adapt −5.28,
3 flattens) — the known unfixed adapt-omits-flattens gap.

---

## Cycle 78 — 2026-08-06 07:55Z (prod DB clock)

**1. Working per plan?** Yes. 8 runs live, both containers on
`20260806-gap77`, docs 200/200, zero tracebacks (the six log "error"
lines are feed counters: `Market Intel inserted=0 errors=4`, not
exceptions). Events current to the second.

**2. Losses and WHY.** 08-06 ledger **−13.77** (tool, ledger
authoritative). Closed today: 949 −15.51, 976 −5.24, 973 −0.70, 969
**+10.57**. 949 HYPEUSDT ended on `stop_event:at_time` — a 2-day run
timing out, not a rail failure.

**976 is the cycle's real finding, and it is a confirmation, not a new
defect.** Its 47-minute life:

| time | event |
|---|---|
| 04:54:31 | buy 1.3166 GC @ 4317.40 |
| 05:40:00 | desk decides `reduce` 0.5 — a deliberate partial exit |
| 05:40:01 | sell 0.6583 @ 4314.10 |
| **05:40:02** | **`stop_event:trailing_lock` flattens the remainder** |

Loss −5.24 on a **0.088%** adverse move; fees were 0.568 of it (11%).
This is unambiguously the **breakeven ratchet**, not the legacy trail:
`trail.activate_usd` = **85.26** against a lifetime peak of **7.22**, so
the legacy lock could never have armed. It is the textbook instance of
the defect #251 was built to kill — and it happened **one hour before
#251 reached prod (06:40)**. `run_engine` already cites 976 by name.

**3. What we missed — and the correction owed.**

*Correction.* Cycle 77 reported the full-book arm as **n=1**. That was
wrong. Over 08-04 → 08-06 the desk armed **42 times, 19 of them
`close 1.0` — 45%**, not one. The clause shipped in #253 was therefore
addressing a base rate, not an anomaly. Post-#253 arms so far: **2, both
`reduce` 0.5** (975 at 07:53, and 977's third partial at 07:57:40).
n=2 is not yet a trend.

*The gap.* `ratchet_audit` can alarm on a bad fire but is **structurally
blind to the fix working**. A post-fix sample of zero fires reads
identically to "the rail never got a chance" — and it printed exactly
that while 976 sat one hour the wrong side of the boundary. Shipped as
**PR #254**: count the *reduces*, not just the fires. The anchor only
decides anything inside one band — the lifetime peak clears the arm on
the **shrunken** book but not the arm on the **largest book ever held**.

*A near-overclaim, caught.* 977 (same symbol, same trail config,
`reduce` 0.5 at 07:12, survived, still running) looks like the positive
control for #251. **It is not.** Its peak of 21.08 cleared *both* arms
(5.69 and 11.37), so both code versions behave identically — it proves
nothing either way. 976 landed inside the band (5.68 ≤ 7.22 < 11.36).
A test now pins that distinction so no future reader can fudge it into
evidence. **The discriminating post-#251 sample is still n=0**, and the
band is narrow (a 2× window plus a retrace to the floor), so an empty
sample is expected for a while rather than suspicious.

**4. Docs.** how-it-works 200, liquidation-defense 200.

**5. Shipped — TWO PRs, because the first was wrong.**

**PR #254** added the in-band reduce table. **Running it live got 976 —
the single case whose answer is known — BACKWARDS**, reporting the
textbook retro-arm as `survived`. **PR #255** fixes three live-only
defects:

1. **Fire matching was exact-second.** 976 reduced at 05:40:01 and was
   flattened at 05:40:02. Now a 90s window, lower-bounded so a fire
   *before* a reduce never counts.
2. **It judged reduces that predate the rail.** The ratchet merged
   2026-08-06 01:45Z; the table scored eight 08-01/08-02 reduces against
   it and called them all "survived" — eight counts of evidence for
   nothing.
3. **A sliver arm printed as `0.00`** — a fractional book's arm is
   $0.004, and at 2dp the band read as trivially satisfied on 9 of 11
   rows. Now 4dp.

**Correction to an inherited claim.** The snapshot recorded **973 as the
second retro-arm instance**. It cannot be: its fire (00:21:23) predates
the ratchet's own merge by **84 minutes**, and its reduce was 2h02m
earlier — not the same-second escalation signature. **Confirmed
retro-arm count is n=1 (976), not 2.** What actually fired 973 is
unexplained by either emitter under its stored config (legacy
`activate_usd` 82.42 vs peak 1.72) — logged as an open question, not
guessed at.

Live table now reads exactly one row — 976, pre-fix, **FLATTENED**.

Deployed `20260806-band2` (main `4ea2a00`). Verified: containers on the
new image; auditor runs from the image twice with identical output;
38/38 in-image tests twice; events current to the second (08:49:53 vs
NOW 08:49:54); 8 runs live; **0 tracebacks** both containers.

⚠️ `pnl_audit` reports 08-06 **DRIFT** (ledger −14.58 vs adapt −5.28, 3
flattens) — the *known unfixed* gap where the adapt query omits forced
flattens. Not caused by this change (read-only, `ratchet_audit` only).


---

## Inter-cycle ship — 2026-08-06 ~08:1xZ — owner asked for solutions to cycle 77's two gaps; PR #253

Owner: *"make solution for [the two honest gaps]."* Both shipped in one
PR (#253, branch `20260806-gap77`).

### Gap 1 — #251 was unproven live, and proving it was a manual chore

The problem was never that the fix was wrong; it was that **the only
evidence path was a human remembering to hand-audit every future
`trailing_lock`** — the same arrangement that let the retro-arm defect
run undetected in the first place. So the watch became a tool.

`ratchet_audit.py` replays each fire's own trade events and asks: was
the book at the fire smaller than the largest book that run ever held?
Post-fix that must never happen — such a fire is flagged and the module
**exits non-zero**, like `pnl_audit` on ledger drift. An empty post-fix
sample prints *"post-fix sample is EMPTY — the anchor is untested
live"* rather than implying success.

**Running it against live prod caught two defects in my own tool that
the unit tests did not**, and both are now pinned by regression tests:

1. **The fire's own flatten leg carries the SAME timestamp as the fire.**
   A naive `ts <= fire_ts` snapshot counted the liquidation as part of
   the preceding book, so **15 of 16 fires read as a flat → "shrunken"
   book**. Post-fix, the first genuine full-book fire would have raised
   a false alarm. (A desk *reduce* in the same second must still count —
   that is the actual signature — so the filter keys on the flatten's
   `client_order_id`, not on time.)
2. **A stop emits TWO `run_status` rows** (`running→stopping`,
   `stopping→stopped`) and both contain "stopping" — every fire was
   double-counted. Now matched on the transition INTO stopping.

**And I corrected an overclaim before shipping.** The first draft
declared a shrunken-book post-fix fire a `*** REGRESSION ***`. But
`stop_event:trailing_lock` is **shared with the legacy trailing lock**,
whose `trail.activate_usd` is a **fixed dollar figure written at build**
— so the legacy trail *cannot* retro-arm, and a shrunken-book legacy
fire is perfectly normal (the desk banked some, the trail caught the
rest). The tool now flags for **REVIEW** and names the disambiguator:
the worker log line `breakeven ratchet fired`.

**Live result (deduped, corrected), 8 fires since 07-01:**

| run | max book | at fire | verdict | era |
|---|---|---|---|---|
| 119 | 760.04 | 760.04 | full-book | pre-fix |
| 125 | 1.32 | 1.32 | full-book | pre-fix |
| **854** | 57.28 | 37.32 | **shrunken** | pre-fix (legacy trail) |
| 897 | 41.58 | 41.58 | full-book | pre-fix |
| 919 | 84.64 | 84.64 | full-book | pre-fix |
| **921** | 44.43 | 1.37 | **shrunken** | pre-fix (legacy trail) |
| **973** | 22.24 | 11.12 | **shrunken** | pre-fix (ratchet — the defect) |
| **976** | 1.32 | 0.66 | **shrunken** | pre-fix (ratchet — the defect) |

`0 post-fix; 0 to review` — the honest state. 854/921 carry the shape
but predate the ratchet entirely, so they are NOT extra instances of the
defect; noting them as such would have been the overclaim.

### Gap 2 — the arm vocabulary never got the exit-verb lesson

968 armed a **full-book close**. #245 taught the partial verb for
*discretionary* exits only; the skill text contained **no arm-sizing
guidance at all** — structural, not an n=1 behavioural read, which is
why it did not need a second occurrence. An armed level fires
unattended: the size armed is the size taken, with no cycle in between
to reconsider, and whole-book exits carry **91% of all measured loss**.
`position-management` now teaches the partial verb as an arm's default
and names why an arm repeating the stop with a full close buys nothing.

**Sized to fit the EXISTING budget** rather than raising `MAX_BLOCK_LEN`
a fifth time — the first draft overflowed (pushing `Execution Plan
Check` out of the block) and was tightened instead.

Verification: fail-before on the skill clause and on both live-data
defects; mutation ×3 on the auditor, each killed by its pinned test;
ruff green; **3381 backend tests green**.

---

## Cycle 77 — 2026-08-06 07:00Z — the arm-reachability skill LANDED: an arm inside 0.60 ordinary days (was ~25)

DB clock 07:00:12. Session handover cycle (new account); **both crons
re-armed** — 30-min `688d79c1` (`13,43 * * * *`) and the 24h sweep
`d869c56a` (08:07 local = 15:07Z). Prior session's `3e0160dc` cancelled.
Prod `20260806-armanchor`, 0 tracebacks, docs 200/200.

### 1. Working per plan — yes, and the arm watch produced its best result yet

**#247's open question was whether the desk would arm REACHABLE levels.**
Measured against each symbol's own ordinary daily move:

| when | run | arm | distance | ordinary days |
|---|---|---|---|---|
| 08-05 (pre-skill) | various | — | 11–13% | **~25** |
| 08-06 00:22 | 968 | `price_above 1440 → reduce 0.5` | 1.21% | 2.5 |
| **08-06 06:26** | **977 GC** | **`price_above 4350 → reduce 0.5`** | **0.80%** | **0.60** ✅ |
| 08-06 06:25 | 968 | `price_below 1414 → close 1.0` | 0.87% | 1.76 |

977's arm is **inside one ordinary day** — the skill's actual ask, met for
the first time. Progression 25 → 2.5 → 0.60 days across two days. It is a
BANKING arm (`reduce 0.5` above), not merely protective.

**Still zero `armed_exit` events fleet-wide.** Reachable ≠ fired; the
executor remains unproven end-to-end. That is the next thing to catch.

**New observation (n=1, not a finding):** 968 armed **`close 1.0`** — a
full-book arm. The measured killer is the whole-book dump (full closes =
91% of all loss), and #245's exit-verb lesson targets *discretionary*
exits; the ARM vocabulary was never given the same `reduce`-over-`close`
teaching. Watch whether armed full-closes recur; if a second appears,
the AI-first fix is a clause in `position-management` extending the exit
verb discipline to armed levels.

### 2. Losses and WHY — 08-06 ledger −15.48 (pnl_audit `ok`, delta −4.93)

| run | realized | cause |
|---|---|---|
| 969 HG | **−8.41** (−2.08, −3.10, flatten −3.24) | `retire_consecutive_losses` after 3 losses; review honest: "returned −0.5% vs the anticipated +4%". The rail cutting a bleeding thesis — working as designed |
| 976 GC | −2.64 | the **pre-fix retro-arm death** (#251 shipped 06:40Z, after this) |
| 968 USDKRW | −1.29 net | three small legs, size laddered 0.5→0.25 by adapt |
| 960 SI | +1.80 net | banking |

No new pathology. The day's largest single loss is **−3.24** — the
971-class tail (−58) remains absent, and the whole-book-dump shape did
not appear.

### 3. What we missed — nothing new; two honest gaps

- **Post-#251 sample is n=0.** Both 08-06 `trailing_lock` fires (973
  00:21, 976 05:40) predate the 06:40Z deploy. The retro-arm trap is
  fixed in code and verified 3× at ship, but **no live fire has yet
  exercised the new anchor.** Do not call it proven.
- `armed_exit` still 0 (above).

### 4. Docs — `how-it-works` 200, `plan-16` 200.

### 5. Suggestions / shipped

Nothing shipped this cycle — no reproduced evidence supported a change,
and per §1 the daily obligation never licenses a thin ship. Two triggers
now armed: a second armed full-close, and the first post-#251 ratchet
fire (audit peak/now/arm against the max-book anchor).

Book at read: 977 GC +6.3, 968 +0.4, 972 +0.3, 975 −4.6, 960 −15.5
→ net ≈ **−13.2** unrealized across 8 runs.

---

## Cycle 76 — 2026-08-06 06:54Z — first post-#251 beat: all quiet, and the fix's intended shape is visible on 960

DB clock 06:54:04. Image `armanchor` up 10 min, 0 tracebacks, **0 ratchet
fires, 0 daily-move blindness logs**, pnl_audit `ok` (−15.48, unchanged —
no closes since the ship), docs 200, events fresh.

**Fleet grew to 8:** 978 ETHUSDT born 06:48 (969's retired slot, HG on
24h cooldown → different symbol). Cycle-1 `hold` at conf 0.45 — a patient
newborn, no forced entry (newborn-guard count n=6).

**960 SI is the fix working as intended:** unrealized slid −6.9 → −16.47
(total +20.75, down from +30.36; adapt loss-cooldown active). Its peak
+42.84 ≥ its max-book arm (~9.8), so the breakeven floor is GENUINELY
armed — if total ever touches 0 the run flattens with its +37 realized
intact. That is the floor protecting a real winner's breakeven, exactly
what it is for; under the old sizing nothing changes here either (book
grew, not shrank). The residual-shape watch (big paper gain
round-tripping to the BRAKE on an unarmed floor) does not apply — 960's
floor is armed.

Books: 960 +20.75, 977 +2.88 (GC gave back most of the pop; arm at 4350
stands), 968 −3.47 but open book turned POSITIVE (+0.39, short finally
paying; banking arm `price_below 1414 → close` stands), 975 −6.22 (BTC
long drifting against — no brake proximity, desk's next read due), 972
+3.24, 961/974/978 flat. 974 still sell-gated at sub-0.5 conf; idle-retire
will eventually collect it if SOL stays refused — correct behaviour.

Nothing shipped; nothing warranted. Next beat :13.

---

## Cycle 75-FIX — 2026-08-06 06:44Z — owner said "fix 2,3": #251 SHIPPED to prod, retro-arm removed, pnl_audit in-image

Owner directive on the cycle-75 report: *"fix 2,3."* The retro-arm defect
is deterministic (source + live-log arithmetic, not a statistical claim),
so the n=1 bar did not apply; shipped as **PR #251**, prod image
**`sooppiy-backend:20260806-armanchor`** (containers up 06:40Z).

**The fix:** `_run_max_abs_qty(run)` replays the run's own trade events
(pnl_audit's signed convention) and the breakeven floor's arm is now
sized off **the largest book the run ever held** — a reduce can no longer
lower the bar under an already-earned peak. Strictly conservative vs the
old sizing (constant books and adds byte-identical); fail-soft to the
current book. Plus: `_typical_daily_move_pct` now logs when a symbol has
no usable daily history (976's silent GC blindness).

**Pipeline:** fail-before 9/9 red → pass-after 17/17; 4 verified
mutations killed (`__pycache__` cleared); ruff clean; local suite 3369 +
1312 subtests green; CI green (2nd full pass, backend 12m12s); squash
merge `77c628a`; drift guard held (prod ≡ parent `29018da` pre-copy);
in-image `Ran 17 — OK` + anchor-wiring assert + `import pnl_audit` OK.

**Verified 3× live:** (1) worker replays 976 → max book **1.316579**,
arm 11.36, floor on the exact death inputs now **False** (old sizing:
True); `docker exec … -m pnl_audit` works — **08-06 reads `ok`, delta
−4.93, EXIT=0** (runbook item closed, §4 caveat lifted). (2) 6 min on new
image: 0 tracebacks, 0 spurious ratchet fires. (3) fleet cycling — 7 runs
intact, 34 skills, events fresh (06:44:29Z), margin bookkeeping flowing,
and TWO new banking arms since 05:53: 977 `price_above 4350 → reduce`
(~+0.9% ≈ inside one GC ordinary day — the #247 skill's ask), 968 rotated
to `price_below 1414 → close`.

**CORRECTION to the 05:53 note:** 973 was NOT a clean small-book fire.
Live replay shows its max book was **22.24 vs 11.12 at fire** — its
morning fire was ALSO retro-arm-class (a reduce had halved the book
earlier). **Both of today's ratchet fires were the same defect (n=2)**;
the "n=1, watch first" caution was over-conservative and the ship is
better evidenced than first stated. Under the new anchor neither would
have fired (973: arm 3.29 > peak 1.72; 976: arm 11.36 > peak 7.22).

**Post-ship watch (next cycles + 15:07Z sweep):** ratchet fire rate
should drop; every `trailing_lock` fire must now audit as same-size-book
genuine (log carries peak/now/arm); the tail rail (max_loss/drawdown
brake) still backstops runs whose peak never covered their biggest book.

---

## Cycle 75 — 2026-08-06 05:53Z — resumption cycle; the ratchet cut a recovering winner, and the desk's `reduce` armed the rail that flattened it

DB clock `05:52:59` (= UTC). Prod image `20260806-flatpnl` on both
containers, host app tree ≡ `origin/main` (sha256 ×5 files). 0 tracebacks
90 min. Events fresh (MAX ts 05:52:57Z). how-it-works 200 (SPA shell; full
DOM check due at the sweep). liq-defense: `liquidation_watch` task running
since the 00:35:45Z worker start. `[TradingRuns] tick` healthy —
eval_failures 0.

**Fleet (7):** 960 SI, 961 UBER, 968 USDKRW, 972 SLV, 974 SOLUSDT,
975 BTCUSDT, **977 GC (new — replaced 976)**.

**P&L (pnl_audit, mounted — the RUNNING IMAGE LACKS the module, see
below):** UTC 08-05 ledger **+7.09** (2 flattens). UTC 08-06 so far ledger
**−15.48**, adapt −10.43, delta −5.05, 3 flattens, verdict `*** DRIFT ***`
— **explained, NOT a #249 regression** (decomposition below). Open books
right now: 960 −6.86 unreal (realized +37.22), 968 −0.48 (r −3.86),
972 +0.27 (r +2.96), 975 −2.78 (r −2.13), 977 **+16.88** (r −0.28),
961/974 flat. Net open unrealized ≈ +7.1.

### The main finding — run 976 GC, born 04:53Z, dead 05:40Z, −5.24

Timeline (all confirmed from `run_events` + worker log):

1. **04:53:44Z** — GC daily-bars fetch FAILED at build ("possibly
   delisted; no price data found (1d …)"). One-shot; 977's build at
   05:40 did not log it. Consequence: `_typical_daily_move_pct` had no
   candles, so 976's Exit-scale line would render WITHOUT the
   ordinary-day sentence (the line itself still renders — fail-soft only
   drops that sentence).
2. **04:54:30** — cycle 1: buy 1.3166 GC @ 4317.40, conviction 0.8725,
   authored stop 0.76% / target 2.0%. (Newborn-guard count → n=5 incl.
   977; no cycle-1 retire pathology.)
3. Position ran to **peak +7.22** (05:13Z), then faded to −0.68 by
   05:32, −4.50 by 05:34:53 (GC dropped 4317→4313 fast).
4. **The breakeven floor was NOT armed this whole time**: arm_usd on the
   full book = qty·mark·0.001·2 ≈ **11.36 > peak 7.22**. The configured
   trail (activate 85.26) was never in play either.
5. **05:40:00** — cycle 2: decision `sell` conf 0.68 → **order_intent
   `reduce 0.5`** — the desk chose the cheap verb on adverse drift
   (−0.076%). **Exit-verb #245 evidence n=2** (line rendered; caveat:
   day-sentence likely absent per (1), and the move was tiny).
6. **05:40:01** — the reduce **halved the book → arm_usd fell to 5.68 <
   peak 7.22 → the floor retro-armed against a peak earned by the FULL
   book**, saw total −5.10 ≤ 0, and fired the same second (worker log:
   `breakeven ratchet fired (run 976): peak=7.22 now=-5.10 arm=5.6792`).
   Remaining half flattened −2.64. Run total **−5.24**.
7. **05:40:38** — fleet planner rebuilt the slot as **977 GC**, cycle-1
   buy 1.3187 @ 4310.50 (conviction 0.7675, stop 0.58%). 977 is now
   **+16.88 unrealized** — GC rallied to ~4323.

**Counterfactual:** had the floor not fired, 976's remaining half at the
current mark ≈ +3.75 → run ≈ +1.2 and rising. The ratchet's promise is
"exit ≈ breakeven"; it delivered −5.24 because the floor ARMED only at
the instant of the reduce, with the book already at −5.10 — breakeven
protection engaged five dollars below breakeven by construction (the
retro-arm defect; no evaluation lag was involved — control scans were
evaluating it all along, correctly unarmed). The position it cut
recovered within 15 minutes. **First cut-winner instance (n=1).** The replacement catching the rebound was
planner luck, not design (949's slot shows replacements don't always
re-enter the same symbol).

**The mechanism worth recording:** `_breakeven_arm_usd` is computed from
the **current** position size while `peak_pnl_usd` is a run-lifetime
high-water mark. **Any reduce on a red book lowers the arm and can
retro-arm the floor → instant full flatten.** The desk's deliberate
`reduce` (exactly what #245 teaches) gets escalated by the rail into the
expensive verb it deliberately avoided. This couples two shipped fixes
against each other. n=1 — NOT shipping; per §2.3 this needs a second
instance. Candidate fixes if it reproduces (platform, not skill — the
desk cannot see the floor): snapshot arm_usd at arming time; or scale
peak down proportionally on reduces; or suppress the floor for the cycle
in which a desk-authored reduce just executed.

### Second ratchet fire today — 973 SOLUSDT, 00:21Z (clean)

peak +1.72 ≥ arm ~1.65 (small book) → armed on the full book → total ≤ 0
→ flatten −0.70. No reduce involved, no verb-escalation. Working as
designed. **Ratchet fires now n=2 (973, 976); churn cost today −5.94 =
38% of the day's realized red.** SOL after 973's cut: replacement 974 has
sat flat 5 cycles (sell 0.48 < gate 0.5) — can't call 973 a cut winner.

### The rest of the day's −15.48 (attribution)

969 HG: 3 consecutive losing closes → **adapt retire** (+10.57 lifetime,
24h HG cooldown, flatten −3.24 journaled correctly). The adapt system
retiring a former winner on schedule — working as designed. 949 HYPEUSDT
died on its scheduled `at_time` (−15.51 lifetime; no flatten — was
already flat). 968 net −1.29 today (three small closes). 975 fresh BTC
long carrying −2.13 realized (entry fee) — watch. 960 realized +1.92
today but note its 04:31 buy 78.44 @ 62.32 → 05:16 sell 39.22 @ **62.32**
— a same-price half-unwind 45 min later, pure fee burn (~0.37); shape
logged, not actionable.

### DRIFT decomposition (why −5.05 is explained)

(a) 976's dying reduce leg −2.31: a close on a run's FINAL cycle never
gets its next-cycle `losing_close` adapt — structural, ledger catches it;
(b) 975's entry fee −2.13 sits in ledger-realized but adapt only speaks
at closes — structural; (c) 960's 05:16 close adapts next cycle; (d) the
pre-restart 973 flatten (00:21, old image) predates the #249 journal.
Post-restart flattens (969, 976) both journaled. **#249 works; the tool's
$5 tolerance is simply tighter than the structural deltas on a day with a
mid-day image restart + fresh entries.**

### Fix-verification ledger (what this cycle proves)

- **#245 exit-verb: n=2** (969 c20, 976 c2 — both with the line
  rendered). `why` still empty fleet-wide.
- **#249 ratchet: n=2 fires**, but tonight bought −5.94 of churn against
  a tail it didn't need to cut; **watch triggers**: (i) a second
  cut-winner (position recovers past breakeven within ~2 cycles of a
  floor fire), (ii) a second reduce-triggered retro-arm, (iii) slippage
  > $5 through the floor again. Any of these → design the fix above.
- **#249 flatten journal: verified again** (2/2 post-restart).
- **#244 newborn guard: n=5**, zero wrongful retires.
- **#247 arm executor: alive** (ticks clean); 968's arm standing
  (price_above 1440 → reduce 0.5, ~1.55% away); no `armed_exit` fires
  yet; no NEW arms this window — the fleet's arming habit is still thin.
- **#250 pnl_audit: the RUNNING IMAGE does not contain it** — it landed
  on the host tree at 04:58, after the 00:32 image build. Use the
  HANDOFF §4 mount fallback; fold the file into the NEXT image build (do
  not rebuild prod for this alone). Its drift alarm is working (it
  correctly flagged today, and the flag decomposed to structural causes).

### Owner-facing summary

Working: newborn guard, exit-verb (n=2), arm executor plumbing, adapt
retire, flatten journal, liq-defense, docs up, 0 tracebacks. Lost today
(UTC): −15.48 realized, no catastrophic dump (largest single loss −5.24 —
the 971-class tail remains absent). New issue found: the breakeven ratchet
can (a) cut recovering winners and (b) be retro-armed by the desk's own
reduce — both n=1, evidence bar set, nothing shipped. Watching, not
tuning: `BREAKEVEN_ARM_FEES` stays untouched until the triggers above
fire.
