# Swing Signal Stack

> A blueprint for finding 3–5 day (extendable to ~2 weeks) buy/sell points in US stocks and crypto
> by combining crowd psychology, the macro tide, changes in a company's fundamental story, and
> what informed money is doing.
>
> ⚠️ Research framework, not financial advice. See the disclaimer at the end.

---

## 1. Core rule: two axes must agree

Every reliable signal needs agreement between two **independent** axes:

| Axis | What it contains |
|---|---|
| **Quantitative** | price, volume, technicals (RSI, trend structure, relative strength) |
| **Qualitative** | sentiment, news, fundamentals/expectations, crowd psychology |

- Sentiment alone is noisy and manipulable.
- Price alone tells you *what* happened, not *why*.
- **When they agree → act. When they conflict → WAIT** on *that ticker, at that moment*.

### The agreement matrix

| | Sentiment bearish | Sentiment bullish |
|---|---|---|
| **Price bullish** | WAIT — price firm, crowd fearful → watch for contrarian entry | **BUY zone** |
| **Price bearish** | **SELL / avoid** | WAIT — crowd euphoric, price weak → possible trap / top |

### What "WAIT" actually means

- It applies **per ticker, per moment** — across a 10–20 name watchlist, some names agree on most days.
- Conflict is temporary: write the **resolving condition** ("price reclaims the 5-day high on volume"),
  set an alert, and do nothing until it fires. That is active waiting.
- Being flat is a position — and the retail trader's only structural edge (no one forces you to be invested).
- If the system says WAIT on everything for two weeks, the regime is choppy and cash was the right trade.

---

## 2. The pipeline

```
COLLECT (6 feeds)          SCORE (5 processors)       COMBINE            DECIDE
─────────────────          ────────────────────       ───────            ──────
Social crawl ─────┐
News feeds ───────┼──────► Sentiment score (w=0.25) ─┐
                  └──────► Macro regime  (w=0.20) ───┤
Macro calendar ──────────► Macro regime               │
Earnings & catalysts ────► Thesis score  (w=0.20) ───┼──► Composite ──► ≥ +40  BUY
Filings (13F/insider) ───► Smart-money   (w=0.15) ───┤    (−100…+100)   −40…+40 WAIT
Price & volume ──────────► Technical     (w=0.20) ───┘        │          ≤ −40  SELL
                                                              ▼
                                                         Risk gate (veto)
                                                    event blackout · sizing
```

Each processor outputs a score from **−100 (max bearish) to +100 (max bullish)**.
Composite = weighted sum. Weights and thresholds are **starting points to calibrate by backtesting**;
the structure (independent scores → one composite → a veto gate) is the part that matters.

### The six feeds

| # | Feed | Contents | Notes |
|---|---|---|---|
| 1 | **Social crawl** | Reddit (r/stocks, r/wallstreetbets), X/FinTwit, StockTwits, YouTube | mentions/hr vs baseline, bullish/bearish ratio |
| 2 | **News feeds** | headlines, geopolitics (tariffs, export controls, elections, conflicts) | feeds sentiment *and* macro |
| 3 | **Macro calendar** | CPI, FOMC, PCE, jobs, yields | event blackout rule |
| 4 | **Earnings & catalysts** | EPS/revenue surprise, guidance, estimate revisions, product events | the "future of the company" feed |
| 5 | **Filings** | 13F, insider Form 4, US congress disclosures | up to 45-day lag |
| 6 | **Price & volume** | OHLCV, options flow | the confirmation gate |

> TikTok / Instagram / Facebook have no practical public APIs for this — treat them as manual scouting, not pipeline feeds.

---

## 3. The four pillars

### Pillar 4 — Fundamental catalysts (the engine)

Great traders trade a company's **future** — but on a swing horizon "future" only moves price when
**expectations change**: an earnings surprise, raised/cut guidance, analyst estimate revisions, a product
event (launch, new chip, contract). Everyone already knows NVIDIA is a great company — that is in the price.
The tradeable moment is when the market's view of the future *shifts*.

- **Measure:** EPS/revenue surprise % vs consensus · guidance direction · estimate-revision momentum · days to next catalyst
- **Role:** sets the watchlist and the direction; also sets the trade window (3–5 days normally, 1–2 weeks when the catalyst is dated further out)
- **Caveat:** "good company" ≠ buy signal. Story stocks (AI, space, EV) are where crowds overpay for exciting futures — the two-axis rule matters most here.

### Pillar 1 — Social & news sentiment (human factor)

- The signal is not the sentiment *level* — it's the **rate of change**: a mention surge with a tone flip usually leads price by hours to days.
- **Measure:** mentions/hour vs 7-day baseline · bullish/bearish ratio · headline impact score
- **Caveat:** sentiment lags fast moves, gets gamed by bots and pump rooms, and peaks at tops. Never trade it without the quant axis agreeing.

### Pillar 2 — Macro regime (the tide)

- Tech/growth stocks are long-duration assets: they move inversely to real yields and with liquidity.
- **Measure:** 10Y yield direction · DXY · VIX · Fed-speak tone · event calendar (CPI, FOMC, PCE, jobs, big-tech earnings)
- **Rule:** no fresh swing position < 24h before a binary macro event unless the trade IS the event.
- **Caveat:** geopolitical headlines hit tech supply chains fastest and override technicals.

### Pillar 3 — Smart-money tracking

- Three tiers: institutional 13F (Buffett, Burry, Druckenmiller…), insider Form 4 buys, congress disclosures.
- Strongest signal = **cluster agreement** (several independent actors accumulating the same name in the same quarter).
- **Use for:** the watchlist (which tickers), **not** timing (when).
- **Caveat:** 13F and congress data lag up to 45 days — the position may already be exited.

---

## 4. Quantifying crowd psychology

You don't read emotions — you measure their proxies.

| Emotion | Measurable proxy | Reading |
|---|---|---|
| **Fear / capitulation** | Fear & Greed extreme low · VIX spike · put/call surge · high-volume flush | **BUY setup** — contrarian entry once selling volume exhausts |
| **Shock** | sharp negative sentiment spike + volume surge on sudden news | **CUT RISK** — reduce size first, analyze second |
| **Anticipation** | pre-event mention volume climbing · options IV rising into a known catalyst | **EARLY ENTRY** — small size, before the confirming headline |
| **Euphoria** | overbought RSI + social blow-off + parabolic price + "can't lose" tone | **SELL / TRIM** — tops form when everyone bullish is already in |

---

## 5. Scoring — worked example (invented numbers)

| Component | Weight | Score | Contribution |
|---|---|---|---|
| Sentiment | 0.25 | +62 | 15.5 |
| Macro regime | 0.20 | +35 | 7.0 |
| Thesis (fundamentals) | 0.20 | +55 | 11.0 |
| Smart money | 0.15 | +20 | 3.0 |
| Technical confirm | 0.20 | +48 | 9.6 |
| **Composite** | | | **+46.1 → BUY candidate** |

All five positive and technicals confirm → two-axis rule satisfied. The risk gate still checks:
no binary event inside the window, position sized to a fixed max loss.

---

## 6. The 3–5 day playbook

```
D−2        D0               D+2         D+5              D+10 ──── D+14
DETECT     CONFIRM+ENTER    MANAGE      EXIT             EXTENSION ZONE
mention    composite ≥ +40  trail stop  target / stop /  only with a DATED catalyst
surge,     AND technical    watch for   euphoria — or    inside the window,
revision,  trigger fires    shock /     default time     decided at ENTRY
whale                       tone flip   stop
cluster
```

- **Time stop is the most ignored rule.** No follow-through and no dated catalyst by D+5 = failed thesis → exit.
- The 1–2 week extension exists for catalyst-driven theses (feed 4). It must be decided at entry with the catalyst date written down — "hold and hope" is not an extension.

### Trigger table

| Signal | Trigger (all must hold) | Exit / invalidation |
|---|---|---|
| BUY · fear reversal | extreme fear + selling volume drying up + first positive sentiment turn + price reclaims a short-term level | stop below the flush low; exit on target or time stop |
| BUY · anticipation | rising pre-catalyst buzz + smart-money presence + uptrend intact; enter small *before* the headline | exit into the event spike ("sell the news"), or if buzz fades pre-event |
| BUY · expectations shift | earnings beat **with raised guidance** (or a wave of upward revisions) + first pullback holds + volume confirms | post-earnings drift favors 1–2 weeks; invalidated on a close below the earnings-day low |
| BUY · macro tailwind | dovish macro surprise + tech leading the tape + relative strength on volume | invalidated if yields reverse within 2 sessions |
| SELL · euphoria top | overbought RSI + social blow-off + gap-up on no news | trim into strength; full exit on first high-volume red day |
| SELL · shock / broken thesis | sudden negative headline, guidance cut, or sentiment spike down + volume surge | cut size immediately; re-evaluate flat, never while holding |
| WAIT · conflict | any disagreement between quant and sentiment axes | write the resolving condition, set an alert, do nothing until it fires |

---

## 7. Building feed 4 (fundamentals) — yes, it's crawlable

It is the **easiest** feed to automate: mostly structured, official, free data.

| What you need | Source | How to collect |
|---|---|---|
| **Earnings dates** | Finnhub / Alpha Vantage earnings-calendar API · Nasdaq & Yahoo calendars | free API, daily cron — flag watchlist names reporting in the next 14 days |
| **Surprise vs consensus** | Finnhub / Alpha Vantage earnings endpoints (actual vs estimate EPS) | compute surprise % the morning after each report |
| **Guidance & events** | SEC EDGAR 8-K filings & press releases (official, free, RSS + full-text search) | poll per ticker; LLM classifies "guidance raised / kept / cut" → score |
| **Estimate revisions** | yfinance analyst data, Finnhub estimates (free, rough) · Zacks / paid feeds (proper) | weekly pull; direction of change matters more than level |
| **Product catalysts** | company IR pages + newsroom RSS · news feed filtered per ticker | IR pages are public and stable; LLM tags catalyst / noise |

**Minimum viable script (daily):**

```
pull earnings calendar
→ mark watchlist names reporting soon
→ after each report: fetch actual-vs-estimate + the 8-K
→ LLM scores guidance direction
→ thesis score updates
```

---

## 8. Crypto adaptation — same stack, three feeds swapped

Crypto is **more** psychology-driven than stocks (no earnings anchor). The two-axis rule, psychology
table, macro score, and risk gate apply unchanged. Three feeds get replaced — one swap is a strict upgrade.

| Stock feed | Crypto replacement | Sources |
|---|---|---|
| Earnings & catalysts | **Token catalyst calendar:** unlock schedules (dated sell pressure), upgrades & halvings, ETF/listing decisions, protocol fees & TVL (closest thing to revenue). Regulatory headlines = the "geopolitics" of crypto. | Tokenomist/TokenUnlocks, DefiLlama, Token Terminal, CoinGecko events |
| Filings (13F, 45-day lag) | **On-chain whale tracking — real-time:** whale wallet moves, exchange inflows (= preparing to sell) / outflows (= accumulation), smart-money labels | Glassnode, CryptoQuant, Nansen, whale-alert feeds |
| Options flow | **Perp derivatives:** funding rate (spike = euphoria), open interest, liquidation cascades (= capitulation) | Coinglass, exchange APIs via CCXT |
| Fear & Greed (CNN) | Crypto Fear & Greed Index — same contrarian reading | alternative.me |
| Social / news / macro | Unchanged; add crypto Twitter, Telegram, Discord. BTC/alts trade like high-beta tech (with liquidity, against real yields & DXY) — same CPI/FOMC blackout | same sources + CoinGecko API |

**Rules that tighten for crypto:** 24/7 market → time stop in clock hours (e.g. 120h), shocks land on
thin-liquidity weekends; volatility several times higher → ≤1% sizing matters more; manipulation
(pump groups, wash-traded volume, botted sentiment) far worse → never trade sentiment without quant
confirmation; risk of total loss is real.

---

## 9. Resource directory

**Fundamentals · earnings & estimates**
- SEC EDGAR — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany (8-K, 10-Q; free, RSS + full-text search)
- Finnhub — https://finnhub.io · Alpha Vantage — https://www.alphavantage.co (earnings calendar, actual-vs-estimate, estimates)
- yfinance (Python) — analyst targets & estimates, rough but free
- Zacks — https://www.zacks.com (estimate-revision data, freemium)
- Company IR pages + earnings-call transcripts — primary source for guidance tone

**Sentiment · social & news**
- FinBERT — https://github.com/ProsusAI/finBERT (finance-tuned sentiment model)
- FinGPT — https://github.com/AI4Finance-Foundation/FinGPT (financial LLM framework)
- Tradestie — https://tradestie.com/tools/reddit-sentiment/ (free Reddit/WSB sentiment + API)
- StockTwits — https://stocktwits.com · Apify StockTwits scraper — https://apify.com/maximedupre/stocktwits-scraper
- VADER (Python) — quick lexicon sentiment; weaker than FinBERT on finance text

**Macro · calendar & regime**
- TradingView — https://www.tradingview.com/economic-calendar/ · Investing.com — https://www.investing.com/economic-calendar
- FRED — https://fred.stlouisfed.org (yields, spreads, liquidity, API)
- CME FedWatch — https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html
- CNN Fear & Greed — https://edition.cnn.com/markets/fear-and-greed

**Smart money · trader tracking**
- Dataroma — https://www.dataroma.com (free superinvestor 13F portfolios)
- WhaleWisdom — https://whalewisdom.com (13F screening & backtests)
- Quiver Quantitative — https://www.quiverquant.com (congress trades, insider buys, alt-data)
- OpenInsider — http://openinsider.com (Form 4 insider-buy clusters)

**Price data & APIs**
- yfinance (Python) · Finnhub — https://finnhub.io · Alpha Vantage — https://www.alphavantage.co · Polygon.io — https://polygon.io

**Crypto**
- CoinGecko API — https://www.coingecko.com · Coinglass — https://www.coinglass.com · CCXT — https://github.com/ccxt/ccxt
- Glassnode — https://glassnode.com · CryptoQuant — https://cryptoquant.com · Nansen — https://www.nansen.ai
- DefiLlama — https://defillama.com · Token Terminal — https://tokenterminal.com · TokenUnlocks — https://token.unlocks.app
- Crypto Fear & Greed — https://alternative.me/crypto/fear-and-greed-index/

**Build & backtest**
- OpenBB — https://github.com/OpenBB-finance/OpenBB (open-source research terminal)
- vectorbt — https://github.com/polakowo/vectorbt · backtrader — https://github.com/mementum/backtrader
- Qlib — https://github.com/microsoft/qlib · FinRL — https://github.com/AI4Finance-Foundation/FinRL
- awesome-systematic-trading — https://github.com/wangzhe3224/awesome-systematic-trading

---

## 10. The minimum loop (manual, < 1 hour/day)

1. **Build the watchlist weekly (Pillars 3 + 4).** Scan Dataroma / Quiver / OpenInsider for cluster buys; add names with upward estimate revisions. 10–20 tickers max.
2. **Know every catalyst date (Pillar 4).** Next earnings date, next product event per name → decides the trade window (3–5 days vs 1–2 weeks) and the blackout rule.
3. **Score the macro regime each morning (Pillar 2).** 10Y direction, VIX, DXY, today's calendar → one number, −100…+100. No fresh entries within 24h of a binary event.
4. **Scan sentiment per watchlist name (Pillar 1).** Mention surge vs baseline? Tone flip? Fear/greed extreme? Score it.
5. **Demand technical confirmation.** Composite ≥ +40 means nothing until price confirms — level reclaimed, relative strength, volume behind the move.
6. **Write the exit before the entry.** Stop, target, and time stop (D+5, or catalyst date + 1–2 days), on paper, before the order.
7. **Size to survive.** Risk a fixed small fraction (≤1% of account) per trade. Signal quality picks direction; sizing decides survival.
8. **Log every trade, backtest every rule.** The weights above are guesses until your own data (vectorbt / backtrader) says otherwise.

Automate the step that hurts most first, one at a time.

---

## Disclaimer

⚠️ **Research aid, not financial advice.** Signals are probabilistic and can be wrong. Sentiment
indicators lag, are noisy, and are manipulable (bots, pump rooms, fake news). 13F and congress data
arrive with up to a 45-day delay. Stock and crypto trading carry risk of substantial or total loss.
Use hard stop-losses, position limits, and a max-drawdown circuit breaker — final decisions and
outcomes are your own responsibility.
