# Automation monitoring — 2026-11-21 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-21T19:45:55Z (KST day 2026-11-21 = 11-20T15:00Z → 11-21T15:00Z, closed)

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-21 19:45:55. **This sweep ran 4 h 39 m late** (it is scheduled for 15:07Z). The first scratch
clone from GitHub failed with "curl 56 connection reset", so the clone was made from the local checkout's `origin/main` ref instead.
Image: `.env` = worker = backend = `sooppiy-backend:20261121-long-exit-policy` = 5d48cf3 = origin/main HEAD, so there is **no drift**. A
leftover `/tmp/sooppiy-sweep.*` existed only from this run's own failed clone.

**Trading set re-derived = {6} only, not {6, 60}.** Agent 60's fleet 43 was `fleet_stop_all` at 11-20T02:54Z. It has had no run since
11-14 and no fleet now, although `ai_automation_state` is still `active`. Agent 63 (`trend-module`, `user_id NULL`) holds 3 crypto shorts
opened before the block (SOL / ETH / BNB, 11-09…11-12). It is outside the two-user scope and is listed only for completeness.

**Ground state:** the shorts block was lifted at about 11-20T19:00Z (bd41889). Fleet 54 (agent 6, horizon archetype `short`, 6 slots)
started at 20:41Z and traded crypto shorts until the owner's **long-only + long-exit-policy** deploy at **11-21T03:03:52Z**. That deploy
retired every flat run. **`MAX(run_events.ts)` = 04:06:37Z, so nothing has traded for 15 h 39 m.** Fleet 54 shows `replenishing:0/6`.

**Deploy record:** `scripts/deploy.sh sweep-20261121` from 2bb2992 at about 20:10Z (a notes-only image, deployed because R44's falsifier verdict moved and a new trap was found). Verified twice, 60 s apart. `.env` and both containers are on `20261121-sweep-20261121`, and `/app/docs/reports/` lists this file. `futures_blocked()` and `shorts_blocked()` are True. 0 tracebacks, and `/api/subscriptions/plans` returns 200. Rollback tag: `20261121-long-exit-policy`.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 | combined | n trips | fees |
|---|---|---|---|---|---|
| **KST 11-21** (11-20T15Z→11-21T15Z) | **−1.23** | 0.00 (no fleet) | **−1.23** | 16 (16 shorts, 0 longs) | 0.62 |
| **24 h** (11-20T19:45Z→11-21T19:45Z) | −1.23 (same fills, 20:50Z–04:04Z) | 0.00 | −1.23 | 16 | 0.62 |
| without the largest winner (LTC 231128 +1.84) | **−3.07** | | | 15 | |
| without the largest loser (STRK 231106a −1.62) | +0.39 | | | 15 | |
| `pnl_audit` UTC 11-20 / 11-21 (day-attributed) | −2.61 / +2.68 | | | | |
| open uPNL now | 0 (flat) | 0 | 0 | | |

- **Routes (three, independent):** (1) Agent A's trip pairing gives −1.23. (2) My own `run_events` `trade` replay over the window gives
  **−1.2319**, with every position closed. (3) Cash: agent 6 has 9,998.768 against the 10,000.00 reset, a delta of **−1.2317**. Agent B's Σ
  `realized_pnl_usd` gives −1.23, which is a fourth route. `pnl_audit` exits 0 and reports "ok". Its UTC-day lines mix the pre-reset 11-20
  00–02:55Z trades with cross-midnight trips, so they are not window figures. This is not drift.
- **Verdict: a −$1.23 day. The sign flips when either extreme trade is removed, so with n = 16 the result is inconclusive as an edge
  reading.** As a dollar result it is a loss. Since 03:03Z the result is **$0, by construction** (§3).

### 2. Per-trade reasons (A = AI-authored, B = algorithm-authored; cross-checked)

| run | sym | net $ | entry (conf/sf/stop%) | exit author | reason |
|---|---|---|---|---|---|
| 231106a | STRK | **−1.62** | AI .58/.10/2.5 | watcher SL | **rebuilt 46 s after its parent 231098 banked +0.12 on a trailing lock** and shorted into a rally (−3.7 % at 1 h). The 2.5 % stop sat inside the move |
| 231103 | AAVE | **−1.18** | AI .63/.10/2.5 | AI ½ reduce (−0.54) then SL (−0.64) | wrong at 1 h and 4 h. The half-cut saved about 0.11 against the full stop |
| 231104 | TRUMP | **−1.07** | AI .58/.10/2.5 | watcher SL | **rebuilt 19 s after 231100 banked +0.14**, re-shorted 0.8 % lower into the rally (−3.0 % at 1 h) |
| 231128 | LTC | **+1.84** | AI .58/.10/2.5 | AI armed ½ (+0.40), then TP (+1.44) | right late (+5.4 % move over 5.5 h). The armed half-exit gave up about 1.03 against holding to TP |
| 231133 | BTC | +0.80 | AI .57/.05/2.0, TP 3 % | watcher TP | right. No trail was set, so the trade reached its target |
| 11 others | TRUMP/FIL/STRK/WLD/SUI/BCH/ETH/BTC/HYPE/STRK/LINK | Σ ≈ −0.01 | AI | trailing lock 3–60 min | the lock arms at about one round trip of fees. Peaks were 0.04–0.35, so fees (0.42) ate the gross (0.41). 4 of 11 fired at a gross loss (price stepped through the floor). HYPE / STRK 231106b / LINK were right by +5–6 % at 4 h and **captured nothing** |

| exit mechanism (B) | n | gross | fees | net |
|---|---|---|---|---|
| trailing lock | 11 | +0.413 | 0.420 | **−0.008** |
| watcher stop-loss | 3 | −3.216 | 0.111 | **−3.326** |
| watcher take-profit | 2 | +2.282 | 0.046 | **+2.236** |
| AI closes (AAVE ½, LTC armed ½) | 2 | | | −0.134 |
| **all** | 18 closes / 16 trips | | 0.62 | **−1.232** |

- **Direction (A):** 10 of 10 entries from 20:50 to 21:57Z were wrong at 1 h on a squeeze. All 6 entries from 22:31Z were right at 4 h.
  Combined: 7/16 right at 1 h. This is the **6th replication of "no entry timing edge"**, and the profit side came from the tape.
- **Two-axis attribution of the losers:** the algorithm (the watcher) executed all three stops, but the **stop level was AI-authored**
  (2–2.5 %, R:R 2:1). On alts with 1 h adverse ranges of 1.2–3.7 %, those stops were inside noise. The shape cannot recur now: shorts
  are refused, and a long's stop is the owner's −15 %.
- **Confidence (A):** range 0.55–0.68. The 0.68 ETH lost, and the three big losers were at 0.58–0.63. Sizes were $25–60. No sizing error.
- **Reviewer flips (A):** 3 of 16 entries were proposed buy by the trader and finalised sell (net +0.15). Every decision carries
  `reviewed_by='local-fallback'` / `llm.source='rule'`. That stamp is known to be unreliable (memory `decision-llm-stamp-always-local`),
  so provider attribution needs `llm_usage`. **Not verified this run.**
- **A vs B:** no disagreement on numbers. Both reconcile to −1.232. A blames the stop width (the AI's authorship). B blames
  same-symbol rebuilds (selection). Both are true of the same two trades. The disagreement is about which lever to pull, and it was
  chased in E2.

### 3. Experiments (hypothesis → falsifier → result)

**E1. R44 measurement (owed since 11-20).** H: under long-only, research yields a buildable long. Falsifier: zero long theses, or every
long fails `backtest_gate`.
- DATA (my `research_theses` query): every hourly batch since 03:00Z (16 batches) holds **exactly 1 long, GLD (us-stock)**, against 17–27
  shorts. 24 h total: 547 short / 23 long. All 23 longs are us-stock (XOM ×2, LLY ×1, GLD ×20). There are 0 crypto longs, and the
  last one was 11-19T23Z.
- B, read-only `select_targets` with rollback at 19:50Z: the fleet's open-markets scope (Saturday: crypto + polymarket) returns `[]`.
  With no scope it returns GLD, which `backtest_gate` then drops: **−727.53 USD/trade over 6 trades**.
- **Falsifier MET today: the only long fails the gate.** The R44 ship form (rank only longs when blocked) would build nothing today.
  It saves only thesis compute. R44 stays STAGED, and today counts as reading 2 *against* its P&L value.
- **Killed by B:** "archetype `short` blocks longs". `short` is the short-HORIZON archetype (`fleet_planner.py:722-725`). This is the
  second kill; 11-20 killed it too. "The planner tick counters prove a stall" was also killed: `researched` / `built` count only fleets in
  `researching` / `building` (`fleet_planner.py:2082-2087`), and fleet 54 is `active` and replenishes via `select_targets`
  (`fleet_supervisor.py:1157`).

**E2. NEW — "an immediate same-symbol rebuild after a PROFITABLE stop is a loss path" (from B's n = 2 today).**
- CODE (origin/main `fleet_supervisor.py:833-845`, verified by me): `vary-on-loss` cools a symbol down only when a `stop_event:` close had
  `realized < 0`. A profitable trailing lock sends the symbol straight back into selection. This is by design (2026-08-07).
- DATA, a second reading by my own replay: agents 6 and 60, fleet runs from 10-20 on, net per run from `trade` fills. A rebuild = the
  same fleet and symbol started ≤ 300 s after a profitable `stop_event:` stop.
  - Rebuilds: **n = 205, Σ −10.84, mean −0.053**, win 137/205. Without the largest loser: −7.70.
  - Control: **n = 319, Σ −2.82, mean −0.009**, win 214/319.
  - **Permutation test, one-sided: p = 0.145.** Medians: +6.1 bp rebuild vs +5.0 bp control. The three worst rebuilds alone = −8.5.
  - Per day: 10 days positive and 8 negative.
- **Result: INCONCLUSIVE.** The gap is tail-driven and not significant. It is also all-short-era data, and the book is now long-only,
  where a "profitable stop" would be the +5 % target. Under the 11-20 rule (R32), short-book tallies do not transfer. **Nothing ships.**
  Staged as **R45 (SOFT)**.

**E3. Long-exit policy (owner, 5d48cf3) — day-1 reading of its pre-registered falsifier.**
- Automation longs opened since the deploy: **0**. Emergency fires 0, target fires 0, refused AI sells 0, underwater longs 0.
- (a) realized + unrealized = $0. (b) 0 of 0 longs are underwater.
- **NOT YET MEASURABLE, and structurally it may stay that way:** with crypto research 100 % short and the only us-stock long failing the
  gate, the rule cannot fire. **The day-7 checkpoint (11-27) will judge a rule that has never run unless a long builds.** That is a fact
  the owner needs before 11-27, not a reason to loosen a gate.

### 4. Three-axis verification

- **DATA:** −1.23 by four routes (A pairing, my fill replay −1.2319, cash −1.2317, B's Σ realized). The window boundaries were checked: the
  15:00Z and 19:45Z windows return identical fill sets (34 fills, 18 with pnl). I re-queried the research direction counts myself. E2 is my
  own replay, independent of B's two-run observation.
- **CODE:** I read `fleet_supervisor.py:833-845` on origin/main. In the running worker: `futures_blocked()` True, `shorts_blocked()` True,
  `LONG_EXIT_POLICY` env unset (so the default is on). B read the archetype and tick-counter lines. I did not re-read them.
- **ADVERSARY:**
  - "The loss is the trailing lock's fault": rejected. The lock netted −0.008. The three stops (−3.33) are the loss.
  - "Bench the symbol after any stop": not supported, p = 0.145 (E2).
  - "Fleet 54 is broken": rejected. It is the owner's rule working as written in a down-tape, plus Saturday hours for us-stock.
  - "−1.23 shows the desk got worse than 11-20's +2.44": rejected. Both days are tape-driven, and both are inconclusive ex-largest.

### 5. Re-verification ledger (items shipped or raised since the 11-20 sweep)

| item | evidence on prod | verdict |
|---|---|---|
| 11-20 sweep deploy (sweep-20261120) | superseded by 6 owner-session deploys. Prod = 5d48cf3 = origin/main | HELD (no drift) |
| shorts two-way again (bd41889 … 96f0c87, ~19Z) | fleet 54 traded 16 crypto shorts 20:50Z–04:04Z | HELD while live. Then superseded by long-only |
| long-only + long-exit policy (5d48cf3, 03:03Z) | `shorts_blocked()` True live. 0 short entries after 03:03Z. 0 longs either | **HELD in code; never exercised by an order** (E3) |
| deploy retire mislabel | at the deploy, 6 flat runs were retired under `no_prospect_switched` (`run_engine.py:1662-1672`, B): 4 at 03:04:07 (FIL 231138 aged 40 s), BTC 03:33, LTC 04:06 | **NEW TRAP** (handoff §10). `no_prospect_switched` counts on deploy days overstate desk switching |
| R44 long-only research | E1: falsifier met today (the only long fails the gate) | STAGED; reading 2 against its P&L value |
| R37b ratchet single-sample spike | 4/11 locks fired at a gross loss today (step-through). Not re-replayed | SOFT, not measured |
| R32 ratchet arm | frozen (premise was the short book). Long-only has 0 trips | FROZEN |
| R43 / R42 / R40 / R34 | short-book items. Only R42 had a reading: the AAVE half-cut saved 0.11 (n = 1, against H-CUT); the LTC armed half cost 1.03 (n = 1, for H-CUT) | OPEN, moot until a book exists |
| 12 h min-hold (feat/fleet-ai-12h-horizon) | owner withdrew it on evidence. Not on main | CLOSED (not shipped) |
| agent 60 | no fleet since 11-20T02:54Z (owner stop_all) | OPEN (owner) |

### 6. Health

| check | value |
|---|---|
| containers | worker and backend on `20261121-long-exit-policy`, restarted 03:03:52Z (logs cover 16.7 h, not 24 h). admin up. mysql healthy |
| `MAX(run_events.ts)` | 04:06:37Z at 19:45:55Z. Correct for 0 running runs. Research batches are still hourly (latest 19:27Z). Not a dead worker |
| Traceback / ERROR (24 h) | worker **0** (10,388 lines), backend **0** |
| fleet 54 | `active`, `replenishing:0/6`, last_supervise 19:46:57Z. A single `slot_waiting` event at 03:05:04Z, then suppressed by the regate memo |
| llm no-verdict | 1 panel "no llm response / json unparseable" at 03:59Z out of 3 decisions after 03:00Z. Not measurable at this n |

### 7. Today's solution (for today's −1.23)

- **The losing shape** was three AI-authored 2–2.5 % stops on alt shorts during a squeeze (−3.33), two of them on same-symbol rebuilds.
  Under long-only **that shape is unreachable**. Shorts are refused, and automation longs stop only at the owner's −15 %. An AI-first
  lesson on short-stop width would teach the desk about a trade it can no longer make. **No change ships.** Shipping one would break this
  sweep's own rule that short-era evidence does not transfer.
- **The live problem is $0 throughput, and it is by design:** no long has passed the gate in a down-tape. Loosening `backtest_gate` or
  the research direction rule "to get trading" is ruled out. 11-19 buy-low research: dip longs worse than random. Six replications: no
  entry edge.
- **Watch, with a trigger:** if by **2026-11-24T15:00Z** (after one full us-stock session, Mon 11-23) fleet 54 has still built 0 runs,
  the owner should be told before the 11-27 day-7 checkpoint that the long-exit-policy experiment has **n = 0**. A rule that never fires
  cannot be judged PASS. The day-7 verdict must then read NOT MEASURABLE, never "not refuted".
- **R45 (SOFT):** a cooldown after a profitable stop. Promote only if a long-only reading shows rebuilds below control with
  permutation p < 0.05 **and** the sign holds ex-largest.

### 8. Not verified

- Provider attribution of the 16 entries (the `local-fallback` stamp is unreliable; `llm_usage` not queried).
- B's code citations `fleet_planner.py:722-725`, `:2082-2087`, `run_engine.py:1662-1672`, `fleet_supervisor.py:1157` (I verified only
  `fleet_supervisor.py:833-845`).
- Agent 63's open short uPNL. The stored `current_price` may be stale. Out of scope.
- The R37b counterfactual for today's 4 gross-loss locks (no 1 m replay run).
- Why agent 60 still shows `ai_automation_state='active'` with no fleet.
