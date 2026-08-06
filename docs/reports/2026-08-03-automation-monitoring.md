# Automation monitoring — 2026-08-03 hourly loop

Owner-set loop (cron `e8d5917a`, :17 each hour), started 2026-08-02 18:30 PDT
/ 2026-08-03 01:30Z, runs until 2026-08-03 10:00 PDT unless stopped earlier.
Cycle notes newest-first. Predecessor: `2026-08-02-automation-monitoring.md`.

---

## Cycle 25 — 2026-08-03 23:22Z (the book turned strongly positive)

### `horizon-discipline` is measurably working

**One** capital-protection close in the 24 hours since the skill shipped
(2026-08-02 23:24Z), against **9 churn round-trips ≈ −6** in the two days
before it. Queried the whole window for "protect capital" / "preserve capital"
/ "protecting capital" — a single row came back.

That one is **947 HG**, opened 22:05Z and closed 22:50Z for **−0.92**:

> *"After losing the high-water mark and seeing weak momentum, we close the long
> position **to protect capital**."*

`horizon-discipline` names that phrase explicitly as **not** a valid trigger. So
the skill was in its prompt and it went anyway — but at 1 instance against a
9-instance baseline, this is an exception, not a pattern. **Not shipping.**

### …and the "high-water mark" it lost never existed

947's `peak_pnl_usd` is **−0.92**, equal to its realized — the position was never
green. `_position_state_line` only renders the high-water sentence
`if peak and peak > 0`, so **no high-water line was in that prompt at all.**

That is #210 working exactly as intended (the peak is correctly anchored, not
stale) and the desk **fabricating a justification** for a decision it had
already made. Different defect from the one #210 fixed, and worth watching: a
rationale citing a number the prompt never contained.

### The book

| run | realized | open | net |
|-----|----------|------|-----|
| **942 SOL short** | +6.753 | **+7.944** | **+14.70** |
| **943 ETH short** | +5.722 | +4.528 | **+10.25** |
| **945 ZEC short** | −2.123 | **+9.358** | **+7.24** |
| 946 USDKRW long | −0.130 | +0.329 | +0.20 |
| 947 HG | −0.920 | closed | −0.92 |
| **total** | | | **≈ +31.5** |

All three crypto shorts are paying as the tape falls. 942 reduced half at
73.398 (banking +8.39), 943 at 1855.30 (+5.74) — both after genuine progress
toward target, so both compliant with #211. 945 sits in loss cooldown from its
earlier bad reduce while its remaining half runs **+9.36**.

944 BTC held (conf 0.58) — no `rr_floor` refusal this cycle because it did not
try to enter. 948 ZC holding. 939/940 weekend-gated.

0 tracebacks, site/docs 200.

---

## Cycle 24 — 2026-08-03 22:22Z

### 943's tight stop did NOT trigger — my concern did not materialise here

Price went 1865.90 → 1863.10, in the short's favour. 943 reduced half at 1863.4
instead, taking realized from −1.975 to **−0.021**. **Still one stop-out total;
the second-stop-out bar remains unmet and I am not shipping the tight-stop
change.** Stating that plainly because I flagged this position as the likely
proof and it went the other way.

### The ladder rule met its 2-cycle bar

**942 cycle 2 held a green short rather than halving it**, for the second
consecutive cycle across the 932/942 pattern:

> *"Maintain the short position while it remains below entry, with a modest stop
> at ~74.5 and target near 72.0; close fully if price breaches $75."*

`intent: arm {price_above 75.0 → close 1.0}`, `action: hold`. Named the level,
kept the position. Its authored bracket this cycle was `0.99 / 2.5` — sane.
**#211 is working.**

### #209 confirmed across three fresh fleet builds

946 forex/spot, 947 futures/spot, 948 futures/spot — **all `dir=long`, all
`via=fleet`**. No short-on-spot thesis was published. 947 traded on cycle 1
(HG copper long, `stop 1.43 / target 2.86`).

### NEW (1 instance) — 945 called a losing leg "profit"

945 cycle 2: *"Reduce half the short to bank profit while arm a close if price
falls below 480."* It was short from **484.27** and covered at **484.29** — the
price had moved *against* it. The leg cost **−0.75**, almost all of it the 0.687
fee. `_position_state_line` would have shown roughly −0.06 open P&L at that
moment, so the desk contradicted a number it was handed.

One instance, no pattern yet. Logged, not acted on.

### The `arm` case is now the strongest open item

Four structured **apply-mode** arms, every one compiling to `steps: []`:

| run | when | conditional |
|-----|------|-------------|
| 916 | 08-02 17:18 | price_above 478 → reduce 0.5 |
| 937 | 08-03 11:07 | price_below 462 → reduce 0.5 |
| 932 | 08-03 17:06 | price_above 74.0 → reduce 0.5 |
| **942** | **08-03 21:57** | **price_above 75.0 → close 1.0** |

Plus prose-only attempts from 932 c15 and 945 c2 — **six occasions the desk
wanted a conditional and received nothing**, against 11 shadow-mode arms.

And #211 now *instructs* it to name a level and wait instead of reducing. 942 is
doing exactly that, and its stated protection at 75.0 does not exist. **I made
the unbuilt path the recommended one.** This is a feature build rather than a
fix, so it is not a late-night job — but it is the largest open item, and it is
open partly because of a skill I shipped.

### Book

| run | realized | open |
|-----|----------|------|
| 942 SOL short | −1.633 | **+7.329** |
| 943 ETH short | −0.021 | +3.293 |
| 945 ZEC short | −2.123 | +0.882 |
| 947 HG long | −0.095 | −0.730 |

Open net **≈ +6.90**. 944/946/948 flat, 939/940 weekend-gated. 0 tracebacks,
site/docs 200.

---

## Cycle 23 — 2026-08-03 21:22Z (book reset by the owner; two findings confirmed live)

### #214 deployed — image `20260803-sellverb`

Verified in the image: light path gates `"sell"` on `can_sell`, `can_sell`
derived from `is_futures_book or pos_qty > 0`, and both `_trader_risk_decision`
and `run_analysis` carry the parameter. After: 0 tracebacks, both gates live in
the worker, 26/26 skills, all three positions through the recreate,
site/docs/health 200. Rollback `20260803-emphstrip`.

### The day's closed book

| run | final | note |
|-----|-------|------|
| **937 ZEC** | **+11.661** | run of the session — seven scale-outs, then re-entered and flattened on stop |
| 941 BTC | **−8.045** | the tight-stop stop-out |
| 932 SOL | −0.638 | |
| 933 / 934 / 938 | **0.000** | never traded — the paralysis runs |
| **total realized** | **+2.979** | |

The three zeroes are the whole story of the night: 933, 934 and 938 burned ~25
cycles between them and never opened a position. Every fix shipped today exists
to stop that recurring.

### Owner reset at 21:05Z — new fleet, all crypto shorts

942 SOL, 943 ETH, 944 BTC, 945 ZEC created 21:09Z. Positions are far larger than
the previous fleet (SOL **49.19** vs the old 7.2), and entry fees alone came to
**4.98**.

### CONFIRMED LIVE — the aggressive preset is still blocking the owner's runs

**944 BTC, cycle 1:** `gate_skip rr_floor: reward 9556.2000 < 2x risk
5096.6400 (entry 63708.0000)` → **15.0% / 8.0% = 1.875**.

That is exactly the bracket from cycle 3. #205 corrected the *preset* so future
applications write 0.16, but agent 6's stored `risk_limits` row still reads
`take_profit_pct 0.15` — and 944 deferred its params, so it inherited it and was
refused. **Code fixed, stored row unchanged; that row is the owner's to rewrite,
not mine.** First live proof that the distinction matters.

### CONFIRMED LIVE — fifth sub-1% stop, now on real size

**943 ETH, cycle 1:** authored `stop_pct 0.3 / target_pct 0.6000000000000001`
on a **2.3524 ETH (~$4,390)** short. Stop sits at **1871.498** against a
**1865.90** entry — 5.6 points on ETH, which is minutes of ordinary movement.
Both sides of the bracket are inside noise; the float artifact again shows the
target is `0.3 × 2`, computed to clear the R:R floor rather than derived.

Sub-1% stops authored: 941 c1 **0.60** (stopped out, −8.045), 932 c18 **0.64**,
937 c17 **0.30**, 937 c21 **0.30**, **943 c1 0.30 on ~$4,390**.

Its siblings chose sane brackets the same minute — 942 `1.6 / 3.4`, 945
`2.2 / 4.5` — so this is 943's own choice, not a systemic default.

**Still not shipped.** My bar remains a *second* stop-out and there has not been
one. But 943 is now a live experiment that should resolve within a cycle or two,
and if it stops out on noise the bar is met with the largest exposure yet.
**That is the first thing to check next cycle.**

### Book

942 −1.633 / +1.968 · 943 −1.975 / +3.764 · 945 −1.373 / +0.819 →
open net **≈ +1.57**. 939/940 weekend-gated. 0 tracebacks, site/docs 200.

---

## Cycle 21 — 2026-08-03 19:22Z

### #213 deployed — image `20260803-emphstrip`

Verified in the image before the swap on the real 939 payload: the bolded key
now parses to `confidence 0.57` **and** `**News analyst**` survives inside the
report. After: 0 tracebacks, stripper live and wired into `_json_objects`,
26/26 skills, 932's position through the recreate, site/docs/health 200.
Rollback `20260803-laddertarget`.

### NEXT FIX IDENTIFIED — the desk is offered a verb its book cannot execute

939 cycle 19 decided `sell` at **conf 0.62, thesis_alignment 0.8** and was
refused: *"spot sell with no inventory — treated as hold"*. Same wall 938 died
on — but **939 is owner-created**, so #209 (which gates fleet *research theses*)
does not cover it. This is the desk reaching the conclusion independently.

**Measured across the whole history: 33 blocked spot-sells, 16 runs,
2026-07-27 → today** — ~1.8% of 1,807 decisions. 935 SPCX alone has 3 today now
that US markets are open.

The cause is an internal contradiction in one prompt. `inventory_rule`
(`run_engine.py:2527`) says *"Spot book with no inventory: 'sell' is NOT
available… a bearish read means 'hold'"* — while the action set five lines later
(`:2609`) offers `"buy"|"sell"|"hold"` unconditionally. **The prompt tells it
sell is impossible and then lists sell as an option.** The comment at `:2513`
even records the symptom — *"spot runs emitted unactionable sells"* — so the
awareness fix landed and the vocabulary fix never did.

This is the same shape as every other fix tonight: an instruction the model is
shown and ignores. The answer is to stop offering the verb, exactly as `retire`
is already offered only when flat.

**Not shipped this cycle, deliberately.** The light path is a one-line
conditional, but 939 runs the **full** path, and
`analysis_agents._trader_risk_decision` receives `position_state` as a
*pre-rendered string* — gating its action list means plumbing a `can_sell` flag
through two modules. Both paths need it and both need tests; that is not a
job to rush at the end of a long session. Next cycle.

### Book

932 deteriorating: adapt `losing_close` −0.6323, `size_mult` 0.5, `conf_bump`
0.1, loss cooldown. Its short sits −1.062 with price 74.043 against a 73.579
entry — above the 74.0 level it thought it had armed.

| run | realized | open | net |
|-----|----------|------|-----|
| 937 | **+11.895** | flat | **+11.895** |
| 932 | −0.179 | −1.062 | −1.241 |
| 941 | −8.045 | — | −8.045 |
| **total** | | | **≈ +2.61** |

0 tracebacks, site/docs 200.

---

## Cycle 19 — 2026-08-03 17:22Z (ladder rule: one landed, one didn't)

### 932 held instead of reducing — and named the milestone

First decision under #211 with a position open:

```
decision c23   HOLD, conf 0.58            <- not "reduce"
order_intent   intent: arm
               arm {if price_above, level 74.0, then reduce, size_frac 0.5}
```

That is the skill working as written: it did not reduce merely because the
position was green — it named the condition that would earn the next
reduction and waited. Peak also ratcheted 0.605 → **1.909** on the new
position, still measuring from its own baseline.

### 937 reduced again — and on inspection it was entitled to

Seventh halving, 0.0477 → **0.0238** @ 492.16, realized **+11.558**. The
position is now **1.6%** of what it opened.

But the skill's test is whether price covered meaningful further ground toward
the stated target since the last reduction. Last reduce was 488.72; target
497.99. 492.16 is **15.7% of the remaining distance** further along. **That is a
genuine advance, so this reduction is compliant, not a violation.** The position
is dust because the halving began at cycle 13 and the trend kept running — a
consequence of the pre-#211 legs, not of this one.

**One cycle, one clear landing, one compliant reduce. Not judging the rule yet
— the 2-cycle bar applies.**

### The skill I shipped increases demand for a feature that does not exist

`arm` intents in apply mode are now **3** (916 on 08-02, 937 c12, and 932 c23
today) against 11 in shadow. All three compile to `steps: []`.

This is worth stating plainly: **#211 tells the desk to wait for a milestone
instead of reducing, and the natural way to express "reduce when X" is `arm` —
which is journaled and discarded.** I have made the unbuilt path more attractive.
932's decision was still an improvement (it held rather than churned), but its
stated protection at 74.0 is not real. Arm execution moves up the queue on the
strength of this, not down.

### Other

- **941 recovering**: conf 0.42 → **0.54**, `thesis_alignment` 0.7, momentum 0.6,
  `risk_context` still 0.3. Holding, not re-entering, `size_mult` 0.5.
- **939 TSLA** cycle 17, hold with a genuinely specific condition: *"No new
  position is taken until TSLA clears its 20-day MA and fear subsides."*

### Book

937 +11.558 / +0.343 = **+11.90** · 932 +0.453 / +0.023 = +0.48 ·
941 −8.045 · total **≈ +4.34**. 0 tracebacks, site/docs 200.

---

## Cycle 18 — 2026-08-03 16:22Z

### Deployed #211 + #212 — image `20260803-laddertarget`

`exit-discipline` auto-upgraded (`updated_by=seed-upgrade`) with the
target-indexed ladder rule; the review scrub is live in `run_feedback`.
Blocks: light/crypto **8580**, trader/us-stock **18528** / 20000. 26/26 skills
enabled. Both open positions survived the recreate. 0 tracebacks,
site/docs/health 200. Rollback `20260803-peakanchor`.

### The peak re-anchor survived a full round trip — this is the real proof

Last cycle 932 was flat and its peak had been re-anchored 1.842 → 0.605. This
cycle it opened a **new** short (4.5786 SOL @ 73.579) and the peak ratcheted to
**1.103** — up from the 0.605 baseline, not from the old 1.842.

**The new position is measuring its own high-water from its own starting
equity.** That is precisely the behaviour #210 was written for, observed
end-to-end on live data rather than in a test.

### 937 halved a sixth time — realized **+11.180**

1.5251 → 0.7626 → 0.3813 → 0.1906 → 0.0953 → **0.0477**. The position is now
**3.1%** of what it opened. #211 deployed *after* this cycle's decision, so the
next cycle is the first genuine test of the ladder rule.

### NEW — a third tight-stop instance, and it sharpens the finding

937 cycle 17 authored `stop_pct 0.3 / target_pct 0.6000000000000001`.

A **0.3% stop on crypto** (~2%/day vol) is the tightest yet. But the revealing
part is the target: `0.6000000000000001` is literally `0.3 × 2` in float. **The
desk is computing the target mechanically to clear the R:R floor, not deriving
it from structure.** So when it shrinks the stop into noise, the floor drags the
target into noise with it, and the whole bracket can only generate fees.

Sub-1% stops authored so far: 941 c1 **0.60** (stopped out, −8.045),
932 c18 **0.64**, 937 c17 **0.30**. Three authored, **one bound**.

**Still not shipping.** My stated bar last cycle was a *second stop-out*, and
there has not been one — 4 stop-triggered exits exist in the entire history, so
stops rarely bind at all. The mechanism is now well understood; the outcome
evidence is not there yet.

### Other

- **941 degrading correctly**: cycle 5, conf 0.42, conviction 0.3625,
  `risk_context` 0.2, `size_mult` 0.5 from the post-stop-out adapt chain.
  Holding, not re-entering. That is the adapt machinery doing its job.
- **939 TSLA**: 16 cycles, all holds, all via the **full** path (`route: null`)
  with real rationales rather than gate skips.

### Book

| run | realized | open | net |
|-----|----------|------|-----|
| 937 | +11.180 | +0.606 | **+11.79** |
| 932 | +0.453 | −0.009 | +0.44 |
| 941 | −8.045 | — | −8.045 |
| **total** | | | **≈ +4.19** |

---

## Cycle 14 — 2026-08-03 12:22Z (the venue gate proved itself in production)

### #209 confirmed on live data — and the prediction was exact

| batch | created | selectable |
|-------|---------|-----------|
| `research:496042` | 10:58:18Z (pre) | **12 / 12** |
| `research:496043` | 11:27:14Z (post) | **7 / 12** |

Worker came up on `venuegate` at **11:23:47Z**, 3½ minutes before 496043 —
attribution is clean. The five dropped rows are exactly the short-on-spot set:

```
NG       futures   short  spot   0
QCOM     us-stock  short  spot   0
SPCX     us-stock  short  spot   0
USDJPY   forex     short  spot   0
USDKRW   forex     short  spot   0
```

All three crypto shorts (`futures`) and all four longs survived. **The pre-ship
measurement said 5 dropped / 7 survive; production delivered 5 / 7.**

### 938 died exactly as diagnosed

```
decision c12   sell, conf 0.58, thesis_alignment 0.8
gate_skip      "spot sell with no inventory — treated as hold"
alert          {"stop_reason": "idle_retired"}
run_status     running -> stopping -> stopped (idle_retired)
```

Twelve cycles, zero trades. It finally *tried* to sell and got the refusal
`run_engine.py:2527` guarantees. Same fate as 933 (6 cycles) and 934 (7).
**#209 stops the fleet building the next one.**

### The refill traded on cycle 1

Fleet 26 replaced it with **941 BTCUSDT — crypto / futures / short**, i.e. an
expressible thesis:

```
created 12:08:16Z, cycle 1 at 12:09:01Z (45 seconds later)
decision  sell, conf 0.71, conv 0.735
params    stop 0.6% / target 2.0%  -> R:R 3.33, self-authored
trade     short 0.014887 BTCUSDT @ 62425, fee $0.418
```

**938 never traded in twelve cycles; its replacement traded in one.** That is the
venue gate and the skills working together end to end.

### 937 scaled out half — realized **+3.748**

`reduce 0.5` compiled to `sell 0.5` (correct verb for a long), 0.7626 ZEC @
481.65. Remaining half **+6.047** open, peak 9.795. Stop 466.09 / target 497.99
still from its own cycle-11 bracket.

### 932 re-entered large

Short **12.628** SOL @ 72.389 (conf 0.71, conv 0.74, size_scale 0.967), stop
0.64% / target 1.28%. Currently −1.452.

### NEW WATCH — stops tighter than a day's noise

| run | cycle | stop | market daily vol | distance travelled in 1 cycle |
|-----|-------|------|------------------|-------------------------------|
| 932 | 18 | **0.64%** | crypto ≈2%/day | already 0.16% against it |
| 941 | 1 | **0.60%** | crypto ≈2%/day | already **0.33%** against it |

Both new entries put their stop well inside one day's ordinary range, and both
are over a third of the way to it within a single cycle of entering. This is the
**mirror** of the unreachable-trail problem: `reachable-exits` warns about a stop
*wider* than the expected move and says nothing about one *tighter* than noise.

Two instances, **no outcome yet** — neither has been stopped out. Logged, not
shipped. If either dies to noise next cycle that is the evidence.

### Book

| run | realized | open | net |
|-----|----------|------|-----|
| 932 | +0.624 | −1.452 | −0.828 |
| 937 | +3.748 | +6.047 | **+9.795** |
| 941 | −0.418 | −3.067 | −3.485 |
| **total** | | | **≈ +5.48** |

Running: 932, 935, 937, 939, 940, 941 (938 retired). 0 tracebacks, docs 200.

---

## Cycle 13 — 2026-08-03 11:22Z

### 932 closed out at **+1.036**, and the intent path stopped an inversion

```
decision c17   sell, conf 0.56, conv 0.7225
order_intent   intent: CLOSE, size_frac 1.0   |   legacy_action: "SHORT"
trade          cover 0.45113191 @ 72.503, fee $0.0147
realized       +1.036 (final)
```

On a short book `sell` means **add to the short**. The desk's legacy verb said
`short`; its intent said `close`. **The intent path took the intent** — this is
exactly the inversion class that killed run 919's +6.79 peak on 2026-08-02, and
Plan 17 caught it live.

Full lifecycle: **7.218 → 3.609 → 1.805 → 0.902 → 0.451 → 0**, five legs, no
churn. The position produced **+2.55** against the −1.51 the run inherited.

### 937 is running **+5.49**, and it is genuinely protected

Position stop **466.092**, target **497.99** — both written from the 2.1% / 4.6%
bracket it authored itself at cycle 11. `peak_pnl` 7.94.

### The `arm` finding, softened by evidence

937 cycle 12 emitted a **structured, apply-mode** conditional:

```
intent: "arm", arm: {"if": "price_below", "level": 462.0, "then": "reduce", "size_frac": 0.5}
compiled: {"steps": [], "note": "arm"}
```

Confirmed: `arm` appears in exactly two places in the codebase — the prompt
offering the verb (`run_engine.py:2602`) and the journaling (`:3060`). **No
storage, no evaluation, no execution**, which matches the 2026-08-02 note that
it is shadow-collection by design. Totals: **11 shadow, 2 apply**.

**But the alarm I raised last cycle was overstated.** 937's existing stop sits at
**466.09**, *tighter* than the 462 it asked to arm — the conditional would have
been looser than the protection it already had, and `legacy_action` was `hold`,
so no action was sacrificed. It is not an unprotected winner. This is evidence
**for** eventually building arm execution, not an emergency, and nothing ships
for it.

### #209 deployed — image `20260803-venuegate`

Verified in the image before the swap: crypto short → `futures` expressible;
forex / us-stock / futures short → `spot`, **not** expressible; every long
expressible everywhere. After, 3 passes: containers Up, 0 tracebacks,
site/docs/health 200; `thesis_is_expressible` live in the worker;
26/26 skills, all six runs cycling, and **937's open ZEC long survived the
container recreate**. Backups `/tmp/venue-bak/`,
`.env.bak-20260803-venuegate`; rollback `20260803-scrubstale`.

### (c) The scrub holds at four cycles

938 cycle 11: `thesis_alignment` **0.9**, confidence 0.65, still no level cited.
It holds because it cannot short — which #209 now prevents at the source for
future builds.

### Book

932 **+1.036** realized and flat · 937 −0.327 realized, **+5.49** open ·
total ≈ **+6.20**. 0 tracebacks, docs 200.

---

## Cycle 11 — 2026-08-03 09:22Z

### (a) Third halving; run realized **+0.797**, and `thesis_review` fired

```
thesis_review  INTACT — "net positive P&L with 2 of 3 closes winning,
                confirming the anticipated retracement"     <- 3-closes trigger
adapt          winning_close, realized 0.7316, size_mult [1.0, 1.0]
decision c15   buy, conf 0.69 (highest of the night), conv 0.6775
trade          cover 0.90226381 @ 72.314, fee $0.0294
realized       +0.318 -> +0.797     peak 1.842
remaining      0.902 units, +0.439 unrealized
```

Still **zero churn** — every exit has been a partial into strength.

### The ladder that never ends — quantified, and NOT shipped

932's position: **7.218 → 3.609 → 1.805 → 0.902**, halved every single cycle.
By the time price had travelled **21%** of the distance to its own 70.546 target,
the run had shed **87.5%** of the position.

Cost versus simply holding, at the current 72.391:

| | |
|---|---|
| held whole | (72.878−72.391) × 7.218 − 0.237 fee = **+3.28** |
| actual | 2.307 realized + 0.439 open = **+2.75** |
| drag | **≈0.53**, of which 0.206 is the three extra cover fees |

**This shape is new.** Historical runs do something healthier: 902 exited in
roughly equal thirds and was done (36.25 → 11.59 / 11.34 / 13.32); 908 did full
round-trips. Nothing in the archive halves geometrically like this.

**But the cause is not mechanical greed, and that is why nothing ships.**
Cycle 15's own rationale:

> *"Take half profit now and **arm a close if price rebounds above 73**,
> preserving upside while protecting the remaining short."*

The desk wanted *reduce now* **plus** *a conditional exit at 73*. It emitted
`intent: reduce` with **`arm: null`** — the conditional survived only as prose.
Across all 235 order intents ever journaled, `arm` is populated **12 times, all
in `shadow` mode**, and arm execution is not built (by design, noted 2026-08-02).

So the desk halves every cycle because the protection it actually wants does not
exist, and certain profit is the rational substitute. Telling it to reduce less
would strip its only working protection. **The durable fix is arm execution**,
which is a real build, not a skill. Logged, not acted on: one run, the run is
winning, and "hold a bigger size" is a risk-appetite judgement rather than a bug.

### (b) Confidence — this cycle 0.69 / 0.62 / 0.58

0.69 is the night's high and another value absent from the historical top twelve.

### (c) The scrub holds — 938 is now two clean cycles

| cycle | report |
|-------|--------|
| 8 | *"**Thesis remains plausible** but the entry price has been missed and downside headroom is limited"* |
| 9 | *"**Short bias remains supported by recent down-trend**, but entry is suboptimal and stop proximity limits risk appetite, so we stay flat."* |

Neither mentions a level. `thesis_alignment` 0.8 both cycles, confidence 0.60 →
0.62. **This meets the two-cycle bar I set after judging `level-integrity` too
early.** 938 now holds on ordinary trading grounds.

937 cycle 10: `buy`, self-authored `stop 2.96 / target 7.21` (R:R 2.44), blocked
at 0.58 < its own 0.6. Consistent and legitimate.

### Health

Both containers on `20260803-scrubstale`, **0 tracebacks**. `sooppiy.com` 200,
`/docs/how-it-works` 200, bundle `index-dSlM0LOf.js`. Open positions: 1.

---

## Cycle 10 — 2026-08-03 08:22Z (all three watch items answered)

### (a) 932 laddered out again — the run is PROFITABLE

```
adapt          winning_close, realized 1.0948, size_mult 0.75 -> 1.0 (ratchet up)
decision c14   buy, conf 0.60, conv 0.64
order_intent   reduce 0.5 -> compiled [cover 0.5]
trade          cover 1.804527615 SOLUSDT @ 72.44, fee $0.0588
realized       -0.414 -> +0.318      <- THE RUN CROSSED INTO PROFIT
remaining      quarter position, +0.877 unrealized
```

Full → half → quarter, banking on each leg and letting the rest ride. The
position has produced **+1.826 realized + 0.877 open = +2.70** against the
−1.51 churn debt the run carried into it. **No churn: three cycles holding or
reducing, zero round-trips.** `horizon-discipline` still untested — the trade
has been in profit throughout, so nothing has provoked a panic close.

### (b) Confidence clustering — early, but the shape has changed

| window | cluster share {0.62, 0.58, 0.55} |
|--------|----------------------------------|
| 2026-07-28 → 08-03 05:50Z (**n=820**) | **55.9%** |
| since 05:50Z (**n=9**) | **11.1%** (one 0.58) |

Values since: 0.44, 0.52, 0.57, 0.58, 0.60, 0.60, 0.61, 0.63, 0.66 — **eight
distinct values in nine decisions**, and 0.61/0.63 never appeared in the
historical top twelve at all. The second decimal is carrying information.

Under the old distribution, seeing ≤1 cluster value in 9 draws has probability
**≈0.8%**. Suggestive, **not proven** — n=9. The honest test remains 24h.

**CORRECTION:** cycle 5 reported this clustering as "63% of all decisions". The
true figure over all 820 decisions with a real confidence is **55.9%** — the 63%
was computed against a truncated denominator (the top-twelve values only, which
omits the tail). The finding stands; the number was overstated.

### (c) THE SCRUB WORKED — 938 stopped citing the level entirely

Full decision history, the scrub landing at cycle 8:

| cycle | `ta` | report |
|-------|------|--------|
| 1 | 0.8 | *"Short thesis is invalidated by price already above the **152** level"* |
| 2 | 0.8 | *"Downtrend backs the short view but entry was missed…"* |
| 3 | 0.3 | *"…lacks a clear **invalidation level**"* |
| 4 | 0.4 | *"**Invalidation level (152)** is already breached"* |
| 5 | 0.6 | *"**Invalidation level is on the wrong side**, making the brief stale"* |
| 6 | 0.8 | *"…but the provided **invalidation level** is already breached"* |
| 7 | 0.3 | *"Short thesis is already **invalidated (price > 152)**"* |
| **8** | **0.8** | *"**Thesis remains plausible** but the entry price has been missed and downside headroom is limited, so we hold without taking a new position."* |

**Six of the first seven cycles cite the level. Cycle 8 mentions no level at
all** — because it never saw one. `thesis_alignment` 0.3 → **0.8**, and the
reason for holding moved from "my brief is broken" to an ordinary execution
judgment. This is one cycle, but the mechanism is deterministic: the number is
not in the prompt, so the desk *cannot* cite it. What still needs cycles is
whether the overall behaviour improves.

### Other

937 ZEC cycle 9: `hold`, conf 0.52, `ta` 0.45, momentum 0.4 — momentum genuinely
weakened since its cycle-8 buy attempt. Legitimate hold, no defect.

### Health

Both containers on `20260803-scrubstale`, **0 tracebacks**. `sooppiy.com` 200,
`/docs/how-it-works` 200. Runs 932/935/937/938/939/940 cycling; 939/940/935
weekend-gated. Open positions: 1 (932's quarter).

---

## Cycle 9 — 2026-08-03 07:22Z–08:00Z

### Priority watch

**(a) SOL short holding, no churn.** Run 932's remaining half at **+1.12
unrealized**, realized −0.414, run net **+0.71**, peak 1.134. The desk has not
touched it since the 07:03Z scale-out. `horizon-discipline` untested so far —
there has been no adverse move to provoke a panic close.

**(b) Confidence — too early to call.** Three post-deploy decisions. Notable:
937 cycle 8 landed `conf 0.58 / conv 0.58`, `conf_conviction_gap: 0.0` — exactly
the reconciliation `confidence-resolution` asks for. It also authored
`stop 4.3 / target 9.0` (R:R 2.09). Blocked at 0.58 < its own 0.6.

**(c) 938 REGRESSED — and this is the cycle's finding.**

| cycle | report | verdict |
|-------|--------|---------|
| 5 (05:05Z) | *"the level is on the wrong side, **making the brief stale**; price trend still modestly supports short"* | landed |
| 6 (06:05Z) | *"thesis aligns with a strong yen-strength move, **but** the invalidation level is already breached"* | half |
| 7 (07:05Z) | *"Short thesis is already invalidated (price > 152), so we hold."* | **fully regressed** |

`momentum_quality` on cycle 7 was **0.8** — the direction is right. It is
refusing on a number that was stale before the run started.

### ROOT CAUSE — a run that cannot trade cannot get the review that would let it

`maybe_review_thesis` (`run_feedback.py:315`) fires on exactly two triggers:
`due_by_closes` (needs `state["closes"] > 0`) or `due_by_drawdown` (needs an
open position). **A run that never opened a position has neither — and the
broken thesis is precisely what stops it opening one.** The run cannot reach the
checkpoint that would adjudicate its own brief.

And the verdict is monotone-tightening: `intact` → nothing, `weakened` → shrink
size, `invalidated` + pnl ≤ 0 → retire. **It cannot repair a thesis even if it
ran.** So triggering it is not the fix either.

That is how 933 (6 cycles) and 934 (7 cycles) died, and 938 is at 7 and still
going. **~20 cycles and zero trades across the three.**

### DEPLOYED — image `20260803-scrubstale` (07:42Z)

main was exactly prod + #208; two files, no SPA. Prod's `run_engine.py`
sha-matched the `01480f0` baseline before upload (`b144fb6e98ee6d12`) and the
merged commit after (`5053cd5440ff952f`).

**Verified in the image before the swap, against the real prod payloads:**
938's *"A break above 152.00…"* at 156.73 → level removed, rationale kept,
**stored thesis untouched**; 937's *"$18"* at 472.29 → removed; a genuinely
usable *"swing high near 158.0"* at 156.73 → **survives verbatim**.

**Verified after, 3 passes:** (1) both containers Up on `20260803-scrubstale`,
0 tracebacks each, site/docs/health 200; (2) live worker — `_usable_thesis`
present, `"_usable_thesis(thesis, entry)"` confirmed inside `_light_analysis`,
and it calls `invalidation_is_coherent` so both ends of the pipe share one
definition; 26 skills, `MAX_BLOCK_LEN` 20000; (3) prod MySQL 26/26 skills
enabled, all six runs cycling, and **the open SOL position survived the
container recreate** (−3.60905523 @ 72.878, +1.075 unrealized), 15 worker loops.

Backups `/tmp/scrub-bak/`, `.env.bak-20260803-scrubstale`; rollback
`20260803-confres`.

**Next cycle (~08:03Z) is the first with the scrub live — 938 is the run to
watch.** It should no longer be able to cite 152 at all.

### Shipped — PR #208, `_usable_thesis`

The confidence lesson, again: the light prompt has told the desk not to default
to a habitual value since 2026-07-26 and it does it anyway; `level-integrity`
tells it a stale level means a stale brief and it complies twice out of three.
**Instructions do not reliably beat text the model is shown.** So do not show
it — `_usable_thesis` drops an already-passed level before the prompt is
assembled and substitutes a derive-your-own-from-structure instruction. The
stored thesis is untouched; only the desk's *view* changes. Relative levels and
genuinely reachable ones pass through as written.

Coherence is judged by `symbol_research.invalidation_is_coherent` — the same
function the research planner is gated on, so both ends of the pipe agree on
what "usable" means.

**Verification: 4 of 5 mutations killed.** `drop-callsite` **survived the first
pass** — five tests exercised the helper and none proved it was wired into the
prompt, which is the only property that matters; a test now asserts `152.00` is
absent from the actual prompt string. The remaining survivor is the entry guard,
made redundant by the empty-level check below it — not a coverage gap, and not
claimed as one. Suite **3090 passed + 1300 subtests**, ruff clean.

### Health

`0` tracebacks both containers, `sooppiy.com` 200, `/docs/how-it-works` 200,
SPA bundle `index-dSlM0LOf.js` (matches the cycle-4 publish). Open positions: 1.

---

## Cycle 8 — 2026-08-03 07:10Z (the trade paid, and the desk banked half)

**Run 932 cycle 13, 07:03:52Z — scaled out of its winner.** Not churn: a
partial profit-take with half still riding, the exact shape the 2026-08-02
report praised in run 916.

```
decision      buy, conf 0.61, conv 0.64  "Partial profit-take: buy to close half"
order_intent  reduce, size_frac 0.5, basis position -> compiled [cover 0.5]
trade         cover 3.60905523 SOLUSDT @ 72.542, fee $0.1178, signal_id 321
position      -7.21811046 -> -3.60905523   (half remains)
realized      -1.51 -> -0.414              (this leg banked +1.096 net)
```

Entry 72.878 → scale-out 72.542 = +0.336/unit × 3.609 = +1.213 gross, −0.118
fee. The remaining half sits at **+1.090 unrealized**, so the run is now
**+0.676 net** against the −1.51 it carried into the position.

**Four separate mechanisms, all shipped in the last 24h, are visible in this one
run's lifecycle:**

| mechanism | evidence |
|-----------|----------|
| `confidence-resolution` (#207, 05:50Z) | conf 0.57×3 → **0.63**, cleared the gate, trade opened |
| `reachable-exits` (#204/#206) | self-authored `1.45/3.2`, **R:R 2.21**, cleared `rr_floor` |
| `exit-discipline` (pre-existing) | *"banking profit is a first-class action… prefer reducing"* → half covered |
| Order Intent apply mode (Plan 17) | `intent: reduce 0.5` compiled to `cover`, executed as a real trade |

`horizon-discipline` was **not** contradicted — this is a reduce, not an exit,
and the thesis stays on with half the size. The churn test is still ahead: the
question is whether the remaining half survives to its target or gets closed on
generic capital-protection language.

### Query note (not a defect)

My first pass reported "no `trade` event journaled". That was wrong — the trade
is at seq 759. The `CONCAT(... JSON_EXTRACT(payload,'$.cycle') ...)` in my query
returns NULL for `trade` rows, whose payload has no `cycle` key, so the row
printed blank. `order_intent` was also missing from that query's event filter.
No telemetry gap; a reporting-query bug on my side.

---

## Cycle 7 — 2026-08-03 06:44Z (THE FLEET TRADED)

### First trade of the night, 13 minutes after `confidence-resolution` went live

**Run 932, cycle 12, 06:03:19Z — short 7.218 SOLUSDT @ 72.878**, fee $0.2367,
`client_order_id run:932:cyc:12`. Position 127 is open and **+1.94 unrealized**
before fees (price 72.609 against a 72.878 entry).

The chain, end to end:

| step | evidence |
|------|----------|
| confidence moved off the habitual value | **0.57 → 0.63** (0.57 had held for cycles 9, 10, 11) |
| it reconciled with its own scored evidence | conviction 0.6725, gap now +0.04 instead of −0.08 |
| it cleared the gate | 0.63 > 0.5800000000000001 |
| it authored its own bracket | `stop_pct 1.45 / target_pct 3.2`, **R:R 2.21** |
| that bracket cleared `rr_floor` | 2.21 > 2.0 |
| the bracket reached the position verbatim | `sl 73.9347` = entry ×1.0145, `tp 70.5459` = entry ×0.968 |

Its own reasoning: *"Short entry is justified by a clear downtrend, decent
momentum and a good price relative to the reference, with a stop near the recent
swing high offering ~2:1 R:R."*

**Every skill shipped tonight is visible in that one decision** — the confidence
was derived rather than picked, the bracket was authored rather than inherited,
and the geometry cleared a floor that a house default could not.

### `level-integrity` landed hardest on run 937

937 ZEC, cycle 7: *"**Invalidation at $18 is irrelevant**; entering long with a
2% stop and 5% target aligns modestly with the rebound thesis."*

That is the skill working exactly as written — the desk names the unusable level,
dismisses it, and proceeds on structure with a bracket it authored itself
(R:R 2.5). Two cycles ago this run deferred its bracket and died at `rr_floor`;
before that it refused outright on the bad level. Blocked this cycle only on
confidence (0.57 < its own 0.6), which is a legitimate refusal.

### Confidence distribution — moving, but 3 decisions is not a distribution

| run | before | **now** |
|-----|--------|---------|
| 932 | 0.57, 0.57, 0.57 | **0.63** |
| 938 | 0.45, 0.58 | **0.66** |
| 937 | 0.62, 0.58, 0.56 | 0.57 |

Two of three moved decisively off the 0.55/0.58/0.62 cluster. **This is three
decisions, not a distribution** — the 63% clustering figure came from ~1,150
decisions over six days. Promising, not proven. The honest test is whether the
cluster share falls over the next 24h.

### Still open

- **938 USDJPY** raised confidence to 0.66 and still holds, citing *"the provided
  invalidation level is already breached"* alongside *"thesis aligns with a
  strong yen-strength move"*. It half-applies `level-integrity`: it no longer
  treats the level as fatal, but still lets it block. 937 shows the fully-landed
  form. Worth one more cycle before judging.
- Run 932's `realized_pnl` is −1.51 from the earlier churn; the new position is
  the first that could pay it back.

### Health

Both containers Up 59m on `20260803-confres`, **0 tracebacks** each. Liquidation
daemon active. `sooppiy.com` 200, `/docs/how-it-works` 200, liq-defense doc
intact (42,432 bytes). Open positions: **1**.

---

## Cycle 5–6 — 2026-08-03 05:05Z–05:50Z

### THE BIGGEST BRAKE ON THE FLEET — and it is not the gates

Confidence values across every decision since 2026-07-28:

| confidence | decisions | gate it sits under |
|-----------|-----------|--------------------|
| **0.62** | **166** | 0.65 |
| **0.58** | **156** | 0.60 |
| **0.55** | **136** | 0.57 / 0.58 / 0.60 |
| 0.0 (parse fail) | 59 | — |
| 0.60 | 52 | 0.65 |

**63% of all decisions land on three numbers, and each parks just under a
common threshold.** Runs 37/38/39 emitted 0.62 for *dozens of consecutive
cycles* against a 0.65 gate and never traded. Run 932 has said **0.57 three
cycles running** (c9/c10/c11) while its own `conviction` — the deterministic
blend of the four component scores it emits itself — climbed 0.5625 → 0.5675 →
**0.6475**. The evidence moved; the stated confidence did not.

This is not a gate problem. 0.62 against 0.65 is a *correct* refusal of a
mediocre read. The problem is that the read is never computed.

**Why the existing instruction fails.** The light prompt already says *"Do not
default to a habitual value"* (`run_engine.py:2511`, from the 2026-07-26
recalibration) and is ignored — because the same rubric names **0.55 / 0.65 /
0.75** as landmarks. A model asked for a number from a list of landmarks returns
a landmark, or the midpoint between two. `0.55` is named outright; `0.58` and
`0.62` are the gaps. Repeating the prohibition louder was never going to work.

**Shipped: PR #207, `confidence-resolution`** (prio 48, light+trader) — a
*construction* instead of a prohibition: derive the number from the same four
components you are about to score, then reconcile the two before emitting.
`compute_conviction` (`run_engine.py:2228`) already blends those scores
deterministically, so the system can already see when stated confidence and
scored evidence disagree; the skill makes the desk do that reconciliation first.
A landmark answer is named as the tell it is, and the second decimal is asked to
carry information.

`MAX_BLOCK_LEN` 18000 → 20000. 18000 technically still fit at **17859** — 141
characters spare, which is not headroom: the first custom skill an admin wrote
would have pushed a *default* out instead of itself, inverting the budget's
purpose. Mutation-tested at 17000 and 17800; the guard fails at both.

**Deployed image `20260803-confres`.** Verified in the image before the swap
(26 skills, `MAX_BLOCK_LEN` 20000, prompts light+trader, prio 48). Verified
after, 3 passes: (1) containers Up, 0 tracebacks each, site/docs/health 200;
(2) live worker — in DB, enabled, 26/26, light/crypto 7911 and trader/us-stock
17859 both carrying it; (3) prod MySQL — all four monitoring-derived skills at
the right priorities with `["light","trader"]`, 26/26 enabled.
Backups `/tmp/confres-bak/`, `.env.bak-20260803-confres`; rollback
`20260803-presetskill`.

### CORRECTION — `level-integrity` did land, one cycle later

Cycle 4 filed an "honest negative" on run 938. It was premature. Cycle 5
(05:05:07Z):

> *"Invalidation level is **on the wrong side, making the brief stale**; price
> trend still modestly supports short but risk context is weak, so hold."*

That is the skill's own framing — brief stale, not trade dead — and 938 now
holds on a different, legitimate reason. The skill needed one cycle to land, not
a rewrite.

### Health

Both containers Up on `20260803-confres`, **0 tracebacks** each. Book still
**flat — 0 open positions**. No decisions in the 05:30–05:50Z window (hourly
cycles fire ~:02–:05; next is ~06:02Z and is the **first to carry
`confidence-resolution`**). `sooppiy.com` 200, `/docs/how-it-works` 200.

---

## Cycle 4 — 2026-08-03 04:44Z–05:10Z

### The minimum-distance fix works — first batch under it is clean

`research:496036` (04:35:47Z) is the first batch generated under the
minimum-distance rule. Every level is on the correct side **and** a real
distance out:

| symbol | :496034/:496035 level | dist then | **:496036 level** | **dist now** |
|--------|----------------------|-----------|-------------------|--------------|
| BTCUSDT short | 63,140.4 | 0.03% | **63,400** | **+0.72%** |
| ETHUSDT short | 1,864.74 (*below spot*) | wrong side | **1,885** | **+1.31%** |
| SOLUSDT short | 73.07 | 0.03% | **74** | **+1.35%** |
| ZECUSDT short | 477.69 | 0.13% | **485** | **+1.65%** |

The validator fired **0 times** on this batch — the model satisfied the rule
from the prompt alone, again. Both halves of the fix are now confirmed working
in production against live data.

### The skills are changing decisions, in one cycle

Decisions at 04:03–04:05Z are the first to carry `level-integrity` and
`reachable-exits` (deployed ~03:32Z):

- **937 ZEC, cycle 5 — it now authors its own bracket.** Cycle 4 (03:05Z)
  deferred (`deferred: true, outcome: absent`), inherited the house 8%/15% and
  died at `rr_floor`. Cycle 5: *"set a ~4% stop and ~9% target to respect a
  realistic risk/reward"* — **R:R 2.25, clears the floor.** The behaviour
  changed in a single cycle, and from the *base* `reachable-exits` body; the
  explicit "always author" extension (#206) is not even deployed yet.
- **932 SOL, cycle 10** — *"tight stop near the recent high (~73.09) and a target
  around 71.5"*: a bracket anchored to visible structure rather than a
  percentage, which is what the skill asks for.

Both were then blocked on confidence, correctly: 932 at 0.57 < 0.58, 937 at
0.58 < its own 0.6 minimum. **No trade yet, but the refusals have moved from
"impossible configuration" to "not confident enough" — which is a real gate
doing its job rather than a defect.**

### HONEST NEGATIVE — `level-integrity` did not move run 938

938 USDJPY, cycle 4 (04:04Z), with the skill confirmed in its prompt
(forex `light` block = 6452 chars, both skills present):

> *"Invalidation level (152) is already breached, making the short thesis unsafe
> despite recent down-trend momentum."*

The skill says an unusable level means the brief is stale, not that the trade is
dead — say so and judge on structure. 938 acknowledged supporting structure
("recent down-trend momentum") **and refused on the level anyway**. So the skill
rode and did not land, at least on the first cycle.

One instance. Not acting on it. Candidates if it repeats: the wording is
outranked by something earlier in the prompt, or 938's build-time thesis
(baked into `config_snapshot_json` with the stale 152) needs re-deriving rather
than reinterpreting. Watch next cycle.

### Health

Both containers Up on `20260803-leveldist`, **0 tracebacks** each over 60m.
Book still **flat — 0 open positions**. Runs 932/935/937/938/939/940 all
cycling. `sooppiy.com` 200, `/docs/how-it-works` 200 (SPA bundle
`index-BkMlsZgE.js`), liq-defense doc intact.

### SHIPPED — #205 + #206, image `20260803-presetskill` (04:52Z)

main was exactly prod + my two PRs (no other session merged in between), so the
five changed files went up surgically. All three pre-existing prod files
sha-matched the `c043248` baseline before upload and the merged commit after.

**Verified in the built image before the swap:** all three presets now grade
**exactly 2.000** and clear `rr_floor_violation` in *both* directions —
stable 3/6, balanced 5/10, aggressive **8/16**. The skills probe returned empty
there, which is the documented fail-soft (`docker run` has no DB, so
`skills_block` degrades to `""`); the catalogue body was checked directly
instead and carries both the authorship line and the closing line.

**THE THREE-ROOTS TRAP BIT, AND WAS CAUGHT.** After publishing the new dist to
`/usr/share/nginx/sooppiy`, the admin root still held
`AutomationPage-B5KwyVwr.js` — the *old* chunk, still reading `tp:15`.
Republished `~/sooppiy/admin-site` with `sudo cp` + `chown root:root` +
`restorecon` + `docker restart sooppiy-admin`. Proof by comparison:

```
new  aggressive:{interval_minutes:30,min_confidence:.55,size_usd:1e3,sl:8,tp:16}
old  aggressive:{interval_minutes:30,min_confidence:.55,size_usd:1e3,sl:8,tp:15}
```

**Verified after, 3 passes:** (1) both containers Up on
`20260803-presetskill`, 0 tracebacks each, site/docs/health 200; (2) live
worker — `aggressive 0.08/0.16`, `reachable-exits` **`updated_by=seed-upgrade`**
(the catalogue auto-upgrade fired exactly as `test_catalogue_upgrade_flows_to_
untouched_rows` predicts), authorship line present in the DB body,
light/crypto 6916 and trader/us-stock 16864 ≤ 18000; (3) prod MySQL 25/25
enabled with the new description, and **both hostnames serve the same bundle
`index-dSlM0LOf.js`** — main app and admin console in sync.

Backups: `/tmp/presetskill-bak/`, `.env.bak-20260803-presetskill`,
`/usr/share/nginx/sooppiy.prev-20260803-045425`,
`~/sooppiy/admin-site.prev-20260803-045517`. Rollback image
`20260803-leveldist`.

---

## Cycle 3 — 2026-08-03 03:44Z–04:20Z

### The desks started deciding again — and hit two different walls

**First entry verdicts since the paralysis.** Both fleet desks moved off `hold`
for the first time in hours (these ran 03:02–03:05Z, i.e. after the cycle-1
thesis fix but *before* the cycle-2b swap at ~03:32Z):

- **932 SOL — `sell`**, conf 0.57 / conv 0.5625, and it authored its own bracket:
  *"Short entry near 73.02 with ~1.5% stop above recent swing high and ~3.2%
  target down"* → R:R 2.2, a clean self-authored geometry.
- **937 ZEC — `buy`**, conf 0.62 / conv 0.645, thesis_alignment 0.6.

Neither executed. Two separate gates, and the second one is a real defect.

### THE PHANTOM 15%/8% BRACKET IS FOUND — a shipped preset that can never trade

937's buy died at `rr_floor`:

> `r:r floor: reward 71.6595 < 2x risk 38.2184 (entry 477.7300)`

71.66/477.73 = **15%**, 38.22/477.73 = **8%**. `risk_limits` for agent 6 reads
`stop_loss_pct 0.08 / take_profit_pct 0.15`. Source found —
`routes_automation.py:36`, `RISK_LEVEL_PRESETS`:

| preset | stop | target | R:R |
|--------|------|--------|-----|
| stable | 3% | 6% | 2.0 ✓ |
| balanced | 5% | 10% | 2.0 ✓ |
| **aggressive** | **8%** | **15%** | **1.875 ✗** |

`RR_FLOOR` is 2.0 and `rr_floor_violation` applies it to the **deterministic**
bracket too. **So every entry that defers its stop/target to the house bracket
on the aggressive profile is refused — always, by arithmetic, silently, for any
user who picks that profile.** The gate is right; the preset is wrong. The other
two sit exactly on 2.0, so `0.15` was plainly meant to be `0.16`.

This closes backlog item #5 from 2026-08-02 ("investigate phantom 15%/8% house
bracket — where does it come from?"). Three instances: runs 908 and 923 on the
2nd, run 937 today. Note 932 was *not* rr_floor-blocked — it authored its own
2.2 geometry, so only deferred brackets hit this.

**Shipped: PR #205** — preset `0.15` → `0.16`, plus the matching literal in
`AutomationPage.tsx` (the card renders SL/TP from its own copy and would
otherwise advertise a number the backend no longer applies).
`test_every_preset_can_clear_the_house_rr_floor` pins the invariant for every
preset in both directions *through the live gate*; mutation-tested (reverting to
0.15 fails it). Suite 3084 + 1300 subtests, ruff clean, tsc exit 0.
**This one touches the SPA — the dist must be republished, not just the image
swapped.**

**OPEN — needs the owner.** The code fix changes what *future* preset
applications write. Agent 6's stored row still reads `take_profit_pct 0.15`
(`updated_at 2026-08-02T12:55:17Z`), so deferred-bracket entries stay blocked
until it is rewritten. That is a live risk setting, so it is the owner's call,
not a silent edit.

### The float-precision gate, re-read

932's `sell` was blocked: *"confidence 0.57 below threshold 0.5800000000000001"*.
**This block is correct on the merits** — 0.57 really is below 0.58. Correcting
the earlier note: the float artifact only bites at exact equality, and the one
genuine instance remains 932 cycle 5 (23:02Z, confidence exactly 0.58). Still
one instance, still low priority — not the thing costing trades.

### Not yet verifiable

`research:496035` (03:08Z) is still the newest batch and **predates the
minimum-distance deploy**, so the cycle-2b fix has not been exercised. Batch
cadence has been roughly hourly (01:54 → 02:05 → 03:08); the next one is the
first under the new rule. Likewise no decision has yet run with `level-integrity`
or `reachable-exits` in its prompt — the 03:02–03:05Z decisions predate the swap.
Both land next cycle.

### Health

Both containers Up on `20260803-leveldist`, **0 tracebacks** each over 65m.
Validator fired 0 times this hour. Book still **flat — 0 positions, 0 trades**.
Runs: 932, 935, 937, 938, 939, 940. `sooppiy.com` 200, `/docs/how-it-works` 200,
liq-defense doc intact.

---

## Cycle 2b — 2026-08-03 03:08Z–04:00Z (reproduction + ship)

### Confirmed, then shipped — PR #204, image `20260803-leveldist`

`research:496035` (03:08Z) reproduced the spot-pinned levels independently of
:496034 — **7 of 8 bare-number levels across the two batches sat inside 0.13% of
spot**, and :496035's ETH level came out *below* spot for a short (`$1,864.74`
vs 1,866.05) because `factors["last"]` is the last daily candle close and the
tape had moved past it. Evidence bar cleared: two batches, independent.

**Bonus confirmation — the cycle-1 validator is firing in production.** NG in
:496035 reads *"Break above the recent swing high, or a flip to positive 5-day
momentum."* — that is the exact `_RELATIVE_INVALIDATION["short"]` string. The
backstop caught a level the prompt did not.

**Upstream fix:** a minimum distance in the prompt *and* in
`invalidation_is_coherent`, scaled to **half a day's realized volatility** — 0.5%
is noise on 4%/day crypto and a real level on 0.2%/day forex. A flat 0.3% floor
covers `vol_daily_pct is None` (any symbol with under five usable returns).

**Two skills** — per the owner's standing rule that findings land in the
catalogue, not only in the report ([[decisions-become-skills]]):

- **`level-integrity`** (prio 17, light+trader) — a level must be able to fire:
  right side of spot, far enough out that noise cannot trip it. The load-bearing
  sentence is that an unusable level means *the brief is stale, not that the
  trade is dead* — say so and judge on structure instead of refusing. Runs 933
  and 934 burned 6 and 7 cycles doing precisely that.
- **`reachable-exits`** (prio 46, light+trader) — exit parameters must be
  reachable inside the forecast move. Covers the three desk-authored trails
  (919/925/930) that set `trail_arm_pct` 40 on ~2% positions, so activation sat
  near $240 on a ~$600 book and the trail could never arm.

`MAX_BLOCK_LEN` 16000 → 18000. trader/us-stock measures **16400** with both
skills, and `test_defaults_never_hit_the_budget` **fails at 16000** — verified by
mutation, so the bump is load-bearing rather than precautionary.

**Deploy was surgical and had to be.** Between my branch point and the merge,
another session merged **#147** (`fleet_supervisor.py`) and deployed it as
`20260803-coolblocked`. A full-main deploy would have shipped their work
unverified. Proved separation with `git diff --name-only 90ae925 17f78bd` —
`fleet_supervisor.py` + its test only, **zero overlap** with my three files — then
sha-matched all three prod files to the 90ae925 baseline before upload and to
the merged commit after.

**Verified before the swap:** the built image rejected all three spot-pinned
levels and passed both controls; `MAX_BLOCK 18000`, 25 skills.

**Verified after, 3 passes:** (1) both containers Up on `20260803-leveldist`,
0 tracebacks each, site/docs/health 200; (2) live worker: `MIN_DIST` 0.003,
`MAX_BLOCK` 18000, both skills in the DB enabled at prio 17/46, light/us-stock
block 6452 and trader/us-stock 16400, both skills present in each;
(3) prod MySQL `trading_skills` — 25/25 enabled, both new rows `updated_by=seed`
with `["light","trader"]`; 39 worker tasks, no tracebacks.

Backups `/tmp/leveldist-bak/`, `.env.bak-20260803-leveldist`. Rollback image
`20260803-coolblocked`.

**Next cycle:** the first batch generated under the minimum-distance rule
(~04:05Z) should show levels a meaningful distance out, and the fleet desks'
`light` prompt now carries both new skills — watch whether any run finally takes
a position.

---

## Cycle 2 — 2026-08-03 02:44Z–03:00Z

### The fix works — and it exposed the next layer

**`research:496034` (02:05:28Z, three minutes after the swap) is the first batch
generated by the new code, and it is unrecognizable from its predecessors:**

| symbol | dir | pre-fix level | post-fix level |
|--------|-----|---------------|----------------|
| BTCUSDT | short | "above **$30,500**" | "closes above **63140.4**" |
| ETHUSDT | short | "above **$1,850**" | "closes above **1865**" |
| SOLUSDT | short | "above **$22**" | "closes above **73.0**" |
| ZECUSDT | short | (long, "above $18") | "closes above **479.2**" |
| USDJPY | short | "above **152.00**" | "above the recent swing high (**around 158**)" |

Every level is now anchored to the live price and on the correct side.
**The validator fired zero times** (`grep -c "invalidation incoherent"` = 0) —
the prompt change alone fixed it at source; the clamp gate is an unused backstop,
which is the outcome to want.

**The desks' reasoning changed with it.** Run 938 USDJPY, cycle 1 (pre-fix) vs
cycle 2 (post-fix, 02:04:18Z):

> before — "Short thesis is **invalidated by price already above the 152 level**"
> after  — "**Downtrend backs the short view** but entry was missed and a viable
>          stop-to-target ratio cannot be set, so we hold flat."

`momentum_quality` 0.6 → 0.85, confidence 0.50 → 0.58, conviction 0.57 → 0.6275,
size_scale 0.4 → 0.5917. Run 937 likewise dropped its "stop level ($18) is
unrealistically distant" complaint → "mixed price action and weak momentum".
**Both are now holding for ordinary trading reasons instead of impossible ones.**

### NEW — the model over-corrected: bare numeric levels are pinned AT spot

Given `last`, the model now answers with `last` itself. Measured against live
price 40 minutes later:

| symbol | level written | live price | distance | already crossed? |
|--------|---------------|-----------|----------|------------------|
| BTCUSDT short | 63,140.4 | 63,159.5 | **0.03%** | yes |
| ETHUSDT short | 1,865 | 1,866.05 | **0.06%** | yes |
| SOLUSDT short | 73.0 | 73.0495 | **0.07%** | yes |
| ZECUSDT short | 479.2 | 477.075 | 0.45% | not yet |

Three of four invalidated by ordinary noise inside 40 minutes. An invalidation
level set at spot is not a level — it is a restatement of spot, and it lands the
desk back in "thesis invalidated" every cycle by a different route.

Note the split: the *relative* phrasings kept sane distance (USDJPY "swing high
around 158" is ~1.0% out; HG "swing low around 6.30"; NG "closes below 2.75").
Only the bare-number answers collapse onto spot. My prompt said "ABOVE `last`
… within 50%" and the model satisfied "above" by a rounding error — there is a
maximum distance rule and **no minimum**.

Also note `factors["last"]` is `closes[-1]`, the last *daily candle close*
(`symbol_research.py:180`), not live spot — so a level pinned to it can already
be on the wrong side of the tape at build time.

**Not shipped this cycle.** Reproduced 3/3 within one batch, but that is one
batch. Per the operating model, confirming against `research:496035` (~03:05Z)
before changing anything. Candidate fix: a minimum-distance floor in both the
prompt and `invalidation_is_coherent` — scaled to `expected_move_pct` or
`vol_daily_pct` rather than a flat percentage, so it adapts per market.

### Other

- **Book still flat: 0 open positions, 0 trades.** The paralysis *reasoning* is
  fixed; the fleet has not yet taken a position. Holds are now legitimate.
- **Run 932 burned cycle 8 silently** — `cycle_seq` 8 and `last_cycle_at`
  02:01:58Z, but no `decision`, `order_params` or `gate_skip` event. The worker
  was recreated at 02:02Z, four seconds in, killing the cycle mid-flight. A
  deploy artifact, not a defect — but it shows `cycle_seq` is incremented
  *before* the decision is journaled, so any restart silently burns a cycle.
- Float-precision gate artifact recurred (932 cyc-5, 23:02Z: "confidence 0.58
  below threshold 0.5800000000000001"). Still the low-priority epsilon fix.
- 939 TSLA / 940 NVDA / 935 SPCX: `market closed` gate_skips, correct.

### Health

Both containers Up 42m on `20260803-thesiscoherence`, **0 tracebacks** each.
`sooppiy.com` 200, `/docs/how-it-works` 200; local
`docs/plan/16-liquidation-defense-daemon.html` intact (42,432 bytes). Events last
hour: 2 decisions, 5 gate_skips, 2 order_params, 366 equity — no errors.

---

## Cycle 1 — 2026-08-03 01:30Z–01:50Z

### TOP FINDING — the research planner writes price levels it was never shown, and the whole fleet is paralyzed by it

**The book is flat. Zero open positions, zero trades all night, 4/4 fleet-26
runs unable to enter.** Not caution — a data defect upstream of the desk.

`symbol_research.generate_theses()` asks the LLM for an `invalidation` *price
level* while the prompt payload contains **no price**. Rows forwarded to the
model (`symbol_research.py:533-538`) are `symbol, market, mom_5d, mom_20d,
vol_daily_pct, vol_ratio, eps_raw`. The current price exists — `factors["last"]`
is computed at `symbol_research.py:212` and is even used for the reuse key at
`:595` — it is simply never put in the prompt. With no anchor the model falls
back on training-era price memory:

| run | symbol | dir | entry_ref | invalidation emitted | live price | verdict |
|-----|--------|-----|-----------|----------------------|-----------|---------|
| 933 | BTCUSDT | short | 63,361.5 | "break above **$30,500**" | ~63,500 | 2× stale (2023 price) |
| 934 | ETHUSDT | short | 1,875.15 | "close above **$1,850**" | ~1,875 | wrong side |
| 937 | ZECUSDT | long | 488.675 | "stay above **$18**" | ~484 | 27× stale |
| 938 | USDJPY | short | 156.148 | "break above **152.00**" | 156.22 | wrong side |

Not one bad generation — three separate batches (`research:496026/496031/496032`).
Wider sample confirms the split: every thesis naming an **absolute** number is
wrong (BTC $30k/$31k, SOL $22, ZEC $18, USDJPY 152), every thesis naming a
**relative** level ("above the 20-day MA", "recent swing high") is fine. The
model is only wrong when it has to know a number nobody told it.

**Why it costs money.** For a SHORT the invalidation must sit *above* entry — a
break up kills a short. Every short above emitted a level *below* entry, so the
thesis is void the instant it is written. The desk then reads it each cycle and
correctly refuses to enter:

- **933 BTC** — 6 cycles, cycles 1/2/4/6 all "price already above the $30,500
  trigger", `thesis_alignment` 0.2–0.4 → **cycle 6 `retire`**.
- **934 ETH** — 7 cycles, cycles 2–6 all "price already exceeds the $1,850
  invalidation" → **cycle 7 `retire`** (01:02:14Z).
- **938 USDJPY** — built 01:03:30Z, **dead on cycle 1** (01:03:54Z, 24s later):
  "short thesis is invalidated by price already above the 152 level". Note
  `thesis_alignment: 0.8` while its own text says the thesis is void — the score
  and the prose disagree.
- **937 ZEC** — cycle 2: "stop level ($18) is unrealistically distant, making a
  reliable risk/reward bracket unavailable."

**The loop that makes it permanent:** invalid thesis → desk holds → desk retires
→ fleet refills the slot **from the same research pool** → new run inherits the
same defect. 933 retired → 937 built with an $18 stop on a $484 asset. The
refill cannot escape, because nothing between research and build ever checks
the level against the price.

`clamp_thesis()` (`symbol_research.py:292`) clamps direction, horizon,
confidence and expected_move — `invalidation` is passed through as raw free text
truncated to 300 chars. **No coherence validation exists.**

This is instance **#5 of the exposure-feasibility-build-gate class** (memory
`exposure-feasibility-build-gate`), on a new axis: *thesis-invalid-at-build*
rather than exposure-infeasible. The class rule holds exactly — gate it at
build, or idle-retire + refill churns forever. It is churning forever.

**Not fixable by a trading skill.** Skills are prompt blocks for the *desk*, and
the desk is already behaving correctly here: refusing a void thesis is the right
call. The defect is upstream, in what research is given. Fix belongs in
`symbol_research.py`.

### SHIPPED TO PROD — PR #203, image `20260803-thesiscoherence` (02:02Z)

Merged `90ae925`; prod swapped 02:02Z. Surgical: 2 files, no migration, no SPA.
Guard (`SOOPPIY_IMAGE=…authwave` + `app/…/symbol_research.py` sha
`8db3db56181c219f` + app mtime 1785717060) captured before build and re-checked
at the swap with a hard abort — held both times. Prod's file was byte-identical
to `origin/main` before upload, and to the merged commit after
(`b97d68b802082dfa`).

**Verified before the swap:** the built image was run directly and replayed the
four prod theses — all four rejected, both control cases passed.

**Verified after the swap, 3 passes:**
1. Both containers Up on `20260803-thesiscoherence`, **0 tracebacks** in each,
   `sooppiy.com` 200, `/docs/how-it-works` 200, `/api/health` 200.
2. Live code inside the **running worker**: `invalidation_is_coherent` present,
   `INVALIDATION_MAX_DIST` 0.5, `last` in the prompt rows, `last` in the
   `clamp_thesis` signature.
3. 38 worker tasks up, no new errors (market-news `errors=3` is the known
   pre-existing count).

Backups: `/tmp/thesiscoh-bak/` (both source files + `.env.bak`),
`.env.bak-20260803-thesiscoherence`. Rollback image: `20260803-authwave`.

**OPEN — next cycle must confirm end-to-end.** Batch `research:496033` landed
01:54Z, eight minutes *before* the swap, so it is still pre-fix. Batches run
roughly hourly (23:05 → 00:20 → 01:54), so **`research:496034` (~02:50-03:00Z)
is the first generated by the new code.** Check that its absolute levels sit on
the correct side of `last` — and that runs built from it actually enter.
Existing runs 937/938 carry their bad thesis baked into `config_snapshot_json`
and will not be repaired; they will hold until they retire, and the *refill* is
what should come back healthy.

### Fix — branch `fix/thesis-invalidation-coherence` (off `origin/main` ee21ada)

Three parts, `symbol_research.py` + its test only:

1. **Forward the price.** `"last": f.get("last")` joins the prompt rows, plus an
   explicit rule: a named absolute level must be ABOVE `last` for a short, BELOW
   for a long, within 50%, else describe the level relatively.
2. **Gate at clamp.** New `invalidation_is_coherent(text, direction, last)`;
   `clamp_thesis` gains `last=` and swaps an incoherent level for a deterministic
   relative one (never blanks it, never rejects the thesis — rejecting would
   starve the fleet into the `research_empty` loop).
3. **Close the reuse path.** Reuse keeps a stored thesis verbatim, so a
   pre-existing bad one would survive every quiet-tape refresh (a frozen weekend
   us-stock price holds `stage1_key` steady indefinitely). Incoherent stored
   theses are re-derived instead.

Number parsing skips percentages and durations — and prod emits **U+2011
non-breaking hyphens** (`5‑day`, `48‑hours`), not ASCII `-`, so the scrubber is
tested with the character the model actually writes.

**Verification:** replay of the real prod theses → **5/5 known-bad rejected**
(933 BTC, 934 ETH, 937 ZEC, 938 USDJPY, 3859 SOL), **4/4 known-good preserved**
(3857 ETH $1,950, 3876 GM 2%/48h, 3864 SPCX 20-day MA, 3861 ZC swing low).
**6/6 mutations killed** — `drop-long-side-check` initially SURVIVED (no test
covered a long with a wrong-side level; the ZEC case was caught by the distance
rule, not the side rule) and a test was added for it.

### Finding #2 — `historical_data` never maps Yahoo symbols, so forex research runs blind

Worker log, 01:03:25Z: `Quote not found for symbol: USDJPY` /
`['USDJPY']: possibly delisted; no timezone found` — the **yfinance** error
shape, not the chart endpoint's.

`historical_data._fetch_yfinance` (`historical_data.py:113`) passes the raw
symbol to `yf.download`. `price_fetcher._yahoo_symbol` knows forex needs `=X`
and futures `=F` (`price_fetcher.py:796-806`) — `historical_data` never calls it.
So every forex, futures and a-stock symbol 404s on this path.

Consumer is `market_intel.py:952`, "Research-L2 long-window features". It is
fail-soft, so nothing errors: the features simply come back empty and **forex
and futures theses are generated without their long-window factors**. Silent
degradation, and it compounds finding #1 — USDJPY was researched blind *and*
handed an impossible invalidation level.

Not fixed in this deploy — one change per swap, so the paralysis fix can be
verified in isolation. Next cycle's candidate.

### Other observations

- **939 TSLA / 940 NVDA** created by the owner 01:15/01:17Z (`created_via=user`),
  both immediately `gate_skip: market closed`. Correct behaviour — US market shut
  on a Sunday night — but the create flow gives no signal that a us-stock run
  will sit inert ~14h until Monday open. UX gap, not a bug.
- **Forex feed 404s**: Yahoo returns `Quote not found for symbol: USDJPY` and
  `USDKRW` ("possibly delisted") at 01:03:25Z, seconds before run 938 was built
  at 01:03:30Z. 938 still received `entry 156.220001`, so a fallback path served
  it — worth confirming which source, and whether forex prices are trustworthy.
- **Zombie position row**: `positions.id=80` BTCUSDT, `quantity=0.00000000`,
  `run_id=NULL`, opened 2026-07-31T03:24:14Z. Dead weight in the table.
- **932 SOL** cycle 7: disciplined `hold` (conf 0.55, "no clear 2:1 risk-reward,
  so we stay flat") — the horizon-discipline skill deployed 23:24Z is not being
  contradicted; there was simply no position to churn out of this hour.
- **934's retire payload** carries `confidence 0.0` and all four scores `0.0`
  with `conviction_missing: false` — same shape as 933's retire. Retire appears
  to bypass score population. Cosmetic, but it makes retires indistinguishable
  from parse failures in the event log.

### Health

Containers `sooppiy-worker` / `sooppiy-backend` Up 40m on image
`20260803-authwave` (deployed ~00:50Z by a parallel session). 402 worker log
lines / 2h, **0 tracebacks**; only the USDJPY+USDKRW Yahoo 404s above. Feeds
green (psych fng=28, factor snapshots 3, scanner 1 candidate, stock analysis 6).
`sooppiy.com` 200, `/docs/how-it-works` 200. Guide API `how-it-works-en` and
`liq-defense-en` return 401 — owner-gated, auth not a regression (an unauthed
probe cannot 200 by design).

Running: 932 SOL (−1.27 realized), 935 SPCX (weekend-gated), 937 ZEC, 938
USDJPY, 939 TSLA, 940 NVDA. Open positions: **0**. Trades this hour: **0**.
