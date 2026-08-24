"""Contract tests for desk_reference — the desk's own ledger, rendered.

Two properties matter more than any individual number here:

  1. FAIL-SOFT. Every query must degrade to None/"" rather than raise. A
     reference block that throws costs the cycle a decision; one that is
     silent costs it a sentence.
  2. THIN RECORDS STAY SILENT. Telling the desk a "record" derived from one
     trade is worse than telling it nothing (`desk_record._MIN_RUNS` is the
     precedent this follows).
"""
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _seed(conn, rows, trades, mechs=()):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE trading_runs (
        id INTEGER PRIMARY KEY, agent_id INT, symbol TEXT, market TEXT,
        status TEXT, realized_pnl_usd REAL, peak_pnl_usd REAL,
        stopped_at TEXT)""")
    cur.execute("""CREATE TABLE run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INT, event_type TEXT,
        ts TEXT, payload TEXT)""")
    for r in rows:
        cur.execute(
            "INSERT INTO trading_runs (id, agent_id, symbol, market, status,"
            " realized_pnl_usd, peak_pnl_usd, stopped_at)"
            " VALUES (?,?,?,?,?,?,?,?)", r)
    for t in trades:
        cur.execute("INSERT INTO run_events (run_id, event_type, ts, payload)"
                    " VALUES (?, 'trade', ?, ?)", t)
    for m in mechs:
        cur.execute("INSERT INTO run_events (run_id, event_type, ts, payload)"
                    " VALUES (?, 'stop_mechanism', ?, ?)", m)
    conn.commit()


@pytest.fixture()
def mod(monkeypatch):
    """desk_reference bound to an in-memory ledger."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    class _KeepOpen:
        """The module closes what it opens; the fixture must outlive that."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            return None

    fake_db = types.ModuleType("database")
    fake_db.get_db_connection = lambda: _KeepOpen(conn)
    monkeypatch.setitem(sys.modules, "database", fake_db)
    for name in list(sys.modules):
        if name == "desk_reference":
            del sys.modules[name]
    import desk_reference as dr
    dr._CACHE.clear()
    return dr, conn


def _recent(hours_ago):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc)
            - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_symbol_side_record_reports_the_prior_loss(mod):
    """The LINK#2 case: a second short on a symbol whose first short lost."""
    dr, conn = mod
    _seed(conn,
          rows=[(1, 6, "LINKUSDT", "crypto", "stopped", -4.11, 0.0, _recent(6)),
                (2, 6, "LINKUSDT", "crypto", "stopped", -0.90, 0.0, _recent(1))],
          trades=[(1, _recent(7), json.dumps(
                      {"side": "short", "quantity": 21.0, "price": 11.5,
                       "fee": 0.11})),
                  (1, _recent(6), json.dumps(
                      {"side": "cover", "quantity": 21.0, "price": 11.7,
                       "fee": 0.11})),
                  (2, _recent(2), json.dumps(
                      {"side": "short", "quantity": 42.0, "price": 11.55,
                       "fee": 0.22})),
                  (2, _recent(1), json.dumps(
                      {"side": "cover", "quantity": 42.0, "price": 11.57,
                       "fee": 0.22}))])
    rec = dr.symbol_side_record("LINKUSDT", "crypto", "short")
    assert rec is not None
    assert rec["n"] == 2 and rec["wins"] == 0
    assert rec["net"] == pytest.approx(-5.01, abs=0.01)

    block = dr.reference_block("LINKUSDT", "crypto", "short")
    assert "LINKUSDT SHORT" in block
    assert "0 profitable" in block


def test_thin_symbol_record_stays_silent(mod):
    """One prior trade is not a record."""
    dr, conn = mod
    _seed(conn,
          rows=[(1, 6, "LINKUSDT", "crypto", "stopped", -4.11, 0.0, _recent(6))],
          trades=[(1, _recent(7), json.dumps(
                      {"side": "short", "quantity": 21.0, "price": 11.5,
                       "fee": 0.11}))])
    assert dr.symbol_side_record("LINKUSDT", "crypto", "short") is None


def test_stale_history_is_excluded(mod):
    """Beyond the lookback the record is history, not a lesson."""
    dr, conn = mod
    old = 24 * (dr._LOOKBACK_DAYS + 5)
    _seed(conn,
          rows=[(1, 6, "OLDUSDT", "crypto", "stopped", -4.0, 0.0, _recent(old)),
                (2, 6, "OLDUSDT", "crypto", "stopped", -1.0, 0.0, _recent(old))],
          trades=[(1, _recent(old + 1), json.dumps(
                      {"side": "short", "quantity": 1.0, "price": 10.0,
                       "fee": 0.01})),
                  (2, _recent(old + 1), json.dumps(
                      {"side": "short", "quantity": 1.0, "price": 10.0,
                       "fee": 0.01}))])
    assert dr.symbol_side_record("OLDUSDT", "crypto", "short") is None


def test_fee_reality_reads_the_ledger_not_a_constant(mod):
    """The booked fee is summed off trade payloads, so a changed fee
    constant elsewhere cannot move this number."""
    dr, conn = mod
    rows, trades = [], []
    for i in range(1, dr._MIN_N_MARKET + 1):
        rows.append((i, 6, f"S{i}USDT", "crypto", "stopped", -0.50, 0.0,
                     _recent(i)))
        # $1000 notional, $0.90 total fees => 0.090% round trip.
        trades.append((i, _recent(i + 1), json.dumps(
            {"side": "short", "quantity": 100.0, "price": 10.0, "fee": 0.45})))
        trades.append((i, _recent(i), json.dumps(
            {"side": "cover", "quantity": 100.0, "price": 10.0, "fee": 0.45})))
    _seed(conn, rows, trades)
    rec = dr.fee_reality("crypto")
    assert rec is not None
    assert rec["median_rt_pct"] == pytest.approx(0.090, abs=0.001)
    assert "0.090%" in dr.reference_block("S1USDT", "crypto")


def test_exit_author_record_counts_mechanisms(mod):
    dr, conn = mod
    mechs = [(1, _recent(i), json.dumps(
        {"mechanism": "breakeven_ratchet", "reason": "trailing_lock",
         "total": -0.30, "peak": 1.50}))
        for i in range(dr._MIN_N_MARKET)]
    _seed(conn,
          rows=[(1, 6, "AUSDT", "crypto", "stopped", -0.30, 1.5, _recent(1))],
          trades=[(1, _recent(2), json.dumps(
              {"side": "short", "quantity": 1.0, "price": 10.0, "fee": 0.01}))],
          mechs=mechs)
    rec = dr.exit_author_record("crypto")
    assert rec is not None
    m = rec["mechanisms"][0]
    assert m["mechanism"] == "breakeven_ratchet"
    assert m["n"] == dr._MIN_N_MARKET and m["positive"] == 0
    # Gave back more than the whole peak.
    assert m["median_giveback"] > 1.0
    block = dr.reference_block("AUSDT", "crypto")
    assert "breakeven_ratchet" in block
    # The framing correction must survive: never blame the rail outright.
    assert "not fault" in block


def test_direction_record_splits_long_and_short(mod):
    dr, conn = mod
    rows, trades = [], []
    for i in range(1, 5):  # 4 shorts, all losing
        rows.append((i, 6, f"S{i}", "crypto", "stopped", -1.0, 0.0, _recent(i)))
        trades.append((i, _recent(i + 1), json.dumps(
            {"side": "short", "quantity": 1.0, "price": 10.0, "fee": 0.01})))
    for i in range(5, 8):  # 3 longs, all winning
        rows.append((i, 6, f"L{i}", "crypto", "stopped", 1.0, 0.0, _recent(i)))
        trades.append((i, _recent(i + 1), json.dumps(
            {"side": "buy", "quantity": 1.0, "price": 10.0, "fee": 0.01})))
    _seed(conn, rows, trades)
    rec = dr.direction_record("crypto")
    assert rec is not None
    assert rec["by_side"]["short"]["n"] == 4
    assert rec["by_side"]["short"]["wins"] == 0
    assert rec["by_side"]["long"]["wins"] == 3
    assert "YOUR DIRECTIONAL RECORD" in dr.reference_block("S1", "crypto")


def test_block_is_empty_when_nothing_is_measurable(mod):
    dr, conn = mod
    _seed(conn, rows=[], trades=[])
    assert dr.reference_block("ANY", "crypto", "long") == ""


def test_every_query_fails_soft(mod, monkeypatch):
    """A raising ledger must cost a sentence, never the cycle."""
    dr, _ = mod

    def boom():
        raise RuntimeError("ledger down")

    monkeypatch.setattr(dr, "_closed_trips", lambda market: boom())
    dr._CACHE.clear()
    assert dr.symbol_side_record("X", "crypto", "long") is None
    assert dr.direction_record("crypto") is None
    assert dr.fee_reality("crypto") is None
    assert dr.reference_block("X", "crypto", "long") == ""


def test_block_states_facts_not_instructions(mod):
    """The module must not grow a veto. desk_record's history is why."""
    dr, conn = mod
    rows, trades = [], []
    for i in range(1, dr._MIN_N_MARKET + 2):
        rows.append((i, 6, f"S{i}", "crypto", "stopped", -1.0, 0.0, _recent(i)))
        trades.append((i, _recent(i + 1), json.dumps(
            {"side": "short", "quantity": 1.0, "price": 10.0, "fee": 0.01})))
        trades.append((i, _recent(i), json.dumps(
            {"side": "cover", "quantity": 1.0, "price": 10.0, "fee": 0.01})))
    _seed(conn, rows, trades)
    block = dr.reference_block("S1", "crypto", "short")
    assert block
    lowered = block.lower()
    for banned in ("do not open", "you must", "forbidden", "never take",
                   "refuse"):
        assert banned not in lowered, f"reference block grew an instruction: {banned}"
    assert "your call" in lowered
