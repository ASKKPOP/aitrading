# Plan 24 — Four Desk Fixes: Turning Observed Loss Classes into Profit

*2026-08-12. Evidence source: fleets 31/32 (agents 5/6) monitored live on prod all day —
run_events, fleet_events, positions, and worker logs. Every fix below maps to a loss
observed TODAY, not a hypothesis.*

**Owner frame (binding):** AI-FIRST. Each fix is trading logic the sooppiy AI runs —
a skill/prompt input plus, where needed, a deterministic backstop rail. The desk keeps
decision authority; the platform never silently overrides it (forced actions get a
close-reason taxonomy entry and a desk-visible rationale).

---

## The day's ledger that motivates this plan

Agent 5 (yoojinbe) net: **−$8.22** on $100k. Composition:

| Run | Symbol | Outcome | Class |
|---|---|---|---|
| 1086 | ZECUSDT short | **−$5.55**, adapt_retired | Wrong-way hold on a stale thesis (fix 1) |
| 1083 | ETHUSDT short | +$1.87 realized, then a **$4.45 dust remainder** | Fee-infeasible residue (fix 2) |
| 1085 | BTCUSDT | idle_retired **1 s before** its first actionable decision | Churned slot (fix 3) |
| 1088 | GC | +$2.40 banked, remainder lost, desk retired | AI-decided — working as designed |

Agent 6 additionally carries **orphan leveraged positions** (run_id NULL): a 3× CRM long
(−$2.2 unrealized, liq-health 0.75 and drifting) plus USDKRW fragments and a zero-qty
row — watched only by the liquidation daemon, closable by no desk (fix 4).

The ZEC class alone was ~67% of the day's gross loss. These are small absolute numbers
on a $100k simulated book, but they are *structural*: each class recurs every day the
cause stays unfixed.

---

## Fix 1 — Contradiction rule (모순 규칙): a held position may not ignore the desk's own reading

**Evidence.** Run 1086 shorted ZEC at conf 0.58. For the next three full-route cycles the
desk's own report read *“Technical signal is 'buy' (score 3); news sentiment 10 bullish
vs 1 bearish”* — a direct contradiction of the held short — and each cycle it emitted
`hold` with confidence 0.0 (`conviction_missing`). No reduce, no re-underwrite. The run
was adapt-retired at −$5.55.

**Precedent.** The flat-run case is already solved: thesis invalidation retires a run
whose desk keeps contradicting its own thesis while holding *nothing* (runs 116/117).
The held-position case — where the money actually bleeds — has no equivalent.

**Design.**
- *Signal (platform, zero-LLM):* at decision time the engine already computes the rule
  technical signal and the news sentiment tallies. Keep a `contradiction_streak` in
  `adapt_state_json`: +1 each cycle where both the technical direction and the news
  balance oppose the held side; reset on alignment or position close.
- *AI path (skill + prompt):* inject the streak into the decision context. New skill
  (all markets): *“You are holding against your own reading (streak N). At N≥2 you must
  either reduce or explicitly re-underwrite the thesis with fresh evidence — a silent
  hold is not an available action.”*
- *Backstop rail:* at streak ≥3 with the desk still holding silently, compile a forced
  `reduce 0.5` with close-reason `contradiction_reduce` (platform-forced taxonomy), and
  surface it in the run feed. The rail reduces — it never flattens; exits stay the
  desk's call.

**Profit mechanism.** Caps the depth of wrong-way holds. Applied to today: ZEC would
have cut at cycle 3–4 near breakeven instead of riding to −$5.55.

**Verify.** Replay test: a synthetic run with 3 contradicting cycles must (a) show the
streak in the prompt context, (b) force the rail reduce at streak 3 when the desk holds
silently. Fail-before/pass-after on both. Prod: watch `contradiction_reduce` events and
compare the class's realized loss per week before/after.

---

## Fix 2 — Dust-close rule (먼지 청산): never leave a position that cannot pay its own fees

**Evidence.** Run 1083 took profit by "cover half" four times in a row — correct each
time individually — and ended holding **0.00237 ETH ≈ $4.45 notional**. At the platform
fee floor, a position that small cannot clear a round trip on any plausible move
(the R1 fee-hurdle finding: ~2.4% favourable move needed at flat-fee minimums; on $4.45
that is $0.11 of gross edge against a larger fixed cost). The desk then spends 30-min
cycles and LLM ticks babysitting an unbankable remainder.

**Design (deterministic compiler rail, E1 philosophy — zero-LLM):**
- Define `DUST_FLOOR_USD` per market: the notional below which the frozen thesis's
  `expected_move_pct` cannot return ≥2× the round-trip fee. Same arithmetic family as
  `_thesis_fee_infeasible` — pure, no samples needed.
- In the order-intent compiler: a `reduce` whose remainder would fall below the floor
  compiles to `close` (note: `dust_close`). A cycle that starts with the position
  already below the floor and no add intent compiles `hold` → `close` likewise.
- *Prompt line:* tell the desk the floor so it proposes clean exits instead of halves.

**Profit mechanism.** Converts trapped residue into realized P&L, stops fee bleed and
wasted desk attention. Small per-instance, but it fires on essentially every scaled-out
winner — the platform's best trades are exactly the ones that produce dust.

**Verify.** Compiler unit tests (reduce-to-dust ⇒ close; sub-floor start ⇒ close; above
floor unchanged). Prod: zero positions below floor older than one cycle.

---

## Fix 3 — Idle-retire yields to an in-flight decision (유휴 은퇴 유예)

**Evidence.** Run 1085 (BTC): eleven hold cycles, then idle-retire fired at
**16:35:55** — and the desk's first actionable decision (`sell`, conf 0.55) landed at
**16:35:56**, dying on the "fence: run is stopped" gate. The slot paid twelve cycles of
research for an entry it was forbidden to take by a one-second race.

**Design.** Ordering, not policy: evaluate the idle-retire verdict *after* the cycle's
decision is known.
- If the current cycle produced an actionable decision (buy/sell with size), skip the
  retire this cycle — the run is no longer idle by definition.
- The existing counting fix (only open-market cycles count, `_closed_market_cycles`)
  stays; this adds the same-cycle race closure.

**Profit mechanism.** Two savings: the entry the desk actually wanted (BTC had moved
64,128 → 63,456 over the held window — the sell was live edge), and the churn cost of
retire → research → rebuild for a slot that was one second from working.

**Verify.** Unit test reproducing the race: cycle 12 emits `sell` while the idle limit
is reached ⇒ run stays running and the trade executes; a silent cycle 12 ⇒ retires as
today. Prod: count of runs whose retire timestamp is within one cycle of an actionable
decision must go to zero.

---

## Fix 4 — Orphan position recovery (고아 포지션 회수): every open risk gets a desk

**Correction (2026-08-12, implementation):** the original finding overstated the gap.
`orphan_reclaim` already exists and is LIVE on prod (`ORPHAN_RECLAIM_ENABLED=true`,
`ORPHAN_RECLAIM_EXIT=true`): every orphan carries a protective stop (CRM 189.99 —
the SL/TP watcher owns its exit, capping the tail at ~−3.4%), and the desk is
consulted for any orphan that blocks a fleet slot. The module's own design decision
— protect + desk-verdict-exit, never run-adoption ("runs never adopt a book they did
not open") — stands. What actually remained: zero-quantity ghost rows lived forever;
the sweep now deletes unowned zero rows each pass (owned zero rows stay the run
engine's).

**Original evidence (kept for the record).** Agent 6 book: CRM 3× long, `run_id
NULL`, −$2.2 and drifting (liq-health 0.751 when logged); two USDKRW fragments; one
zero-qty ghost row.

**Design (the owner's routing rule: forced situations get a path to the desk):**
- *Sweep (supervisor):* detect orphan rows — `run_id` NULL, or pointing at a stopped
  run outside the `positions_held` protocol. Zero-qty rows are deleted outright
  (hygiene; no decision content).
- *Adopt (AI path):* for each real orphan, create a **recovery run** on the owning
  agent (bound into the owning fleet's slot when one exists, standalone otherwise) with
  a manage-to-exit mandate: the desk reads the position, the thesis is "inherited
  exposure — decide close/reduce/hold each cycle", entries are disabled. Close-reason
  taxonomy: desk-decided. Liq defense keeps running in parallel throughout.
- *Guard:* the sweep is idempotent and never flattens by itself — it only ensures a
  desk exists.

**Profit mechanism.** Direct loss-cap: an unmanaged 3× position's terminal state is the
liquidation price; a desk's terminal state is a decision. Today's CRM alone risks ~$40
of the $122 at stake on a continued slide. Systemically: every past source of orphans
(deleted runs, migration edges, copy-trade leader removal) stops leaking.

**Verify.** Test: seed an orphan position ⇒ one sweep creates exactly one recovery run,
entries blocked, desk cycle can close it; zero-qty row deleted; re-sweep creates
nothing. Prod: `SELECT COUNT(*) FROM positions WHERE run_id IS NULL AND ABS(quantity) > 0`
converges to 0 and stays there.

---

## Order of execution and expected value

| Priority | Fix | Class size (today) | Effort | Notes |
|---|---|---|---|---|
| 1 | Contradiction rule | −$5.55 (67% of gross loss) | M | skill + streak counter + rail |
| 2 | Orphan recovery | −$2.2 open, tail risk ~$40 | M | supervisor sweep + recovery runs |
| 3 | Idle-retire yield | 1 lost entry + churn | S | ordering change in run_cycle |
| 4 | Dust-close | fee bleed on every scaled winner | S | compiler rail + prompt line |

Ship order 3 → 4 → 1 → 2 (smallest-risk first, both S fixes are pure ordering/compiler
changes; the M fixes carry the new surfaces). Each lands with fail-before/pass-after
tests, full local suite + CI, prod deploy, and a one-week before/after read of its
class metric in the monitoring notes.

---

## Fix 5 — US-stock target selection: rank fresh 2-day movers, not slow trends (owner algorithm)

**Owner directive (2026-08-12):** *"AI choose target USA stock — main algorithm is high
price changed for 2 days."*

**What the picker actually does today** (`symbol_research.screen_universe` →
`technical_subscore`): an equal-weight blend of `mom_5d` (tanh/8), `mom_20d` (tanh/20),
`sma20_dist` (/10) and `vol_ratio` (/3), multiplied by a vol-band fit that *penalizes*
high-volatility names, ranked by |composite|. **There is no 2-day factor at all.** The
shortest lookback is 5 days, diluted 1:3 by slower factors.

**Evidence that the current picker costs money:**
- Today's us-stock picks were the blend's natural output — SLV, T, GLD, XOM, TMO, UBER:
  slow, low-range names. Three runs idle-retired after 12 cycles of holds; the desk had
  nothing to trade on a 30-min cadence.
- GLD has been picked repeatedly and holds **−$300.66/trade expectancy over 7 closed
  trades** — the backtest gate now blocks it every pass. A picker that keeps nominating
  a proven loser is mis-ranked for this cadence.
- The fee-hurdle finding (R1, ~2.4% favourable move to break even) demands symbols with
  real short-term range; a 20-day trend factor is structurally mismatched to a 30-minute
  buy/sell desk.
- The 2-day mover criterion is also the **big-trader footprint**: a large 2-day move on
  elevated volume is what institutional accumulation/distribution looks like in daily
  candles — this fix and the Follow-the-Big-Trader skill are two halves of one thesis.

**Design (archetype-aware, minimal surface):**
- `candle_factors`: add `mom_2d` (`_ret(2)`) — one line beside `mom_5d`/`mom_20d`.
- For us-stock candidates feeding **day-trade (short-archetype) fleets**, rank by
  `|mom_2d| × volume confirmation (vol_ratio)` with `mom_5d` as tiebreaker; swing
  fleets keep the trend blend (their holding period matches it).
- Widen (or bypass) the vol-band cap for the day-trade ranking — the band currently
  taxes exactly the movers the owner wants; the fee hurdle already floors the useless
  low-vol end.
- Stamp `mov_2d_pct` on the thesis so the desk sees *why* the symbol was chosen.
- **Guardrails (the AI decides, but informed):** liquidity floor stays; earnings-gap
  awareness via the existing PEAD skill; a new skill line for mover handling — *"trade
  WITH a 2-day mover only on volume confirmation; after a parabolic >3σ day the desk
  prefers the first pullback, never a day-3 chase."* Chasing exhausted spikes is the
  one way this criterion loses money reliably; the skill puts that judgment where it
  belongs, on the desk.

**Verify.** Unit: ranking test — a +6%/2d mover with 2× volume must outrank a +8%/20d
trend name for a short-archetype us-stock request; swing request unchanged. Prod: next
session's picks should show 2-day range (watch idle-retire rate fall and per-run trade
count rise); one-week expectancy read per pick class.

---

Not in this plan (tracked separately): the **Follow-the-Big-Trader us-stock skill +
volume-flow detector** — fix 5's ranking change is its screening half; the intraday
flow detector completes it — and the swing-gate crypto daily-candle symbol mapping.
