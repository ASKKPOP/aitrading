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
platform's own feed). n = 632.

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
| trader LLM returned nothing; chair turned the rule engine's text into a buy | 99 | **−$19.69** | −$16.17 |
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
3. **Repair or replace the local AI link.** ~67 timeouts/hour for 25 days;
   tailscale path is relayed. Until this is fixed the "AI desk" is a rule
   engine plus a 180-token chair. Owner-side (Mac/network) or a provider
   decision.
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

- Why the local model times out (prompt size vs relay latency vs host load) —
  inferred from `llm_usage` prompt sizes and the tailscale line only.
- Prod `.env` values — read access to it was denied in this session; cap and
  arm values are inferred from event payloads.
- `equity` events are retained 7 days, so peak/give-back figures (n=46) cover
  the last week only and are not a random sample.
- Counterfactuals use 15m candle closes; the feed check (fill vs containing
  candle close) is 15bp median, so sub-hour horizons are coarse.
- Real-world truth of the catalysts the Risk agent cited.
