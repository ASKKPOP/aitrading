"""Admin capital reset (routes_admin_manage.py): every agent of a member goes
to cash = starting_capital = amount, deposited = 0, open positions and the
profit_history equity curve wiped — displayed profit exactly zero."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


class AdminResetCapitalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    ("member@x.com", "x"))
        self.user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, user_id, cash, starting_capital, deposited) "
            "VALUES (?, ?, ?, ?, ?)",
            ("reset-me", self.user_id, 55_000.0, 100_000.0, 500.0))
        self.agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity, "
            "entry_price, opened_at) VALUES (?, 'BTC', 'crypto', 'long', 0.5, "
            "60000, datetime('now'))", (self.agent_id,))
        cur.execute(
            "INSERT INTO profit_history (agent_id, total_value, cash, "
            "position_value, profit) VALUES (?, 90000, 55000, 35000, -10000)",
            (self.agent_id,))
        # A closed fill (the automation profit tiles sum operation signals)
        # and a social post that must SURVIVE the reset.
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market, "
            "symbol, side, entry_price, exit_price, quantity, pnl, timestamp, "
            "created_at) VALUES (901, ?, 'operation', 'crypto', 'BTC', 'sell', "
            "60000, 58000, 0.5, -1000, 1, '2026-08-01T00:00:00Z')", (self.agent_id,))
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market, "
            "symbol, timestamp, created_at) VALUES (902, ?, 'discussion', "
            "'crypto', 'BTC', 2, '2026-08-01T00:00:00Z')", (self.agent_id,))
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, realized_pnl_usd, "
            "peak_pnl_usd, created_at) VALUES (?, 'BTC', -420.5, 100.0, "
            "'2026-08-01T00:00:00Z')", (self.agent_id,))
        conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def _agent_row(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT cash, starting_capital, COALESCE(deposited, 0) AS deposited, "
            "(SELECT COUNT(*) FROM positions WHERE agent_id = a.id) AS positions, "
            "(SELECT COUNT(*) FROM profit_history WHERE agent_id = a.id) AS history, "
            "(SELECT COUNT(*) FROM signals WHERE agent_id = a.id "
            " AND message_type = 'operation') AS fills, "
            "(SELECT COUNT(*) FROM signals WHERE agent_id = a.id "
            " AND message_type != 'operation') AS social, "
            "(SELECT COALESCE(SUM(ABS(realized_pnl_usd)), 0) FROM trading_runs "
            " WHERE agent_id = a.id) AS run_pnl_abs "
            "FROM agents a WHERE id = ?", (self.agent_id,))
        return dict(cur.fetchone())

    def test_requires_admin(self):
        r = self.client.post(f"/api/admin/members/{self.user_id}/reset-capital", json={})
        self.assertEqual(r.status_code, 401)

    def test_reset_defaults_to_10000_and_zeroes_everything(self):
        r = self.client.post(f"/api/admin/members/{self.user_id}/reset-capital",
                             json={}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["amount"], 10000.0)
        self.assertEqual(len(body["agents"]), 1)
        report = body["agents"][0]
        self.assertEqual(report["before"]["cash"], 55_000.0)
        self.assertEqual(report["positions_deleted"], 1)
        self.assertEqual(report["profit_history_deleted"], 1)
        self.assertEqual(report["trade_fills_deleted"], 1)
        self.assertEqual(report["runs_pnl_zeroed"], 1)
        row = self._agent_row()
        self.assertEqual(row["cash"], 10_000.0)
        self.assertEqual(row["starting_capital"], 10_000.0)
        self.assertEqual(row["deposited"], 0)
        self.assertEqual(row["positions"], 0)
        self.assertEqual(row["history"], 0)
        self.assertEqual(row["fills"], 0)      # trade ledger wiped
        self.assertEqual(row["social"], 1)     # discussion post survives
        self.assertEqual(row["run_pnl_abs"], 0)  # run tiles read zero
        # profit is cash − (starting + deposited) — exactly zero after reset
        self.assertEqual(row["cash"] - (row["starting_capital"] + row["deposited"]), 0)

    def test_custom_amount_and_validation(self):
        r = self.client.post(f"/api/admin/members/{self.user_id}/reset-capital",
                             json={"amount": 25_000}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._agent_row()["cash"], 25_000.0)
        bad = self.client.post(f"/api/admin/members/{self.user_id}/reset-capital",
                               json={"amount": -5}, headers=self.admin)
        self.assertEqual(bad.status_code, 400)

    def test_unknown_user_and_agentless_user(self):
        r = self.client.post("/api/admin/members/999999/reset-capital",
                             json={}, headers=self.admin)
        self.assertEqual(r.status_code, 404)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    ("noagent@x.com", "x"))
        bare_id = cur.lastrowid
        conn.commit()
        r = self.client.post(f"/api/admin/members/{bare_id}/reset-capital",
                             json={}, headers=self.admin)
        self.assertEqual(r.status_code, 404)

    def test_action_is_audited(self):
        self.client.post(f"/api/admin/members/{self.user_id}/reset-capital",
                         json={}, headers=self.admin)
        r = self.client.get("/api/admin/audit", headers=self.admin)
        actions = [e["action"] for e in r.json()["entries"]]
        self.assertIn("member.reset_capital", actions)


if __name__ == "__main__":
    unittest.main()
