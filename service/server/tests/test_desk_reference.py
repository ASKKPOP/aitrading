"""Contract tests for desk_reference — the desk's own ledger, rendered.

Three properties matter more than any individual number here:

  1. TRIP-LEVEL, NOT RUN-LEVEL. One run can hold several round trips, and a
     trip that closed inside a still-running run must still count. The first
     cut of this module aggregated per run and was therefore blind to the
     exact repeat it exists to prevent (see the LINK regression below).
  2. FAIL-SOFT. Every query degrades to None/"" rather than raising. A
     reference block that throws costs the cycle a decision; a silent one
     costs it a sentence.
  3. THIN RECORDS STAY SILENT. A "record" derived from one trade is worse
     than no record (`desk_record._MIN_RUNS` is the precedent).
"""
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _seed(conn, legs=(), mechs=()):
    """legs: (run_id, symbol, market, side, qty, price, pnl, fee, ts).

    `pnl` is None on entry legs and, on exit legs, is gross MINUS the
    exit-side fee only — the production convention.
    """
    cur = conn.cursor()
    cur.execute("""CREATE TABLE signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INT, symbol TEXT,
        market TEXT, side TEXT, quantity REAL, entry_price REAL, pnl REAL,
        fee_usd REAL, created_at TEXT)""")
    cur.execute("""CREATE TABLE trading_runs (
        id INTEGER PRIMARY KEY, agent_id INT, symbol TEXT, market TEXT,
        status TEXT, realized_pnl_usd REAL, peak_pnl_usd REAL,
        stopped_at TEXT)""")
    cur.execute("""CREATE TABLE run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INT, event_type TEXT,
        ts TEXT, payload TEXT)""")
    for rid, sym, mkt, side, qty, price, pnl, fee, ts in legs:
        cur.execute(
            "INSERT INTO signals (run_id, symbol, market, side, quantity,"
            " entry_price, pnl, fee_usd, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, sym, mkt, side, qty, price, pnl, fee, ts))
    for rid, mkt in {(rid, mkt) for rid, _, mkt, *_ in legs}:
        cur.execute(
            "INSERT OR IGNORE INTO trading_runs (id, agent_id, symbol,"
            " market, status, realized_pnl_usd, peak_pnl_usd, stopped_at)"
            " VALUES (?,1,'',?, 'stopped', 0, 0, '')", (rid, mkt))
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
    sys.modules.pop("desk_reference", None)
    import desk_reference as dr
    dr._CACHE.clear()
    return dr, conn


def _recent(hours_ago):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc)
            - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── the regression this module exists for ──────────────────────────────────

def test_two_trips_inside_ONE_run_are_both_counted(mod):
    """Run 1748 held two LINK shorts: -$4.00 at 11:36 and -$0.68 at 17:12.

    Aggregated per run that is a single -$5.00 row; while the run was open it
    was no row at all. The desk re-shorted at 2x size in between and was
    shown nothing. Both trips must be visible, from the fill ledger."""
    dr, conn = mod
    _seed(conn, legs=[
        # trip 1: short 21 @ 11.526, cover -> exit pnl -3.996, entry fee 0.111
        (1748, "LINKUSDT", "crypto", "short", 21.0, 11.526, None, 0.111,
         _recent(10)),
        (1748, "LINKUSDT", "crypto", "cover", 21.0, 11.711, -3.996, 0.111,
         _recent(9)),
        # trip 2: same run, 5h later, 2x size
        (1748, "LINKUSDT", "crypto", "short", 42.0, 11.554, None, 0.218,
         _recent(4)),
        (1748, "LINKUSDT", "crypto", "cover", 42.0, 11.565, -0.680, 0.218,
         _recent(3)),
    ])
    trips = dr._closed_trips("crypto")
    assert len(trips) == 2, "one run with two round trips must yield two trips"

    rec = dr.symbol_side_record("LINKUSDT", "crypto", "short")
    assert rec is not None, "the LINK record must exist from a single run"
    assert rec["n"] == 2 and rec["wins"] == 0
    # net = exit.pnl - entry.fee per trip: (-3.996-0.111) + (-0.680-0.218).
    # Prod's own realized_pnl_usd for run 1748 is -5.0032, which this
    # reconstruction reproduces from the legs alone.
    assert rec["net"] == pytest.approx(-5.005, abs=0.01)
    block = dr.reference_block("LINKUSDT", "crypto", "short")
    assert "LINKUSDT SHORT" in block and "0 profitable" in block


def test_partial_exit_is_prorated(mod):
    """A half-size exit closes half the entry, and charges half its fee."""
    dr, conn = mod
    _seed(conn, legs=[
        (1, "AUSDT", "crypto", "short", 100.0, 10.0, None, 1.00, _recent(5)),
        (1, "AUSDT", "crypto", "cover", 50.0, 10.0, -2.00, 0.50, _recent(4)),
        (1, "AUSDT", "crypto", "cover", 50.0, 10.0, -2.00, 0.50, _recent(3)),
    ])
    trips = dr._closed_trips("crypto")
    assert len(trips) == 2
    # each: exit pnl -2.00 minus half the 1.00 entry fee
    assert all(t["net"] == pytest.approx(-2.50, abs=0.001) for t in trips)


# ── the registry ───────────────────────────────────────────────────────────

def test_thin_symbol_record_stays_silent(mod):
    dr, conn = mod
    _seed(conn, legs=[
        (1, "LINKUSDT", "crypto", "short", 21.0, 11.5, None, 0.11, _recent(7)),
        (1, "LINKUSDT", "crypto", "cover", 21.0, 11.7, -4.0, 0.11, _recent(6)),
    ])
    assert dr.symbol_side_record("LINKUSDT", "crypto", "short") is None


def test_stale_history_is_excluded(mod):
    dr, conn = mod
    old = 24 * (dr._LOOKBACK_DAYS + 5)
    legs = []
    for i in (1, 2):
        legs += [
            (i, "OLDUSDT", "crypto", "short", 1.0, 10.0, None, 0.01,
             _recent(old + 1)),
            (i, "OLDUSDT", "crypto", "cover", 1.0, 10.0, -1.0, 0.01,
             _recent(old)),
        ]
    _seed(conn, legs=legs)
    assert dr.symbol_side_record("OLDUSDT", "crypto", "short") is None


def test_fee_reality_reads_the_ledger_not_a_constant(mod):
    dr, conn = mod
    legs = []
    for i in range(1, dr._MIN_N_MARKET + 1):
        # $1000 notional, $0.45/side => 0.090% round trip
        legs += [
            (i, f"S{i}USDT", "crypto", "short", 100.0, 10.0, None, 0.45,
             _recent(i + 1)),
            (i, f"S{i}USDT", "crypto", "cover", 100.0, 10.0, -0.05, 0.45,
             _recent(i)),
        ]
    _seed(conn, legs=legs)
    rec = dr.fee_reality("crypto")
    assert rec is not None
    assert rec["median_rt_pct"] == pytest.approx(0.090, abs=0.001)
    assert "0.090%" in dr.reference_block("S1USDT", "crypto")


def test_exit_author_record_counts_mechanisms(mod):
    dr, conn = mod
    mechs = [(1, _recent(i), json.dumps(
        {"mechanism": "breakeven_ratchet", "reason": "trailing_lock",
         "total": -0.30, "peak": 1.50})) for i in range(dr._MIN_N_MARKET)]
    _seed(conn, legs=[
        (1, "AUSDT", "crypto", "short", 1.0, 10.0, None, 0.01, _recent(2)),
        (1, "AUSDT", "crypto", "cover", 1.0, 10.0, -0.30, 0.01, _recent(1)),
    ], mechs=mechs)
    rec = dr.exit_author_record("crypto")
    assert rec is not None
    m = rec["mechanisms"][0]
    assert m["mechanism"] == "breakeven_ratchet"
    assert m["n"] == dr._MIN_N_MARKET and m["positive"] == 0
    assert m["median_giveback"] > 1.0  # gave back more than the whole peak
    block = dr.reference_block("AUSDT", "crypto")
    assert "breakeven_ratchet" in block
    assert "not fault" in block  # the framing correction must survive


def test_direction_record_splits_long_and_short(mod):
    dr, conn = mod
    legs = []
    for i in range(1, 5):  # 4 shorts, all losing
        legs += [
            (i, f"S{i}", "crypto", "short", 1.0, 10.0, None, 0.01,
             _recent(i + 1)),
            (i, f"S{i}", "crypto", "cover", 1.0, 10.0, -1.0, 0.01, _recent(i)),
        ]
    for i in range(5, 8):  # 3 longs, all winning
        legs += [
            (i, f"L{i}", "crypto", "buy", 1.0, 10.0, None, 0.01,
             _recent(i + 1)),
            (i, f"L{i}", "crypto", "sell", 1.0, 10.0, 1.0, 0.01, _recent(i)),
        ]
    _seed(conn, legs=legs)
    rec = dr.direction_record("crypto")
    assert rec is not None
    assert rec["by_side"]["short"]["n"] == 4
    assert rec["by_side"]["short"]["wins"] == 0
    assert rec["by_side"]["long"]["wins"] == 3
    assert "YOUR DIRECTIONAL RECORD" in dr.reference_block("S1", "crypto")


def test_block_is_empty_when_nothing_is_measurable(mod):
    dr, conn = mod
    _seed(conn, legs=[])
    assert dr.reference_block("ANY", "crypto", "long") == ""


def test_every_query_fails_soft(mod, monkeypatch):
    dr, _ = mod

    def boom(market):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(dr, "_closed_trips", boom)
    dr._CACHE.clear()
    assert dr.symbol_side_record("X", "crypto", "long") is None
    assert dr.direction_record("crypto") is None
    assert dr.fee_reality("crypto") is None
    assert dr.reference_block("X", "crypto", "long") == ""


def test_block_states_facts_not_instructions(mod):
    """The module must not grow a veto. desk_record's history is why."""
    dr, conn = mod
    legs = []
    for i in range(1, dr._MIN_N_MARKET + 2):
        legs += [
            (i, "S1", "crypto", "short", 1.0, 10.0, None, 0.01, _recent(i + 1)),
            (i, "S1", "crypto", "cover", 1.0, 10.0, -1.0, 0.01, _recent(i)),
        ]
    _seed(conn, legs=legs)
    block = dr.reference_block("S1", "crypto", "short")
    assert block
    lowered = block.lower()
    for banned in ("do not open", "you must", "forbidden", "never take",
                   "refuse"):
        assert banned not in lowered, f"grew an instruction: {banned}"
    assert "your call" in lowered


# ── wiring: the block must actually reach the prompt ───────────────────────
# `brief-line-wiring-is-untested-by-default` — a line was once unwired in
# this repo and every test still passed, because the helpers were tested for
# RENDERING and never for CONCATENATION.

def test_ledger_line_is_wired_into_position_state(monkeypatch):
    import run_engine

    monkeypatch.setattr(run_engine, "_desk_ledger_enabled", lambda: True)
    fake = types.ModuleType("desk_reference")
    fake.reference_block = lambda symbol, market, side=None: (
        f"<<LEDGER {symbol}/{market}/{side}>>")
    monkeypatch.setitem(sys.modules, "desk_reference", fake)

    # Silence every other brief helper so a pass here cannot be borrowed.
    for name in dir(run_engine):
        if name.startswith("_") and name.endswith("_line") \
                and name != "_desk_ledger_line":
            try:
                monkeypatch.setattr(run_engine, name, lambda *a, **k: "")
            except AttributeError:
                pass

    out = run_engine._compose_position_state(
        {"id": 1, "symbol": "LINKUSDT", "market": "crypto"},
        {}, 0.0, {"direction": "short"})
    assert "<<LEDGER LINKUSDT/crypto/short>>" in out, \
        "desk_ledger block never reached the composed prompt"


def test_ledger_line_is_off_by_default(monkeypatch):
    import run_engine
    monkeypatch.delenv("DESK_LEDGER_BLOCK", raising=False)
    assert run_engine._desk_ledger_line(
        {"id": 1, "symbol": "X", "market": "crypto"}, {},
        {"direction": "short"}) == ""


def test_ledger_line_survives_a_broken_registry(monkeypatch):
    import run_engine
    monkeypatch.setattr(run_engine, "_desk_ledger_enabled", lambda: True)
    broken = types.ModuleType("desk_reference")

    def _boom(*a, **k):
        raise RuntimeError("registry down")

    broken.reference_block = _boom
    monkeypatch.setitem(sys.modules, "desk_reference", broken)
    assert run_engine._desk_ledger_line(
        {"id": 1, "symbol": "X", "market": "crypto"}, {},
        {"direction": "short"}) == ""
