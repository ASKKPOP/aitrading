"""Add-churn guard (2026-07-25): bound same-direction adds on an open position.

Fleet 17 live finding: SOL re-shorted 5× at conf 0.58 into a flat tape —
every 45-min cycle averaged into a losing short, stacking fees. The guard is
config-driven (compose_run_settings emits add_limits for fleet runs): at most
max_adds additional same-direction opens per open position, and at least
cooldown_minutes between opens. Reduce/close orders are never limited.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine

TS = "%Y-%m-%dT%H:%M:%SZ"


def _iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(minutes=minutes_ago)).strftime(TS)


class AddLimitBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, cash) VALUES ('a', 100000)")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type,"
            " status, config_snapshot_json, start_condition_json,"
            " stop_conditions_json, created_at) VALUES (1,'SOL','crypto',"
            "'futures','running','{}','{}','{}','2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()
        self.run_row = {"id": 1, "agent_id": 1, "symbol": "SOL",
                        "market": "crypto", "market_type": "futures"}

    def tearDown(self):
        self.tmp.cleanup()

    def _position(self, qty):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, opened_at, run_id) VALUES (1,'SOL','crypto',?,?,"
            " 74.0,'2026-01-01T00:00:00Z',1)",
            ("short" if qty < 0 else "buy", qty))
        conn.commit()
        conn.close()

    _sig = 800000

    def _open(self, side, minutes_ago):
        AddLimitBase._sig += 1
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market,"
            " signal_type, symbol, side, entry_price, quantity, content,"
            " timestamp, created_at, executed_at, run_id) VALUES (?,1,"
            "'operation','crypto','automation','SOL',?,74.0,1,'t',0,?,?,1)",
            (AddLimitBase._sig, side, _iso(minutes_ago), _iso(minutes_ago)))
        conn.commit()
        conn.close()

    CFG = {"add_limits": {"max_adds": 2, "cooldown_minutes": 90}}


class AddLimitUnitTests(AddLimitBase):
    def test_no_limits_config_passes(self):
        self._position(-5)
        self._open("short", 200)
        self.assertIsNone(run_engine._add_limit_skip(self.run_row, {}, "sell"))

    def test_flat_book_passes(self):
        self.assertIsNone(
            run_engine._add_limit_skip(self.run_row, self.CFG, "sell"))

    def test_first_add_within_budget_passes(self):
        self._position(-5)
        self._open("short", 200)                     # initial open, adds=0
        self.assertIsNone(
            run_engine._add_limit_skip(self.run_row, self.CFG, "sell"))

    def test_max_adds_blocks(self):
        self._position(-5)
        for m in (300, 200, 100):                    # open + 2 adds = cap
            self._open("short", m)
        skip = run_engine._add_limit_skip(self.run_row, self.CFG, "sell")
        self.assertIsNotNone(skip)
        self.assertIn("max", skip)

    def test_cooldown_blocks_recent_add(self):
        self._position(-5)
        self._open("short", 10)                      # opened 10 min ago
        skip = run_engine._add_limit_skip(self.run_row, self.CFG, "sell")
        self.assertIsNotNone(skip)
        self.assertIn("cooldown", skip)

    def test_reduce_orders_never_limited(self):
        self._position(-5)
        for m in (300, 200, 100, 10):
            self._open("short", m)
        # buy against a short book = cover (reduce) — always allowed
        self.assertIsNone(
            run_engine._add_limit_skip(self.run_row, self.CFG, "buy"))

    def test_long_book_buy_add_limited(self):
        self.run_row["market_type"] = "spot"
        self._position(5)
        for m in (300, 200, 100):
            self._open("buy", m)
        skip = run_engine._add_limit_skip(self.run_row, self.CFG, "buy")
        self.assertIn("max", skip or "")


class ComposeEmitsLimitsTests(unittest.TestCase):
    def test_compose_run_settings_includes_add_limits(self):
        import fleet_planner as fp
        thesis = {"symbol": "AAA", "market": "crypto", "direction": "short",
                  "confidence": 0.7, "expected_move_pct": 2.0,
                  "horizon_hours": 24}
        settings = fp.compose_run_settings(thesis, 1000.0,
                                           {"risk_appetite": "aggressive"})
        al = settings.get("add_limits")
        self.assertIsInstance(al, dict)
        self.assertGreaterEqual(int(al["max_adds"]), 1)
        self.assertGreaterEqual(float(al["cooldown_minutes"]), 30)


class BuildWiresLimitsTests(unittest.TestCase):
    """add_limits must survive into the member run's config snapshot —
    compose emits it, _do_build must carry it into core (like thesis)."""

    def test_built_member_config_carries_add_limits(self):
        from test_fleet_planner import FleetTestBase, _seed_batch
        import fleet_planner as fp

        class _T(FleetTestBase):
            def runTest(self):  # noqa: N802
                _seed_batch()
                fleet_id = self._fleet(n=1, budget=1000.0)
                fp.start_fleet(fleet_id, self.agent_id)
                fp._do_research(fp.get_fleet(fleet_id))
                fp._do_build(fp.get_fleet(fleet_id))
                member = fp.list_members(fleet_id)[0]
                cfg = json.loads(member["config_snapshot_json"])
                assert isinstance(cfg.get("add_limits"), dict), cfg.keys()
                assert int(cfg["add_limits"]["max_adds"]) >= 1

        t = _T()
        t.setUp()
        try:
            t.runTest()
        finally:
            t.tearDown()


if __name__ == "__main__":
    unittest.main()
