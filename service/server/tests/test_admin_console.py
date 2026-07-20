"""Manager console — admin identities, paid membership, member management,
statistics, moderation, and the audit trail (routes_admin_auth.py,
routes_admin_manage.py, routes_subscriptions.py)."""
from __future__ import annotations

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


class _Base(unittest.TestCase):
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

    def tearDown(self):
        self.tmp.cleanup()

    def _make_user(self, email: str = "member@x.com", password: str = "memberpass1") -> dict:
        from utils import hash_password
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, hash_password(password)))
        conn.commit()
        conn.close()
        r = self.client.post("/api/users/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()


class AdminIdentityTests(_Base):
    def test_operator_cannot_manage_admins(self):
        r = self.client.post("/api/admin/admins",
                             json={"email": "op@test.com", "password": "operator12",
                                   "role": "operator"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/admin/login",
                             json={"email": "op@test.com", "password": "operator12"})
        op = {"Authorization": f"Bearer {r.json()['token']}"}
        self.assertEqual(self.client.get("/api/admin/admins", headers=op).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/overview", headers=op).status_code, 200)

    def test_disable_revokes_sessions(self):
        r = self.client.post("/api/admin/admins",
                             json={"email": "op@test.com", "password": "operator12",
                                   "role": "operator"}, headers=self.admin)
        op_id = r.json()["id"]
        r = self.client.post("/api/admin/login",
                             json={"email": "op@test.com", "password": "operator12"})
        op = {"Authorization": f"Bearer {r.json()['token']}"}
        r = self.client.patch(f"/api/admin/admins/{op_id}",
                              json={"status": "disabled"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/overview", headers=op).status_code, 401)
        r = self.client.post("/api/admin/login",
                             json={"email": "op@test.com", "password": "operator12"})
        self.assertEqual(r.status_code, 403)

    def test_cannot_disable_own_account(self):
        r = self.client.patch("/api/admin/admins/1",
                              json={"status": "disabled"}, headers=self.admin)
        self.assertEqual(r.status_code, 400)

    def test_audit_log_records_actions(self):
        self.client.post("/api/admin/admins",
                         json={"email": "op@test.com", "password": "operator12",
                               "role": "operator"}, headers=self.admin)
        r = self.client.get("/api/admin/audit", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        actions = [e["action"] for e in r.json()["entries"]]
        self.assertIn("admin.create", actions)
        self.assertIn("login", actions)


class SubscriptionFlowTests(_Base):
    def test_plans_seeded(self):
        r = self.client.get("/api/subscriptions/plans")
        codes = [p["code"] for p in r.json()["plans"]]
        self.assertEqual(codes, ["junior", "pro", "professional", "enterprise"])

    def test_bank_transfer_to_approval(self):
        session = self._make_user()
        self.assertEqual(session["subscription_status"], "none")
        user_h = {"Authorization": f"Bearer {session['token']}"}
        r = self.client.post("/api/subscriptions/bank-transfer",
                             json={"plan_code": "pro", "reference": "WIRE-1"}, headers=user_h)
        self.assertEqual(r.status_code, 200)
        # A second pending bank claim is blocked.
        r = self.client.post("/api/subscriptions/bank-transfer",
                             json={"plan_code": "pro", "reference": "WIRE-2"}, headers=user_h)
        self.assertEqual(r.status_code, 400)
        r = self.client.get("/api/admin/subscriptions?status=pending", headers=self.admin)
        sub_id = r.json()["subscriptions"][0]["id"]
        r = self.client.post(f"/api/admin/subscriptions/{sub_id}/approve",
                             json={"note": "confirmed"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/subscriptions/me", headers=user_h)
        self.assertEqual(r.json()["status"], "active")

    def test_reject_pending(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        self.client.post("/api/subscriptions/bank-transfer",
                         json={"plan_code": "junior", "reference": "WIRE-9"}, headers=user_h)
        r = self.client.get("/api/admin/subscriptions?status=pending", headers=self.admin)
        sub_id = r.json()["subscriptions"][0]["id"]
        r = self.client.post(f"/api/admin/subscriptions/{sub_id}/reject",
                             json={"note": "no wire received"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/subscriptions/me", headers=user_h)
        self.assertEqual(r.json()["status"], "none")

    def test_enterprise_uses_contract_form(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        r = self.client.post("/api/subscriptions/bank-transfer",
                             json={"plan_code": "enterprise", "reference": "X"}, headers=user_h)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/subscriptions/contract",
                             json={"name": "Corp", "email": "ceo@corp.com",
                                   "company": "Corp", "message": "enterprise"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/admin/contracts", headers=self.admin)
        self.assertEqual(r.json()["total"], 1)

    def test_manual_grant_and_replace(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        # Grant by email with no prior payment request.
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "member@x.com", "plan_code": "pro", "days": 45},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["replaced"], 0)
        r = self.client.get("/api/subscriptions/me", headers=user_h)
        self.assertEqual(r.json()["status"], "active")
        self.assertEqual(r.json()["subscription"]["plan_code"], "pro")
        # Granting again replaces the active row (plan change) — enterprise is
        # allowed here: manual grant is how contracts activate.
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "member@x.com", "plan_code": "enterprise",
                                   "days": 365, "note": "contract #1"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["replaced"], 1)
        r = self.client.get("/api/subscriptions/me", headers=user_h)
        self.assertEqual(r.json()["subscription"]["plan_code"], "enterprise")
        # Comped grants are not revenue.
        r = self.client.get("/api/admin/analytics", headers=self.admin)
        revenue = sum(m["revenue"] for m in r.json()["revenue_by_month"])
        self.assertEqual(revenue, 0)
        # Unknown member / plan.
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "ghost@x.com", "plan_code": "pro"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "member@x.com", "plan_code": "gold"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 404)

    def test_cancel_active_subscription(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        self.client.post("/api/admin/subscriptions/grant",
                         json={"email": "member@x.com", "plan_code": "junior"},
                         headers=self.admin)
        r = self.client.get("/api/admin/subscriptions?status=active", headers=self.admin)
        sub_id = r.json()["subscriptions"][0]["id"]
        r = self.client.post(f"/api/admin/subscriptions/{sub_id}/cancel",
                             json={"note": "refunded"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/subscriptions/me", headers=user_h)
        self.assertEqual(r.json()["status"], "none")
        # Cancelling twice fails cleanly.
        r = self.client.post(f"/api/admin/subscriptions/{sub_id}/cancel",
                             json={"note": ""}, headers=self.admin)
        self.assertEqual(r.status_code, 400)

    def test_paypal_unconfigured_503(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        r = self.client.post("/api/subscriptions/paypal/create-order",
                             json={"plan_code": "junior"}, headers=user_h)
        self.assertEqual(r.status_code, 503)


class UsdtPaymentTests(_Base):
    """USDT is the default rail: same pending -> admin-approve machinery as a
    bank transfer, keyed on the on-chain transaction hash."""

    ENV = {"USDT_ADDRESS": "TXk9Yk4testaddress0000000000000000", "USDT_NETWORK": "TRC20"}

    def test_plans_expose_the_usdt_address_and_network(self):
        with patch.dict(os.environ, self.ENV):
            body = self.client.get("/api/subscriptions/plans").json()
        self.assertTrue(body["usdt_available"])
        self.assertEqual(body["usdt_address"], self.ENV["USDT_ADDRESS"])
        self.assertEqual(body["usdt_network"], "TRC20")

    def test_paypal_button_is_hidden_unless_explicitly_re_enabled(self):
        configured = {"PAYPAL_CLIENT_ID": "id", "PAYPAL_CLIENT_SECRET": "secret"}
        with patch.dict(os.environ, configured):
            self.assertFalse(self.client.get("/api/subscriptions/plans").json()["paypal_available"])
        with patch.dict(os.environ, {**configured, "PAYPAL_UI_ENABLED": "true"}):
            self.assertTrue(self.client.get("/api/subscriptions/plans").json()["paypal_available"])

    def test_usdt_submission_to_approval(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        with patch.dict(os.environ, self.ENV):
            r = self.client.post("/api/subscriptions/usdt",
                                 json={"plan_code": "pro", "tx_hash": "0xdeadbeef"},
                                 headers=user_h)
            self.assertEqual(r.status_code, 200, r.text)
            # a second pending USDT claim is refused, same as bank
            r = self.client.post("/api/subscriptions/usdt",
                                 json={"plan_code": "pro", "tx_hash": "0xfeedface"},
                                 headers=user_h)
            self.assertEqual(r.status_code, 400)

        # the admin console sees it with method 'usdt' and the hash as reference
        subs = self.client.get("/api/admin/subscriptions?status=pending",
                               headers=self.admin).json()["subscriptions"]
        self.assertEqual(subs[0]["method"], "usdt")
        self.assertEqual(subs[0]["reference"], "0xdeadbeef")

        r = self.client.post(f"/api/admin/subscriptions/{subs[0]['id']}/approve",
                             json={"note": "confirmed on-chain"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/subscriptions/me",
                                         headers=user_h).json()["status"], "active")

    def test_usdt_refused_when_no_address_is_configured(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        with patch.dict(os.environ, {"USDT_ADDRESS": ""}):
            r = self.client.post("/api/subscriptions/usdt",
                                 json={"plan_code": "pro", "tx_hash": "0xabc"}, headers=user_h)
        self.assertEqual(r.status_code, 503)

    def test_empty_tx_hash_is_refused(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        with patch.dict(os.environ, self.ENV):
            r = self.client.post("/api/subscriptions/usdt",
                                 json={"plan_code": "pro", "tx_hash": "   "}, headers=user_h)
        self.assertEqual(r.status_code, 400)

    def test_bank_transfer_still_works_alongside_usdt(self):
        """The shared helper must not have changed the bank rail's behaviour."""
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        with patch.dict(os.environ, self.ENV):
            self.assertEqual(self.client.post(
                "/api/subscriptions/usdt", json={"plan_code": "pro", "tx_hash": "0x1"},
                headers=user_h).status_code, 200)
        # a bank claim is a DIFFERENT method, so it is not the blocked duplicate
        self.assertEqual(self.client.post(
            "/api/subscriptions/bank-transfer", json={"plan_code": "pro", "reference": "W-1"},
            headers=user_h).status_code, 200)
        methods = {s["method"] for s in self.client.get(
            "/api/admin/subscriptions?status=pending", headers=self.admin).json()["subscriptions"]}
        self.assertEqual(methods, {"usdt", "bank"})


class PaymentSettingsTests(_Base):
    """The USDT receiving address is registered in the console, not .env."""

    ADDR = "TXk9Yk4consoleaddress00000000000000"

    def _save(self, address: str, network: str = "TRC20"):
        return self.client.put("/api/admin/settings/payment",
                               json={"usdt_address": address, "usdt_network": network},
                               headers=self.admin)

    def test_address_saved_in_console_reaches_the_subscribe_page(self):
        self.assertFalse(self.client.get("/api/subscriptions/plans").json()["usdt_available"])
        self.assertEqual(self._save(self.ADDR, "BEP20").status_code, 200)
        body = self.client.get("/api/subscriptions/plans").json()
        self.assertTrue(body["usdt_available"])
        self.assertEqual(body["usdt_address"], self.ADDR)
        self.assertEqual(body["usdt_network"], "BEP20")

    def test_console_value_wins_over_the_env_fallback(self):
        with patch.dict(os.environ, {"USDT_ADDRESS": "TEnvFallbackAddress0000000000000"}):
            # nothing stored yet -> env serves
            self.assertEqual(self.client.get("/api/subscriptions/plans").json()["usdt_address"],
                             "TEnvFallbackAddress0000000000000")
            self._save(self.ADDR)
            # stored value takes precedence from then on
            self.assertEqual(self.client.get("/api/subscriptions/plans").json()["usdt_address"],
                             self.ADDR)

    def test_settings_read_reports_where_the_value_came_from(self):
        with patch.dict(os.environ, {"USDT_ADDRESS": "TEnvFallbackAddress0000000000000"}):
            got = self.client.get("/api/admin/settings/payment", headers=self.admin).json()
            self.assertEqual(got["usdt_address"]["source"], "env")
        self._save(self.ADDR)
        got = self.client.get("/api/admin/settings/payment", headers=self.admin).json()
        self.assertEqual(got["usdt_address"]["source"], "console")
        self.assertEqual(got["usdt_address"]["value"], self.ADDR)
        self.assertEqual(got["usdt_address"]["updated_by"], "root@test.com")

    def test_a_malformed_address_is_refused(self):
        """A typo here sends subscribers' money to a stranger."""
        for bad in ("short", "has spaces in it", "punctuation!!@#$", "x" * 200):
            self.assertEqual(self._save(bad).status_code, 400, bad)
        self.assertFalse(self.client.get("/api/subscriptions/plans").json()["usdt_available"])

    def test_an_unsupported_network_is_refused(self):
        r = self._save(self.ADDR, "DOGECHAIN")
        self.assertEqual(r.status_code, 400)
        self.assertIn("TRC20", r.json()["detail"])

    def test_clearing_the_address_takes_usdt_off_the_page(self):
        self._save(self.ADDR)
        self.assertTrue(self.client.get("/api/subscriptions/plans").json()["usdt_available"])
        self.assertEqual(self._save("").status_code, 200)
        self.assertFalse(self.client.get("/api/subscriptions/plans").json()["usdt_available"])

    def test_change_is_audited_with_masked_old_and_new_values(self):
        self._save(self.ADDR)
        entries = self.client.get("/api/admin/audit", headers=self.admin).json()["entries"]
        row = next(e for e in entries if e["action"] == "settings.payment")
        self.assertIn("TXk9Yk", row["detail"])          # masked, not the full string
        self.assertNotIn(self.ADDR, row["detail"])
        self.assertIn("was=(unset)", row["detail"])

    def test_settings_require_an_admin(self):
        self.assertEqual(self.client.get("/api/admin/settings/payment").status_code, 401)
        self.assertEqual(self.client.put("/api/admin/settings/payment",
                                         json={"usdt_address": self.ADDR}).status_code, 401)
        # and an anonymous caller cannot read it through the public plans route
        self.assertNotIn("usdt_address_updated_by",
                         self.client.get("/api/subscriptions/plans").json())


class PlanManagementTests(_Base):
    def test_create_edit_deactivate_plan(self):
        # Create a new tier; it appears on the public subscribe page.
        r = self.client.post("/api/admin/plans",
                             json={"code": "starter", "name": "Starter",
                                   "price_usd": 25, "sort_order": 0},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/subscriptions/plans")
        codes = [p["code"] for p in r.json()["plans"]]
        self.assertIn("starter", codes)
        # Members can subscribe to it.
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        r = self.client.post("/api/subscriptions/bank-transfer",
                             json={"plan_code": "starter", "reference": "W-1"}, headers=user_h)
        self.assertEqual(r.status_code, 200)
        # Price edit sticks.
        r = self.client.patch("/api/admin/plans/starter",
                              json={"price_usd": 35}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/subscriptions/plans")
        starter = next(p for p in r.json()["plans"] if p["code"] == "starter")
        self.assertEqual(starter["price_usd"], 35)
        # Deactivating hides it from the public page and blocks new subscribes.
        r = self.client.patch("/api/admin/plans/starter",
                              json={"active": 0}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/subscriptions/plans")
        self.assertNotIn("starter", [p["code"] for p in r.json()["plans"]])
        # Admin view still shows it, with subscriber_rows counted.
        r = self.client.get("/api/admin/plans", headers=self.admin)
        starter = next(p for p in r.json()["plans"] if p["code"] == "starter")
        self.assertEqual(starter["active"], 0)
        self.assertEqual(starter["subscriber_rows"], 1)

    def test_validation_and_delete_rules(self):
        r = self.client.post("/api/admin/plans",
                             json={"code": "Bad Code!", "name": "X"}, headers=self.admin)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/admin/plans",
                             json={"code": "junior", "name": "Dup"}, headers=self.admin)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/admin/plans",
                             json={"code": "temp", "name": "Temp", "price_usd": 10},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200)
        # Unreferenced plan deletes cleanly.
        r = self.client.delete("/api/admin/plans/temp", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        # A plan with subscription history refuses deletion.
        self._make_user()
        self.client.post("/api/admin/subscriptions/grant",
                         json={"email": "member@x.com", "plan_code": "junior"},
                         headers=self.admin)
        r = self.client.delete("/api/admin/plans/junior", headers=self.admin)
        self.assertEqual(r.status_code, 400)


class MemberManagementTests(_Base):
    def test_suspend_blocks_login_and_kills_sessions(self):
        session = self._make_user()
        user_h = {"Authorization": f"Bearer {session['token']}"}
        uid = session["user_id"]
        r = self.client.post(f"/api/admin/members/{uid}/status",
                             json={"status": "suspended"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/users/login",
                             json={"email": "member@x.com", "password": "memberpass1"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/api/users/me", headers=user_h).status_code, 401)
        r = self.client.post(f"/api/admin/members/{uid}/status",
                             json={"status": "active"}, headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/users/login",
                             json={"email": "member@x.com", "password": "memberpass1"})
        self.assertEqual(r.status_code, 200)

    def test_member_detail_shape(self):
        session = self._make_user()
        r = self.client.get(f"/api/admin/members/{session['user_id']}", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("user", "agent", "subscriptions", "positions", "trades", "equity_history"):
            self.assertIn(key, body)


class StatsAndModerationTests(_Base):
    def test_stats_endpoints_shape(self):
        for path, keys in (
            ("stats/assets", ("totals", "top_members", "equity_curve")),
            ("stats/positions", ("totals", "by_market", "by_side", "top_symbols", "largest")),
            ("stats/automation", ("totals", "runs_by_day", "by_agent", "skip_reasons")),
            ("analytics", ("signups_by_day", "trades_by_day", "revenue_by_month",
                           "subscriptions_matrix", "active_subscriptions")),
        ):
            r = self.client.get(f"/api/admin/{path}", headers=self.admin)
            self.assertEqual(r.status_code, 200, f"{path}: {r.text[:200]}")
            for key in keys:
                self.assertIn(key, r.json(), path)

    def test_discussion_moderation(self):
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "mod-bot", "email": "mod@x.com",
                                   "password": "testpass123"})
        agent_token = r.json()["token"]
        r = self.client.post("/api/signals/discussion",
                             json={"title": "spam post", "content": "buy now!!", "market": "crypto"},
                             headers={"Authorization": f"Bearer {agent_token}"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/admin/discussions?q=spam", headers=self.admin)
        self.assertEqual(r.json()["total"], 1)
        sid = r.json()["discussions"][0]["signal_id"]
        r = self.client.delete(f"/api/admin/discussions/{sid}", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/admin/discussions", headers=self.admin)
        self.assertEqual(r.json()["total"], 0)

    def test_leaderboard_exclusions(self):
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "lb-bot", "email": "lb@x.com",
                                   "password": "testpass123"})
        agent_id = r.json()["agent_id"]
        r = self.client.post("/api/admin/leaderboard/exclusions",
                             json={"agent_id": agent_id, "reason": "test account"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/admin/leaderboard", headers=self.admin)
        excluded = [e["agent_id"] for e in r.json()["exclusions"] if e["active"]]
        self.assertIn(agent_id, excluded)
        r = self.client.delete(f"/api/admin/leaderboard/exclusions/{agent_id}",
                               headers=self.admin)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/admin/leaderboard/refresh", headers=self.admin)
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
