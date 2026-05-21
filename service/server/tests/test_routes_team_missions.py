"""Tests for team mission API routes."""

import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app

_MISSION_PAYLOAD = {
    "title": "Test Mission Alpha",
    "market": "us-stock",
    "symbol": "AAPL",
    "mission_type": "consensus",
    "team_size_min": 2,
    "team_size_max": 4,
    "submission_due_at": "2099-12-31T23:59:59Z",
}


def _register_agent(client: TestClient, name: str = "tm-agent") -> dict:
    resp = client.post(
        "/api/claw/agents/selfRegister",
        json={"name": name, "password": "pw", "initial_balance": 10000.0},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TeamMissionRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        self.agent = _register_agent(self.client)
        self.token = self.agent["token"]
        self.agent_id = self.agent["agent_id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _create_mission(self, payload: dict | None = None) -> dict:
        resp = self.client.post(
            "/api/team-missions",
            json=payload or _MISSION_PAYLOAD,
            headers=self._auth(),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_list_missions_empty(self) -> None:
        resp = self.client.get("/api/team-missions")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("missions", body)
        self.assertIn("total", body)
        self.assertEqual(body["total"], 0)

    def test_create_mission_requires_auth(self) -> None:
        resp = self.client.post("/api/team-missions", json=_MISSION_PAYLOAD)
        self.assertEqual(resp.status_code, 401)

    def test_create_mission_succeeds(self) -> None:
        mission = self._create_mission()
        self.assertIn("mission_key", mission)
        self.assertEqual(mission["title"], "Test Mission Alpha")
        self.assertEqual(mission["market"], "us-stock")

    def test_list_missions_after_create(self) -> None:
        self._create_mission()
        resp = self.client.get("/api/team-missions")
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["missions"]), 1)

    def test_get_mission_by_key(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.get(f"/api/team-missions/{key}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mission_key"], key)

    def test_get_mission_not_found(self) -> None:
        resp = self.client.get("/api/team-missions/no-such-mission")
        self.assertEqual(resp.status_code, 404)

    def test_mission_teams_empty(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.get(f"/api/team-missions/{key}/teams")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("teams", body)

    def test_mission_leaderboard_returns_200(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.get(f"/api/team-missions/{key}/leaderboard")
        self.assertEqual(resp.status_code, 200)

    def test_join_mission(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.post(f"/api/team-missions/{key}/join", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body.get("joined"))

    def test_join_mission_idempotent(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        self.client.post(f"/api/team-missions/{key}/join", headers=self._auth())
        resp = self.client.post(f"/api/team-missions/{key}/join", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body.get("idempotent"))

    def test_join_mission_requires_auth(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.post(f"/api/team-missions/{key}/join")
        self.assertEqual(resp.status_code, 401)

    def test_my_team_missions_empty(self) -> None:
        resp = self.client.get("/api/team-missions/me", headers=self._auth())
        self.assertEqual(resp.status_code, 200)

    def test_my_team_missions_after_join(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        self.client.post(f"/api/team-missions/{key}/join", headers=self._auth())
        resp = self.client.get("/api/team-missions/me", headers=self._auth())
        self.assertEqual(resp.status_code, 200)

    def test_create_mission_missing_title_rejected(self) -> None:
        resp = self.client.post(
            "/api/team-missions",
            json={"market": "us-stock"},
            headers=self._auth(),
        )
        self.assertNotEqual(resp.status_code, 200)

    def test_create_team_for_mission(self) -> None:
        mission = self._create_mission()
        key = mission["mission_key"]
        resp = self.client.post(
            f"/api/team-missions/{key}/teams",
            json={"team_key": None},
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("team_key", body)


if __name__ == "__main__":
    unittest.main()
