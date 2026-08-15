"""Young-position dump brief (owner-directed, 2026-08-13).

Live run 1104 (KAITO): short at 0.44731, FULLY covered 30 minutes later on a
−0.9% wiggle for −$10.14 — confidence 0.80 against conviction 0.30 — and the
tape then fell below the original entry. The single largest loss mechanism
on the book (the #245 class). No rail — exits are never refused; the desk is
handed the situation and a mandate: a full close must state why it beats a
half reduce. A telemetry flag journals every exit-shaped decision in the
situation so the class is measurable before/after.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database  # noqa: E402
import run_engine  # noqa: E402
import trading_runs  # noqa: E402
from routes import create_app  # noqa: E402


def _iso(dt):
    return dt.strftime(trading_runs.TS_FMT)


class BriefRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (id, name, token, starting_capital)"
                    " VALUES (6, 'yd', 't', 100000.0)")
        cur.execute(
            "INSERT INTO trading_runs (id, agent_id, symbol, market,"
            " market_type, status, config_snapshot_json, created_at,"
            " cycle_seq) VALUES (77, 6, 'KAITOUSDT', 'crypto', 'futures',"
            " 'running', '{}', ?, 2)",
            (_iso(datetime.now(timezone.utc) - timedelta(hours=1)),))
        conn.commit()
        conn.close()
        self.run = {"id": 77, "agent_id": 6, "symbol": "KAITOUSDT",
                    "market": "crypto"}
        self.cfg = {"interval_minutes": 30}

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_position(self, age_minutes, entry=0.44731, mark=0.44329,
                       qty=-2281.56):
        # default: short, mark ~0.9% ABOVE profit direction? mark < entry is
        # PROFIT for a short — use mark above entry for adverse.
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM positions WHERE run_id = 77")
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, current_price, opened_at, first_opened_at, run_id,"
            " price_updated_at, leverage) VALUES (6, 'KAITOUSDT', 'crypto',"
            " ?, ?, ?, ?, ?, ?, 77, ?, 1.0)",
            ("short" if qty < 0 else "long", qty, entry, mark,
             _iso(datetime.now(timezone.utc) - timedelta(minutes=age_minutes)),
             _iso(datetime.now(timezone.utc) - timedelta(minutes=age_minutes)),
             _iso(datetime.now(timezone.utc))))
        conn.commit()
        conn.close()

    def _brief(self, pos_qty):
        pnl = {"mark_age_ok": True,
               "position": None, "total": 0.0, "trades": 1}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantity, entry_price, current_price, leverage "
                    "FROM positions WHERE run_id = 77")
        row = cur.fetchone()
        conn.close()
        pnl["position"] = dict(row) if row else None
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=4.0):
            return run_engine._young_exit_brief(self.run, self.cfg, pos_qty)

    def test_young_noise_adverse_position_renders_the_mandate(self):
        # short 30 min old, price +0.9% against (KAITO shape, ordinary ~4%)
        self._seed_position(30, entry=0.44731, mark=0.45135)
        line = self._brief(-2281.56)
        self.assertIn("FULL close beats a HALF reduce", line)
        self.assertIn("ordinary daily range", line)

    def test_profit_is_silent(self):
        self._seed_position(30, entry=0.44731, mark=0.44329)  # short in profit
        self.assertEqual(self._brief(-2281.56), "")

    def test_old_position_is_silent(self):
        # 3 cycles × 30 min = 90; 120 minutes old ⇒ the desk judges freely
        self._seed_position(120, entry=0.44731, mark=0.45135)
        self.assertEqual(self._brief(-2281.56), "")

    def test_real_move_is_silent(self):
        # adverse 0.9% vs ordinary 0.5% ⇒ bigger than an ordinary day: silent
        self._seed_position(30, entry=0.44731, mark=0.45135)
        pnl = {"mark_age_ok": True, "total": 0.0, "trades": 1,
               "position": {"quantity": -2281.56, "entry_price": 0.44731,
                            "current_price": 0.45135, "leverage": 1.0}}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=0.5):
            self.assertEqual(
                run_engine._young_exit_brief(self.run, self.cfg, -2281.56), "")

    def test_flat_is_silent(self):
        self.assertEqual(
            run_engine._young_exit_brief(self.run, self.cfg, 0.0), "")

    def test_wired_into_both_prompt_paths(self):
        import inspect
        import run_engine
        self.assertIn("_young_exit_brief(run, cfg, pos_qty)",
                      inspect.getsource(run_engine._compose_position_state),
                      "brief must be in the composed prompt (both paths)")


class DumpFlagTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "yd-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _run(self) -> int:
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0},
            headers={"Authorization": f"Bearer {self.token}"}).json()["id"]
        assert self.client.post(
            f"/api/runs/{run_id}/start",
            headers={"Authorization": f"Bearer {self.token}"}
        ).status_code == 200
        return run_id

    def _seed_young_losing_long(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, current_price, opened_at, first_opened_at, run_id,"
            " price_updated_at, leverage) VALUES (?, 'BTC', 'crypto', 'long',"
            " 5.0, 100.5, 100.0, ?, ?, ?, ?, 1.0)",
            (self.agent_id, _iso(now - timedelta(minutes=20)),
             _iso(now - timedelta(minutes=20)), run_id, _iso(now)))
        conn.commit()
        conn.close()

    def _events(self, run_id, kind):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND"
                    " event_type = ?", (run_id, kind))
        out = [json.loads(r["payload"]) for r in cur.fetchall()]
        conn.close()
        return out

    def _analysis(self, action):
        return {"symbol": "BTC", "market": "crypto", "analysts": {},
                "decision": {"action": action, "confidence": 0.8,
                             "scores": {"thesis_alignment": 0.2,
                                        "momentum_quality": 0.3,
                                        "entry_quality": 0.5,
                                        "risk_context": 0.2},
                             "entry": 100.0, "report": "r"}}

    def test_exit_on_young_noise_position_is_flagged(self):
        run_id = self._run()
        self._seed_young_losing_long(run_id)
        with patch("analysis_agents.run_analysis",
                   return_value=self._analysis("sell")), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=4.0):
            run_engine.run_cycle(run_id)
        flags = self._events(run_id, "young_dump_flag")
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["action"], "sell")
        self.assertAlmostEqual(flags[0]["confidence"], 0.8)

    def test_hold_is_not_flagged(self):
        run_id = self._run()
        self._seed_young_losing_long(run_id)
        with patch("analysis_agents.run_analysis",
                   return_value=self._analysis("hold")), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=4.0):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "young_dump_flag"), [])


if __name__ == "__main__":
    unittest.main()
