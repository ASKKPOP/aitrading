# Chart Analysis vs Human Psychology: What the Verified Numbers Say

**Deep research report — success rates per parameter, buy/sell prediction · July 2026**
**Method:** every percentage below was adversarially fact-checked against the primary source by 3 independent verifiers. Claims that failed verification are flagged, not reported as fact.

---

## The headline answer to your question

Your instinct is half right — and the research shows the *other* half is also weaker than people think.

You wrote that most people believe charts, but that **"people's mental patterns shaped by government policies, market trends, wars, social issues, news, social media, economic indicators, and major headlines"** matter more. The verified evidence says:

1. **The famous chart-pattern numbers are folklore.** The "80%+ success rate" for Head & Shoulders and Double Bottom that circulates on trading sites has **no peer-reviewed support**. It traces to practitioner tallies (Bulkowski's *Encyclopedia of Chart Patterns*) — in-sample counts, never independently replicated, and this research pass could not verify them.
2. **But the famous psychology number is also folklore-adjacent.** The most-quoted evidence for your view — "Twitter mood predicts the market with 87.6% accuracy" (Bollen et al. 2011) — was based on only **~15 out-of-sample trading days**, used a proprietary lexicon nobody can inspect, **failed independent replication** (zero out-of-sample predictive power), and the hedge fund built on it closed within a year.
3. **What both sides actually deliver, verified: roughly 50–55% directional accuracy, or a few percent per year of risk-adjusted edge.** Markets are hard. Statistically detectable edges exist on both sides; economically large ones don't survive scrutiny.
4. **Where you're most right:** the academic consensus is that chart patterns are *informative but not profitable stand-alone* — while human-behavior data (sentiment, news timing) measurably *adds* information to models. Modern AI systems treat psychology as a real input; they treat classic chart patterns mostly as weak features, not decision rules.

---

## Part A — Chart analysis: verified success rates

### A1. Chart patterns in general (10 classic patterns)
**Lo, Mamaysky & Wang (2000), *Journal of Finance*** — the canonical academic test, US stocks 1962–1996, including Head & Shoulders, Double Top/Bottom, Triangles.

| Result | Number |
|---|---|
| Patterns statistically informative (NYSE/AMEX) | **7 of 10** (double bottoms NOT among them) |
| Patterns statistically informative (Nasdaq) | **10 of 10** |
| Under the stricter Kolmogorov–Smirnov test | only 5 of 10 |
| Proof this makes money | **None** — the authors state it "does not necessarily imply that technical analysis can be used to generate excess trading profits" |

**Verdict on the "80%+ success" claims:** informativeness ≠ win rate. No peer-reviewed source supports 80%+ success for any classic pattern.

### A2. Head & Shoulders specifically
**Savin, Weller & Zvingelis (2007), *Journal of Financial Econometrics*** — S&P 500 & Russell 2000 stocks, 1990–1999.

| Result | Number |
|---|---|
| Risk-adjusted excess return, market-hedged strategy | **5–7% per year** |
| Stand-alone H&S trading on S&P 500 stocks | **no evidence of profitability** |
| Stand-alone on Russell 2000 (small caps) | weak evidence; ~4.2%/yr after institutional costs |

The pattern contains real information — but not the high raw win rate traders claim.

### A3. Moving-average / golden-cross rules
**Brock, Lakonishok & LeBaron (1992), *Journal of Finance*** — DJIA, 1897–1986. The canonical measured "win rate" in the academic literature:

| Result | Number |
|---|---|
| Days positive after a BUY signal | **53–54%** |
| Days positive after a SELL signal | **~49%** |
| Buy-signal days annualized | ~+12% vs +4% unconditional |
| Sell-signal days annualized | ~−7% |
| After data-snooping correction + transaction costs (Sullivan et al. 1999; Bajgrowicz & Scaillet 2012) | **profits essentially disappear**, especially in recent decades |

So the true measured edge of the most famous technical rule is **~4–5 percentage points of win rate above a coin flip, before costs** — not 70–80%.

### A4. MACD and RSI
**Chio (2022), arXiv backtest** of DJIA/Nasdaq/S&P 500, 2015–2021 (⚠️ preprint, no peer review, no transaction costs, bullish period, no buy-and-hold benchmark):

| Rule | Win rate |
|---|---|
| MACD alone | **37–68%** depending on variant/index; Sharpe only 0.28–0.50 — "not a strong predictive tool" |
| MACD + RSI combined | **78–86%** — but never benchmarked against just holding the index, so this is NOT evidence of beating the market |

This matches the community view you quoted: indicators combined (with volume, support/resistance) do better than any single pattern — but "win rate" here still isn't profit.

### A5. Is technical analysis profitable at all?
**Park & Irwin (2007), *Journal of Economic Surveys*** — a review of 95 modern studies (1988–2004):

| Result | Number |
|---|---|
| Studies finding positive results | **56 of 95 (~59%)** |
| Negative | 20 · Mixed: 19 |
| Overall conclusion | **inconclusive** — positive results undermined by data snooping, ex-post rule selection, and understated costs |
| Stock markets specifically (early literature) | technical rules worked in FX/futures, **not in stocks** |

---

## Part B — Human psychology: verified success rates

### B1. The famous number — and its collapse
**Bollen, Mao & Zeng (2011):** Twitter "calm" mood → DJIA direction, **87.6% accuracy** claimed.

| Fact | Verified detail |
|---|---|
| Training window | ~8 months of 2008 only |
| Test window for the 87.6% | **~15 trading days** (Dec 1–19, 2008) |
| Mood lexicon | proprietary, never released |
| Independent replication (Lachanski & Pav 2017) | effect exists only in the original subsample; **vanishes when the sample is extended** ("consistent with data snooping"); **no out-of-sample predictive power** |
| Real-world test | Derwent Capital Markets hedge fund, built on this strategy, **closed in early 2012** |

### B2. What sentiment actually delivers
**Greyling & Rossouw (2025, CEPR/VoxEU; ~3 million tweets, 8 markets):**

| Result | Number |
|---|---|
| Directional accuracy, all 8 markets (FR, DE, JP, ES, UK, US, IN, PL) | **>50% in all** — barely above chance |
| US S&P 500 | **>55%** accuracy (recall up to 92%, likely class-imbalance inflated) |

**From the first research round (verified 3-0):** overnight/non-market-hours Twitter sentiment predicts next-day S&P 500 returns at **~6 basis points per standard deviation** (Federal Reserve research) — real, tradable-ish, but tiny.

### B3. What could NOT be verified this round (honesty section)
For these human-psychology channels, **no quantified claim survived adversarial verification** in this pass — not because they don't matter, but because clean peer-reviewed percentages were not confirmed:

- VIX / AAII investor sentiment indices as directional predictors
- Economic Policy Uncertainty (government policy) index → return effects
- War / geopolitical event-study percentages
- FOMC / CPI announcement-day effects
- Herding, loss aversion, overreaction — quantified return effects
- **Any direct head-to-head ML study of sentiment features vs technical features** — the exact comparison your hypothesis needs remains an open research question

So the strongest honest statement is: psychology-based inputs are standard in AI systems and add measurable but modest accuracy; the literature has **not** established that they beat technical inputs by X%.

---

## The comparison table

| Parameter | Folklore number | Verified number | Beats a coin flip? | Profitable after costs? |
|---|---|---|---|---|
| Head & Shoulders | "80%+ success" | 5–7%/yr hedged excess; standalone not profitable | Informative | No (S&P 500) |
| Double Bottom | "80%+ success" | NOT significant on NYSE/AMEX (LMW 2000) | Weak | Unproven |
| Pennants/Flags | "~50% fail" | Not covered by peer-reviewed tests | Unknown | Unproven |
| Golden cross / MA | high win rates | **53–54% vs 49%** win rate | Barely | Vanishes after corrections |
| MACD alone | popular | **37–68%** win rate, weak Sharpe | Sometimes | No benchmark |
| MACD + RSI | — | 78–86% win rate (preprint, no costs, no benchmark) | In-sample yes | Unproven |
| Twitter mood (Bollen) | **87.6%** | failed replication; 0 out-of-sample | No | Fund closed |
| Social sentiment (realistic) | — | **50–55%** directional accuracy | Barely | Marginal |
| Overnight news/social sentiment | — | ~6bp per SD next-day | Yes, tiny | Marginal |
| Policy/war/FOMC/VIX effects | many claims | not verified this pass | — | — |

## What this means for an AI trading system

The practical synthesis — consistent with both research rounds:

1. Use chart/technical signals as **features, not rules** — they carry statistical information (LMW 2000) even though none works as a stand-alone strategy.
2. Use human-psychology data (news sentiment, social media, macro announcements) as **additional features** — they add real information, especially overnight sentiment, but expect percentage points, not 87.6%.
3. Expect **50–55% directional accuracy** from a good model. The Gu–Kelly–Xiu benchmark shows the edge comes from *combining* many weak signals nonlinearly (Sharpe 1.35 vs 0.61) — not from any single parameter, chart or psychological.
4. Distrust any single number above ~60% accuracy without out-of-sample, cost-adjusted, replicated evidence. Both camps' famous numbers failed that test.

*Not investment advice. I'm not a financial advisor — these are descriptions of published measurements, and historical edges decay after publication.*

## Key sources

1. Lo, Mamaysky & Wang (2000), *Journal of Finance* — https://web.mit.edu/wangj/www/pap/LoMamayskyWang00.pdf
2. Savin, Weller & Zvingelis (2007), *Journal of Financial Econometrics* — https://academic.oup.com/jfec/article-abstract/5/2/243/785044
3. Park & Irwin (2007), *Journal of Economic Surveys* — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x
4. Brock, Lakonishok & LeBaron (1992), *Journal of Finance* — https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1992.tb04681.x
5. Sullivan, Timmermann & White (1999), *Journal of Finance* — https://ideas.repec.org/a/bla/jfinan/v54y1999i5p1647-1691.html
6. Chio (2022), MACD/RSI backtest, arXiv — https://arxiv.org/pdf/2206.12282
7. Bollen, Mao & Zeng (2011) — https://arxiv.org/abs/1010.3003
8. Lachanski & Pav (2017), *Econ Journal Watch* (failed replication) — https://econjwatch.org/articles/shy-of-the-character-limit-twitter-mood-predicts-the-stock-market-revisited
9. Greyling & Rossouw (2025), CEPR/VoxEU — https://cepr.org/voxeu/columns/twitter-sentiment-and-stock-market-movements-predictive-power-social-media
