# Automation monitoring — 2026-11-17 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-17T15:13:07Z (KST day 2026-11-17 = 11-16T15:00Z → 11-17T15:00Z, just closed)

**EARLY P&L COMMIT** (full analysis follows in this section once Agents A/B report).

| window | agent 6 (info) | agent 60 (forevery1969) | combined | fills | fees |
|---|---|---|---|---|---|
| 24 h (11-16T15:13Z → 11-17T15:13Z) realized | **−5.17** | 0.00 (0 fills) | **−5.17** | 94 (50 closes) | 1.43 |
| 24 h without largest loser (TRUMP 217302 −2.74) | −2.43 | — | −2.43 | | |
| KST 11-17 (11-16T15Z → 11-17T15Z) | **−5.20** | 0.00 | −5.20 | 92 | 1.39 |
| pnl_audit all_in UTC 11-16 / 11-17 (to 15:13Z) | +0.17 / **−5.34** (`ok`, EXIT 0) | 0 | | | |
| open uPNL (ETH 215281 short 0.0209 @1793.1, mark 1803.7) | −0.22 | — | −0.22 | | |

Routes agree: pnl_audit UTC 11-17 −5.34 = SQL Σ close pnl − entry fees −5.343; cash 9,858.48 (11-16 sweep) + 33.53 margin released
− 5.155 realized since sweep − 37.52 ETH margin = 9,849.335 vs live 9,849.338.
Four runs carry −6.02 (TRUMP 217302 −2.74, LINK 215403 −1.18, SOL 215280 −1.18, AVAX 215524 −0.91); the other ~40 trips +0.85.
