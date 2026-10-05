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

DAY_MS = 86_400_000


def _completed_bars(bars: list[dict[str, Any]],
                    now_ms: Optional[int] = None) -> list[dict[str, Any]]:
    """Daily bars with the one still FORMING dropped.

    The rule this module trades — and the only form of it with a tested
    record (research/trend_replay, 2026-10-05: 115 trades 2020-2026,
    +114R, on completed bars) — decides on a bar's CLOSE. The feed's last
    row is the bar in progress, and the loop ticks hourly, so until this
    filter every tick read an intraday price as "today's close". Replayed
    hourly on that reading: 164 trades for +93R; the 63 entries that exist
    only because a bar was read before it closed net -2.2R. Live, the
    2026-09-21 BNB entry is one the completed-bar rule never takes.

    A bar with no timestamp is kept — nothing can be said about it."""
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    out = []
    for bar in bars or []:
        ts = bar.get("ts")
        if ts is not None and int(ts) + DAY_MS > now_ms:
            continue
        out.append(bar)
    return out


def _get_bars(symbol: str) -> list[dict[str, Any]]:
    """Completed daily bars, fetched fresh.

    Not price_fetcher.get_daily_candles: that caches for hours, so a
    snapshot taken mid-bar would still be served after the bar closed and
    its stale "close" would pass the completed-bar filter as final. Five
    symbols an hour is nothing to the venue. Fail-soft to [] — the cycle
    already treats missing bars as "skip this symbol"."""
    try:
        import crypto_feed
        bars = crypto_feed.fetch_candles(symbol, bar="1D",
                                         limit=HISTORY_DAYS + 1)
    except Exception:  # noqa: BLE001
        logger.warning("trend_module: daily bars unavailable for %s", symbol,
                       exc_info=True)
        return []
    return _completed_bars(bars)


def _bar_ts(bars: list[dict[str, Any]]) -> Optional[int]:
    """Timestamp of the newest bar in hand, when the feed carries one."""
    try:
        ts = bars[-1].get("ts") if bars else None
        return None if ts is None else int(ts)
    except (TypeError, ValueError, AttributeError):
        return None


def _mark(symbol: str, fallback: float) -> float:
    """The price a fill happens at: the live mark, not the bar's close.

    The decision is taken on a completed bar, but the tick that takes it
    runs up to an hour after that bar closed. Booking the fill at the old
    close records a price the market no longer offers; the replay fills at
    the next bar's open for the same reason. Falls back to the close when
    no mark is available rather than skipping the order."""
    try:
        import price_fetcher
        px = price_fetcher.get_price_from_market(symbol, _now_iso(), "crypto")
        if px is not None and float(px) > 0:
            return float(px)
    except Exception:  # noqa: BLE001
        logger.debug("trend_module: no live mark for %s", symbol,
                     exc_info=True)
    return fallback


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

def _agent_is_dedicated(agent_id: int) -> bool:
    """Verification Q2-2: a mistyped TREND_AGENT_ID pointing at a REAL
    user's agent would trade that user's sim book with no check (and the
    entry freeze would not stop it — the freeze lives in run_cycle). The
    dedicated module agent is created with user_id NULL; refuse anything
    else. Fail closed on lookup errors — a module that cannot prove its
    agent is dedicated must not trade."""
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return bool(row) and row["user_id"] is None
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


def _ledger_positions(agent_id: int) -> dict[str, dict[str, Any]]:
    """The module agent's OPEN ledger positions, keyed by symbol. Every
    lot on a dedicated agent belongs to this module, so any symbol here
    that state does not track is an orphan (crash between ledger commit
    and _save_state — verification A3-5) and must be re-adopted."""
    return _ledger_read(agent_id) or {}


def _ledger_read(agent_id: int) -> "dict[str, dict[str, Any]] | None":
    """`_ledger_positions`, with a failed read told apart from an empty
    book (None vs {}). Dropping state needs that difference: a database
    hiccup must not look like every position having been closed."""
    from database import get_db_connection
    try:
        conn = get_db_connection()
    except Exception:  # noqa: BLE001
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT symbol, quantity, entry_price FROM positions "
            "WHERE agent_id = ? AND market = 'crypto'", (agent_id,))
        return {r["symbol"]: dict(r) for r in cursor.fetchall()
                if float(r["quantity"] or 0) != 0}
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def _drop_closed_outside(state: dict[str, Any], actions: list[dict[str, Any]],
                         agent_id: int) -> None:
    """Forget positions the ledger no longer holds.

    The module's stop sits on the ledger row and the SL/TP watcher closes on
    it between ticks, so a position can be gone before the module looks.
    Without this the state kept it — occupying one of TREND_MAX_POSITIONS —
    until the module's own exit was refused, which for a position that never
    reaches its trail is the 30-day time stop."""
    ledger = _ledger_read(agent_id)
    if ledger is None:
        return
    for symbol in sorted(state["positions"]):
        if symbol not in ledger:
            pos = state["positions"].pop(symbol)
            _emit(state, actions, "closed_outside", symbol=symbol,
                  side=pos.get("side"), stop=pos.get("initial_stop"))


def _sync_stop(agent_id: int, symbol: str, stop: float) -> None:
    """Put the module's initial stop on its ledger row, and only that.

    The SL/TP watcher enforces whatever `positions.stop_loss` holds, intraday.
    Replay 2020-2026, same entries (research/trend_replay): exits on the
    daily close only +114.2R; this stop enforced intraday +122.9R with the
    drawdown 14.6R against 20.2R; the 5% stop the orphan sweep used to write
    here +71.4R. Written directly rather than through execute_paper_trade's
    stop_loss argument: that also stamps exit_policy='v1', which arms the
    watcher's own loser time-stop and trail — two more exits this rule never
    had. Idempotent, so it also replaces a stop somebody else left."""
    from database import get_db_connection
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE positions SET stop_loss = ? WHERE agent_id = ? "
            "AND market = 'crypto' AND symbol = ? AND run_id IS NULL "
            "AND (stop_loss IS NULL OR stop_loss != ?)",
            (float(stop), agent_id, symbol, float(stop)))
        conn.commit()
    except Exception:  # noqa: BLE001 — the daily-close stop still stands
        logger.warning("trend_module: stop sync failed for %s", symbol,
                       exc_info=True)
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass


def _reconcile_ledger(state: dict[str, Any], actions: list[dict[str, Any]],
                      agent_id: int) -> None:
    """Adopt ledger lots the state forgot. Stops/trail are rebuilt from the
    CURRENT bars (entry-time ATR is lost with the crash) — approximate but
    managed beats exact but orphaned."""
    for symbol, row in _ledger_positions(agent_id).items():
        if symbol in state["positions"]:
            continue
        highs, lows, closes = _series(_get_bars(symbol))
        atr = wilder_atr(highs, lows, closes) if closes else None
        if not closes or not atr or atr <= 0:
            _emit(state, actions, "orphan_unadoptable", symbol=symbol,
                  reason="insufficient bars")
            continue
        qty = float(row["quantity"])
        side = "long" if qty > 0 else "short"
        entry = float(row["entry_price"] or closes[-1])
        stop = entry - STOP_ATR_MULT * atr if side == "long" \
            else entry + STOP_ATR_MULT * atr
        state["positions"][symbol] = {
            "side": side, "qty": abs(qty), "entry_price": entry,
            "entry_atr": atr, "initial_stop": stop, "trail": None,
            "best_close": entry, "entry_ts": _now_iso(),
            "entry_kind": "adopted", "signal_id": None,
        }
        _emit(state, actions, "orphan_adopted", symbol=symbol,
              qty=abs(qty), price=entry, signal_id=None)


def _adopt_orphan(agent_id: int, symbol: str, sig: dict[str, Any],
                  today: str) -> "dict[str, Any] | None":
    """Same-day duplicate refusal: the ledger already holds today's entry
    for this signal. Rebuild the position from the ledger row + the
    current signal's ATR."""
    positions = _ledger_positions(agent_id)
    row = positions.get(symbol)
    if not row:
        return None
    qty = float(row["quantity"])
    side = "long" if qty > 0 else "short"
    entry = float(row["entry_price"] or sig["close"])
    stop = entry - STOP_ATR_MULT * sig["atr"] if side == "long" \
        else entry + STOP_ATR_MULT * sig["atr"]
    return {"side": side, "qty": abs(qty), "entry_price": entry,
            "entry_atr": sig["atr"], "initial_stop": stop, "trail": None,
            "best_close": entry, "entry_ts": _now_iso(),
            "entry_kind": sig["entry_kind"], "signal_id": None}


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


# platform_settings.setting_value is TEXT on MySQL: 65,535 bytes, strict mode.
STATE_MAX_BYTES = 60_000


def _save_state(state: dict[str, Any]) -> None:
    """Persist the module state — inside the column it lives in.

    EVENT_CAP rows of telemetry (~180 bytes each) do not fit a TEXT column,
    and the write is all-or-nothing: on prod the state stopped saving at 366
    rows (last write 2026-09-27T06:25Z) and every hourly cycle after that ran
    from the same frozen snapshot. Positions and entered bars are what
    trading depends on; the oldest telemetry is dropped until the whole fits.
    The rows are also on the JSON log line `_emit` writes."""
    from platform_settings import set_setting
    raw = json.dumps(state)
    while len(raw.encode("utf-8")) > STATE_MAX_BYTES and state.get("events"):
        del state["events"][:max(1, len(state["events"]) // 4)]
        raw = json.dumps(state)
    set_setting(STATE_KEY, raw, updated_by="trend_module")


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

    if not _agent_is_dedicated(agent_id):
        logger.warning("trend_module: TREND_AGENT_ID=%s is not a dedicated "
                       "agent (user_id must be NULL) — refusing to run",
                       agent_id)
        summary["error"] = "TREND_AGENT_ID not a dedicated agent"
        return summary

    from automation import execute_paper_trade

    state = _load_state()
    actions: list[dict[str, Any]] = []
    _reconcile_ledger(state, actions, agent_id)
    _drop_closed_outside(state, actions, agent_id)
    for symbol, pos in state["positions"].items():
        _sync_stop(agent_id, symbol, pos["initial_stop"])
    fear_greed = _fear_greed_value()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── open positions: trail update once per cycle, then exit checks ──
    for symbol in sorted(state["positions"]):
        pos = state["positions"][symbol]
        bars = _get_bars(symbol)
        bar_ts = _bar_ts(bars)
        # One evaluation per completed bar, and none on the bar the entry
        # itself was decided on — the position was not open for it. Hourly
        # ticks inside the same bar have nothing new to rule on.
        if (bar_ts is not None and pos.get("bar_ts") is not None
                and bar_ts <= int(pos["bar_ts"])):
            continue
        highs, lows, closes = _series(bars)
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
            # Ruled on. Stamped only here: an exit that FAILS below must be
            # retried on the next tick, not parked until tomorrow's bar.
            if bar_ts is not None:
                pos["bar_ts"] = bar_ts
            continue
        side = "sell" if pos["side"] == "long" else "cover"
        close = _mark(symbol, close)
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
        bars = _get_bars(symbol)
        # A signal bar is taken once. After an intraday stop-out the slot is
        # free while that bar is still the newest one and its signal still
        # evaluates true; without this every tick re-entered it.
        bar_ts = _bar_ts(bars)
        if (bar_ts is not None
                and state.get("entered_bar", {}).get(symbol) == bar_ts):
            continue
        sig = evaluate_symbol(bars, fear_greed)
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
        entry = _mark(symbol, sig["close"])
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
            if err and "client_order_id" in err:
                # Verification A3-5: a crash between the ledger commit and
                # _save_state leaves an orphaned lot the module forgot; the
                # next-day rerun then DOUBLE-enters. The duplicate refusal
                # is that orphan announcing itself — re-adopt it into state
                # (same-day parameters are reconstructible from the signal)
                # instead of leaving it unmanaged.
                adopted = _adopt_orphan(agent_id, symbol, sig, today)
                if adopted:
                    state["positions"][symbol] = adopted
                    _emit(state, actions, "orphan_adopted", symbol=symbol,
                          qty=adopted["qty"], price=adopted["entry_price"],
                          signal_id=adopted["signal_id"])
                    continue
            _emit(state, actions, "entry_failed", symbol=symbol, reason=err)
            continue
        state["positions"][symbol] = {
            "side": book_side, "qty": qty, "entry_price": entry,
            "entry_atr": sig["atr"], "initial_stop": initial_stop,
            "trail": None, "best_close": entry, "entry_ts": _now_iso(),
            "entry_kind": sig["entry_kind"], "signal_id": signal_id,
            "bar_ts": bar_ts,
        }
        if bar_ts is not None:
            state.setdefault("entered_bar", {})[symbol] = bar_ts
        _sync_stop(agent_id, symbol, initial_stop)
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
    """The module's own record from its agent's fills: n closed trades, win
    rate, payoff, total pnl.

    EVERY fill on the dedicated agent, not only those carrying the module's
    'trend:' order id: its stop is enforced by the SL/TP watcher, whose
    close has no order id, and a record without the stop-outs is a record
    without most of the losses."""
    agent_id = _agent_id()
    if agent_id is None:
        return {"error": "TREND_AGENT_ID unset"}
    from database import get_db_connection
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT side, pnl FROM signals WHERE agent_id = ? "
            "AND message_type = 'operation'", (agent_id,))
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
