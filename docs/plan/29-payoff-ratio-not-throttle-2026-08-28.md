# Plan 29 — The lever is payoff ratio, not throttle position

**Date:** 2026-08-28 · **Trigger:** owner, verbatim — *"3 days monitoring, logic totally some wrong, it's will be doesn't change for a month or a years, so need analysis more aggressive trading. Analysis and make plan."*

**Owner's premise is accepted:** the system has produced **zero trades for 16+ hours** and **$0.00**, and nothing in the current configuration will change that on its own. Three days of monitoring produced readings, not profit. That is a fair verdict and this plan does not argue with it.

**What the analysis found instead:** the zero-trade state is not the disease. Three agents, working independently with different methods, converged on one diagnosis — **the book has no positive gross edge to be aggressive with, and the desk is correctly refusing to trade it.** Aggression applied today multiplies a measured loss.

---

## 1. The four findings that decide the plan

### 1.1 Gross edge is negative BEFORE fees, in every market

| Market | n episodes | Mean gross bp | Notional-wtd | Fee bp/leg | Net USD |
|---|---|---|---|---|---|
| crypto | 87 | −4.55 | −32.68 | 4.5 | −109.44 |
| forex | 22 | −0.56 | −3.10 | 0.8 | −6.13 |
| futures | 23 | −5.87 | −7.85 | 0.5 | −23.98 |
| us-stock | 16 | −12.83 | −48.36 | 0.5 | −47.69 |
| **Total** | **148** | | **−20.76** | | **−$187.24** |

Verified by **three independent routes agreeing to 0.0000** (fill-price replay, `Σ(exit.pnl+exit.fee)` local, raw SQL on prod). A fourth agent's independent replay reconciles to `agents.cash` to the cent on all three clean agents.

**Abolishing every fee recovers $29.41 of a $187.24 loss.** Perfect routing to the cheapest venue recovers $60.83 and still loses $165. **Fees are 15.7% of the loss, not its cause.** Fee reduction cannot fix this: break-even would require a fee of **−10.61 bp**.

### 1.2 The actual defect, in one line

> **Median winning excursion is 7.8 bp. The round-trip fee is 9.00 bp. 15 of 22 directional winners earn less than the fee. The median loser runs to −42.4 bp.**

| | Value |
|---|---|
| Directional hit rate (gross > 0) | **57.9%** |
| All-in net win rate (net > 0) | **18.4%** |
| Fee converts winners → losers | **39.5 pp** |
| Gross payoff ratio | **0.316** |
| Mean win / mean loss | 34.0 bp / 71.9 bp |

**The hit rate is not the problem — 57.9% is above a coin flip.** Expectancy fails on magnitude: `0.579 × 34.0 − 0.421 × 71.9 = −10.6 bp`. **The desk cuts winners at roughly its own transaction cost and lets losers run five times further.**

**The single target number for this whole plan: gross payoff ratio 0.316 → 0.727** (break-even at the observed 57.9% hit rate). Equivalently: **double the mean win**, or **cut the mean loss by 65%**.

### 1.3 The desk's refusal is correct, and 08-25 proved it experimentally

The only recent day with throughput (08-25, 64 legs) traded **because the panel failed open.** Every leg fired after `09:09:09Z`, the minute the panel began emitting `"error": "panel fallback (not the AI): no llm response"` — `run_engine.py:6447-6453` fails open by design.

**A controlled experiment inside one day — same fleet, same model, same prompt:**

| 08-25 window | Entry proposals | Panel errors | Trades |
|---|---|---|---|
| 00:00–09:09 (panel working) | 20 | 0 | **0** |
| 09:09–24:00 (panel broken) | 18 | 46 | **64 legs** |

Proposal rate was unchanged; the only variable was whether the panel answered. **Outcome: −$6.15 net on 22 round trips, 18.2% win rate, and 9 of 22 were directionally CORRECT and still lost to fees.**

The desk's own most common stated reason for holding (580 of 2,279 holds) is fee/expectancy, tracing to doctrine in `trading_skills.py:139-148`: *"A decision with no positive-expectancy case … is not a trade, it is a fee you volunteered to pay."* **§1.1 measures that doctrine to be right.**

### 1.4 Gates are not the constraint; the AI's own `hold` is

| Funnel stage (48h) | Enter | Survive | Killed |
|---|---|---|---|
| Desk forms a directional outlook | 2,356 | 206 | **2,150 (91.3%)** |
| Panel keeps the entry | 67 | **1** | **66 (98.5%)** |
| **Risk gates** | 1 | 1 | **0** |
| **Confidence gate** | 1 | 1 | **0** |

The confidence gate fired **zero times in 48h**; 2,786 of 2,851 `gate_skip` rows are the tautology `"decision is 'hold'"`. **Loosening gates changes nothing — nothing reaches them.**

**Refuted by name, do not re-run:** *entries scale with slot count* — on 08-27 there were **188 runs alive** (3× the 08-13 peak of 60) producing **2 entries instead of 60**; per-run conversion degraded 91×. Capacity was never the constraint.

---

## 2. The aggression dollar grid — every cell is negative

Expected **net $/week**. 1x = 35.1 trips/week measured. CI90 upper bound is negative in every cell; stripping the largest contributor never flips a sign.

| Multiplier | Current size $154 | Consolidated $308 **(LIVE)** | Armed $3,083 **(FLEET 42)** |
|---|---|---|---|
| 1x | −$12 | −$25 | −$249 |
| 3x | −$37 | −$75 | −$747 |
| 10x | −$124 | −$249 | −$2,489 |
| 30x | −$372 | −$747 | **−$7,466** |

**Both scaling axes are optimistic.** Frequency: raising trade count means relaxing the bar now rejecting trades, so the marginal trade is worse than the average by construction. Size: measured exit slippage is **9 of 9 adverse**, mean 18.9 bp — structural, because an armed exit only fires *after* price crosses its level. Under a square-root impact law at ~20× size that adds ~71 bp/trip:

> **Impact-adjusted, 30× at the armed size: −$30,535/week = −27.8% of the $110k book per week. The book is destroyed in roughly four weeks.**

**VERDICT: NO-GO on every aggression setting, including 1×.**

---

## 3. The plan

### PHASE 0 — Disarm the loaded gun (needs owner approval; no experiment required)

`FLEET_TARGET_SLOTS=4` has already re-anchored fleet 41 (agent 6) to **$1,125 max_bet**, and fleet 42 is armed at **~$11,250 on a $100k book** — a ~20× size increase that fires **silently on the next slot turnover**. At 1× frequency it alone moves the weekly bleed from −$12 to −$249 (−$1,017 impact-adjusted).

It was justified by #593's finding that "even long-only random loses at the current slot size" — but `simulate_trip` is **exactly homogeneous of degree 1 in notional** (verified by inspection; 2,000-trial check, max deviation 3.1e-15), so that replay is *mathematically incapable of seeing size*. The claim is equally true at every size. **The consolidation was shipped on a quantity its own experiment could not measure.**

```bash
ssh -i ~/shell/sierrabiolab/sierrabiolab-aws.pem ec2-user@52.9.147.202 \
  'cd /home/ec2-user/sooppiy && sed -i "/^FLEET_TARGET_SLOTS=/d" .env && docker compose up -d worker'
```

**Size is the last lever to raise, not the first. It is currently the only one armed.**

### PHASE 1 — Close two instrumentation gaps (small, safe, unblocks everything else)

1. **Persist the desk's confidence on every closed trip.** Today no conviction score survives to the closed trip, so *marginal-vs-average expectancy — the single most important aggression parameter — cannot be measured at all.* Without it, every frequency lever is a guess.
2. **Fix agent 6's settlement defect.** On exit rows the writer overwrites `entry_price` with `exit_price`, so `(exit−entry)×qty ≡ 0` and `agents.cash` never moves (exactly `10000.00000000` across 72 trips). **The fill prices are intact**, so replay recovers all 72 trips. Fixing the write makes the account measurable and **unblocks a ZI-control re-run that was impossible before**.

### PHASE 2 — The fork experiment: is the direction signal real?

The hit rate is 57.9% — above a coin flip — but the ZI control said the AI is indistinguishable from random, and its n=57 was **degenerate** (56 of 57 netted exactly $0.00 from the settlement defect ⇒ effective n≈1). **With Phase 1's replay, that control can now be re-run on real data.**

- **If AI direction beats random at CI90** → the signal is real, the defect is purely exit geometry, and Phase 3 is the whole job.
- **If it does not** → no exit fix can help, and the entry generator must be replaced rather than tuned. **This is the fork; do not build Phase 3 before it resolves.**

### PHASE 3 — Attack the payoff ratio (only if Phase 2 says the signal is real)

Target: **gross payoff 0.316 → 0.727**, i.e. median winning excursion **7.8 bp → >9.0 bp** so winners clear their own fee.

#592 (`RATCHET_LOCK_FRAC=0.5`) already pushes this direction and its one fire returned +$1.09 where the old rule guaranteed $0. **But it stands at n=2 against a required n≈690 per arm** (per-trip SD 88.4 bp vs a +10.11 bp effect) — **underpowered by ~345×, ≈20 weeks per arm at 35 trips/week.** Therefore Phase 3 must be decided by **replay, not by live accrual**: the live book cannot answer it this year.

Replay design is specified in full (arms: authored policy / zero-fee / re-routed fee / **zero-intelligence control** / buy-and-hold; event-cluster resampling; prod-fill slippage basis, not candle basis; kill condition if the authored arm cannot beat the ZI arm in any market at any horizon).

### PHASE 4 — Aggression, and only then

Reconsider when **all four** hold on the same replay method:

1. DW gross ≥ **+9.00 bp/trip**, bootstrap CI90 lower bound > 0, over **n ≥ 690** closed trips post-change
2. **Median winning excursion > 9.00 bp** (now 7.8)
3. Sign survives stripping the largest contributor **and** collapsing to one observation per correlated-event cluster
4. Exit slippage no longer one-directional: adverse share **< 70%** over n ≥ 30 `armed_exit` fires (now **9/9 = 100%**)

Then raise **count** levers first, one at a time, re-measuring after each. **The size lever goes last**, and only after slippage is re-measured *at the new size*.

---

## 4. What this plan refuses to do, and why

- **It will not loosen gates.** Nothing reaches them; the confidence gate fired 0 times in 48h.
- **It will not restore slot count as a throughput fix.** 188 live runs produced 2 entries; conversion, not capacity, is broken.
- **It will not route aggression to low-fee markets.** Gross is negative in all four; zero-fee still loses $158 of $187.
- **It will not disable the panel or the fee doctrine to manufacture trades.** That is the one change available today that would produce "aggressive trading" — and 08-25 measured what it costs: −$6.15 with 9 of 22 correct calls losing anyway. **Turning off the immune system is not a strategy.**

## 5. Honest limits

- Slices J and I have CI90s including zero: **if the three worst trades of the week could be deleted, the book is indistinguishable from zero** — still not profitable, and not an available action.
- The ~20× impact projection uses a square-root law — **inference, not measurement** (n=9 slippage observations, all at ~$137 notional). Could be 2× off either way.
- Hold-time matching across markets is not achievable at current n (forex n=1, futures n=2 in the <1h bucket); the horizon artifact is noted, not excluded.
- **Methodology trap recorded:** this ledger closes positions in dust-halving slices. Equal-weighting partials reports crypto at **+13.48 bp**; collapsing to position episodes gives **−4.55 bp**. **Any per-trip statistic here that does not collapse partials is wrong by ~46 bp and by sign.** An earlier "+5.10 bp gross edge" figure in this stack could not be reproduced on any slice and is retracted.
