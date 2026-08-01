> **2026-08-01 — China A-shares removed.** Per owner decision, the `a-stock`
> market (phase 4 below) has been removed from the platform entirely — market
> registry, symbols, prices, research, docs and UI. The phase notes below are
> retained as history only.

# Plan 13 — Market Expansion (외환 / 선물 / A주 / 옵션)

**Date:** 2026-07-19
**Trigger:** The market dropdown ships four `개발 중` entries and two `(테스트)` entries. Placeholder labels should not be in a user-facing product — either the market is real, or it is not offered.
**Status:** Decided 2026-07-19 — building Phase 0+1+2 now.

**Decisions (Henry):**
1. **Options: build it**, as phase 5 (last). The 옵션 entry stays in the dropdown.
2. **Currency: native + USD aggregates.** Positions store their native currency; convert to USD
   only for portfolio totals and leaderboards.
3. **Delivery: Phase 0+1+2 in one pass** — bug fix, registry refactor, and forex enabled
   end-to-end, reviewed together.

---

## 1. Why this is not a one-line change

`supported: false` in `appShared.tsx` is a **label**, not a feature gate. Behind it there is no backend
support of any kind for `forex`, `futures`, `a-stock`, or `options`.

### 1.1 Five allowlists have drifted apart

| Constant | File | Members |
|---|---|---|
| `SUPPORTED_MARKETS` | `routes_shared.py:62` | us-stock, crypto, polymarket |
| `VALID_MARKETS` | `automation.py:38` | crypto, us-stock |
| `VALID_RUN_MARKETS` | `trading_runs.py:42` | crypto, us-stock |
| `_SUPPORTED_PRICE_MARKETS` | `tasks.py:23` | crypto, polymarket, us-stock |
| `MARKETS` (frontend) | `appShared.tsx:290` | all 8 |

Plus two inline literal tuples that bypass the shared helpers entirely
(`routes_analysis.py:201,242`, `consult.py:301` — the latter *silently coerces* an unknown market to `crypto`).

### 1.2 Three structural blockers

1. **Schema cannot represent the instruments.** `positions` (`database.py:842`) has
   `quantity`, `entry_price`, `current_price`, `market`. There is **no `currency`, no
   `contract_multiplier`, no `expiry` / `strike` / `right`**. Options and futures are unrepresentable.
   The only `currency` column in the entire schema is on `stock_analysis_snapshots`, hardcoded `'USD'`.
2. **PnL math has no multiplier.** `risk_engine.py:299` — `pnl = (price - book["avg"]) * closed`.
   For ES futures ($50/point) that is wrong by 50×; for equity options (×100) by 100×.
   `backtest.py:349` repeats the same naive form.
3. **Session calendar fails open.** `is_market_open()` (`routes_shared.py:498`) returns `True`
   for any unrecognised market. Forex (24/5, Sunday 17:00 ET open) and futures (near-24h with a
   daily break) would be treated as always-open, and the NYSE 09:30–16:00 window is duplicated
   in the frontend at `appShared.tsx:305`.

### 1.3 Live bug, independent of this work

`BacktestPage.tsx:404` and `ResearchExportsPage.tsx:111` render all 8 markets **without**
`disabled={!m.supported}`. Users can select 외환 today and get a 400. The discussion composer
(`appCommunityPages.tsx:743`) and Challenge/TeamMissions do guard correctly.

---

## 2. Data sources — verified 2026-07-19

Contrary to first assumption, three of the four are **not** blocked on paid feeds.

| Market | Provider | Status |
|---|---|---|
| 외환 forex | Yahoo v8 chart `EURUSD=X` | ✅ verified live, keyless |
| 선물 futures | Yahoo v8 chart `ES=F` → CME, USD | ✅ verified live, keyless |
| A주 a-stock | Yahoo v8 `600519.SS` → CNY/Shanghai; Sina `hq.sinajs.cn` | ✅ both verified live |
| 옵션 options | Yahoo v7 options chain | ✅ **works — see 2.0 below** (was ❌ `Invalid Crumb`) |

### 2.0 CORRECTED 2026-07-20 — the options chain is reachable, keylessly

The `Invalid Crumb` above was read as a blocker. It is not; it is the documented
handshake, and implementing it takes about thirty lines:

1. `GET https://fc.yahoo.com` — 404s, but issues an `A3` session cookie.
2. `GET /v1/test/getcrumb` with that cookie — returns a short opaque token.
3. `GET /v7/finance/options/{underlying}?crumb=…` with cookie + crumb — 200.

Measured from this machine 2026-07-20: AAPL returned 23 expirations and 53 calls /
48 puts with strike, bid, ask, open interest and IV. Live through the app at
`/api/markets/options/AAPL`.

**Consequences:**
- Phase 5 is **not** blocked on a paid feed, and the Alpha Vantage premium
  recommendation in §2.1 no longer has options as its justification. The
  remaining arguments for it (keyed forex, lifting the 25/day news cap) stand
  on their own.
- The crumb is session-scoped and cached for 30 minutes
  (`price_fetcher._yahoo_crumb_pair`); a 401/403 forces one re-handshake and
  retry. It is unofficial and can break — the same standing caveat as the v8
  chart endpoint.
- Out of hours every strike quotes bid 0 / ask 0, so the mark falls back from
  mid to last trade. Marking to a zero mid would wipe an option position to
  nothing overnight.

### 2.1 CORRECTED 2026-07-20 — it was never throttling, it was the User-Agent

**The section below (2.2) is wrong and is kept only as a record of the mistake.**

Measured from the production host on 2026-07-20, the deciding variable is the exact
User-Agent string, not request volume:

| User-Agent | Result |
|---|---|
| `Mozilla/5.0` | **200 — 12/12 with no delay between requests** |
| Full spoofed Chrome UA | **429 — 6/6, on the very first request** |
| `requests` default UA | 429, always |

A detailed browser UA with no matching TLS fingerprint or headers reads as a scraper to
Yahoo's edge; the bare `Mozilla/5.0` token reads as a generic HTTP client and is served
normally. My original "throttled at ~1 req/min" reading came from A/B-ing nothing — I
picked a realistic-looking Chrome UA, saw 429s, and attributed them to rate limiting.

Consequences, all corrected in the follow-up commit:
- `_YAHOO_USER_AGENT` is now `"Mozilla/5.0"`, with a comment warning not to "improve" it.
- `forex.server_priced` is back to `True` — it was set `False` purely to work around a
  problem that did not exist.
- `retry_on_rate_limit=False` for Yahoo is **kept**. Retrying a genuine 429 is still wrong,
  and the guard costs nothing.
- The Alpha Vantage premium recommendation stands for **options** (phase 5), which still has
  no free chain endpoint — but it is no longer needed for forex.

### 2.2 SUPERSEDED — original (incorrect) reading, 2026-07-19

Yahoo's chart endpoint is **far more aggressively rate-limited than it first appeared.** Measured
from this machine after the provider was wired up:

- The first handful of requests succeed, returning correct data (EURUSD → 1.1447).
- After that, **a second request within the same minute returns HTTP 429**, and the penalty
  persists for minutes.
- Requests without a browser `User-Agent` are 429'd immediately, always.

At roughly one request per minute, refreshing 30 forex pairs would take 30 minutes per cycle.
**This is not a viable primary price source for a portfolio.** Two mitigations already landed:

1. `forex.server_priced = False` — forex is off the synchronous trade path, priced only by the
   background refresher (same treatment as Alpha Vantage).
2. `retry_on_rate_limit=False` for the Yahoo provider — retrying a 429 tripled the offending
   load and dug the hole deeper. It now goes straight to cooldown.

Caveat on the measurement: this machine's IP was likely already penalized by the burst of probe
requests during development. Production may see a different limit — **it must be measured there
before forex is promoted past `(테스트)`.**

Alpha Vantage is not an escape hatch on the free tier: **25 requests/day**, already consumed by
news sentiment (see `docs/plan/08-api-keys-reference.md`).

**Recommendation:** Alpha Vantage premium (~$50/mo) is the highest-leverage purchase available.
One key would (a) give forex a keyed, SLA'd intraday feed, (b) unlock the options chain needed
for phase 5, and (c) lift the 25/day cap currently forcing news sentiment to a 6-hour cadence.
It is already the integrated `us-stock` provider, so no new adapter is required.

Yahoo's endpoints are also **unofficial** — no SLA, ToS grey area. Acceptable for a simulated
ledger; must be replaced before any of these route to live execution.

Note: `ALPHA_VANTAGE_API_KEY=demo` locally, so even `us-stock` pricing returns `None` on dev machines.

---

## 3. Target architecture

### 3.1 One market registry

Collapse all five allowlists into a single declarative registry (new `service/server/markets.py`):

```python
@dataclass(frozen=True)
class MarketSpec:
    value: str                  # 'forex'
    currency: str               # quote currency for PnL
    contract_multiplier: float  # 1.0 equity/fx, 50.0 ES, 100.0 equity options
    session: str                # '24x7' | 'nyse' | '24x5' | 'sse' | 'cme'
    price_provider: str         # dispatch key into price_fetcher
    supports_short: bool
    tradeable: bool             # can carry positions / runs
    symbol_pattern: re.Pattern
    price_decimals: int         # fx needs 5, not 2
```

Every existing allowlist becomes a derived view (`{m.value for m in REGISTRY if m.tradeable}`).
This is the single highest-leverage change and must land first.

### 3.2 Provider dispatch table

Replace the if/elif chain at `price_fetcher.py:786-801` with a lookup keyed on
`MarketSpec.price_provider`. Add one `_get_yahoo_chart_price(symbol, executed_at)` helper that
serves forex, futures, and a-stock — it reuses the existing `_request_json_with_retry` and
provider-cooldown infrastructure.

### 3.3 Session calendars

Replace the two duplicated NYSE windows with a `session_open(spec, at)` function covering
`24x7`, `nyse`, `24x5` (fx), `cme`, `sse`. Frontend consumes a backend-served calendar rather
than reimplementing it.

### 3.4 Schema

**Deferred to phase 3 — deliberately not built in phase 1.** The original plan put a
`0027_market_instrument_metadata` migration here (`positions`/`signals` gaining `currency`
and `contract_multiplier`). Forex does not need either: its multiplier is 1.0, and its
settlement currency is a pure function of the pair (`markets.position_currency`). Adding
columns that nothing writes and nothing reads is speculative, so they land with futures,
which is the first market that actually needs a non-1.0 multiplier:

- phase 3: `positions` / `signals` `+ contract_multiplier`, then thread it through
  `risk_engine.py:299,311` and `backtest.py:349`.
- phase 4: `+ currency` (first non-USD market).
- phase 5: `+ expiry`, `+ strike`, `+ right` for options.

---

## 4. Phasing

| Phase | Scope | Risk |
|---|---|---|
| **0** | Fix the `disabled` guard on BacktestPage + ResearchExportsPage. Standalone bug fix. | trivial |
| **1** | Market registry + provider dispatch + session calendars + schema migration. **No new market enabled yet.** All existing tests must stay green — this is a pure refactor. | medium — touches 5 allowlists |
| **2** | Enable **forex**. Yahoo provider, 24/5 calendar, 5-decimal display, pair symbol format. Quote-currency PnL. | low once phase 1 lands |
| **3** | Enable **futures**. Contract multiplier table (ES/NQ/CL/GC), CME calendar. Resolve the naming collision with the existing `market_type='futures'` crypto-perp axis (`trading_runs.py:43`). | medium — naming collision |
| **4** | Enable **a-stock**. CNY currency, lot size 100, T+1 settlement, ±10% daily limit, SSE/SZSE calendar. Requires FX conversion for cross-market portfolio totals. | medium — first non-USD market |
| **5** | Enable **options**. Crumb handshake, chain browsing UI, strike/expiry/right schema, ×100 multiplier, assignment handling. | high — largest by far |

Phases 2–4 are independent of each other and can ship separately once phase 1 lands.

### 4.1 Phases 3–5 delivered 2026-07-20 — with two deviations from the plan above

All three markets are enabled: `futures`, `a-stock` and `options` are `tradeable`,
and every `개발 중` label is gone from `appShared.tsx`. Two things were built
differently from §3.4, and both are deliberate.

**Deviation 1 — the instrument-metadata columns were not added.**
§3.4 called for `positions`/`signals` to gain `contract_multiplier` (phase 3) and
`currency` (phase 4). A migration was written and then deleted. Both values are
**pure functions of `(market, symbol)`**, which are already columns on every row:
`markets.contract_multiplier('futures', 'ES')` is 50, `markets.position_currency`
already derived forex settlement currency this exact way before this work. Adding
denormalised columns meant threading them through ~8 insert sites for no
behavioural gain. The one argument for booking them at trade time — an exchange
respecifying a contract — is speculative, and the registry stays the single source
of truth.

Consequence to be aware of: if `FUTURES_MULTIPLIERS` is ever corrected, historical
P&L restates. That is the accepted trade. If a contract is genuinely respecified,
the fix is a symbol-with-vintage key, not a denormalised column.

**Deviation 2 — futures backtests are fully funded, not margined.**
`backtest.py` now multiplies every cash and P&L term through the contract
multiplier, so mark-to-market is correct. But a contract reserves its **whole
notional** rather than exchange initial margin, so the simulation under-states
leverage: a run holds fewer contracts than a real margin account would. That is
the safe direction for a backtest, but these are **not** margin-accurate results.
A margin model is separate work and was not built.

**Also resolved:** the `market_type` naming collision. `market_type` ('spot' |
'futures') is the crypto spot-vs-perpetual axis and predates the CME market;
`market='futures'` is now a market in its own right. Either makes a book
short-capable, expressed once as `trading_runs.is_futures_book()`. Without it a
CME run would carry `market_type='spot'` and could never open a short.

**Options is tradeable but not automatable.** A rule cannot express "roll to the
next expiry", so runs may not target an options contract even though a user can
trade one by hand. The chain picker (underlying → expiry → strike) lives in
`SymbolSelect`, because the booked symbol is an OCC contract nobody types.

---

## 5. Open decisions (need Henry)

1. ~~**Options — in or out?**~~ **Resolved 2026-07-19: build it** (Henry). Shipped
   2026-07-20; the "no verified free data source" premise was wrong, see §2.0.
2. **Currency display.** A-share is CNY, forex has a quote currency per pair. Do we convert
   everything to USD for portfolio totals, or show native currency per position and skip a
   combined total? Recommendation: store native, convert to USD for aggregates only.
3. **`(테스트)` on crypto / Polymarket.** These are already `supported: true` and functional.
   Dropping the label is a verification task, not an implementation task — separate from this plan.

---

## 6. Success criteria

- One registry; `grep -rn "'us-stock', 'crypto'"` returns no allowlist literals in backend.
- `pytest service/server/tests` green before and after phase 1 with zero behavior change.
- For each enabled market: create a signal → position opens → price refresh updates it →
  PnL matches a hand-computed value including multiplier → an automation run trades it.
- No `개발 중` string remains in `appShared.tsx`.
