# 2026-08-07 — automation monitoring (newest first)

Ground state: owner reset the balance to **1000** and cleared all history at
2026-08-06 ~22:56Z. Fleet 28 rebuilt from scratch. This is day 1 of the new book.

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
