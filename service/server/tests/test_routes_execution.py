"""Integration tests for execution route endpoints."""
from __future__ import annotations

import hashlib
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
from routes_shared import utc_now_iso_z


def _create_agent(name: str = "exec-route-agent", token_raw: str = "tok-exec") -> tuple[int, str]:
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, 100000.0)",
        (name, token_hash),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id, token_raw


class BrokersEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_brokers_returns_200(self):
        resp = self.client.get("/api/execution/brokers")
        self.assertEqual(resp.status_code, 200)

    def test_list_brokers_contains_alpaca(self):
        resp = self.client.get("/api/execution/brokers")
        self.assertIn("alpaca", resp.json()["brokers"])

    def test_list_brokers_contains_binance(self):
        resp = self.client.get("/api/execution/brokers")
        self.assertIn("binance", resp.json()["brokers"])


class AccountsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent()
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_account_returns_201(self):
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 201)

    def test_create_account_returns_account_id(self):
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.assertIn("account_id", resp.json())

    def test_create_account_defaults_to_paper_mode(self):
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "binance", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.assertEqual(resp.json()["execution_mode"], "paper")

    def test_create_account_invalid_broker_returns_422(self):
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "robinhood", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 422)

    def test_list_accounts_returns_200(self):
        self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        resp = self.client.get("/api/execution/accounts", headers=self.auth)
        self.assertEqual(resp.status_code, 200)

    def test_list_accounts_shows_created_account(self):
        self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        resp = self.client.get("/api/execution/accounts", headers=self.auth)
        accounts = resp.json()["accounts"]
        self.assertGreater(len(accounts), 0)
        self.assertEqual(accounts[0]["broker"], "alpaca")

    def test_unauthenticated_returns_401(self):
        resp = self.client.get("/api/execution/accounts")
        self.assertEqual(resp.status_code, 401)


class ExecutionModeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("mode-agent", "tok-mode")
        self.auth = {"Authorization": f"Bearer {self.token}"}
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.account_id = resp.json()["account_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_mode_to_shadow_returns_200(self):
        resp = self.client.put(
            f"/api/execution/accounts/{self.account_id}/mode",
            json={"mode": "shadow"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200)

    def test_set_mode_returns_updated_mode(self):
        resp = self.client.put(
            f"/api/execution/accounts/{self.account_id}/mode",
            json={"mode": "shadow"},
            headers=self.auth,
        )
        self.assertEqual(resp.json()["execution_mode"], "shadow")

    def test_set_live_without_tcs_returns_403(self):
        resp = self.client.put(
            f"/api/execution/accounts/{self.account_id}/mode",
            json={"mode": "live"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 403)

    def test_set_invalid_mode_returns_422(self):
        resp = self.client.put(
            f"/api/execution/accounts/{self.account_id}/mode",
            json={"mode": "yolo"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 422)


class TcsAcceptEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("tcs-agent", "tok-tcs")
        self.auth = {"Authorization": f"Bearer {self.token}"}
        resp = self.client.post(
            "/api/execution/accounts",
            json={"broker": "alpaca", "api_key": "K", "api_secret": "S"},
            headers=self.auth,
        )
        self.account_id = resp.json()["account_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_accept_tcs_returns_201(self):
        resp = self.client.post(
            "/api/execution/tcs-accept",
            json={"broker": "alpaca"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 201)

    def test_accept_tcs_response_has_message(self):
        resp = self.client.post(
            "/api/execution/tcs-accept",
            json={"broker": "alpaca"},
            headers=self.auth,
        )
        self.assertIn("message", resp.json())

    def test_after_tcs_can_switch_to_live(self):
        self.client.post(
            "/api/execution/tcs-accept",
            json={"broker": "alpaca"},
            headers=self.auth,
        )
        resp = self.client.put(
            f"/api/execution/accounts/{self.account_id}/mode",
            json={"mode": "live"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["execution_mode"], "live")

    def test_accept_unknown_broker_returns_400(self):
        resp = self.client.post(
            "/api/execution/tcs-accept",
            json={"broker": "bad-broker"},
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)


class OrdersEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent_id, self.token = _create_agent("orders-agent", "tok-orders")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_orders_empty_on_fresh_db(self):
        resp = self.client.get("/api/execution/orders", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["orders"], [])

    def test_list_orders_requires_auth(self):
        resp = self.client.get("/api/execution/orders")
        self.assertEqual(resp.status_code, 401)

    def test_get_nonexistent_order_returns_404(self):
        resp = self.client.get("/api/execution/orders/9999", headers=self.auth)
        self.assertEqual(resp.status_code, 404)

    def test_reconciliations_empty_on_fresh_db(self):
        resp = self.client.get("/api/execution/reconciliations", headers=self.auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reconciliations"], [])


if __name__ == "__main__":
    unittest.main()
