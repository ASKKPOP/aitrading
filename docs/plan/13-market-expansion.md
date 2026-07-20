# Plan 13 — Market Expansion (외환 / 선물 / A주 / 옵션)

**Date:** 2026-07-19
**Trigger:** The market dropdown ships four `개발 중` entries and two `(테스트)` entries. Placeholder labels should not be in a user-facing product — either the market is real, or it is not offered.
**Status:** Draft — awaiting scope confirmation.

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
| 옵션 options | Yahoo v7 options chain | ❌ `Invalid Crumb` — needs cookie+crumb handshake |

Caveat: Yahoo's endpoints are **unofficial**. No SLA, rate-limited, ToS grey area. Acceptable for a
simulated ledger; must be replaced before any of these route to live execution.

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

New migration `0027_market_instrument_metadata`:
- `positions`: `+ currency TEXT NOT NULL DEFAULT 'USD'`, `+ contract_multiplier REAL NOT NULL DEFAULT 1.0`
- `signals`: same two columns
- Options only (phase 3): `+ expiry DATE`, `+ strike REAL`, `+ right TEXT` (`C`/`P`)

Then thread `contract_multiplier` through `risk_engine.py:299,311` and `backtest.py:349`.

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

---

## 5. Open decisions (need Henry)

1. **Options — in or out?** It is roughly as much work as phases 2–4 combined, and it is the one
   market with no verified free data source. Recommendation: ship 1–4, and **remove the 옵션 entry
   from the dropdown** rather than leave a `개발 중` label sitting there.
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
