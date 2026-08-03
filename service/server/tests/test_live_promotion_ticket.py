"""Plan 21 P5 — the shadow→live promotion ticket on automation rules.

Promoting a rule TO account_type 'live' requires the caller to re-type
symbol, the literal 'live', and size_usd in `live_confirm`; any mismatch is
a 400 naming the bad fields (the upstream trade ticket's demote-on-mismatch
contract). Simulator/shadow rules, and edits to an already-live rule, pass
untouched — the ticket gates the TRANSITION only. Order-time live gating
(gateway config, consent, allowlist, caps) is unchanged.
"""

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

RULE = {"symbol": "BTC", "market": "crypto", "interval_minutes": 60,
        "min_confidence": 0.65, "size_usd": 500}


class LivePromotionTicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "promoter", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def tearDown(self):
        self.tmp.cleanup()

    def _post(self, **overrides):
        return self.client.post("/api/automation/configs",
                                headers=self.headers,
                                json={**RULE, **overrides})

    def _put(self, config_id: int, **overrides):
        return self.client.put(f"/api/automation/configs/{config_id}",
                               headers=self.headers,
                               json={**RULE, **overrides})

    def _account_type(self, config_id: int) -> str:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT account_type FROM automation_configs "
                        "WHERE id = ?", (config_id,))
            return cur.fetchone()["account_type"]
        finally:
            conn.close()

    # ── untouched paths ────────────────────────────────────────────────

    def test_simulator_and_shadow_need_no_ticket(self):
        self.assertEqual(self._post().status_code, 200)
        self.assertEqual(self._post(symbol="ETH",
                                    account_type="shadow").status_code, 200)

    # ── create: transition to live ─────────────────────────────────────

    def test_live_create_without_confirm_is_refused(self):
        resp = self._post(account_type="live")
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertIn("re-typed confirmation", detail)
        for field in ("symbol", "account_type", "size_usd"):
            self.assertIn(field, detail)

    def test_live_create_with_matching_confirm_passes(self):
        resp = self._post(account_type="live",
                          live_confirm={"symbol": "btc",
                                        "account_type": "LIVE",
                                        "size_usd": 500})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(self._account_type(resp.json()["id"]), "live")

    def test_live_create_mismatch_names_only_bad_fields(self):
        resp = self._post(account_type="live",
                          live_confirm={"symbol": "ETH",
                                        "account_type": "live",
                                        "size_usd": 500})
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertIn("symbol", detail)
        self.assertNotIn("size_usd", detail)

    def test_real_spelling_is_normalized_and_still_gated(self):
        resp = self._post(account_type="real")
        self.assertEqual(resp.status_code, 400)

    # ── update: transition vs already-live ─────────────────────────────

    def test_update_transition_to_live_requires_ticket(self):
        config_id = self._post().json()["id"]
        resp = self._put(config_id, account_type="live")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._account_type(config_id), "simulator")
        ok = self._put(config_id, account_type="live",
                       live_confirm={"symbol": "BTC", "account_type": "live",
                                     "size_usd": 500})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(self._account_type(config_id), "live")

    def test_editing_an_already_live_rule_needs_no_ticket(self):
        config_id = self._post(account_type="live",
                               live_confirm={"symbol": "BTC",
                                             "account_type": "live",
                                             "size_usd": 500}).json()["id"]
        resp = self._put(config_id, account_type="live", interval_minutes=30)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_demoting_live_needs_no_ticket(self):
        config_id = self._post(account_type="live",
                               live_confirm={"symbol": "BTC",
                                             "account_type": "live",
                                             "size_usd": 500}).json()["id"]
        resp = self._put(config_id, account_type="simulator")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._account_type(config_id), "simulator")


if __name__ == "__main__":
    unittest.main()
