"""Swing Signal Stack — last-month historical simulation (2026-07-30 .. 2026-08-30).

Experiment (stated before the data, per the owner's experimental-mindset rule):

  H1: BUY entries produced by the stack (two-axis agreement + composite >= +40
      + event blackout + playbook exits) have positive net expectancy over the
      window. Falsifier: net expectancy per trade <= 0. n < 5 -> inconclusive.
  H2: the two-axis WAIT rule adds value — the stack's expectancy per trade
      beats a quant-only control (technical >= +40 alone, same exits, no
      blackout, no agreement requirement). Falsifier: control expectancy per
      trade >= stack expectancy per trade.
  H3: the event-blackout veto fires at least once in a window that contains
      NFP / CPI / Jackson Hole / PCE. Falsifier: zero vetoes.

Data (all keyless, real history):
  - daily OHLCV: Yahoo v8 chart (stocks + SPY + ^VIX + ^TNX + DX-Y.NYB),
    OKX perp daily candles (crypto, BTC-USDT-SWAP style)
  - psychology proxy: CNN Fear & Greed history (stocks),
    alternative.me Fear & Greed history (crypto)

Named limitations:
  - thesis + smart_money feeds have no free historical source -> None
    (composite renormalizes; the doc's structure, not its exact weights,
    is what this tests)
  - sentiment is a MARKET-level psychology proxy, not per-ticker social flow
  - the macro event calendar is the approximate structural US schedule
    (first-Friday NFP, mid-month CPI, late-August Jackson Hole / PCE),
    not a fetched historical calendar
  - long-only; SELL signals close positions but never open shorts

Run from repo root:
  .venv/bin/python research/swing_stack_sim_20260830.py
Writes research/swing_stack_sim_result_20260830.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service" / "server"))
import swing_stack as ss  # noqa: E402

WINDOW_START = date(2026, 7, 30)
WINDOW_END = date(2026, 8, 30)
HISTORY_DAYS = 130  # baseline before the window (RSI/SMA/RS need ~30 bars)

US_STOCKS = ["NVDA", "TSLA", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "AMD", "PLTR", "COIN"]
CRYPTO = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

STARTING_EQUITY = 100_000.0
FEES_PER_SIDE = {"us_stock": 0.0002, "crypto": 0.0010}

# Approximate structural US macro schedule (binary events), UTC.
MACRO_EVENTS = [
    ("FOMC decision", datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)),
    ("NFP jobs report", datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc)),
    ("CPI", datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)),
    ("Jackson Hole (Fed chair)", datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)),
    ("PCE", datetime(2026, 8, 28, 12, 30, tzinfo=timezone.utc)),
]

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
FETCH_LOG: list[str] = []


def _get_json(url: str, params: dict | None = None, tries: int = 3) -> dict | None:
    for attempt in range(tries):
        try:
            resp = requests.get(url, params=params, headers=UA, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            FETCH_LOG.append(f"HTTP {resp.status_code} {url}")
        except Exception as exc:  # noqa: BLE001
            FETCH_LOG.append(f"{type(exc).__name__} {url}: {exc}")
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_yahoo_daily(ticker: str) -> list[dict]:
    data = _get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"interval": "1d", "range": "1y"},
    )
    if not data:
        return []
    try:
        result = data["chart"]["result"][0]
        stamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        FETCH_LOG.append(f"yahoo shape {ticker}")
        return []
    bars = []
    for i, ts in enumerate(stamps):
        close = (quote.get("close") or [])[i] if i < len(quote.get("close") or []) else None
        if ts is None or close is None:
            continue
        bars.append({
            "date": datetime.fromtimestamp(int(ts), tz=timezone.utc).date(),
            "ts": int(ts),
            "open": (quote.get("open") or [None] * len(stamps))[i] or close,
            "high": (quote.get("high") or [None] * len(stamps))[i] or close,
            "low": (quote.get("low") or [None] * len(stamps))[i] or close,
            "close": float(close),
            "volume": (quote.get("volume") or [None] * len(stamps))[i] or 0,
        })
    return bars


def fetch_okx_daily(symbol: str) -> list[dict]:
    data = _get_json(
        "https://www.okx.com/api/v5/market/candles",
        params={"instId": f"{symbol}-USDT-SWAP", "bar": "1Dutc", "limit": "300"},
    )
    rows = (data or {}).get("data") or []
    bars = []
    for row in reversed(rows):
        if len(row) < 6:
            continue
        ts_ms = int(row[0])
        bars.append({
            "date": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date(),
            "ts": ts_ms // 1000,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return bars


def fetch_cnn_fear_greed() -> dict[date, float]:
    data = _get_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
    out: dict[date, float] = {}
    for point in ((data or {}).get("fear_and_greed_historical") or {}).get("data") or []:
        try:
            d = datetime.fromtimestamp(float(point["x"]) / 1000, tz=timezone.utc).date()
            out[d] = float(point["y"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_alternative_fng() -> dict[date, float]:
    data = _get_json("https://api.alternative.me/fng/", params={"limit": "250", "format": "json"})
    out: dict[date, float] = {}
    for row in (data or {}).get("data") or []:
        try:
            d = datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc).date()
            out[d] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Score construction per (symbol, day)
# ---------------------------------------------------------------------------

def series_at(series: list[dict], day: date, back: int = 0) -> float | None:
    """Close `back` entries before the most recent bar dated <= day."""
    idx = None
    for i in range(len(series) - 1, -1, -1):
        if series[i]["date"] <= day:
            idx = i
            break
    if idx is None or idx - back < 0:
        return None
    return float(series[idx - back]["close"])


def fg_inputs(fg: dict[date, float], day: date) -> tuple[float | None, float | None]:
    today = None
    probe = day
    for _ in range(5):  # F&G skips weekends on the stock side
        if probe in fg:
            today = fg[probe]
            break
        probe -= timedelta(days=1)
    if today is None:
        return None, None
    prior = [fg[day - timedelta(days=k)] for k in range(1, 11) if day - timedelta(days=k) in fg]
    avg7 = statistics.mean(prior[:7]) if len(prior) >= 3 else None
    return today, avg7


def hours_to_next_event(entry_dt: datetime) -> float | None:
    future = [(ts - entry_dt).total_seconds() / 3600 for _, ts in MACRO_EVENTS if ts > entry_dt]
    return min(future) if future else None


def build_scores(
    bars_upto: list[dict],
    bench_upto: list[dict],
    macro_series: dict[str, list[dict]],
    fg: dict[date, float],
    day: date,
) -> dict[str, float | None]:
    fg_today, fg_avg = fg_inputs(fg, day)
    return {
        "technical": ss.technical_score(bars_upto, bench_upto),
        "macro": ss.macro_score(
            series_at(macro_series["vix"], day), series_at(macro_series["vix"], day, 5),
            series_at(macro_series["tnx"], day), series_at(macro_series["tnx"], day, 5),
            series_at(macro_series["dxy"], day), series_at(macro_series["dxy"], day, 5),
        ),
        "sentiment": ss.psych_sentiment_score(fg_today, fg_avg),
        "thesis": None,       # no free historical estimate-revision source
        "smart_money": None,  # 13F/Form4 history not reconstructable keyless
    }


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def entry_datetime(bar: dict, market: str) -> datetime:
    if market == "crypto":
        return datetime.combine(bar["date"], datetime.min.time(), tzinfo=timezone.utc)
    return datetime.combine(bar["date"], datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=13, minutes=30)


def run_arm(
    arm: str,
    universe: dict[str, dict],
    macro_series: dict[str, list[dict]],
) -> dict:
    """arm='stack' -> full pipeline; arm='control' -> technical>=+40 only."""
    equity = STARTING_EQUITY
    trades: list[dict] = []
    decision_counts: dict[str, int] = {}
    vetoes = 0

    for symbol, info in universe.items():
        bars = info["bars"]
        market = info["market"]
        bench = info["bench"]
        fg = info["fg"]
        fee = FEES_PER_SIDE[market]
        open_pos = None

        for i, bar in enumerate(bars):
            day = bar["date"]
            if day < WINDOW_START or day > WINDOW_END:
                continue
            upto = bars[: i + 1]
            bench_upto = [b for b in bench if b["date"] <= day]
            scores = build_scores(upto, bench_upto, macro_series, fg, day)

            # ---- manage an open position on THIS bar (entered earlier) ----
            if open_pos is not None and i > open_pos["entry_i"]:
                open_pos["bars_held"] += 1
                exit_price, reason = None, None
                if bar["open"] <= open_pos["stop"]:
                    exit_price, reason = bar["open"], "gap_stop"
                elif bar["low"] <= open_pos["stop"]:
                    exit_price, reason = open_pos["stop"], "stop"
                elif bar["high"] >= open_pos["target"]:
                    exit_price, reason = open_pos["target"], "target"
                else:
                    sig = ss.signal_exit_reason(scores) if arm == "stack" else None
                    if sig:
                        exit_price, reason = bar["close"], sig
                    elif ss.time_stop_hit(open_pos["bars_held"]):
                        exit_price, reason = bar["close"], "time_stop"
                if exit_price is not None:
                    qty = open_pos["qty"]
                    gross = (exit_price - open_pos["entry"]) * qty
                    fees = (open_pos["entry"] + exit_price) * qty * fee
                    net = gross - fees
                    equity += net
                    risk = (open_pos["entry"] - open_pos["stop"]) * qty
                    trades.append({
                        "symbol": symbol, "market": market,
                        "entry_date": str(open_pos["entry_date"]), "exit_date": str(day),
                        "entry": round(open_pos["entry"], 6), "exit": round(exit_price, 6),
                        "qty": round(qty, 6), "bars_held": open_pos["bars_held"],
                        "exit_reason": reason,
                        "gross_pnl": round(gross, 2), "fees": round(fees, 2),
                        "net_pnl": round(net, 2),
                        "r_multiple": round(net / risk, 3) if risk > 0 else None,
                        "entry_composite": open_pos["composite"],
                        "entry_axis": open_pos["axis"],
                    })
                    open_pos = None

            # ---- evaluate a fresh entry at this close (enter next open) ----
            if open_pos is not None or i + 1 >= len(bars):
                continue
            next_bar = bars[i + 1]
            if next_bar["date"] > WINDOW_END:
                continue
            if arm == "stack":
                verdict = ss.decide(scores, hours_to_next_event(entry_datetime(next_bar, market)))
                key = verdict["veto"] or verdict["action"]
                decision_counts[key] = decision_counts.get(key, 0) + 1
                if verdict["veto"] == "event_blackout":
                    vetoes += 1
                enter = verdict["action"] == "BUY"
            else:
                tech = scores.get("technical")
                enter = tech is not None and tech >= ss.BUY_THRESHOLD
                verdict = {"composite": scores.get("technical"), "axis": "control"}
            if not enter:
                continue
            stop = ss.initial_stop(upto)
            entry_price = float(next_bar["open"])
            if stop is None or stop >= entry_price:
                continue
            qty = ss.position_size(equity, entry_price, stop)
            if qty <= 0:
                continue
            open_pos = {
                "entry_i": i + 1, "entry": entry_price, "entry_date": next_bar["date"],
                "stop": stop, "target": ss.target_price(entry_price, stop),
                "qty": qty, "bars_held": 0,
                "composite": round(verdict["composite"], 2) if verdict["composite"] is not None else None,
                "axis": verdict["axis"],
            }

        if open_pos is not None:  # force-close at last bar of window
            last = [b for b in bars if b["date"] <= WINDOW_END][-1]
            qty = open_pos["qty"]
            gross = (last["close"] - open_pos["entry"]) * qty
            fees = (open_pos["entry"] + last["close"]) * qty * fee
            net = gross - fees
            equity += net
            risk = (open_pos["entry"] - open_pos["stop"]) * qty
            trades.append({
                "symbol": symbol, "market": market,
                "entry_date": str(open_pos["entry_date"]), "exit_date": str(last["date"]),
                "entry": round(open_pos["entry"], 6), "exit": round(last["close"], 6),
                "qty": round(qty, 6), "bars_held": open_pos["bars_held"],
                "exit_reason": "window_end",
                "gross_pnl": round(gross, 2), "fees": round(fees, 2),
                "net_pnl": round(net, 2),
                "r_multiple": round(net / risk, 3) if risk > 0 else None,
                "entry_composite": open_pos["composite"], "entry_axis": open_pos["axis"],
            })

    return {"trades": trades, "final_equity": round(equity, 2),
            "decision_counts": decision_counts, "blackout_vetoes": vetoes,
            "metrics": metrics(trades)}


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t["net_pnl"] for t in trades]
    rs = [t["r_multiple"] for t in trades if t["r_multiple"] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    out = {
        "n": len(trades),
        "win_rate": round(len(wins) / len(trades), 3),
        "net_pnl": round(sum(pnls), 2),
        "expectancy_usd": round(sum(pnls) / len(trades), 2),
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
        "avg_win": round(statistics.mean(wins), 2) if wins else None,
        "avg_loss": round(statistics.mean(losses), 2) if losses else None,
        "payoff": (
            round(statistics.mean(wins) / abs(statistics.mean(losses)), 3)
            if wins and losses and statistics.mean(losses) != 0 else None
        ),
    }
    # owner rule: never let one outlier stand as the result
    biggest = max(trades, key=lambda t: abs(t["net_pnl"]))
    rest = [t["net_pnl"] for t in trades if t is not biggest]
    out["largest_contributor"] = {"symbol": biggest["symbol"], "net_pnl": biggest["net_pnl"]}
    out["net_pnl_ex_largest"] = round(sum(rest), 2)
    out["expectancy_usd_ex_largest"] = round(sum(rest) / len(rest), 2) if rest else None
    return out


def main() -> None:
    print("fetching history ...", flush=True)
    stock_bars = {s: fetch_yahoo_daily(s) for s in US_STOCKS}
    spy = fetch_yahoo_daily("SPY")
    macro_series = {
        "vix": fetch_yahoo_daily("%5EVIX"),
        "tnx": fetch_yahoo_daily("%5ETNX"),
        "dxy": fetch_yahoo_daily("DX-Y.NYB"),
    }
    crypto_bars = {s: fetch_okx_daily(s) for s in CRYPTO}
    cnn_fg = fetch_cnn_fear_greed()
    alt_fg = fetch_alternative_fng()

    coverage = {
        "stocks": {s: len(b) for s, b in stock_bars.items()},
        "crypto": {s: len(b) for s, b in crypto_bars.items()},
        "spy": len(spy), "vix": len(macro_series["vix"]), "tnx": len(macro_series["tnx"]),
        "dxy": len(macro_series["dxy"]), "cnn_fg_days": len(cnn_fg), "alt_fg_days": len(alt_fg),
        "fetch_errors": FETCH_LOG[:40],
    }
    print(json.dumps(coverage, indent=2)[:1200], flush=True)

    universe: dict[str, dict] = {}
    for s, bars in stock_bars.items():
        if len(bars) >= 40:
            universe[s] = {"bars": bars, "market": "us_stock", "bench": spy, "fg": cnn_fg}
    btc = crypto_bars.get("BTC") or []
    for s, bars in crypto_bars.items():
        if len(bars) >= 40:
            universe[s] = {"bars": bars, "market": "crypto", "bench": btc, "fg": alt_fg}

    stack = run_arm("stack", universe, macro_series)
    control = run_arm("control", universe, macro_series)

    # H2 detail: control entries the stack did NOT take (the WAIT-filtered set)
    stack_keys = {(t["symbol"], t["entry_date"]) for t in stack["trades"]}
    filtered = [t for t in control["trades"] if (t["symbol"], t["entry_date"]) not in stack_keys]

    exp_stack = stack["metrics"].get("expectancy_r")
    exp_ctrl = control["metrics"].get("expectancy_r")
    n_stack = stack["metrics"].get("n", 0)
    result = {
        "generated_at": "2026-08-30",
        "window": [str(WINDOW_START), str(WINDOW_END)],
        "universe": {"us_stocks": US_STOCKS, "crypto": CRYPTO},
        "config": {
            "weights": ss.WEIGHTS, "buy_threshold": ss.BUY_THRESHOLD,
            "sell_threshold": ss.SELL_THRESHOLD, "risk_fraction": ss.DEFAULT_RISK_FRACTION,
            "target_r": ss.TARGET_R_MULTIPLE, "time_stop_bars": ss.TIME_STOP_BARS,
            "fees_per_side": FEES_PER_SIDE, "starting_equity": STARTING_EQUITY,
            "macro_events_approx": [[n, str(ts)] for n, ts in MACRO_EVENTS],
        },
        "experiment_log": [
            "v1 (extremes-only contrarian sentiment mapping): CNN F&G stayed 40.7-66.6 "
            "all window -> sentiment scored 0 on 100% of days -> qual axis flat -> "
            "0 stack trades vs 30 control trades. KILLED 2026-08-30; mapping revised "
            "to doc pillar-1 tone+rate-of-change with contrarian extremes.",
        ],
        "limitations": [
            "thesis + smart_money feeds: no free historical source (None; weights renormalized)",
            "sentiment = market-level Fear&Greed proxy, not per-ticker social flow",
            "macro calendar is the approximate structural schedule, not a fetched one",
            "long-only; SELL closes but never shorts",
        ],
        "coverage": coverage,
        "stack": stack,
        "control_quant_only": control,
        "wait_filtered_control_trades": {"trades": filtered, "metrics": metrics(filtered)},
        "hypotheses": {
            "H1_positive_net_expectancy": {
                "expectancy_r": exp_stack, "n": n_stack,
                "verdict": (
                    "INCONCLUSIVE (n<5)" if n_stack < 5
                    else ("SUPPORTED" if (exp_stack or 0) > 0 else "REFUTED")
                ),
            },
            "H2_wait_filter_adds_value": {
                "stack_expectancy_r": exp_stack, "control_expectancy_r": exp_ctrl,
                "verdict": (
                    "INCONCLUSIVE" if exp_stack is None or exp_ctrl is None
                    else ("SUPPORTED" if exp_stack > exp_ctrl else "REFUTED")
                ),
            },
            "H3_blackout_fires": {
                "vetoes": stack["blackout_vetoes"],
                "verdict": "SUPPORTED" if stack["blackout_vetoes"] > 0 else "REFUTED",
            },
        },
    }

    out_path = Path(__file__).resolve().parent / "swing_stack_sim_result_20260830.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {out_path}")
    print(json.dumps({"stack": stack["metrics"], "control": control["metrics"],
                      "hypotheses": result["hypotheses"]}, indent=2))


if __name__ == "__main__":
    main()
