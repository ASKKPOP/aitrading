# Plan 23 — The Swing Block (v2): PEAD first, the crowd-fade second, everything gated

*v2, 2026-08-11 — replanned after a 5-planner + 5-adversarial-QA agent panel
(10 agents, ~196 tool calls against the repo; every codebase claim below was
either cited-and-verified `file:line` by a planner or adversarially checked by
its paired QA). v1's structure survives; its sequencing contained a genuine
blocker, its build list was mis-scoped in both directions, and its gate was
statistically meaningless. All corrected below. No trading code is changed by
this document.*

---

## 0. The one question (unchanged)

> **Can our read tell a *real signal* from the *crowd's overshoot* — better
> than the crowd, after fees?**

One honest way to answer: build the reader and **measure** it. Everything else
is machinery.

---

## 1. The blocker the panel caught: v1 conflated two OPPOSITE edges

Plan v1 defined the strategy as *fading the crowd's news overshoot* (§3) and
then sequenced first proof on *post-earnings drift* (§8). Those are opposite
trades:

- **PEAD is a continuation / underreaction edge** — you *join* the post-gap
  drift. The platform's own `pead-drift` skill (trading_skills.py:1254-1305,
  us-stock only) says so explicitly: "fading it by reflex is trading against
  that tendency."
- **The fade is an overreaction edge** — you take the other side of an
  exhausted crowd. The `contrarian-crowding-gate` sequence
  (trading_skills.py:946) would fail-close on exactly the setups PEAD wants.

Passing a PEAD trial validates **nothing** about the fade reader — and putting
the contrarian gate in the PEAD prompt would veto every drift entry. So block 2
splits honestly into two sub-strategies, each with its own gate:

| | edge type | direction vs crowd | data it needs | testable how |
|---|---|---|---|---|
| **v1 · PEAD** | underreaction (continuation) | JOIN the drift | earnings dates + surprise + daily OHLCV — **all free, mostly wired today** | **historically backtestable NOW** (daily bars exist) |
| **v2 · fade** | overreaction | OPPOSE the exhausted crowd | positioning (put/call, short-sale volume, sentiment) — **no vendor history exists** | **live-forward only** — history must be self-accrued first |

`contrarian-crowding-gate` governs v2 prompts only. v1 runs on `pead-drift`'s
own rules. **v1 is long-only** — a us-stock short path does not exist on this
platform today (spot long-only, run_engine.py:3810-3813); the short leg of the
fade is a separate, gated project with its own rails (borrow checks, fatter
gap tails).

---

## 2. Architecture (locked, unchanged) + where the archetype lives

| slot type | horizon | market | status |
|---|---|---|---|
| **1 · short** | intraday | crypto only | live, untouched |
| **2 · swing** | ≥1–2 days, holds overnight | US equities, **swing only — never intraday** | this plan |

The archetype homes on the **fleet**: `fleets.archetype ∈ {short, swing}`
(migration), `market_scope` pinned `["us-stock"]` (honored verbatim,
fleet_planner.py:1181), threaded through `compose_run_settings`
(fleet_planner.py:908) and stamped into each run's config snapshot so
run_engine can condition cadence, briefs, and rails per-run without new
columns on `trading_runs`.

**Fee framing corrected:** v1 called the fee "flat." The QA panel refuted the
resulting arithmetic — the active regime matters and ships dark
(`FEE_PER_MARKET` defaults false off-prod). The plan therefore requires a
**published feasibility appendix** before build: the actual per-market fee
under the prod regime, the minimum notional where round-trip cost ≤ 0.5%, and
the gap-safe notional from §4 — three numbers, so feasibility is arithmetic,
not judgment. The horizon logic is unchanged either way: multi-day catalyst
moves (3–8%) dwarf round-trip costs that make sub-hour trading
negative-expectancy.

---

## 3. v1 · PEAD — executable rules (was: philosophy with no numbers)

**Universe (coded in fleet_planner at build time, not prose):** 20-day average
dollar volume ≥ $50M · price ≥ $10 · listed ≥ 12 months · optionable (a Yahoo
chain must exist) · ≥180 daily bars available · earnings date resolvable
(fmp_feed days_to_earnings) · StockTwits coverage above a floor · no
dilution/offering/investigation headline in the window. Ineligible names are
rejected **at build**, fail-closed — the SPCX trap becomes a mechanical
filter. (Platform rule: impossible configs are gated at build, or they churn
forever.)

**Event qualification (pead-drift's own rules):** real surprise
(actual vs estimate — the one missing free feed, see §6) + decisive gap +
volume shock; disqualifiers per the skill.

**Entry:** only at/after the first post-print session open — never into the
print. Enter the first orderly pullback that HOLDS the gap area, on resumption
through the pullback high.

**Exits (was entirely missing):**
- Stop below the pullback low. **Overnight stops are decision levels, not
  fills**: a gap through the stop exits at the open price, slippage recorded
  separately.
- Time-box: exit by day 15 if the drift stalls; hard exit day 25 (the skill:
  edge "spent by week five or six" — we take the front of it).
- Profit: scale ½ at +2R; trail the rest under each higher pullback low.
- Every new stop_conditions key is whitelisted + wire-tested through the API
  (the validator silently strips unknown keys).

---

## 4. Risk rails (now with formulas)

**Gap-sizing — derive the bet from the loss budget, not the loss from the
bet.** Per-slot overnight risk budget **R = 1.0%** of fleet marked equity.
Expected worst gap **G = max(** P99 |close→open| over 250 sessions **,**
2×ATR20/price **,** 1.25×options-implied event move *iff a scheduled print
falls inside the hold* **)**, floored at 3% so thin history can't inflate
size; ×1.25 into Friday or pre-holiday closes. Then **notional_max = R / G**,
leverage pinned 1.0. Fail-closed: no gap history → the slot does not build.

**Book-level overnight caps (checked at the 15:45 ET pass):**
Σ(notionalᵢ×Gᵢ) ≤ **2.5%** of fleet equity (the modeled P99 one-night book
loss); weekend/holiday entry tightens that to 60%; excess is `reduce`d before
the close, never dumped. Direction skew capped |long−short| ≤ ⌈n/2⌉ (the #359
brake pattern — trivially satisfied while v1 is long-only).

**Earnings rule:** any swing slot with a print inside the next session is
flat by 15:45 ET the day before, **unconditionally** — unless the thesis
names that print AND passes the gap formula at G = 1.25×implied move AND at
half risk budget. Enforced in code via the existing earnings feed
(run_engine.py:2866 pattern), not in the prompt.

**A swing stop-geometry tier** (the panel confirmed the intraday tier makes a
1–2 day hold *mechanically impossible*): stop authored at
max(2×ATR20, 1.5×G); `max_loss_usd = notional × stop%` so **the USD rail and
the price stop are the same number** — closing the desk-vs-rail gap
(run_engine.py:3131-3186) by construction. Retire-drawdown for swing evaluates
on **daily-close equity**, not the intra-cycle high-water mark; intraday
brake/tighten fractions disabled for swing, keeping a catastrophe rail at 3×
the stop. Wiring test: a +3% day-1 peak then −1.8% day-2 retrace must NOT
retire the run.

**Session-aware terminal actions:** every flatten path (fleet stop-all,
profit-goal, at_time expiry, drawdown retire — fleet_supervisor.py:205/220/288)
checks `markets.is_market_open('us-stock')`; when closed it queues a
`pending_flatten` executed at next open — **never a sim-fill at a stale
price**. Overnight stop evaluation goes dormant while closed (no
mark-staleness raise) and fires on the first fresh mark after open. Halt
detector: unchanged price + zero volume across 2 in-session cycles → freeze
adds and stop evaluation.

---

## 5. v2 · fade — numeric definitions on latency-correct feeds

v1's "positioning data" hid a fatal latency fact: **exchange/FINRA short
interest is biweekly with ~9 days' settlement lag** — unusable as a trade
trigger. Corrected inputs:

**Crowded (need ≥2 of 3):**
1. Put/call open-interest ratio beyond its own 60-day 10th/90th percentile —
   computed from the Yahoo option chain fetch that **already exists**
   (price_fetcher.py:936), EOD.
2. FINRA **daily short-sale volume ratio** (free, T+1) — the honest "crowd
   just acted" read.
3. StockTwits tilt |t| ≥ 0.6 with n ≥ 30 (drop the crypto `.X` suffix —
   factor_snapshots.py:35 is crypto-configured today).
   Biweekly short interest (SI%float ≥ 15% / days-to-cover ≥ 5) is **context
   only**, never the sole trigger.

**Failing (the exhaustion tell):** within 2 sessions of a favorable catalyst,
the name closes below the catalyst-day open OR retraces >50% of the catalyst
move on ≥1.5× 20-day volume — computable from daily candles today. Silence is
not failure (matches `news-reaction-evidence`).

**v2 is live-forward only** — no vendor sells positioning history, so the
fade cannot be backtested until we accrue our own. Hence:

> **Factor recording starts at build step 1, not step 3.** A
> `us_stock_factor_snapshots` table (sibling of factor_snapshots, same
> no-vendor-history rationale its header states) records
> short_volume_ratio · putcall_oi_ratio · stocktwits_tilt daily for the fixed
> universe **from day one**, and every paper trade stores the positioning
> inputs it saw at decision time — so months of auditable history exist by the
> time v2's own gate needs them. Real-time options-flow feeds ($50–150+/mo)
> are excluded until a gate is cleared: the whole book's realized profit is
> ~$6.5 today, so any recurring feed fails the mandate's cost test.

---

## 6. Build list — corrected in both directions

The panel found v1's build list overstated one item and understated others.

**Smaller than v1 claimed — session timing is ~80% built.** `is_session_open`
/ `is_market_open` / `session_minutes_left` exist (markets.py:282/311/325) and
run_engine + fleet_planner already consume them (skip-when-closed
run_engine.py:3680, closing-soon 2780, no-build-into-close
fleet_planner.py:349-353). The genuinely missing 20%: a
`session_minutes_until_open` twin + pre-open deep-pass trigger, a near-close
hold/flatten decision, hold-across-close as the swing default, and **a NYSE
holiday + half-day calendar** (markets.py's clock is weekday+time only — a
static table + pinned-date tests, mandatory before any swing run ships).

**Larger than v1 admitted — the existing engine actively fights a swing
hold.** Confirmed by the platform + risk lenses, with citations:
- Fleet desk cadence is **hard-capped at 30 minutes** (INTERVAL_CAP_MIN,
  run_engine.py:2040, clamp 2087-2088) — "slow cadence exists" was false at
  the fleet tier. Fix: per-archetype cap (240 min for swing) read from the
  snapshot; the ~60s stop scan (run_engine.py:4153) is untouched, so slower
  *thinking* never delays an *exit*. ⚠️ **Owner decision required:** the
  30-minute cadence is a recorded owner rule; relaxing it for the swing
  archetype needs explicit sign-off.
- The live briefs command the opposite of swing ("closing soon", "banking is
  first-class" — run_engine.py:3682-3705): brief lines become
  archetype-conditioned, each change with a wiring test (the brief-wiring
  trap: unwired lines pass all tests).
- **The horizon gate already exists, dark** (run_engine.py:2286-2436):
  `horizon_until` is already whitelisted (trading_runs.py:178-186) and
  fleet compose already writes `at_time = now + horizon_h` — the swing build
  arms `_horizon_skip` for archetype=swing only and must reconcile the
  at_time/horizon_until collision. The swing paper trial doubles as the
  shadow-vs-outcome evidence the gate's own comment demands.
- Idle-retire counted closed-session cycles before (prod runs 127/128,
  run_engine.py:562-577) — swing runs are exempted from idle-retire while
  their market is closed.
- add_cooldown / max-position-age and other intraday lifecycle rails need
  archetype conditioning, or they strangle a 3–8% multi-day move.

**Phase-1 data is nearly free.** MVD for v1-PEAD, all $0 recurring:
earnings calendar (live), daily OHLCV (live, yfinance-primary), StockTwits
(live), per-symbol news (set the free FINNHUB key —
analysis_sources.fetch_finnhub_news exists), **earnings surprise
actual-vs-estimate (the ONE missing feed: AV EARNINGS / FMP
earnings-surprises, ~100 lines in the fmp_feed union pattern)**.
**Step 0 is a prod key audit**: confirm AV tier, set FINNHUB, decide FMP
(fmp_feed.py:15 shows it has never been keyed on prod) — recorded in the plan
so the trial's data provenance is known. Cross-provider price-adjustment
consistency (yfinance auto_adjust vs AV) is checked before the backtest.

---

## 7. Measurement — the gate that replaces "beat −$0.29"

The panel's harshest confirmed finding: v1's gate ("beat −$0.29 over 6 runs,
dozens of trades") had **no statistical power** — a negative-expectancy
strategy could pass it. Replaced wholesale:

**Gate 0 — historical PEAD event-study, BEFORE any build.** Neither existing
backtest engine can run catalyst trades; a small purpose-built harness
(`backtest_catalyst.py`: enter next open after signal, exit at open of day
H ∈ {1,2,3,5}, fees both legs, stops modeled gap-through, daily bars via
historical_data.get_bars) replays **≥300 earnings events across ≥100 names
over 3 years, walk-forward** (train 2y / test 1y, no tuning on the test
year). Pass = test-set expectancy after fees > 0 with bootstrap 90% lower
bound > 0 AND profit factor ≥ 1.2. **This can kill the whole plan for ~zero
spend** — the correct first move under the "spent nothing real learning it"
principle. Caveats engineered in: survivorship bias (today's-tickers universe
— use point-in-time listings where possible, report the bias), and
clustered/non-independent trades in earnings season (block-bootstrap by
week).

**Paper trial — pre-registered, no peeking.** Universe of 100+ liquid
large-caps (≥$100M ADV, optionable, ≥$10B cap) sustaining 10–30
setups/quarter. Minimum to a decision: **60 closed swing trades AND two full
earnings seasons (~6 months), whichever is later** — the trade-flow arithmetic
makes this quarters, not weeks, and the plan says so. Fill realism is a gate
precondition: paper fills only at settled daily-bar open/close (never the
6h-TTL cached quote), gap-through stops fill at the open, every fill
reconciled to the bar within 0.1%. Both brake regimes run in parallel — the
new daily-close brake live, the old intra-cycle brake in shadow, logging every
shadow fire — turning "the intraday geometry kills swings" into a number.

**Promotion (ALL required):** bootstrap 90% lower bound of per-trade net
expectancy > 0 · Wilson one-sided 90% lower bound of hit rate > 0.50 **or**
profit factor ≥ 1.3 with bootstrap 10th percentile ≥ 1.0 (the asymmetric-R:R
path) · paper max drawdown < 15% · worst single overnight-gap loss < 5%
(proves the gap-sizing works). At 60 trades promotion is to a **probation
tier** (1 live slot, minimum size); full scaling waits for 150+ combined
trades.

**Kill rules — fixed checkpoints (30/60/90 closed trades), no continuous
peeking:** kill if Wilson 90% *upper* bound of hit rate < 0.50, or cumulative
net expectancy is negative beyond fee noise with 90% confidence, or paper
drawdown > 20%. **Unconditional kill at 12 months** without promotion —
timeboxed hypotheses, per the garbage rule.

**Every checkpoint reports the full panel** (n, hit rate + CI, expectancy,
profit factor + bootstrap, avg win/loss, max DD, worst gap loss, and
setups-seen vs setups-taken — the last detects fail-closed gates silently
starving the trial). All computable from backtest_metrics.py primitives.

---

## 8. Build order (phases, with first proof off the critical path of nothing)

0. **Prod key audit** + feasibility appendix (fee regime numbers) + **Gate 0
   backtest** — can kill the plan before any platform work.
1. **Phase A (~2d):** `fleets.archetype` migration + swing FLEET_BOUNDS row +
   snapshot stamping + NYSE holiday calendar.
2. **Phase B (~3d):** per-archetype interval cap (⚠️ owner sign-off) ·
   archetype-conditioned briefs (wiring tests each) · arm `horizon_until` for
   swing (reconcile at_time collision) · overnight stop semantics
   (dormant-when-closed, gap-fires-at-open, tests for both) · idle-retire
   session exemption.
3. **Phase C (~3d):** gap-sized `max_bet` formula + earnings-window build
   guard + universe filter in fleet_planner + book-level overnight caps +
   session-aware queued flattens.
4. **Phase D (~1wk, parallel from day 1):** `us_stock_factor_snapshots`
   recording (short-sale volume ratio, put/call OI, bare-symbol StockTwits) +
   the earnings-surprise feed. v1 needs only the surprise feed; the rest
   accrues history for v2.
5. **Phase E:** simulator paper fleet per §7. → probation → scale.
6. **v2 · fade:** only after v1's gate AND ≥3 months of self-accrued
   positioning history; own paper gate (same statistics); short leg its own
   gated project.

---

## 9. The traps table (v1's, plus what the panel added)

| trap | discipline |
|---|---|
| Volatility ≠ edge | a fast move hits the stop as easily as the target |
| Hindsight ($113→$135) | every visible winner has an invisible loser beside it |
| Great tech ≠ great trade | priced-for-perfection: good news can still drop the stock |
| Trend ≠ catalyst | trade the dated event, not the diffuse trend |
| Verify the instrument | a 2-month IPO has no positioning history — now a **coded** universe filter, not prose |
| "We can tell" is a hypothesis | true only when measured after fees |
| **Two edges conflated** *(new)* | PEAD joins the crowd's underreaction; the fade opposes its overreaction — one trial cannot validate both |
| **Stale positioning data** *(new)* | biweekly short interest with 9-day lag is context, never a trigger |
| **A weak gate flatters** *(new)* | "beat −$0.29 on 6 runs" would pass noise; only CI-gated absolute thresholds count |
| **Peeking bias** *(new)* | evaluate at pre-registered checkpoints only; 12-month unconditional timebox |
| **Phantom paper edge** *(new)* | stale-quote fills fake profit; fills pin to settled bars, gaps fill at the open |

---

## 10. Decisions — RESOLVED (owner, 2026-08-11)

1. **Swing cadence: APPROVED, US-stock swing archetype only.** The 240-min
   desk interval applies solely to `archetype=swing` (which is pinned
   `market_scope=["us-stock"]`); crypto short slots keep the 30-minute rule
   unchanged, and the ~60s stop scan is untouched for both.
2. **Keys: platform-level, default free** (owner confirmed "default is open
   key use"). Step-0a audit on prod (2026-08-11): `ALPHA_VANTAGE_API_KEY`
   SET (tier unconfirmable; Yahoo-first routing already compensates);
   `FINNHUB_API_KEY` UNSET — obtaining the free key is an owner action
   (account signup); `FMP_API_KEY` SET **but legacy-403'd** on the earnings
   calendar (post-2025 keys are barred from the v3 endpoint) — FMP is
   effectively dead for v1's needs. Decision: **do not pay FMP**; earnings
   surprise comes from the free AV `EARNINGS` path (+yfinance for research).
3. **Paid positioning feeds: CONFIRMED excluded** until a gate is cleared —
   feeds at $50–150+/mo against a book whose lifetime realized profit is
   ~$6.5 fail the mandate's cost test by an order of magnitude.

### Appendix (step 0b) — fee feasibility, audited numbers

Prod runs `FEE_PER_MARKET=true`; per-market side rates (fees.py):
crypto 0.045% · futures 0.005% · forex 0.008% · **us-stock 0.005%** ·
(legacy flat `TRADE_FEE_RATE=0.1%` applies only with the flag off).

- **us-stock round trip = 0.01% of notional — proportional.** There is NO
  fee-driven minimum notional: round-trip cost ≤ 0.5% at every size, by ~50×.
  v1-plan's flat-fee feasibility worry is formally dead (as the QA panel
  refuted); the binding swing costs are **spread + gap slippage**, which the
  paper-trial fill rules (settled-bar fills, gap-through at the open) price in.
- Gap-sizing example at fleet equity $10,000: R = $100; G floored at 3% →
  notional_max ≈ $3,333; round-trip fee on that ≈ $0.33 — negligible against
  a 3–8% catalyst move. Feasible with wide margin.

---

## 11. What this plan is not (unchanged, plus one)

Not a promise US equities out-earn crypto. Not a fast-trading strategy. Not
"our AI is smarter." **And not one strategy:** v1-PEAD and v2-fade are two
edges with two gates — passing one says nothing about the other.

## 12. GATE 0 VERDICT (2026-08-11): **FAIL — the plan halts at step 0**

Run on real data the same day the plan was approved: 104 liquid large-caps,
1,539 earnings events (2023-01 → 2026-08), daily bars, walk-forward
(train → 2025-08-11, test = the last 12 months, parameters chosen on train
only). Fees at the audited prod rate. Full artifact:
`research/gate0_pead_backtest.result.json`; harness:
`service/server/backtest_catalyst.py` (18 unit tests).

| variant (test window, untouched) | n | hit% | expectancy/trade | PF | bootstrap LB90 |
|---|---|---|---|---|---|
| long next-open | 46 | 45.7 | −0.26% | 0.90 | −1.47 |
| long next-open + 5% stop | 51 | 41.2 | −0.70% | 0.74 | −1.60 |
| both directions (info; shorts inexpressible) | 85 | 52.9 | +0.51% | 1.29 | −0.08 ≈ 0 |
| **long pullback (the strategy as specified)** | **9** | **33.3** | **−1.93%** | **0.35** | **−3.89** |
| long pullback + 5% stop | 37 | 43.2 | −0.37% | 0.79 | −1.11 |
| both pullback | 78 | 46.2 | −0.27% | 0.84 | −0.96 |

Train windows looked healthy (up to +1.12%/trade, PF 1.84) and did **not**
survive out-of-sample — the signature of a decayed or regime-dependent edge.
Exactly one pre-registered refinement was run (the pullback entry `pead-drift`
actually specifies, replacing the naive spike-chase); it failed harder on a
smaller sample. No further variants were mined — iterating until something
passes is the peeking bias §9 forbids.

**Honest reading.** On deep liquid large-caps — the only universe our own
hygiene rules allow — mechanically-implementable PEAD shows no after-fee edge
in the last 12 months. This is consistent with the literature: PEAD
concentrates in small/mid-caps with thin coverage, which is precisely the
manipulable zone the universe filter (and the manipulation defense) exists to
keep the desk out of. The tension is real and is now measured, not assumed.

**Also honest:** this tested *price-reaction* PEAD (gap + volume shock). True
SUE-based PEAD (earnings-surprise magnitude) was not testable because the
surprise feed was never wired — that build was Phase D of the plan this gate
just killed.

**What was spent:** one reusable event-study harness + tests, one runner with
a cached dataset, ~zero platform work. **What was not spent:** phases A–E.
The gate did its job.

**Revival paths (each requires a new gate pass before any build):**
1. SUE-qualified PEAD — wire the free AV earnings-surprise feed *first*, then
   re-run gate 0 with surprise-magnitude qualification.
2. The v2 fade — needs self-accrued positioning history; the cheap
   `us_stock_factor_snapshots` recording could be built standalone so the
   option exists later (owner's call — the plan that justified it is halted).
3. Re-test after a regime change, unchanged criteria.

### §12.1 — SUE-qualified re-run (path 1, executed 2026-08-11): FAIL, but materially closer

yfinance's earnings dates already carry `Surprise(%)` — no new feed was
needed (1,537 of 1,539 events had it). Same walk-forward, same criteria,
judged on `sue_long`'s untouched test window:

| variant (test) | n | hit% | expectancy | PF | bootstrap LB90 |
|---|---|---|---|---|---|
| **sue_long** (≥10% surprise + gap-confirm + 5d hold, chosen on train) | 61 ✓ | 49.2 | **+0.18%** ✓ | 1.09 ✗ | **−0.67** ✗ |
| sue_long + 5% stop | 61 | 47.5 | +0.20% | 1.11 | −0.58 |
| sue_both (info) | 71 | 53.5 | +0.27% | 1.15 | −0.54 |

Surprise-conditioning was the right variable — expectancy flipped from
negative to slightly positive with exactly the combo the literature predicts —
but PF < 1.2 and the 90% band **spans zero**: an underpowered *maybe*, not a
proven edge. Third pre-registered fail (price-gap, pullback, SUE). No fourth
variant will be mined.

### §12.2 — OWNER DECISION (2026-08-11): paper-gated build, BOTH paper + live

Presented with (A) accept the verdict or (B) build paper-gated, the owner
chose **"both (paper + live)"**. Resolution that honors both the order and
the mandate: **phases A–E are built; the swing block ships with paper AND
live capability; live capital is entered ONLY through the §7 promotion
pipeline** — paper trial (≥60 closed trades, 2 earnings seasons, CI-cleared)
→ probation (1 live slot, minimum size) → scale at 150+ trades. A paper trial
trades no real money, and it is the one instrument that can resolve a +0.18%
whose confidence band spans zero. Real-broker execution additionally remains
behind the platform's per-user gateway + consent rails, unchanged.

**Build status:** Phase A (fleets.archetype migration 0049, swing bounds +
240-min compose cadence, snapshot stamping, NYSE holiday/half-day calendar)
— IN PROGRESS 2026-08-11. Phases B–E follow in sequence per §8.
