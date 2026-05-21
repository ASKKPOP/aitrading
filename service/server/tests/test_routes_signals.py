import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app

# A Tuesday within NYSE market hours (10:00 AM ET) — safe historical timestamp for us-stock.
_MARKET_TS = "2024-01-02T15:00:00Z"


def _register(client: TestClient, name: str = "signal-agent", password: str = "pw123") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": password, "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class SignalRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent = _register(self.client)
        self.headers = {"Authorization": f"Bearer {self.agent['token']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- POST /api/signals/strategy ---

    def test_post_strategy_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "My plan", "content": "Go long AAPL"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_post_strategy_success(self) -> None:
        resp = self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "My plan", "content": "Go long AAPL"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("signal_id", body)
        self.assertTrue(body.get("success"))

    def test_post_strategy_invalid_token_rejected(self) -> None:
        resp = self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "Plan", "content": "x"},
            headers={"Authorization": "Bearer fake"},
        )
        self.assertEqual(resp.status_code, 401)

    # --- POST /api/signals/discussion ---

    def test_post_discussion_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/signals/discussion",
            json={"market": "us-stock", "title": "Thoughts?", "content": "What do you think?"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_post_discussion_success(self) -> None:
        resp = self.client.post(
            "/api/signals/discussion",
            json={"market": "us-stock", "title": "Thoughts?", "content": "What do you think?"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("signal_id", body)
        self.assertTrue(body.get("success"))

    # --- GET /api/signals/grouped ---

    def test_get_signals_grouped_is_public(self) -> None:
        resp = self.client.get("/api/signals/grouped")
        self.assertEqual(resp.status_code, 200)

    def test_get_signals_grouped_includes_posted_strategy(self) -> None:
        self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "Strat A", "content": "Details"},
            headers=self.headers,
        )
        resp = self.client.get("/api/signals/grouped?message_type=strategy")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("agents", body)
        self.assertGreaterEqual(len(body["agents"]), 1)

    # --- GET /api/signals/feed ---

    def test_get_signal_feed_is_public(self) -> None:
        resp = self.client.get("/api/signals/feed")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("signals", resp.json())

    def test_get_signal_feed_contains_posted_discussion(self) -> None:
        self.client.post(
            "/api/signals/discussion",
            json={"market": "us-stock", "title": "Hot take", "content": "Bear market incoming"},
            headers=self.headers,
        )
        resp = self.client.get("/api/signals/feed")
        self.assertEqual(resp.status_code, 200)
        titles = [s.get("title") for s in resp.json()["signals"]]
        self.assertIn("Hot take", titles)

    # --- GET /api/signals/{agent_id} ---

    def test_get_agent_signals_is_public(self) -> None:
        resp = self.client.get(f"/api/signals/{self.agent['agent_id']}")
        self.assertEqual(resp.status_code, 200)

    def test_get_agent_signals_includes_own_strategy(self) -> None:
        self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "Agent strat", "content": "Details"},
            headers=self.headers,
        )
        resp = self.client.get(f"/api/signals/{self.agent['agent_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("signals", body)
        self.assertGreaterEqual(len(body["signals"]), 1)

    # --- POST /api/signals/reply ---

    def _post_strategy(self) -> int:
        resp = self.client.post(
            "/api/signals/strategy",
            json={"market": "us-stock", "title": "Reply target", "content": "To be replied to"},
            headers=self.headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["signal_id"]

    def test_reply_requires_auth(self) -> None:
        signal_id = self._post_strategy()
        resp = self.client.post(
            "/api/signals/reply",
            json={"signal_id": signal_id, "content": "Great idea"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_reply_success(self) -> None:
        signal_id = self._post_strategy()
        resp = self.client.post(
            "/api/signals/reply",
            json={"signal_id": signal_id, "content": "Great idea"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_reply_to_nonexistent_signal_rejected(self) -> None:
        resp = self.client.post(
            "/api/signals/reply",
            json={"signal_id": 99999, "content": "Hello?"},
            headers=self.headers,
        )
        self.assertIn(resp.status_code, (400, 404))

    # --- POST /api/signals/realtime (buy trade) ---

    def test_realtime_signal_buy_us_stock(self) -> None:
        # ALLOW_SYNC_PRICE_FETCH_IN_API defaults to false, so data.price is used directly.
        with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            resp = self.client.post(
                "/api/signals/realtime",
                json={
                    "market": "us-stock",
                    "action": "buy",
                    "symbol": "AAPL",
                    "price": 150.0,
                    "quantity": 1.0,
                    "executed_at": _MARKET_TS,
                },
                headers=self.headers,
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("signal_id", body)
        self.assertTrue(body.get("success"))

    def test_realtime_signal_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/signals/realtime",
            json={
                "market": "us-stock",
                "action": "buy",
                "symbol": "AAPL",
                "price": 150.0,
                "quantity": 1.0,
                "executed_at": _MARKET_TS,
            },
        )
        self.assertEqual(resp.status_code, 401)

    def test_realtime_signal_sell_without_position_rejected(self) -> None:
        with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            resp = self.client.post(
                "/api/signals/realtime",
                json={
                    "market": "us-stock",
                    "action": "sell",
                    "symbol": "AAPL",
                    "price": 150.0,
                    "quantity": 1.0,
                    "executed_at": _MARKET_TS,
                },
                headers=self.headers,
            )
        self.assertEqual(resp.status_code, 400)

    def test_realtime_signal_zero_quantity_rejected(self) -> None:
        with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            resp = self.client.post(
                "/api/signals/realtime",
                json={
                    "market": "us-stock",
                    "action": "buy",
                    "symbol": "AAPL",
                    "price": 150.0,
                    "quantity": 0.0,
                    "executed_at": _MARKET_TS,
                },
                headers=self.headers,
            )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
