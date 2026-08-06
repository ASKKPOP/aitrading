# Sooppiy.com AI desk — decisions on the monitoring recommendations & issues

**Decided BY the platform's own trading AI**, not by the monitoring session.
Model: `local / gpt-oss:120b` (the desk's decision tier, via `llm_client.generate_text(tier="decision")`).
Rendered 2026-07-31 ~22:2x UTC. Escalated per the base rule *"trading decisions belong to the sooppiy AI — escalate to the desk and journal the verdict."*

## Profit recommendations — desk verdict

| ID | Item | Desk decision | Desk reason |
|----|------|---------------|-------------|
| R8 | Per-run risk (max_loss) ceiling | **DEFER** | Need risk-adjusted cap study; $50 may blunt big winners while giving only modest loss reduction. |
| R6 | Breakeven / low-arm trailing ratchet | **REJECT** | Trailing ratchet cuts proven winners more than it protects; backtest shows net loss increase. |
| R7 | Gate entries on conviction vs confidence | **REJECT** | Conviction gating lacks discriminative power; confidence already anti-predictive, no win-rate improvement. |
| R7′ | Down-size missing-conviction entries | **REJECT** | Reducing size on missing conviction harms profitable runs; biggest losers had normal conviction. |
| R9 | Block adds into a losing long | **ACKNOWLEDGE** | Existing gate already blocks adds to losing longs; functionality confirmed. |
| R1 | Per-market fee table / min-edge gate | **ADOPT** | Per-market fee table prevents unprofitable small moves; aligns edge with actual transaction costs. |
| DOCS | Wire /docs/how-it-works | **DEFER** | Routing docs not implemented yet; integration pending before wiring. |
| LB | Leaderboard: real user trading only | **ACKNOWLEDGE** | Leaderboard filter already applied, ensuring only live agents displayed. |

## Observed issues — desk verdict

| ID | Item | Desk decision | Desk reason |
|----|------|---------------|-------------|
| I1 | Give-back leak (trail arms at 1× max_loss) | **DEFER** | Trailing stop triggers too early, limiting winner upside; need more data before changing design. |
| I2 | Large-run risk concentration (83% of loss) | **ADOPT** | Risk concentration from large runs causing majority of losses; diversify exposure now. |
| I3 | Confidence is the gate yet anti-predictive | **REJECT** (as a gate) | Confidence metric inversely correlates with results; stop using it as gate. |
| I4 | qty=0 zombie BTC position open | **ACKNOWLEDGE** | Zero-quantity BTC position adds no risk but clutters books; note and clean later. |
| I5 | KAITO −$10.94 (round-trip + add into fall) | **ADOPT** | KAITO exit timing flawed, adding to loss; improve conviction thresholds. |
| I6 | qa-* test agents ranking on leaderboard | **ACKNOWLEDGE** | QA agents ranking issue resolved; acknowledge fix. |

## Notes
- The desk **aligns** with the monitoring review on R6 / R7 / R7′ (reject) and R9 / LB (acknowledge).
- The desk **diverges / adds urgency**: it wants to **ADOPT R1** (per-market fees) and **act now on risk concentration (I2)**, and to **improve KAITO-style exit/conviction timing (I5)** — where the review had these as staged/self-correcting.
- These are the desk's calls to make; any implementation still follows the operating model (build off `main`, verify, deploy, then monitor).
