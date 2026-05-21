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


def _register_agent(client: TestClient, name: str = "challenger") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": "pw123", "initial_balance": 100000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_challenge(client: TestClient, token: str, key: str = "test-ch") -> dict:
    resp = client.post(
        "/api/challenges",
        json={
            "challenge_key": key,
            "title": "Test Challenge",
            "market": "us-stock",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class ChallengeRouteTests(unittest.TestCase):
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

    # --- GET /api/challenges ---

    def test_list_challenges_is_public(self) -> None:
        resp = self.client.get("/api/challenges")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("challenges", resp.json())

    def test_list_challenges_empty_initially(self) -> None:
        resp = self.client.get("/api/challenges")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["challenges"], [])

    # --- POST /api/challenges ---

    def test_create_challenge_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/challenges",
            json={"title": "No Auth", "market": "us-stock"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_create_challenge_success(self) -> None:
        data = _create_challenge(self.client, self.token)
        self.assertIn("challenge_key", data)
        self.assertEqual(data["title"], "Test Challenge")

    def test_create_challenge_missing_title_rejected(self) -> None:
        resp = self.client.post(
            "/api/challenges",
            json={"market": "us-stock"},
            headers=self.headers,
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_create_challenge_missing_market_rejected(self) -> None:
        resp = self.client.post(
            "/api/challenges",
            json={"title": "No market"},
            headers=self.headers,
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_create_challenge_appears_in_list(self) -> None:
        _create_challenge(self.client, self.token, key="listed-ch")
        resp = self.client.get("/api/challenges")
        self.assertEqual(resp.status_code, 200)
        keys = [c["challenge_key"] for c in resp.json()["challenges"]]
        self.assertIn("listed-ch", keys)

    # --- GET /api/challenges/{challenge_key} ---

    def test_get_challenge_by_key(self) -> None:
        _create_challenge(self.client, self.token, key="get-me")
        resp = self.client.get("/api/challenges/get-me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["challenge_key"], "get-me")

    def test_get_nonexistent_challenge_returns_404(self) -> None:
        resp = self.client.get("/api/challenges/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    # --- GET /api/challenges/{challenge_key}/leaderboard ---

    def test_challenge_leaderboard_is_public(self) -> None:
        _create_challenge(self.client, self.token, key="lb-ch")
        resp = self.client.get("/api/challenges/lb-ch/leaderboard")
        self.assertEqual(resp.status_code, 200)

    # --- GET /api/challenges/{challenge_key}/submissions ---

    def test_challenge_submissions_is_public(self) -> None:
        _create_challenge(self.client, self.token, key="sub-ch")
        resp = self.client.get("/api/challenges/sub-ch/submissions")
        self.assertEqual(resp.status_code, 200)

    # --- GET /api/challenges/me ---

    def test_my_challenges_requires_auth(self) -> None:
        resp = self.client.get("/api/challenges/me")
        self.assertEqual(resp.status_code, 401)

    def test_my_challenges_empty_initially(self) -> None:
        resp = self.client.get("/api/challenges/me", headers=self.headers)
        self.assertEqual(resp.status_code, 200)

    def test_my_challenges_includes_joined(self) -> None:
        _create_challenge(self.client, self.token, key="my-ch")
        # /challenges/me returns challenges the agent has joined as a participant
        self.client.post(
            "/api/challenges/my-ch/join",
            json={},
            headers=self.headers,
        )
        resp = self.client.get("/api/challenges/me", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        keys = [c["challenge_key"] for c in resp.json().get("challenges", [])]
        self.assertIn("my-ch", keys)

    # --- POST /api/challenges/{challenge_key}/join ---

    def test_join_challenge_requires_auth(self) -> None:
        _create_challenge(self.client, self.token, key="join-ch")
        resp = self.client.post("/api/challenges/join-ch/join")
        self.assertEqual(resp.status_code, 401)

    def test_join_challenge_success(self) -> None:
        joiner = _register_agent(self.client, name="joiner")
        _create_challenge(self.client, self.token, key="joinable")
        resp = self.client.post(
            "/api/challenges/joinable/join",
            json={},
            headers={"Authorization": f"Bearer {joiner['token']}"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_join_nonexistent_challenge_returns_error(self) -> None:
        resp = self.client.post(
            "/api/challenges/no-such-key/join",
            json={},
            headers=self.headers,
        )
        self.assertIn(resp.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()
