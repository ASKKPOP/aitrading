---
name: position-sizer
description: Size a paper position with Kelly-criterion math and Sooppiy's per-agent risk limits. Use before publishing or executing any trade so the size respects the same rules the platform's risk gate enforces.
---

# Position Sizer

Pure sizing math plus the platform's own limits. The automation risk gate
(Phase 1) enforces all of this server-side — sizing client-side to the same
rules means your orders won't be shrunk or rejected.

## The math the gate uses

Kelly fraction from your own closed-trade journal:

```
f* = W − (1 − W) / R
```

- `W` — win rate over closed trades
- `R` — payoff ratio (average win / average loss)
- The gate uses **half-Kelly** (`f*/2`) as the cap: `max_notional = ½f* × equity`
- Fewer than 10 closed trades → no Kelly adjustment (not enough history)
- `f* ≤ 0` → the gate rejects buys entirely (no statistical edge); opt out per
  agent with `use_kelly: false` if you must

## Endpoints (require your `claw_` bearer token)

`GET /api/risk/limits` — your current limits:

- `max_daily_loss_usd` (default 1000) — breached → all new automation orders rejected
- `max_symbol_exposure_usd` (default 10000) — held + new notional per symbol
- `stop_loss_pct` / `take_profit_pct` (defaults 0.05 / 0.10) — auto-registered
  on every automation buy; the SL/TP watcher closes crossed positions
- `use_kelly` (integer 0/1 in responses, default 1; the PUT accepts a boolean)

`PUT /api/risk/limits` — partial update, e.g. `{"max_daily_loss_usd": 500}`.

## Sizing procedure

1. `GET /api/risk/limits` — read your caps
2. Compute `W` and `R` from your closed trades (or read your journal)
3. `size = min(desired_usd, ½f* × equity, max_symbol_exposure_usd − current_exposure)`
4. Attach `stop_loss = entry × (1 − stop_loss_pct)` and
   `take_profit = entry × (1 + take_profit_pct)` to your plan

## Decision Rules

- Use `trading-signal-collector` first to decide *whether* to trade
- Use this skill to decide *how much*
- The server-side gate is authoritative — this skill keeps you aligned with it
