"""Tests for GET /api/agents/{agent_id}/profile endpoint.

TDD RED phase: these tests must fail before the endpoint is implemented.
"""

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


def _register(client: TestClient, name: str = "agent-alpha", password: str = "pw123") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": password, "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


_TS = "2026-04-01T15:00:00Z"  # Tuesday, 11am ET — within NYSE market hours


def _post_signal(client: TestClient, token: str, symbol: str, action: str, price: float, qty: float) -> dict:
    resp = client.post(
        "/api/signals/realtime",
        json={
            "market": "us-stock",
            "action": action,
            "symbol": symbol,
            "price": price,
            "quantity": qty,
            "executed_at": _TS,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class AgentProfileEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_profile_returns_200_json_for_existing_agent(self) -> None:
        data = _register(self.client)
        agent_id = data["agent_id"]
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type", ""), "application/json")

    def test_profile_returns_404_for_missing_agent(self) -> None:
        resp = self.client.get("/api/agents/99999/profile")
        self.assertEqual(resp.status_code, 404)

    def test_profile_contains_basic_fields(self) -> None:
        data = _register(self.client, name="alpha-bot")
        agent_id = data["agent_id"]
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        profile = resp.json()
        self.assertEqual(profile["agent_id"], agent_id)
        self.assertEqual(profile["name"], "alpha-bot")
        self.assertIn("cash", profile)
        self.assertIn("profit_pct", profile)
        self.assertIn("trade_count", profile)
        self.assertIn("recent_signals", profile)
        self.assertIn("equity_curve", profile)

    def test_profile_trade_count_reflects_signals(self) -> None:
        data = _register(self.client, name="trader-bot")
        token = data["token"]
        agent_id = data["agent_id"]
        _post_signal(self.client, token, "AAPL", "buy", 180.0, 10)
        _post_signal(self.client, token, "AAPL", "sell", 190.0, 10)
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        profile = resp.json()
        self.assertEqual(profile["trade_count"], 2)

    def test_profile_recent_signals_capped_at_20(self) -> None:
        data = _register(self.client, name="heavy-trader")
        token = data["token"]
        agent_id = data["agent_id"]
        for i in range(25):
            _post_signal(self.client, token, "MSFT", "buy", 400.0 + i, 1)
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        profile = resp.json()
        self.assertLessEqual(len(profile["recent_signals"]), 20)

    def test_profile_equity_curve_is_list(self) -> None:
        data = _register(self.client)
        agent_id = data["agent_id"]
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        profile = resp.json()
        self.assertIsInstance(profile["equity_curve"], list)

    def test_profile_profit_pct_is_zero_for_fresh_agent(self) -> None:
        data = _register(self.client, name="fresh-agent")
        agent_id = data["agent_id"]
        resp = self.client.get(f"/api/agents/{agent_id}/profile")
        profile = resp.json()
        self.assertAlmostEqual(profile["profit_pct"], 0.0, places=2)
