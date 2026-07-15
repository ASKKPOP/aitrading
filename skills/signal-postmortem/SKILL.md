---
name: signal-postmortem
description: Review how past signals and automation runs actually performed — what executed, what was skipped and why, and what the risk gate rejected. Use on a regular cadence to prune losing patterns and keep working ones.
---

# Signal Postmortem

A review framework over Sooppiy's journals. Everything an automated strategy
did — or was prevented from doing — is journaled; this skill reads it back.

## Endpoints (require your `claw_` bearer token)

`GET /api/automation/runs?limit=100` — every rule run:

- `action`, `confidence`, `executed`
- `skip_reason` — why a run did NOT trade. Risk-gate rejections are prefixed
  `risk:` (daily loss, exposure, Kelly no-edge, breaker halted); scanner rules
  log `scanner: no candidates available`
- `signal_id` — links to the executed trade

`GET /api/signals?agent_id=me` — your executed signals (entry, quantity, side).
SL/TP watcher exits carry content like `risk: stop_loss triggered at <price>`.

`GET /api/risk/breaker` — whether a HALT interrupted trading in the window.

## Review procedure

1. Pull the last N runs; split executed vs skipped
2. Group `skip_reason` values — repeated `risk:` rejections mean your sizing or
   limits disagree with your strategy (fix one of them deliberately)
3. Replay executed trades: pair buys with their sells (average-cost basis),
   compute per-trade P&L, win rate `W`, payoff ratio `R`
4. Check SL/TP exits: stop-losses firing often with take-profits rarely →
   entries are poorly timed, or stops too tight for the asset's σ
5. Feed the updated `W`/`R` back into `position-sizer` — Kelly sizing improves
   as the journal grows

## Decision Rules

- Run after every meaningful batch of trades (or weekly)
- Prune rules whose skip/loss patterns repeat; keep what demonstrably works
- Use `trading-signal-collector` to check whether the signal inputs changed
  before blaming the strategy
