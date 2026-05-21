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


def _register(client: TestClient, name: str = "trader", password: str = "pw123") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": password, "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TradingRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- /api/profit/history (leaderboard) ---

    def test_profit_history_is_public(self) -> None:
        resp = self.client.get("/api/profit/history")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("top_agents", body)

    def test_profit_history_empty_db(self) -> None:
        resp = self.client.get("/api/profit/history")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["top_agents"], [])

    def test_profit_history_includes_registered_agent(self) -> None:
        _register(self.client, name="leaderboard-agent")
        resp = self.client.get("/api/profit/history?limit=10")
        self.assertEqual(resp.status_code, 200)
        names = [a["name"] for a in resp.json()["top_agents"]]
        self.assertIn("leaderboard-agent", names)

    def test_profit_history_metric_param_accepted(self) -> None:
        for metric in ("return", "risk", "collaboration", "quality"):
            resp = self.client.get(f"/api/profit/history?metric={metric}")
            self.assertEqual(resp.status_code, 200, metric)

    # --- /api/leaderboard/position-pnl ---

    def test_position_pnl_leaderboard_is_public(self) -> None:
        resp = self.client.get("/api/leaderboard/position-pnl")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("top_agents", resp.json())

    # --- /api/trending ---

    def test_trending_symbols_is_public(self) -> None:
        resp = self.client.get("/api/trending")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("trending", resp.json())

    # --- /api/positions (my positions) ---

    def test_my_positions_requires_auth(self) -> None:
        resp = self.client.get("/api/positions")
        self.assertEqual(resp.status_code, 401)

    def test_my_positions_success(self) -> None:
        agent = _register(self.client)
        resp = self.client.get(
            "/api/positions",
            headers={"Authorization": f"Bearer {agent['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("positions", body)
        self.assertEqual(body["positions"], [])

    def test_my_positions_invalid_token_rejected(self) -> None:
        resp = self.client.get(
            "/api/positions",
            headers={"Authorization": "Bearer bogus"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- /api/agents/{agent_id}/positions ---

    def test_agent_positions_is_public(self) -> None:
        agent = _register(self.client, name="pos-agent")
        resp = self.client.get(f"/api/agents/{agent['agent_id']}/positions")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("positions", body)
        self.assertEqual(body["agent_name"], "pos-agent")

    # --- /api/agents/{agent_id}/summary ---

    def test_agent_summary_is_public(self) -> None:
        agent = _register(self.client, name="summary-agent")
        resp = self.client.get(f"/api/agents/{agent['agent_id']}/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("agent_name", body)
        self.assertEqual(body["agent_name"], "summary-agent")

    # --- /api/signals/follow ---

    def test_follow_requires_auth(self) -> None:
        resp = self.client.post("/api/signals/follow", json={"leader_id": 1})
        self.assertEqual(resp.status_code, 401)

    def test_follow_self_rejected(self) -> None:
        agent = _register(self.client, name="self-follower")
        resp = self.client.post(
            "/api/signals/follow",
            json={"leader_id": agent["agent_id"]},
            headers={"Authorization": f"Bearer {agent['token']}"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_follow_success(self) -> None:
        leader = _register(self.client, name="leader-agent")
        follower = _register(self.client, name="follower-agent")
        resp = self.client.post(
            "/api/signals/follow",
            json={"leader_id": leader["agent_id"]},
            headers={"Authorization": f"Bearer {follower['token']}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_follow_idempotent(self) -> None:
        leader = _register(self.client, name="leader2")
        follower = _register(self.client, name="follower2")
        headers = {"Authorization": f"Bearer {follower['token']}"}
        payload = {"leader_id": leader["agent_id"]}
        self.client.post("/api/signals/follow", json=payload, headers=headers)
        resp = self.client.post("/api/signals/follow", json=payload, headers=headers)
        self.assertEqual(resp.status_code, 200)

    # --- /api/signals/unfollow ---

    def test_unfollow_requires_auth(self) -> None:
        resp = self.client.post("/api/signals/unfollow", json={"leader_id": 1})
        self.assertEqual(resp.status_code, 401)

    def test_unfollow_success(self) -> None:
        leader = _register(self.client, name="lead3")
        follower = _register(self.client, name="follow3")
        headers = {"Authorization": f"Bearer {follower['token']}"}
        self.client.post(
            "/api/signals/follow",
            json={"leader_id": leader["agent_id"]},
            headers=headers,
        )
        resp = self.client.post(
            "/api/signals/unfollow",
            json={"leader_id": leader["agent_id"]},
            headers=headers,
        )
        self.assertEqual(resp.status_code, 200)


    # --- /api/agents/{id}/equity-curve ---

    _TS_BUY  = "2026-04-01T15:00:00Z"   # Tuesday, 11am ET
    _TS_SELL = "2026-04-02T15:00:00Z"   # Wednesday, 11am ET

    def test_equity_curve_empty_when_no_trades(self) -> None:
        agent = _register(self.client, name="eq-empty")
        resp = self.client.get(f"/api/agents/{agent['agent_id']}/equity-curve")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("agent_id", body)
        self.assertIn("curve", body)
        self.assertEqual(body["curve"], [])

    def test_equity_curve_not_found_agent(self) -> None:
        resp = self.client.get("/api/agents/99999/equity-curve")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["curve"], [])

    def test_equity_curve_days_param_clamped(self) -> None:
        agent = _register(self.client, name="eq-days")
        resp = self.client.get(f"/api/agents/{agent['agent_id']}/equity-curve?days=999")
        self.assertEqual(resp.status_code, 200)

    def test_equity_curve_has_correct_shape(self) -> None:
        import os
        from unittest.mock import patch as _mock_patch

        agent = _register(self.client, name="eq-shape")
        token = agent["token"]
        agent_id = agent["agent_id"]

        with _mock_patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            self.client.post("/api/signals/realtime",
                json={"market": "us-stock", "action": "buy", "symbol": "AAPL",
                      "price": 100.0, "quantity": 10.0, "executed_at": self._TS_BUY},
                headers={"Authorization": f"Bearer {token}"},
            )
            self.client.post("/api/signals/realtime",
                json={"market": "us-stock", "action": "sell", "symbol": "AAPL",
                      "price": 110.0, "quantity": 10.0, "executed_at": self._TS_SELL},
                headers={"Authorization": f"Bearer {token}"},
            )

        resp = self.client.get(f"/api/agents/{agent_id}/equity-curve?days=365")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["agent_id"], agent_id)
        curve = body["curve"]
        self.assertGreater(len(curve), 1)
        for point in curve:
            self.assertIn("t", point)
            self.assertIn("v", point)
            self.assertIsInstance(point["v"], (int, float))

    def test_equity_curve_profitable_trade_ends_above_start(self) -> None:
        import os
        from unittest.mock import patch as _mock_patch

        agent = _register(self.client, name="eq-profit")
        token = agent["token"]
        agent_id = agent["agent_id"]

        with _mock_patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            self.client.post("/api/signals/realtime",
                json={"market": "us-stock", "action": "buy", "symbol": "AAPL",
                      "price": 100.0, "quantity": 10.0, "executed_at": self._TS_BUY},
                headers={"Authorization": f"Bearer {token}"},
            )
            self.client.post("/api/signals/realtime",
                json={"market": "us-stock", "action": "sell", "symbol": "AAPL",
                      "price": 110.0, "quantity": 10.0, "executed_at": self._TS_SELL},
                headers={"Authorization": f"Bearer {token}"},
            )

        resp = self.client.get(f"/api/agents/{agent_id}/equity-curve?days=365")
        curve = resp.json()["curve"]
        self.assertGreater(curve[-1]["v"], curve[0]["v"])


if __name__ == "__main__":
    unittest.main()
