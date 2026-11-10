# Automation monitoring — 2026-11-10 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-10T17:27:57Z (KST day 2026-11-10 = 11-09T15:00Z → 11-10T15:00Z)

> EARLY COMMIT (HANDOFF §10, 11-09 trap): P&L + data pass committed first; the agent analyses,
> the ledger and the solution are appended below in the same run.

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-10 17:27:57 (fire ~2.3 h late vs 15:07Z).
Window = 2026-11-09T17:28Z → 2026-11-10T17:28Z. Worker + backend on
`sooppiy-backend:20261109-sweep-20261109` (374bba4); origin/main 9fb2fc0 = +1 docs commit
→ no code drift. Trading set re-derived = **exactly {6, 60}**. No leftover `/tmp/sooppiy-sweep.*`
from a dead prior run.

### 1. P&L — dollars first

| window | agent 6 (info) | agent 60 (forevery1969) | combined | n closes | fees (all legs) |
|---|---|---|---|---|---|
| **24 h window** (ledger ≈ Σ stopped-run realized) | **+2.11** | **0.00** | **+2.11** | 58 | 1.48 |
| **KST day 11-10** (close legs; entry fees ≈ −0.6 not netted) | +1.48 gross-of-entry-fee | 0.00 | +1.48 | 46 | 1.24 |
| UTC day 11-10 (pnl_audit ledger, 00Z→17:28Z) | +2.14 | 0.00 | **+2.14** | 54 | 1.43 |
| UTC day 11-09 (pnl_audit ledger) | −0.07 | 0.00 | −0.07 | 5 | 0.13 |
| open uPNL now (3 shorts, agent 6) | FIL −0.10, NEAR −1.92, BTC −0.03 = **−2.05** | none | **−2.05** | — | — |

- pnl_audit `--since 2026-11-09`: EXIT 0, both days `ok` (resid 0.00 / 0.01), 71/71 validated.
- Independent routes agree: `signals` operation fills 115 (58 short, 57 cover), Σfee 1.4796,
  Σ`pnl` on closes 2.8452 = my close-leg replay 2.84; Σ`realized_pnl_usd` of the 80 agent-6
  runs stopped in window = 2.1082 ≈ ledger.
- Per close leg (24 h, n = 58): win 84 %, avg win +0.065, avg loss −0.038, largest +0.49
  (151796 ETH), worst −0.20 (147516 TRUMP watcher stop). **Without the largest: +2.35 close-leg
  (≈ +1.6 net) — sign holds.**
- **Mark-to-market verdict: realized +2.11, open −2.05 → ≈ +$0.06 for the day.** Agent 60
  made **zero trades**. Lifetime realized: agent 6 −104.99, agent 60 −1.34.
- Stopped runs by reason (agent 6): `stop_event:trailing_lock` 54 runs **+2.38**,
  `no_prospect_switched` 26 runs **−0.27**; agent 60: `idle_retired` 3 runs 0.00.
- Notionals are tiny: open shorts $18.7 / $103.8 / $45.5 on a ~$9.9k book.
