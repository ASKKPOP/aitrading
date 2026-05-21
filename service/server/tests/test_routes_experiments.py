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


def _register_agent(client: TestClient, name: str = "experimenter") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": "pw123", "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_experiment(client: TestClient, token: str, key: str = "test-exp") -> dict:
    resp = client.post(
        "/api/experiments",
        json={
            "experiment_key": key,
            "title": "Test Experiment",
            "status": "active",
            "variants_json": [
                {"key": "control", "weight": 1},
                {"key": "treatment", "weight": 1},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class ExperimentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent = _register_agent(self.client)
        self.token = self.agent["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # --- GET /api/experiments ---

    def test_list_experiments_is_public(self) -> None:
        resp = self.client.get("/api/experiments")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("experiments", resp.json())

    def test_list_experiments_empty_initially(self) -> None:
        resp = self.client.get("/api/experiments")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["experiments"], [])

    # --- POST /api/experiments ---

    def test_create_experiment_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/experiments",
            json={"title": "No Auth Exp", "variants_json": []},
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_experiment_success(self) -> None:
        data = _create_experiment(self.client, self.token)
        self.assertIn("experiment_key", data)
        self.assertEqual(data["experiment_key"], "test-exp")

    def test_create_experiment_appears_in_list(self) -> None:
        _create_experiment(self.client, self.token, key="listed-exp")
        resp = self.client.get("/api/experiments")
        self.assertEqual(resp.status_code, 200)
        keys = [e["experiment_key"] for e in resp.json()["experiments"]]
        self.assertIn("listed-exp", keys)

    def test_create_experiment_duplicate_key_rejected(self) -> None:
        _create_experiment(self.client, self.token, key="dup-key")
        resp = self.client.post(
            "/api/experiments",
            json={
                "experiment_key": "dup-key",
                "title": "Duplicate",
                "variants_json": [{"key": "a", "weight": 1}],
            },
            headers=self.headers,
        )
        self.assertNotEqual(resp.status_code, 200)

    # --- POST /api/experiments/{key}/status ---

    def test_update_status_requires_auth(self) -> None:
        _create_experiment(self.client, self.token, key="status-exp")
        resp = self.client.post(
            "/api/experiments/status-exp/status",
            json={"status": "paused"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_update_status_success(self) -> None:
        _create_experiment(self.client, self.token, key="pause-me")
        resp = self.client.post(
            "/api/experiments/pause-me/status",
            json={"status": "paused"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)

    # --- GET /api/experiments/{key}/assignments ---

    def test_get_assignments_is_public(self) -> None:
        _create_experiment(self.client, self.token, key="assign-exp")
        resp = self.client.get("/api/experiments/assign-exp/assignments")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("assignments", resp.json())

    def test_get_assignments_empty_initially(self) -> None:
        _create_experiment(self.client, self.token, key="empty-assign")
        resp = self.client.get("/api/experiments/empty-assign/assignments")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["assignments"], [])

    # --- POST /api/experiments/{key}/assign ---

    def test_assign_to_experiment_requires_auth(self) -> None:
        _create_experiment(self.client, self.token, key="join-exp")
        resp = self.client.post("/api/experiments/join-exp/assign")
        self.assertEqual(resp.status_code, 401)

    def test_assign_to_experiment_success(self) -> None:
        _create_experiment(self.client, self.token, key="join-me")
        resp = self.client.post(
            "/api/experiments/join-me/assign",
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("variant_key", body)
        self.assertIn(body["variant_key"], {"control", "treatment"})

    def test_assign_to_experiment_creates_assignment_record(self) -> None:
        _create_experiment(self.client, self.token, key="record-me")
        self.client.post("/api/experiments/record-me/assign", headers=self.headers)
        resp = self.client.get("/api/experiments/record-me/assignments")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["assignments"]), 1)

    # --- GET /api/agents/me/experiments ---

    def test_my_experiments_requires_auth(self) -> None:
        resp = self.client.get("/api/agents/me/experiments")
        self.assertEqual(resp.status_code, 401)

    def test_my_experiments_empty_initially(self) -> None:
        resp = self.client.get("/api/agents/me/experiments", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_my_experiments_includes_assigned(self) -> None:
        _create_experiment(self.client, self.token, key="my-exp")
        self.client.post("/api/experiments/my-exp/assign", headers=self.headers)
        resp = self.client.get("/api/agents/me/experiments", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Response uses "assignments" key (not "experiments")
        keys = [e.get("experiment_key") for e in body.get("assignments", [])]
        self.assertIn("my-exp", keys)

    # --- GET /api/agents/me/rewards ---

    def test_my_rewards_requires_auth(self) -> None:
        resp = self.client.get("/api/agents/me/rewards")
        self.assertEqual(resp.status_code, 401)

    def test_my_rewards_empty_initially(self) -> None:
        resp = self.client.get("/api/agents/me/rewards", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("rewards", resp.json())


if __name__ == "__main__":
    unittest.main()
