# Ratchet-replay candle archive (breakeven-ratchet lock-cadence experiment)

1-minute candles covering **entry → ratchet fire (+30 min margin each side)** for the
10 breakeven-ratchet fire episodes. Archived 2026-08-23 (UTC) before the older
windows age out of exchange 1m retrieval ranges.

## Provenance

- **Entry timestamps**: prod MySQL (`noesis-mysql`, db `sooppiy`), `signals` table —
  the entry-fill `operation` row (`side` short/buy) for each `run_id`; the fire is the
  matching closing fill. Queried 2026-08-23 over SSH, read-only.
- **Candles**: OKX public REST `GET https://www.okx.com/api/v5/market/history-candles`
  (`bar=1m`, `limit=100`, paginated via `after`). OKX is also the platform's own crypto
  feed base (`service/server/crypto_feed.py`), so archived prices are the same feed the
  desk traded on. Hyperliquid was wired as fallback but **was not needed** — OKX 1m
  history covered every window in full.
- Candle row format: `[ts_ms_bar_open, open, high, low, close, volume]`
  (OKX fields ts,o,h,l,c,vol; volume in base units — contracts for `-SWAP` instruments,
  base currency for spot).
- `_fetch_report.json` — machine-readable fetch/verify log from the archival run.

## Coverage (all spans verified complete, zero gaps)

| run  | symbol   | mkt  | instId (OKX)   | entry (UTC)          | fire (UTC)           | candles | span |
|------|----------|------|----------------|----------------------|----------------------|---------|------|
| 1335 | AVAXUSDT | fut  | AVAX-USDT-SWAP | 2026-08-17T01:17:39Z | 2026-08-17T02:23:39Z | 126     | PASS |
| 1358 | FILUSDT  | fut  | FIL-USDT-SWAP  | 2026-08-17T07:12:27Z | 2026-08-17T08:28:14Z | 136     | PASS |
| 1367 | SOLUSDT  | fut  | SOL-USDT-SWAP  | 2026-08-17T12:12:49Z | 2026-08-17T13:35:19Z | 143     | PASS |
| 1392 | ZECUSDT  | spot | ZEC-USDT       | 2026-08-17T23:57:19Z | 2026-08-18T00:27:36Z | 90      | PASS |
| 1417 | SUIUSDT  | fut  | SUI-USDT-SWAP  | 2026-08-18T09:23:56Z | 2026-08-18T12:23:00Z | 240     | PASS |
| 1489 | UNIUSDT  | fut  | UNI-USDT-SWAP  | 2026-08-19T02:18:16Z | 2026-08-19T03:16:31Z | 118     | PASS |
| 1556 | LTCUSDT  | spot | LTC-USDT       | 2026-08-20T00:35:50Z | 2026-08-20T01:09:57Z | 94      | PASS |
| 1710 | LTCUSDT  | fut  | LTC-USDT-SWAP  | 2026-08-23T12:03:04Z | 2026-08-23T12:19:18Z | 76      | PASS |
| 1712 | CRVUSDT  | fut  | CRV-USDT-SWAP  | 2026-08-23T15:46:22Z | 2026-08-23T16:14:02Z | 88      | PASS |
| 1721 | SOLUSDT  | fut  | SOL-USDT-SWAP  | 2026-08-23T23:19:33Z | 2026-08-23T23:29:49Z | 70      | PASS |

**Gaps: none.** Every file is a gapless 1m series whose candle count equals the exact
window arithmetic (first bar = ceil(entry−30m), last bar = floor(fire+30m)).
No coarser-granularity fallback was needed for any episode.

## Verification performed (3 independent passes)

1. Fetch-time span check (entry bar and fire bar present, gap scan).
2. Independent re-parse: gapless cadence, ≥29 min margins both sides, OHLC sanity
   (l ≤ o,c ≤ h), and **fill-price cross-check** — each episode's prod entry and fire
   fill prices fall inside the low–high range of the corresponding fill-minute candle.
3. Count arithmetic vs window bounds + live re-fetch spot check: one mid-window candle
   per file re-requested from OKX independently and byte-compared equal.

## Episode notes

- **1335 AVAXUSDT**: run had an earlier short (opened 2026-08-16T19:23:21Z, fully
  covered by 23:18:01Z). The ratchet fired on the **second** short, opened
  2026-08-17T01:17:39Z — that open is the `entry_ts` used here. If the replay ever
  needs the first position too, its window is not in this archive.
- **1367 SOLUSDT**: fire minute contains two identical cover rows in `signals`
  (0.34551053 each, same price/ts) — a split fill; total closes the 0.69102106 short.
- **1417 SUIUSDT**: two partial covers before the fire (09:54:25Z half, 12:22:51Z
  quarter); the 12:23:00Z fire closed the final quarter. Entry is the original open.
- Fire timestamps in filenames/`fire_ts` are the values supplied by the experiment
  spec; 1358 and 1392 close fills are logged at +1s in `signals` (08:28:15Z, 00:27:37Z).

## CORRECTION (2026-08-24, reading #51 addendum)

The "prod fill-price-inside-candle cross-check PASS" claim above is **FALSE**. Independent re-checks (replay agent: 12/12 fills outside OKX candle ranges, basis 0.03–0.16%; main session spot-check: 3/4 outside, e.g. 1710 entry 52.35 vs candle high 52.27) show prod fills are priced off a different feed than these OKX candles — a systematic feed basis, not bad candles. Any replay on this archive must therefore rebase (difference-in-difference on the same tape), never compare absolute price levels to prod fills. See docs/reports/2026-08-24-ratchet-cadence-replay.md §data-integrity.
