"""Plan 31 item 7 — the trend edge module (SIM ONLY, default OFF).

A DETERMINISTIC regime-gated trend-following strategy on large-cap crypto
daily bars, managing its own positions on the simulated ledger. It does NOT
run through the LLM desk / run_engine decision loop: the LLM is demoted to
exactly one veto/size call per new signal (the only role with documented
value — R4 F2), and any LLM failure defaults to "no veto, full size".

Class geometry (the trend pole — R4 F3):
  entry  = 20-day Donchian channel breakout, gated by ADX14 in [25, 40]
           AND close on the right side of the 200-day MA;
  stop   = 1.5×ATR14 from entry;
  exit   = chandelier trail (best close since entry −/+ 3×ATR14, ratcheted),
           NO fixed profit target (this class is exempt from the 0.30%
           target cap BY DESIGN), plus a 30-day hard time-stop;
  sizing = vol-parity: qty = TREND_RISK_USD / (1.5×ATR14).

Psychology overlay (Plan 31 item 8's rule, armed passively):
  F&G ≥ 80 → no NEW longs.  F&G ≤ 20 → a CONTRARIAN long is allowed when
  close < prior 20d low (falling-knife catch, multi-day hold) even when the
  regime gates fail — tagged entry_kind="fg_contrarian" (normal entries are
  "donchian"). In-window F&G 27–74 means this correctly does nothing until
  extremes appear.

Execution: automation.execute_paper_trade under a DEDICATED agent id
(TREND_AGENT_ID — the module refuses to run without it). Module state
(open positions, trail levels, telemetry) lives as JSON in
platform_settings under `trend_module_state`.

Falsifier (pre-registered, Plan 31): 30 trips or 60 trading days of
live-window sim — true-net EV ≤ 0 or payoff < 1.5 → module dies, no
capital. `trend_stats()` reports the module's own record from its fills.

Env: TREND_MODULE_ENABLED (default off) · TREND_AGENT_ID (required, no
default) · TREND_UNIVERSE (csv, default large-cap five) ·
TREND_RISK_USD (25) · TREND_MAX_POSITIONS (3).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

STATE_KEY = "trend_module_state"
DEFAULT_UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

DONCHIAN_DAYS = 20
ATR_PERIOD = 14
ADX_PERIOD = 14
MA_DAYS = 200
MIN_BARS = 210          # 200MA + Donchian/ADX warmup headroom
HISTORY_DAYS = 280      # get_daily_candles caps at 365; OKX paginates fine
ADX_MIN, ADX_MAX = 25.0, 40.0
STOP_ATR_MULT = 1.5
TRAIL_ATR_MULT = 3.0
TIME_STOP_DAYS = 30
FG_GREED_BLOCK = 80
FG_FEAR_CONTRARIAN = 20
EVENT_CAP = 400         # telemetry rows kept in state


def module_enabled() -> bool:
    return os.getenv("TREND_MODULE_ENABLED", "0").strip().lower() in (
        "1", "true", "yes", "on")


def _agent_id() -> Optional[int]:
    """Dedicated sim agent. No default ON PURPOSE — the module must never
    place anything against an implicit agent."""
    raw = os.getenv("TREND_AGENT_ID", "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _universe() -> list[str]:
    raw = os.getenv("TREND_UNIVERSE", "").strip()
    if raw:
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return list(DEFAULT_UNIVERSE)


def _risk_usd() -> float:
    try:
        return max(0.0, float(os.getenv("TREND_RISK_USD", "25")))
    except ValueError:
        return 25.0


def _max_positions() -> int:
    try:
        return max(1, int(os.getenv("TREND_MAX_POSITIONS", "3")))
    except ValueError:
        return 3


# ─────────────────────────── indicators (Wilder) ───────────────────────────

def _series(bars: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float]]:
    """Daily candles → (highs, lows, closes), None-safe (missing H/L → close)."""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for bar in bars or []:
        close = bar.get("close")
        if close is None:
            continue
        close = float(close)
        high = bar.get("high")
        low = bar.get("low")
        highs.append(float(high) if high is not None else close)
        lows.append(float(low) if low is not None else close)
        closes.append(close)
    return highs, lows, closes


def _true_ranges(highs: list[float], lows: list[float],
                 closes: list[float]) -> list[float]:
    return [max(highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))]


def wilder_atr(highs: list[float], lows: list[float], closes: list[float],
               period: int = ATR_PERIOD) -> Optional[float]:
    """ATR with standard Wilder smoothing: seed = mean of the first `period`
    TRs, then atr = (atr·(period−1) + tr) / period."""
    if len(closes) < period + 1:
        return None
    trs = _true_ranges(highs, lows, closes)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def wilder_adx(highs: list[float], lows: list[float], closes: list[float],
               period: int = ADX_PERIOD) -> Optional[float]:
    """ADX with Wilder smoothing throughout (DM/TR sums and the DX average)."""
    if len(closes) < 2 * period + 1:
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    trs = _true_ranges(highs, lows, closes)

    def _dx(sm_tr: float, sm_p: float, sm_m: float) -> float:
        if sm_tr <= 0:
            return 0.0
        pdi = 100.0 * sm_p / sm_tr
        mdi = 100.0 * sm_m / sm_tr
        total = pdi + mdi
        return 100.0 * abs(pdi - mdi) / total if total > 0 else 0.0

    sm_tr = sum(trs[:period])
    sm_p = sum(plus_dm[:period])
    sm_m = sum(minus_dm[:period])
    dxs = [_dx(sm_tr, sm_p, sm_m)]
    for i in range(period, len(trs)):
        sm_tr = sm_tr - sm_tr / period + trs[i]
        sm_p = sm_p - sm_p / period + plus_dm[i]
        sm_m = sm_m - sm_m / period + minus_dm[i]
        dxs.append(_dx(sm_tr, sm_p, sm_m))
    adx = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        adx = (adx * (period - 1) + dx) / period
    return adx


# ─────────────────────────── signal evaluation ───────────────────────────

def evaluate_symbol(bars: list[dict[str, Any]],
                    fear_greed: Optional[int]) -> Optional[dict[str, Any]]:
    """Daily bars → entry candidate, blocked marker, or None.

    Returns {"side": "buy"|"short", "entry_kind": "donchian"|"fg_contrarian",
    ...facts} for a candidate; {"side": None, "blocked": reason} when the
    greed overlay suppresses an otherwise-valid long; None otherwise."""
    highs, lows, closes = _series(bars)
    if len(closes) < MIN_BARS:
        return None
    close = closes[-1]
    atr = wilder_atr(highs, lows, closes)
    adx = wilder_adx(highs, lows, closes)
    if not atr or atr <= 0 or adx is None:
        return None
    ma200 = sum(closes[-MA_DAYS:]) / MA_DAYS
    channel_high = max(highs[-(DONCHIAN_DAYS + 1):-1])
    channel_low = min(lows[-(DONCHIAN_DAYS + 1):-1])
    facts = {"close": close, "atr": atr, "adx": adx, "ma200": ma200,
             "channel_high": channel_high, "channel_low": channel_low,
             "fear_greed": fear_greed}
    regime_ok = ADX_MIN <= adx <= ADX_MAX
    # Extreme-fear contrarian catch (item 8's rule): bypasses the regime
    # gates by design — a falling knife is anti-trend, the edge is the
    # multi-day mean reversion after F&G ≤ 20 (sub-10 F&G → +48% avg 90d
    # forward, 0 negatives). It also pre-empts the symmetric donchian short.
    if (fear_greed is not None and fear_greed <= FG_FEAR_CONTRARIAN
            and close < channel_low):
        return {**facts, "side": "buy", "entry_kind": "fg_contrarian"}
    if close > channel_high and regime_ok and close > ma200:
        if fear_greed is not None and fear_greed >= FG_GREED_BLOCK:
            return {**facts, "side": None, "blocked": "fg_greed_no_new_longs"}
        return {**facts, "side": "buy", "entry_kind": "donchian"}
    if close < channel_low and regime_ok and close < ma200:
        return {**facts, "side": "short", "entry_kind": "donchian"}
    return None


def position_qty(atr: float, size_mult: float = 1.0) -> float:
    """Vol-parity sizing: risk TREND_RISK_USD over the 1.5×ATR initial stop."""
    if atr <= 0:
        return 0.0
    return _risk_usd() / (STOP_ATR_MULT * atr) * size_mult


# ─────────────────────────── trail / exits ───────────────────────────

def update_trail(pos: dict[str, Any], close: float, atr: float) -> None:
    """Chandelier trail, ratcheted: best close since entry −/+ 3×ATR, and the
    trail never loosens (a later ATR expansion must not give back locked
    ground). Mutates `pos` in place."""
    if pos["side"] == "long":
        pos["best_close"] = max(float(pos["best_close"]), close)
        candidate = pos["best_close"] - TRAIL_ATR_MULT * atr
        prev = pos.get("trail")
        pos["trail"] = candidate if prev is None else max(float(prev), candidate)
    else:
        pos["best_close"] = min(float(pos["best_close"]), close)
        candidate = pos["best_close"] + TRAIL_ATR_MULT * atr
        prev = pos.get("trail")
        pos["trail"] = candidate if prev is None else min(float(prev), candidate)


def check_exit(pos: dict[str, Any], close: float,
               now: Optional[datetime] = None) -> Optional[str]:
    """Exit reason for an open position at today's close, or None.
    Effective stop = the tighter of the initial 1.5×ATR stop and the trail."""
    now = now or datetime.now(timezone.utc)
    entry_dt = datetime.fromisoformat(str(pos["entry_ts"]))
    if entry_dt.tzinfo is None:
        entry_dt = entry_dt.replace(tzinfo=timezone.utc)
    if now - entry_dt >= timedelta(days=TIME_STOP_DAYS):
        return "time_stop"
    initial = float(pos["initial_stop"])
    trail = pos.get("trail")
    if pos["side"] == "long":
        stop = initial if trail is None else max(initial, float(trail))
        if close <= stop:
            return "initial_stop" if stop == initial else "trail_stop"
    else:
        stop = initial if trail is None else min(initial, float(trail))
        if close >= stop:
            return "initial_stop" if stop == initial else "trail_stop"
    return None


# ─────────────────────────── feeds / LLM ───────────────────────────

def _get_bars(symbol: str) -> list[dict[str, Any]]:
    import price_fetcher
    return price_fetcher.get_daily_candles(symbol, "crypto", days=HISTORY_DAYS)


def _fear_greed_value() -> Optional[int]:
    """Crypto F&G from the psych snapshot (DB, no network). Fail-soft None —
    with no reading the overlay simply does nothing."""
    try:
        from psych_feed import get_psych_payload
        fng = (get_psych_payload() or {}).get("fear_greed") or {}
        value = fng.get("value")
        return int(value) if value is not None else None
    except Exception:  # noqa: BLE001
        return None


def _llm_veto(symbol: str, sig: dict[str, Any]) -> dict[str, Any]:
    """ONE veto/size call per new signal. Deterministic-first: any error,
    no-answer or unparsable reply defaults to {veto: False, size_mult: 1.0}."""
    default = {"veto": False, "size_mult": 1.0, "raw": None}
    prompt = (
        "A deterministic trend module produced this entry signal on the "
        "simulated ledger. Your ONLY job is veto/size — do not re-decide "
        "the strategy.\n"
        f"Signal: {symbol} {sig['side']} entry_kind={sig['entry_kind']} "
        f"close={sig['close']:.6g} ATR14={sig['atr']:.6g} "
        f"ADX14={sig['adx']:.2f} MA200={sig['ma200']:.6g} "
        f"20d_channel=[{sig['channel_low']:.6g}, {sig['channel_high']:.6g}] "
        f"FearGreed={sig.get('fear_greed')}\n"
        'Answer ONLY this JSON: {"veto": true|false, "size_mult": 0.5 or 1.0}')
    try:
        import llm_client
        raw = llm_client.generate_text(prompt, max_tokens=200,
                                       temperature=0.2, tier="decision")
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend_module llm veto call failed for %s: %s", symbol, exc)
        return default
    if not raw:
        return default
    logger.info("trend_module llm verdict %s: %s", symbol, raw[:400])
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        veto = bool(parsed.get("veto"))
        mult = float(parsed.get("size_mult", 1.0))
        if mult not in (0.5, 1.0):
            mult = 1.0
        return {"veto": veto, "size_mult": mult, "raw": raw}
    except Exception:  # noqa: BLE001
        return {**default, "raw": raw}


# ─────────────────────────── state / telemetry ───────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    from platform_settings import get_setting
    raw = get_setting(STATE_KEY)
    if raw:
        try:
            state = json.loads(raw)
            if isinstance(state, dict):
                state.setdefault("positions", {})
                state.setdefault("events", [])
                return state
        except (ValueError, TypeError):
            logger.warning("trend_module: corrupt state JSON — starting fresh")
    return {"positions": {}, "events": []}


def _save_state(state: dict[str, Any]) -> None:
    from platform_settings import set_setting
    set_setting(STATE_KEY, json.dumps(state), updated_by="trend_module")


def _emit(state: dict[str, Any], actions: list[dict[str, Any]],
          event: str, **fields: Any) -> None:
    """Telemetry: JSON logger line + a queryable row in the module's state."""
    row = {"ts": _now_iso(), "event": event, **fields}
    state["events"].append(row)
    del state["events"][:-EVENT_CAP]
    actions.append(row)
    logger.info("trend_module %s", json.dumps(row, default=str))


# ─────────────────────────── module cycle ───────────────────────────

def run_trend_cycle() -> dict[str, Any]:
    """One module cycle: update trails / exits on open positions, then scan
    the universe for new entries. Returns a summary dict. No-ops (touching
    nothing, not even state) when TREND_MODULE_ENABLED is off, and refuses
    outright when TREND_AGENT_ID is unset."""
    summary: dict[str, Any] = {"enabled": module_enabled(), "scanned": 0,
                               "signals": 0, "entries": 0, "exits": 0,
                               "vetoes": 0, "actions": []}
    if not summary["enabled"]:
        return summary
    agent_id = _agent_id()
    if agent_id is None:
        logger.warning("trend_module: TREND_AGENT_ID unset — refusing to run")
        summary["error"] = "TREND_AGENT_ID unset"
        return summary

    from automation import execute_paper_trade

    state = _load_state()
    actions: list[dict[str, Any]] = []
    fear_greed = _fear_greed_value()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── open positions: trail update once per cycle, then exit checks ──
    for symbol in sorted(state["positions"]):
        pos = state["positions"][symbol]
        highs, lows, closes = _series(_get_bars(symbol))
        atr = wilder_atr(highs, lows, closes) if closes else None
        if not closes or not atr or atr <= 0:
            _emit(state, actions, "skip", symbol=symbol,
                  reason="insufficient bars for open position")
            continue
        close = closes[-1]
        update_trail(pos, close, atr)
        _emit(state, actions, "trail_update", symbol=symbol,
              trail=pos["trail"], best_close=pos["best_close"],
              close=close, atr=atr)
        reason = check_exit(pos, close)
        if not reason:
            continue
        side = "sell" if pos["side"] == "long" else "cover"
        signal_id, err = execute_paper_trade(
            agent_id, symbol, "crypto", side, float(pos["qty"]), close,
            content=json.dumps({"module": "trend", "exit_reason": reason,
                                "entry_kind": pos.get("entry_kind")}),
            run_id=None,
            client_order_id=f"trend:{agent_id}:{symbol}:exit:{today}")
        if signal_id is not None:
            summary["exits"] += 1
            del state["positions"][symbol]
            _emit(state, actions, "exit", symbol=symbol, side=side,
                  reason=reason, price=close, qty=pos["qty"],
                  signal_id=signal_id)
        elif err and "position" in err:
            # Ledger says the book is gone (closed outside the module) —
            # drop the orphaned state rather than retrying forever.
            del state["positions"][symbol]
            _emit(state, actions, "state_desync", symbol=symbol, reason=err)
        else:
            _emit(state, actions, "exit_failed", symbol=symbol,
                  reason=err, exit_reason=reason)

    # ── new entries ──
    for symbol in _universe():
        if symbol in state["positions"]:
            continue
        if len(state["positions"]) >= _max_positions():
            break
        summary["scanned"] += 1
        sig = evaluate_symbol(_get_bars(symbol), fear_greed)
        if sig is None:
            continue
        if sig.get("blocked"):
            _emit(state, actions, "signal_blocked", symbol=symbol,
                  reason=sig["blocked"], close=sig["close"],
                  fear_greed=fear_greed)
            continue
        summary["signals"] += 1
        _emit(state, actions, "signal", symbol=symbol, side=sig["side"],
              entry_kind=sig["entry_kind"], close=sig["close"],
              atr=sig["atr"], adx=sig["adx"], ma200=sig["ma200"],
              fear_greed=fear_greed)
        verdict = _llm_veto(symbol, sig)
        _emit(state, actions, "llm_verdict", symbol=symbol,
              veto=verdict["veto"], size_mult=verdict["size_mult"],
              raw=(verdict["raw"] or "")[:400] or None)
        if verdict["veto"]:
            summary["vetoes"] += 1
            _emit(state, actions, "veto", symbol=symbol,
                  entry_kind=sig["entry_kind"])
            continue
        qty = position_qty(sig["atr"], verdict["size_mult"])
        if qty <= 0:
            continue
        entry = sig["close"]
        if sig["side"] == "buy":
            book_side, initial_stop = "long", entry - STOP_ATR_MULT * sig["atr"]
        else:
            book_side, initial_stop = "short", entry + STOP_ATR_MULT * sig["atr"]
        signal_id, err = execute_paper_trade(
            agent_id, symbol, "crypto", sig["side"], qty, entry,
            content=json.dumps({"module": "trend",
                                "entry_kind": sig["entry_kind"]}),
            run_id=None,
            client_order_id=f"trend:{agent_id}:{symbol}:{sig['side']}:{today}")
        if signal_id is None:
            _emit(state, actions, "entry_failed", symbol=symbol, reason=err)
            continue
        state["positions"][symbol] = {
            "side": book_side, "qty": qty, "entry_price": entry,
            "entry_atr": sig["atr"], "initial_stop": initial_stop,
            "trail": None, "best_close": entry, "entry_ts": _now_iso(),
            "entry_kind": sig["entry_kind"], "signal_id": signal_id,
        }
        summary["entries"] += 1
        _emit(state, actions, "entry", symbol=symbol, side=sig["side"],
              entry_kind=sig["entry_kind"], qty=qty, price=entry,
              stop=initial_stop, signal_id=signal_id)

    _save_state(state)
    summary["actions"] = actions
    summary["open_positions"] = len(state["positions"])
    return summary


# ─────────────────────────── falsifier instrumentation ───────────────────────────

def trend_stats() -> dict[str, Any]:
    """The module's own record from its recorded fills (client_order_id
    prefix 'trend:'): n closed trades, win rate, payoff, total pnl."""
    agent_id = _agent_id()
    if agent_id is None:
        return {"error": "TREND_AGENT_ID unset"}
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT side, pnl FROM signals WHERE agent_id = ? "
            "AND signal_type = 'automation' AND client_order_id LIKE 'trend:%'",
            (agent_id,))
        rows = cursor.fetchall()
    finally:
        conn.close()
    entries = sum(1 for r in rows if r["side"] in ("buy", "short"))
    closed = [float(r["pnl"]) for r in rows
              if r["side"] in ("sell", "cover") and r["pnl"] is not None]
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p <= 0]
    n = len(closed)
    payoff = None
    if wins and losses and sum(losses) != 0:
        payoff = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
    return {
        "agent_id": agent_id,
        "entries": entries,
        "n_trades": n,
        "win_rate": round(len(wins) / n, 4) if n else None,
        "payoff": round(payoff, 4) if payoff is not None else None,
        "total_pnl": round(sum(closed), 4),
    }
