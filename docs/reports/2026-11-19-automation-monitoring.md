# Automation monitoring — 2026-11-19 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-19T15:13:14Z (KST day 2026-11-19 = 11-18T15:00Z → 11-19T15:00Z, closed) — EARLY P&L COMMIT

Prod clock 2026-11-19 15:13:14 (on schedule). Image `.env` = worker = backend = `sooppiy-backend:20261118-sweep-20261118` (f8a015c,
docs-only after it on main). Trading set = {6, 60} (fleet 44 agent 6, fleet 43 agent 60, both active); only agent 6 cycled (85 runs).

| window | agent 6 (info) | agent 60 (forevery1969) | combined | closes / opens | fees (both legs) |
|---|---|---|---|---|---|
| **KST 11-19** net | **+0.97** | 0.00 (0 fills) | **+0.97** | 68 / 68 | 2.10 |
| 24 h (11-18T15:13Z → 11-19T15:14Z) net | +1.03 | 0.00 | +1.03 | 70 / 69 | 2.15 |
| pnl_audit all_in UTC 11-18 (full day) / 11-19 (to 15:13Z) | +4.87 / **−1.15** (`ok`, EXIT 0, orphan 0) | 0 | | | |

Routes: pnl_audit UTC 11-18 +4.87 = signals +4.867; UTC 11-19 −1.15 = −1.155. Cash reconciliation: 9,815.626 (11-18 18:07Z) + 75.01 released
− 219.14 open margin + R = 9,671.194 → R = −0.299 vs signals since 11-18T18:07Z −0.296.

Full analysis follows in the final entry of this sweep.
