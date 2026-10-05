# One-month loss analysis — 2026-09-05 → 2026-10-05

Accounts: `info@askkpop.com` (user 5, agent 6, crypto fleet 44) and
`forevery1969@gmail.com` (user 25, agent 60, us-stock fleet 43). Both were reset
to $10,000 on 2026-08-31. Prod clock at start of analysis: 2026-10-05 15:49Z.

Scripts, pre-registration and data dumps: `research/loss_analysis_20261005/`.

## 1. Verdict, in profit-or-loss terms

| | amount | note |
|---|---|---|
| Claude API spend, agent 6, 09-05 → 09-10 | **−$743.39** real money | `llm_usage`, 9,772 Anthropic calls; stopped by the 09-10 switch to local AI |
| Agent 6 simulated trading | **−$81.08** | 633 round trips; gross −$28.27, fees $52.81 |
| Agent 60 simulated trading | **−$5.23** | 22 round trips + 1 open MSFT position |
| Trend module (agent 63) | −$11.7 | 1 closed loss −$15.02, 2 open longs +$3.6; n=1, says nothing yet |

Ledger check: the round-trip reconstruction sums to −$81.08 for agent 6 and
`agents.cash − starting_capital` is −$81.08 (two independent records, equal to the
cent). Agent 60: −$5.22 closed − $0.007 open entry fee = cash + MSFT mark.

The desk did not lose because the market fell. The 44 coins it traded rose
**+32% on average** over the window (41 of 44 up) and the desk was 78% long by
trade count. Average capital actually deployed was **$114 of $10,000** (agent 6)
and $204 (agent 60); median hold 20 minutes.

## 2. Why it lost

### 2.1 The entries carry no edge (third replication)

Pre-registered H1: side-signed forward return of desk entries beats a
same-symbol, same-side random entry time. Marks: Hyperliquid 15m candles (the
platform's own feed). n = 632 at 1h/4h, 631 / 627 / 623 at 12h / 24h / 48h.

| horizon | desk | random ±24h | desk − random | z |
|---|---|---|---|---|
| 1h | −1.3bp | +5.6bp | −6.8bp | −1.32 |
| 4h | +18.7bp | +21.9bp | −3.1bp | −0.31 |
| 12h | +52.5bp | +51.2bp | +1.3bp | +0.08 |
| 24h | +36.3bp | +60.8bp | −24.4bp | −1.21 |
| 48h | −45.6bp | −7.6bp | −38.0bp | −1.87 |

Same result with a second seed and with a whole-month null. **H1 FALSIFIED at
every horizon.** This repeats 2026-09-08 (n=306) and the 2026-08-30 pair replay.

Nothing the desk knows at entry sorts winners from losers: confidence vs net
Spearman −0.057 (n=633), conviction +0.052, every thesis-momentum bucket and
every confidence bucket nets ≤ ~$0.

Actual gross per trip: −5.2bp, symbol-clustered 95% CI [−12.0, +1.7] — not
distinguishable from zero. Fees are a certain 9.0bp per round trip (4.5bp/side,
verified on 1,359 fills). Net −13.8bp per trip.

With zero-edge entries, expected loss = number of trips × fee. 633 trips ×
$94 × 9bp = $53. That is the loss.

### 2.2 Every entry was taken over the system's own objection

Verified by joining `order_discussion` events to executed entries (and
independently by Agent A; 633/633 agree):

| how the entry was authored | trips | net | ex-worst |
|---|---|---|---|
| analysis panel said **hold**, `veto_overridden: true` | 529 | **−$62.17** | −$57.42 |
| trader LLM returned nothing; chair turned the rule engine's text into an order (97 buys −$16.44; 2 "sells" that opened shorts −$3.25) | 99 | **−$19.69** | −$16.17 |
| no objection recorded | 5 | +$0.78 | |

Agent 60: 19 of 22 trips over a panel hold, −$5.09 (sign flips without QCOM —
inconclusive as a book on its own).

Origin: commit `f528b69` (2026-09-04/05, owner directive "if continue hold then
we will be remove desk hold logic") made the panel's hold on an entry
non-binding. The panel then said hold on 590 of 590 proposed buys and was
overridden 590 times. The commit's premise — "the panel was wrong 434 times out
of 435 by the only test that matters, zero trades in 19 days" — is refuted by
the outcome data it was shipped to collect: the overridden entries lost money
and have no timing edge. (The commit message names a kill switch
`PANEL_ENTRY_VETO=1`; no such variable is read anywhere. The real flag is
`PANEL_ORDER_VETO`, and it also governs the routed stop-hit exemption — see §7.)

Within the overridden entries, 203 were cases where the trader itself did not
propose an entry and the chair flipped it on the Risk agent's challenge. The
Risk prompt sees no market data and must argue against the proposal, so against
"hold" it argues missed upside with unsourced catalysts ("imminent Binance
listing", "NEAR hard-fork next week", "upcoming earnings"). Those trips perform
the same as the trader's own (−13.0 vs −13.3bp net; diff CI [−17, +17]) — no
worse, no better, each paying the fee.

### 2.3 Since 2026-09-11 the AI is mostly not answering

After the 09-10 switch to all-local AI, the trader LLM returns
`no llm response` on 79% of agent 6's decisions (4,173 of 5,257); only 94 of
5,262 decisions are `decided_by: ai`. The worker logged **201
`LLM generation failed (provider=local): Request timed out` in the last 3 hours**
(~67/hour, the same rate as on 09-11). Tailscale shows the local AI host
`active; relay "lax"` (relayed, not direct). Small prompts get through (~50
decision-tier calls/day, ~800 prompt tokens); the ~5,000-token trader prompt
does not.

In that state `_hold_only` turns the rule fallback into a hold, and the chair —
seeing only the rule engine's summary — amends it to a buy (187 of 187
rule-buys carry `chair.amended: [action, …]`). This contradicts the owner
policy recorded in the code itself ("a rule-engine fallback is NOT the sooppiy
AI speaking"). Regime after 09-11: 117 trips, −$20.88, zero AI-authored exits
(106 ratchet +$8.47, 11 stop-outs −$29.35).

### 2.4 The exit geometry explains the shape, not the sign

- 82% of trips are banked by the breakeven ratchet at a median +13bp gross
  after ~15 minutes (arm = 16bp of notional).
- Stops sit at 2.5% (`stop_cap` cap_pct = 2.5 on 316/316 events since 09-04,
  not the 0.5% of Plan 31).
- 70 trips with net < −$1 total −$155.64; the other 563 total +$74.57.
- Break-even bank rate for that geometry is 91%; actual 82%.

This is why it feels like "always losing": many cent-sized wins, then one loss
that erases ten of them. But for a zero-drift entry no exit rule changes the
expected gross result. Agent A's unconditional tests agree: closing at the
first −50bp mark instead of where the desk actually closed is worth −3.6bp
(CI [−26.6, +20.0]); AI vetoes of proposed closes −3.7bp (sign flips
ex-worst); armed stops −1.9bp (CI [−22, +18]).

## 3. Cross-check of the two agents

- Agreement: regime split, 99 chair-authored entries (−$19.69), fee rate,
  no-edge reading of gross.
- **Disagreement, resolved against Agent B's ranking.** B ranked "rail
  geometry" as the #1 cause (−$58.7) and "ratchet 62s sampling" as #3
  (fills $46.89 below the rail's own floor). Both are descriptions of where
  losses land. Neither is shown to be recoverable money, B flagged the second
  as unverified, and A's unconditional tests put exit-timing effects at ≈ 0.
  Rejected as causes; kept as distribution facts.
- B's "gross is negative before fees" and A's "gross CI spans zero" are the
  same data; the defensible statement is the CI.
- Agent A could not verify that 09-05..09-10 was a Claude desk; `llm_usage`
  confirms it (609 `claude-opus-4-8` decision-tier calls for agent 6 on 09-09).

## 4. Hypotheses refuted or inconclusive (do not re-run)

| hypothesis | result |
|---|---|
| H1 entries beat random timing | REFUTED, 1h–48h |
| H2 "hold longer" is an edge | **INCONCLUSIVE as edge.** Fixed 12h/24h/48h holds on the same entries: +$35 / +$56 / +$115 vs −$35 / −$9 / −$12 actual, sign survives ex-best trip and symbol — but random-time entries in the same coins do as well or better (p 0.57–0.70). It is market beta in a +32% month, not desk skill. In 09-11..10-05 the desk's own entries held 12h/24h were at the 5th–8th percentile of random. |
| Confidence / conviction / scores predict outcome | REFUTED (|ρ| ≤ 0.066) |
| Thesis 2-day momentum bucket predicts outcome | REFUTED (no monotone relation; every bucket ≤ ~0) |
| Risk-flipped entries are worse than the trader's own | REFUTED (same) |
| Closing losers earlier / AI close vetoes / armed stops cost money | not demonstrated (CIs span 0) |
| Re-entry after a loss on the same symbol | REFUTED (n=38, CI [−31, +21]) |
| Long vs short | no difference (−0.127 vs −0.134/trip) |
| Claude desk vs local desk changed the outcome shape | INCONCLUSIVE (diff −5.5bp, CI [−24.1, +11.7]); it changed the trade count 12× |
| Rotation (idle_retired / no_prospect) costs money | REFUTED ($0; fires flat-only) |
| Size quartering (`null_size_cap`) is a parse defect | REFUTED (intended, R17); full size would have ~4×'d the loss |
| The 0.5% stop cap is being overridden | REFUTED (it was raised to 2.5% on 09-04) |
| The 09-04 tier falsifier ("expectancy < 0 at n ≥ 50 = FAIL") | **FAILED as registered**: n=633, −$0.128/trip |

## 5. Solutions

Ordered by evidence. None of these makes the desk profitable; 1–3 stop a
measured loss, 4 is the only route to profit that has any test behind it.

1. **Make the panel's hold binding on entries again.** Counterfactual on this
   tape is exact, not modelled: 548 trips not taken, −$67.26 avoided.
   Consequence: the desk goes back to almost never trading. For a desk with no
   entry edge that is the correct output; each trade it takes costs 9bp in
   expectation. (Shipped as a code change, not the env switch — §7.)
2. **Fail closed when the trader LLM does not answer** — the chair must not
   turn a rule fallback into an entry (101 trips, −$19.85). Code fix with a
   fail-before/pass-after test; restores the owner's own rule-is-not-the-AI
   policy. (Shipped — §7.)
3. **Local AI capacity.** ~67–80 timeouts/hour for 25 days (1,924 in the 24h
   to 10-05 16:30Z). *Correction, same day:* the link is not the cause — the
   tailscale path is relayed but pings in 28–30ms, and Ollama answers
   `/api/tags` in 0.07s with both `gpt-oss:120b` and `gpt-oss:20b` loaded.
   These are generation requests not finishing inside the 120s/300s caps,
   which points at load on the single host (the 2026-08-17 precedent measured
   ~5× oversubscription); demand vs capacity was not re-measured today. Until
   it is fixed the full-tier trader is silent ~79% of the time. Owner-side:
   more capacity, less demand, or a paid fallback.
4. **Profit path = an entry rule that passes the permutation test before it
   trades.** The only candidate with a positive backtest is the trend module
   (memory: +117R 2020–26, ~12 signals/yr). Its 09-12 replay scripts are not on
   `main` or any local branch and must be redone before it is relied on; its
   forming-bar defect is still unshipped.
5. Backlog defects, none of which changes the sign: `conviction_collapse`
   zero-hold fee burns (entry gate reads confidence, rail reads conviction;
   5 trips −$0.46); legacy trail takes current realized as baseline so a losing
   partial reduce "arms" it (9 trips, flatten legs −$8.31); `adapt_retired`
   counts three partial exits of one position as three losses; an AI stop level
   typed 6938.0 for 6.938; orphaned position after `stop_eval_failed` unmanaged
   for 12 days (CVX −$2.22); agent 60's fleet starved by plan limit (14,389
   skips) then by the backtest gate (27,310 drops).

## 6. Not verified

- Why the local model times out: relay latency is ruled out (30ms, Ollama
  answers in 0.07s); host load is the remaining candidate and was not measured.
- Prod `.env` values — read access to it was denied in this session; cap and
  arm values are inferred from event payloads.
- `equity` events are retained 7 days, so peak/give-back figures (n=46) cover
  the last week only and are not a random sample.
- Counterfactuals use 15m candle closes; the feed check (fill vs containing
  candle close) is 15bp median, so sub-hour horizons are coarse.
- Real-world truth of the catalysts the Risk agent cited.

## 7. Shipped 2026-10-05 (owner: "do")

Commits `a29cd6b`, `19640db`, `2580528` and the round-3 commit carrying this
report. Ship test: an
independent verifier reproduced every number above from its own computation
(VERIFIED; wording discrepancies only, corrected in this file), and three
rounds of adversarial review. All three returned SHIP-AFTER-FIXES and each
found a real defect — rounds 2 and 3 in my own previous fix. The round-3 fix
is the reviewer's own, which it had already run against its reproductions; it
was not sent for a fourth review.

1. **A panel `hold` binds on entries again** (`run_engine._order_discussion`).
   The 09-05 override is opt-in behind `PANEL_ENTRY_OVERRIDE=1`. The env switch
   `PANEL_ORDER_VETO=1` was deliberately NOT used: it also removes the routed
   stop-hit exemption, letting the panel veto the desk's ruling on its own
   breached stop.
2. **The chair no longer answers for a rule fallback**
   (`analysis_agents._chair_final`): returned unchanged
   (`chair: "no_trader_verdict"`), same scope and switch as `_hold_only`.
   Round 1 narrowed this to `no llm response`; round 2 showed the narrow form
   let a chair order journal as `decided_by: rule`, so it is wide again.
3. **Found in review, fixed:** a rule or scaffold hold no longer clears a routed
   stop hit (`run_engine._settle_stop_hit`). Before, that hold cancelled the
   watcher's 180s fail-safe and suppressed re-noting for 30 minutes.
4. **Found in review of (3), fixed:** left uncleared, the note made the run due
   on every dispatch for as long as the process lived if price touched the
   stop and bounced (reproduced: still due at +6h, six full-tier cycles).
   `stop_router.pending` now ends at the fail-safe deadline, and a breach seen
   again ≥300s (or three watcher scans, if longer) after the level was last
   traded is a new hit with its own window. Round 3: `stop_router.clear` now
   acts only inside that window — a verdict landing after the deadline had
   popped the note and armed 30 minutes of suppression, leaving a position
   through its stop with the watcher off (prod kept the desk's sell there).
5. **Found in review, fixed:** the stop-hit exemption applies to reductions
   only (it had carried an add, and entries behind a stale flag or a raising
   router, over the panel's hold); a failed position lookup no longer reads as
   flat on a stop hit.

Mutation testing of the shipped guards: 28 mutants, 27 killed, 1 equivalent.

**Not changed, and why**

- *Panel unavailable → the desk's entry still stands (fail-open).* 14 of 52
  meetings since 09-11 failed open, 8 of them buys; the 5 resulting trips net
  +$0.78. Holding those would be code overruling a genuine AI verdict (owner
  policy 2026-07-31) on n=8. Owner decision, not shipped.
- *A vetoed entry journals as an ordinary desk hold*, so it feeds the
  no-prospect switch (2 holds over 1h → rotate, 12h bench) exactly as before
  09-05. Rotation was measured at $0 P&L; it costs LLM calls and makes the
  fleet page churn.

**What to expect, and the falsifier (registered before deploy)**

- Entries on agents 6 and 60 fall to roughly the fail-open residue: ≤ ~1/day
  (was 8/day since 09-11, ~100/day before). Slots rotate symbols hourly.
- F-VETO: over the 7 days after deploy, (a) zero `order_discussion` events
  with `veto_overridden: true` on a flat book (a stop-hit reduction may still
  carry it), (b) zero decisions with `fallback_reason: no llm
  response` and action buy/sell, (c) fees on agent 6 < $1.50 for the week
  (was $9.76 over the 25 days since 09-11). Any of the three missing → the
  ship FAILED on that item and is reported in those words.
- This ship does not make the desk profitable and is not claimed to. It stops
  entries that have no measured edge. A positive result needs an entry rule
  that beats the random-timing null first (§5.4).


## 8. Follow-up, same day (owner: four items)

### 8.1 First readout of the §7 ship (deployed 17:25Z)

| window | entry proposals | outcome |
|---|---|---|
| 16:25 → 17:25Z (before) | 7 buys the panel held | all 7 overridden and filled |
| 17:25 → 17:56Z (after) | 4 buys (2 per account) | all 4 held, no fill |

Only fill after the deploy: a protective (armed) partial exit on an existing
position. No worker errors. n=4 — the F-VETO window is seven days.

### 8.2 An entry the panel could not review is now held (owner: "make solution")

`run_engine._order_discussion`: when every panel attempt fails, a REDUCTION
still passes untouched (fail-open is for the book); an ENTRY becomes a hold
labelled `decided_by: rule, fallback_reason: panel unavailable`, with
`entry_held` on the `order_discussion` event. `PANEL_ENTRY_OVERRIDE=1` restores
the old behaviour. Review found three side effects of making this the normal
path during an outage, all fixed before shipping: the book is re-read after the
meeting (a long closed during minutes of timeouts turned the desk's `sell` into
an unreviewed short); held-entry cycles no longer count toward idle-retire (12
of them retired the slot and benched its symbol for 12h); and the held decision
keeps the desk's confidence (zeros diluted the agent-wide percentile gate).

### 8.3 Local AI timeouts — it is an on/off state, not load

Correction to §2.3 and §5.3. Successful local calls per day:

| period | calls/day | large (≥2k-token) decision calls/day |
|---|---|---|
| 09-08 → 09-10 | 2,584 – 3,162 | 433 – 511 |
| 09-11 → 10-04 | 103 – 154 (one day 664) | 0 – 5 |
| 10-05 from 15:30Z | ≈300 per HOUR | 22 – 65 per hour |

The change is a step, to the minute: last normal call 09-10T23:57:07Z; resumed
10-05T15:3xZ. In between the host answered every hour of every day, but only
~5 small requests an hour, with one two-hour window of full service
(09-29 19:24 → 21:16Z, a large call completing about once a minute) and a
small daily blip near 11:00Z. While "off", `/api/tags` would still have
answered — small requests got through. Since 15:30Z today: zero timeouts in the
new worker's log, 99 successful calls in the first 22 minutes.

That is the signature of a host that sleeps and wakes briefly for network
traffic — short requests fit inside the wake, a 60–90s generation does not —
and is fully awake only when someone is using it. It is NOT oversubscription:
the same host served ~3,000 calls a day through 09-10. Not proven from here
(the host's power log is not readable from prod or from this machine). To
prove and fix, on the AI host:

    pmset -g log | grep -E " (Sleep|Wake|DarkWake) " | tail -40   # compare with the times above
    pmset -g                                                      # look at sleep / powernap / standby
    sudo pmset -a sleep 0 disksleep 0 standby 0 autopoweroff 0 powernap 0   # never system-sleep (display may)

Nothing on the platform tells anyone when this happens: the desk ran 25 days
with its trader silent on 79% of decisions. A timeout-rate alert is the
software-side half of the fix and has not been built.

### 8.4 A profit path — what was built, and what it is

The only rule on the platform with a tested record is the trend module
(daily Donchian breakout, ADX/200MA gate, 1.5×ATR stop, 3×ATR trail). Its
2026-09-12 replay never reached the repo, so it was re-run independently and
pre-registered (`research/trend_replay/`), then re-checked by a second pass
(115 trades, fills verified against raw candles, no look-ahead).

| run, 2020-2026, $25 risk a trade | n | net | payoff | years + | max DD |
|---|---|---|---|---|---|
| rule as written (completed bars, exits on the daily close) | 115 | +114.2R | 2.95 | 7/7 | 20.2R |
| … without its best trade | 114 | +87.5R | | | |
| module's own stop enforced intraday (V2) | 118 | +122.9R | 3.58 | 7/7 | 14.6R |
| read hourly on the FORMING bar (how prod ran) | 164 | +92.9R | | 2025 negative | |
| foreign 5% intraday stop (also how prod ran) | 115 | +71.4R | 4.79 | 7/7 | 12.3R |

Permutation null p = 0.002 (0.020 against a null that preserves clustering).
What this is: 47% winners, a median trade of −0.26R, about 19 trades a year,
a losing streak of 11, a 20R drawdown lasting nine months, 507 days under a
prior high. Shorts are +7R of the total. It is a strategy that is right about
a year, not about a week. What cannot be removed: the five coins are large
*today*; trades cluster, so 115 is far fewer independent bets; one history
with two bull legs. A funding-cost proxy takes ~20R off.

Prod was not running that rule. Four defects, all fixed in this ship:

1. **Forming bar.** The hourly tick read the bar in progress as "today's
   close". 63 of 164 replayed entries exist only because of that and net
   −2.2R; the live BNB long of 09-21 is one the rule never takes (ADX 40.5).
   Now: completed bars only, fetched fresh (the cached feed could serve a
   mid-bar snapshot after the close), one ruling per completed bar, fills at
   the live mark.
2. **A foreign stop.** `orphan_reclaim` saw the module's run-less positions as
   unowned and attached the account's 5% stop; the SL/TP watcher closed on it
   intraday. That, not the module, closed the 09-18 XRP short. Cost in replay:
   −42.7R (−15.3R without the one trade that carries most of it). Now the
   sweep leaves the module's book alone and the row carries the module's own
   initial stop (V2). The +122.9R assumes a fill AT the stop; the watcher
   fills at the price it polls, and the review's bounds for that are +117.7R
   (hour close) to +107.1R (hour extreme) — the low end is below
   daily-close-only, so read V2 as "about the same return, smaller
   drawdown", not as an improvement.
3. **Phantom slots.** A position the watcher closed stayed in module state,
   holding one of three slots, until the module's own exit was refused. Now
   reconciled every cycle; a signal bar is entered at most once, so a
   stopped-out signal is not re-taken an hour later; and `trend_stats` counts
   every fill on the module's account — it had been blind to watcher closes,
   i.e. to the stop-outs.

4. **The module could not save its state.** `platform_settings.setting_value`
   is a 65,535-byte TEXT column and the state carries its own telemetry log
   (up to 400 rows of ~180 bytes). It stopped fitting at 366 rows: last
   successful save 2026-09-27T06:25Z, and every hourly cycle for the eight
   days after ran from that frozen snapshot (found by the independent
   verifier, confirmed on prod: 65,403 bytes, strict mode). Old telemetry is
   now trimmed so the state always fits. Checked against live completed bars:
   no close in those eight days exceeded the saved highs, so neither open
   position's trail was left looser than the rule's.

Known remaining differences from the replayed rule, none shown harmful: a
bar missed while the worker is down is not replayed afterwards; the two open
positions carry `best_close` values that were forming-bar highs (805.2 and
1.6487 against real closes of 802.6 and 1.5759), which makes their trails
slightly tighter than the rule's and is kept because a trail never loosens; the
30-day time stop is checked when a bar completes, so it can slip a day; a
signal blocked by the three-position cap can still be entered later the same
day if a slot frees; switching the module off with positions open leaves them
on a static stop with no trail.

Not done, and the owner's call: the module trades its own dedicated sim
account (agent 63, $10k, $25 risk a trade) and by design cannot touch a user's
book. Putting either owner account on this rule is a product decision — a new
fleet archetype — not a fix.

**Falsifier, re-registered.** Plan 31's "30 trips or 60 days, EV ≤ 0 → module
dies" cannot be read: ~3 trips in 60 days on a rule whose median trade loses.
Replaced by (a) process: every live entry must be one the completed-bar replay
also takes on that date, checked monthly — any that is not means the fix
failed; (b) outcome: stand the module down if its closed-trade drawdown passes
30R (1.5× the worst in the replay) or 24 months end net negative.
