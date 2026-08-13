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

    def test_approve_blocks_autorenew_pending_row(self):
        session = self._make_user()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "external_id, auto_renew) VALUES (?, 'junior', 'pending', 'stripe', "
                "'sub_pending', 1)", (session["user_id"],))
            sub_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        r = self.client.post(f"/api/admin/subscriptions/{sub_id}/approve",
                             json={"note": "attempt"}, headers=self.admin)
        self.assertEqual(r.status_code, 400)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status FROM user_subscriptions WHERE id = ?", (sub_id,))
            self.assertEqual(dict(cur.fetchone())["status"], "pending")
        finally:
            conn.close()

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


class BankTransferSettingsTests(_Base):
    """Bank destination details are console-registered like the USDT address.

    Before this, they came only from BANK_TRANSFER_INFO, so a subscriber who
    picked bank transfer was shown no account to send to and the operator had
    no way to fix it without a deploy."""

    ADDR = "TXk9Yk4consoleaddress00000000000000"
    BANK = "Bank of America 123456789\nAccount holder: Sooppiy Inc."

    def _save(self, **fields):
        body = {"usdt_address": self.ADDR, "usdt_network": "TRC20", **fields}
        return self.client.put("/api/admin/settings/payment", json=body, headers=self.admin)

    def test_details_saved_in_console_reach_the_subscribe_page(self):
        self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"], "")
        self.assertEqual(self._save(bank_transfer_info=self.BANK).status_code, 200)
        self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"],
                         self.BANK)

    def test_console_value_wins_over_the_env_fallback(self):
        with patch.dict(os.environ, {"BANK_TRANSFER_INFO": "Old env bank line"}):
            self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"],
                             "Old env bank line")
            self._save(bank_transfer_info=self.BANK)
            self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"],
                             self.BANK)

    def test_omitting_the_field_leaves_saved_details_alone(self):
        """The USDT form posts without this key; that must not wipe the bank
        details. This is the regression the Optional default exists for."""
        self._save(bank_transfer_info=self.BANK)
        self.assertEqual(self._save().status_code, 200)          # no bank key at all
        self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"],
                         self.BANK)

    def test_an_empty_string_clears_them(self):
        self._save(bank_transfer_info=self.BANK)
        self.assertEqual(self._save(bank_transfer_info="").status_code, 200)
        self.assertEqual(self.client.get("/api/subscriptions/plans").json()["bank_transfer_info"], "")

    def test_overlong_details_are_refused(self):
        self.assertEqual(self._save(bank_transfer_info="x" * 2001).status_code, 400)

    def test_the_account_number_is_not_written_to_the_audit_log(self):
        self._save(bank_transfer_info=self.BANK)
        entries = self.client.get("/api/admin/audit", headers=self.admin).json()["entries"]
        row = next(e for e in entries if e["action"] == "settings.payment")
        self.assertIn("bank_info=set", row["detail"])
        self.assertNotIn("123456789", row["detail"])

    def test_settings_read_reports_where_the_value_came_from(self):
        self._save(bank_transfer_info=self.BANK)
        got = self.client.get("/api/admin/settings/payment", headers=self.admin).json()
        self.assertEqual(got["bank_transfer_info"]["source"], "console")
        self.assertEqual(got["bank_transfer_info"]["value"], self.BANK)


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


class MemberRosterTests(_Base):
    """The roster is a list of PEOPLE. A member with ten agents is still one
    member — the old LEFT JOIN fanned them out into ten rows, which also broke
    paging (LIMIT counted joined rows while total counted users)."""

    def _add_agent(self, user_id: int, name: str) -> int:
        from utils import hash_password
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, password_hash, cash, user_id) "
                    "VALUES (?, ?, 100000.0, ?)",
                    (name, hash_password("x" * 12), user_id))
        agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        return agent_id

    def test_a_member_with_many_agents_is_one_row(self):
        session = self._make_user()
        uid = session["user_id"]
        for i in range(3):
            self._add_agent(uid, f"bot-{i}")
        r = self.client.get("/api/admin/users", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        rows = [u for u in body["users"] if u["id"] == uid]
        self.assertEqual(len(rows), 1, f"member repeated: {rows}")
        self.assertEqual([a["name"] for a in rows[0]["agents"]], ["bot-0", "bot-1", "bot-2"])
        self.assertEqual(rows[0]["agent_count"], 3)
        self.assertEqual(len(body["users"]), body["total"])

    def test_paging_counts_members_not_agent_rows(self):
        for n in range(3):
            session = self._make_user(f"m{n}@x.com", "memberpass1")
            self._add_agent(session["user_id"], f"bot-{n}-a")
            self._add_agent(session["user_id"], f"bot-{n}-b")
        r = self.client.get("/api/admin/users?limit=2", headers=self.admin)
        body = r.json()
        self.assertEqual(len(body["users"]), 2)
        self.assertEqual(body["total"], 3)
        r = self.client.get("/api/admin/users?limit=2&offset=2", headers=self.admin)
        self.assertEqual(len(r.json()["users"]), 1)

    def test_trading_mode_is_the_riskiest_across_all_agents(self):
        session = self._make_user()
        uid = session["user_id"]
        sim_agent = self._add_agent(uid, "sim-bot")
        live_agent = self._add_agent(uid, "live-bot")
        conn = database.get_db_connection()
        cur = conn.cursor()
        for agent_id, account_type in ((sim_agent, "simulator"), (live_agent, "live")):
            cur.execute("INSERT INTO automation_configs (agent_id, symbol, market, account_type) "
                        "VALUES (?, 'BTC', 'crypto', ?)", (agent_id, account_type))
        conn.commit()
        conn.close()
        r = self.client.get("/api/admin/users", headers=self.admin)
        row = [u for u in r.json()["users"] if u["id"] == uid][0]
        self.assertEqual(row["trading_mode"], "live")

    def test_member_detail_lists_every_agent(self):
        session = self._make_user()
        uid = session["user_id"]
        self._add_agent(uid, "bot-a")
        self._add_agent(uid, "bot-b")
        r = self.client.get(f"/api/admin/members/{uid}", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([a["name"] for a in r.json()["agents"]], ["bot-a", "bot-b"])


class MemberCreateTests(_Base):
    """Admins can add a member by hand. The account is created with no usable
    password — the member sets their own via the emailed code."""

    def test_create_sends_an_invite_and_leaves_no_usable_password(self):
        with patch("routes_admin_manage.send_verification_code_email",
                   return_value=True) as sent:
            r = self.client.post("/api/admin/members",
                                 json={"email": "New@X.com", "lang": "ko"},
                                 headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["invite_sent"])
        uid = r.json()["user_id"]
        # The code goes to the member's inbox, never back over the API.
        self.assertNotIn("code", r.json())
        self.assertNotIn("password", r.text.lower())
        self.assertTrue(sent.called)
        emailed, code, lang = sent.call_args[0][:3]
        self.assertEqual(emailed, "new@x.com")  # normalised
        self.assertEqual(lang, "ko")
        self.assertRegex(code, r"^\d{6}$")

        # No password works until the member sets one.
        r = self.client.post("/api/users/login",
                             json={"email": "new@x.com", "password": ""})
        self.assertEqual(r.status_code, 401)

        # The emailed code drives the normal reset endpoint.
        r = self.client.post("/api/users/reset-password",
                             json={"email": "new@x.com", "code": code,
                                   "new_password": "chosen12345"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/users/login",
                             json={"email": "new@x.com", "password": "chosen12345"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["user_id"], uid)

    def test_requesting_a_reset_code_invalidates_the_invite_code(self):
        """Why the reset UI needs an 'I already have a code' path: requesting
        a fresh code overwrites the invite under the same reset:{email} key,
        killing the code the invite email told the member to enter."""
        with patch("routes_admin_manage.send_verification_code_email",
                   return_value=True) as sent:
            r = self.client.post("/api/admin/members", json={"email": "inv@x.com"},
                                 headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        invite_code = sent.call_args[0][1]

        # Within the resend cooldown the member cannot even request one …
        r = self.client.post("/api/users/forgot-password",
                             json={"email": "inv@x.com"})
        self.assertEqual(r.status_code, 429, r.text)

        # … and once the cooldown passes, a new request replaces the invite.
        with patch("routes_users.CODE_RESEND_COOLDOWN_SECONDS", 0), \
             patch("routes_users.send_verification_code_email", return_value=True):
            r = self.client.post("/api/users/forgot-password",
                                 json={"email": "inv@x.com"})
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/users/reset-password",
                             json={"email": "inv@x.com", "code": invite_code,
                                   "new_password": "chosen12345"})
        self.assertEqual(r.status_code, 400)

    def test_create_can_grant_a_plan_in_one_step(self):
        with patch("routes_admin_manage.send_verification_code_email", return_value=True):
            r = self.client.post("/api/admin/members",
                                 json={"email": "paid@x.com", "plan_code": "pro", "days": 90},
                                 headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/admin/subscriptions?status=active", headers=self.admin)
        rows = [s for s in r.json()["subscriptions"] if s["email"] == "paid@x.com"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plan_code"], "pro")

    def test_duplicate_and_malformed_emails_are_refused(self):
        self._make_user("dupe@x.com", "memberpass1")
        with patch("routes_admin_manage.send_verification_code_email", return_value=True):
            r = self.client.post("/api/admin/members", json={"email": "dupe@x.com"},
                                 headers=self.admin)
            self.assertEqual(r.status_code, 400)
            r = self.client.post("/api/admin/members", json={"email": "not-an-email"},
                                 headers=self.admin)
            self.assertEqual(r.status_code, 400)
            r = self.client.post("/api/admin/members",
                                 json={"email": "x@y.com", "plan_code": "gold"},
                                 headers=self.admin)
            self.assertEqual(r.status_code, 404)

    def test_a_failed_invite_email_still_creates_the_member(self):
        with patch("routes_admin_manage.send_verification_code_email", return_value=False):
            r = self.client.post("/api/admin/members", json={"email": "nomail@x.com"},
                                 headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["invite_sent"])

    def test_creating_a_member_requires_an_admin(self):
        r = self.client.post("/api/admin/members", json={"email": "anon@x.com"})
        self.assertEqual(r.status_code, 401)


class ManualPaymentRecordTests(_Base):
    """A grant may record a real payment (method / reference / amount) rather
    than only a zero-amount comp."""

    def test_grant_records_the_payment_it_was_given_for(self):
        self._make_user("payer@x.com", "memberpass1")
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "payer@x.com", "plan_code": "pro", "days": 30,
                                   "method": "usdt", "reference": "0xabc123",
                                   "amount_usd": 49.5, "note": "paid in person"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/admin/subscriptions?status=active", headers=self.admin)
        row = [s for s in r.json()["subscriptions"] if s["email"] == "payer@x.com"][0]
        self.assertEqual(row["method"], "usdt")
        self.assertEqual(row["reference"], "0xabc123")
        self.assertEqual(row["amount_usd"], 49.5)
        # A recorded payment IS revenue; a comp is not.
        r = self.client.get("/api/admin/analytics", headers=self.admin)
        self.assertEqual(sum(m["revenue"] for m in r.json()["revenue_by_month"]), 49.5)

    def test_comp_grant_still_defaults_to_manual_and_zero(self):
        self._make_user("comp@x.com", "memberpass1")
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "comp@x.com", "plan_code": "pro"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get("/api/admin/subscriptions?status=active", headers=self.admin)
        row = [s for s in r.json()["subscriptions"] if s["email"] == "comp@x.com"][0]
        self.assertEqual(row["method"], "manual")
        self.assertEqual(row["amount_usd"], 0)
        r = self.client.get("/api/admin/analytics", headers=self.admin)
        self.assertEqual(sum(m["revenue"] for m in r.json()["revenue_by_month"]), 0)

    def test_an_unknown_payment_method_is_refused(self):
        self._make_user("bad@x.com", "memberpass1")
        r = self.client.post("/api/admin/subscriptions/grant",
                             json={"email": "bad@x.com", "plan_code": "pro",
                                   "method": "carrier-pigeon"},
                             headers=self.admin)
        self.assertEqual(r.status_code, 400, r.text)


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

    def test_top_members_lists_active_agents_only(self):
        # Active = at least one trade (operation signal) or an open position.
        # A dormant agent with equity history (leftover QA shell) stays out.
        session = self._make_user()
        uid = session["user_id"]
        conn = database.get_db_connection()
        cur = conn.cursor()
        from utils import hash_password
        agents = {}
        for name in ("traded-bot", "idle-bot"):
            cur.execute("INSERT INTO agents (name, password_hash, cash, user_id) "
                        "VALUES (?, ?, 100000.0, ?)", (name, hash_password("x" * 12), uid))
            agents[name] = cur.lastrowid
            cur.execute(
                "INSERT INTO profit_history (agent_id, total_value, cash, position_value, "
                "profit, recorded_at) VALUES (?, 100000, 100000, 0, 0, '2026-08-02T00:00:00Z')",
                (agents[name],))
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, message_type, market, timestamp, "
            "created_at) VALUES (?, ?, 'operation', 'crypto', 0, '2026-08-02T00:00:00Z')",
            (900001, agents["traded-bot"]))
        conn.commit()
        conn.close()
        r = self.client.get("/api/admin/stats/assets", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        names = [m["name"] for m in r.json()["top_members"]]
        self.assertIn("traded-bot", names)
        self.assertNotIn("idle-bot", names)

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
