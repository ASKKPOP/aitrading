# Automation monitoring — 2026-11-20 (UTC day) — daily 24h sweep

Newest-first. Authority for rules/access/traps: `HANDOFF-automation-monitoring.md`.

## 24h sweep — 2026-11-20T15:13:21Z (KST day 2026-11-20 = 11-19T15:00Z → 11-20T15:00Z, closed)

EARLY COMMIT (P&L + state); analysis sections follow in the amend.

Prod clock `SELECT UTC_TIMESTAMP()` = 2026-11-20 15:13:21 (on schedule; no leftover `/tmp/sooppiy-sweep.*`). Image `.env` = worker =
backend = `sooppiy-backend:20261120-stop-stamp` = 267f742 = origin/main HEAD → **no drift**.

**Ground state changed overnight (owner):** fleets 44 (agent 6) and 43 (agent 60) got `stop_all` (flatten) at **02:54:37Z**; both agents'
`signals` were deleted, `realized_pnl_usd` zeroed, cash back to 10,000.00 (reset); the platform-wide **futures / short / forex / options /
Polymarket block** shipped 04:11Z–06:02Z. Two new agent-6 fleets (51 at 06:22Z, 52 at 07:31Z, archetype `short`) ended `build_failed` after 20
`research_empty` each. **No fleet is active; `MAX(run_events.ts)` = 02:54:59Z — nothing has traded for 12 h 18 m.**

### 1. P&L — dollars first (rebuilt from `run_events` `trade` fills; `signals` and `pnl_audit` are unusable after the reset)

| window | agent 6 (info) | agent 60 (forevery1969) | combined | closes / entries | fees |
|---|---|---|---|---|---|
| **KST 11-20** = 24 h (trading ended 02:54:59Z) | **+2.44** | 0.00 (0 runs) | **+2.44** | 42 / 38 (38/38 shorts) | 1.13 |
| without largest (AAVE 230677 +0.51) | **+1.93** | — | +1.93 | | |
| trips opened AND closed in window (n = 38) | +2.30; ex-largest +1.79 | — | | | |
| UTC 11-19 (15Z–24Z part) n = 25 | +1.63 (ex-largest +1.12) | 0 | | | |
| UTC 11-20 n = 17 | +0.81 (ex-largest LIT 230979 +0.28 → +0.53) | 0 | | | |
| open uPNL now | 0 (flat; 8 members flattened by stop_all) | 0 | 0 | | |

- Shape: 33 W / 9 L (79 %), **payoff 1.40**. By exit: breakeven-ratchet/trailing-lock stops n = 40 **+2.67**, owner `fleet_stop_all`
  flatten n = 2 **−0.23** (TRUMP 230987 −0.17, BNB 230988 −0.07).
- Routes: (1) fill replay +2.437; (2) `adapt` realized Σ +3.003 (n = 44) — adapt nets exit fees only; Δ 0.566 ≈ the 42 trips' open fees
  (½ of 1.129) → reconciled; (3) `trading_runs.realized_pnl_usd` stamps = 0.00 for every run (zeroed by the reset — not a route any more).
- **Verdict: a small profit (+2.44, +1.93 without its largest), on a falling tape the all-short book was positioned for. The owner reset
  then removed it from the ledger.** Agent 60: $0, 9th day (subscription, R39).
