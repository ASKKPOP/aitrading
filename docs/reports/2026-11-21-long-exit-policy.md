# Long exit policy — long only, sell above buy price (owner order 2026-11-21)

## The rule (owner, verbatim chain)

- "buy low price ,, sell over buy price , that is main"
- "only one except , lost 20% expected then selling" → "15% < change"
- "our target rules is over 5% ( base buy price ) and AI desission is going
  down price then selling"
- Answers in chat: scope **all automation runs**; **long only, no shorts**;
  no other loss limit.

## What shipped

**Long only.** `futures_policy.shorts_blocked()` now defaults ON.
- No new shorts open on any market.
- Open shorts wind down under the existing rules (covers are never refused).
- A flat run on a futures or margin book can no longer open anything, so it
  retires as `no_prospect_switched` and the fleet rebuilds the slot.

**Longs held by automation** (runs, fleets, automation rules, trend module,
copy-trading followers) have exactly three exits:

| Exit | Rule | Where |
|---|---|---|
| Target | +5% over the average buy price | SL/TP watcher |
| AI desk sell | Only above buy price + round-trip fees | desk cycle → `execute_paper_trade` |
| Emergency | −15% below the average buy price | SL/TP watcher |

None of these close a held long any more:
- the breakeven ratchet and the trailing lock;
- `max_loss`, `profit_target`, `at_time` and thesis decay;
- conviction collapse and price cross;
- the trailing stop and the time stop;
- fleet breaker and harvest flattens.

A refused machine flatten hands the long off at once as `positions_held`. It
does not retry for an hour. The two liquidation rails still close a legacy
leveraged long.

**Human actions are never refused:**
- a manual trade;
- a Stop the user presses on a run (`user_stop`) or a fleet
  (`fleet_stop_all`);
- resting limit orders;
- the consented start-conflict close;
- a person's own SL/TP, trailing stop or time stop on a manual position.

**Mechanics:**
- `long_exit_policy.py` holds the rule.
- Checks run in `automation.execute_paper_trade`, with
  `services._update_position_from_signal` as the backstop.
- The live-rule check runs before `submit_live`.
- Automation longs carry `positions.exit_policy='long_policy'`. The watcher
  keys on that marker.
- Kill switch: `LONG_EXIT_POLICY=0`. Fractions are set by `LONG_TARGET_FRAC`
  (0.05) and `LONG_EMERGENCY_LOSS_FRAC` (0.15).

## Evidence against, stated to the owner before building

- [2026-11-21 payoff replay](2026-11-21-payoff-ratio-exit-replay.md): holding
  losers longer only looks better in a falling tape for shorts. The same rule
  loses the mirror amount on longs.
- [2026-11-19 buy-low take-profit research](2026-11-19-buy-low-take-profit-slots-research.md):
  selling only in profit gives a ~100% closed-trade win rate, yet slots end
  stuck underwater (crypto spot −59…−82%).

## Measurement (pre-registered; the experiment judges the rule)

**Hypothesis.** The owner's rule makes fleet P&L (realized + open) positive
over the next 14 days.

**Refuted if,** at day 7 or day 14, either of these holds:
- (a) realized + unrealized for agent 6 automation is below zero;
- (b) more than half of the open automation longs have been underwater
  for more than 3 days.

**What each report states:**
- P&L first;
- the count and age of underwater longs;
- emergency fires;
- target fires;
- refused AI sells.

If the rule fails, the report says FAILED in the same terms. The owner
decides whether to switch it off with `LONG_EXIT_POLICY=0`.

## Known limits

- Rows that existed before deploy carry no marker. Prod had **zero open
  longs** at deploy, so none exist.
- A person's PATCH of SL/TP on an automation-marked long is accepted but not
  used by the watcher. The −15% / +5% levels apply.
- A run holding a long keeps running past `at_time` and `max_trades`, so the
  AI desk can still sell it on a downturn. Adds into losers stay blocked
  (`RUN_ADDS_REQUIRE_PROFIT`).
- Copy-trading followers are charged the legacy flat fee. The breakeven uses
  the market rate, so a follower sell just over breakeven can net slightly
  negative.
