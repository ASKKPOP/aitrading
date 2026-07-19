"""Trading Runs reporting (Plan 10, Phase 4) — verification gates.

Covers: the two new notification categories + kind mappings, the
run_stopped reserved budget (digests can't starve the alert that matters),
the SMS tier gate inside the send path, digest due-math across timezones,
journal-before-send with pending->sent + retry sweep (incl. the
dedupe-skip => sent case), P/L threshold triggers, and the throttled
notification test endpoint.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_reports
import trading_runs
from routes import create_app


def _ts(offset_seconds: float = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).strftime(trading_runs.TS_FMT)


class RunReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "report-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        # a real users row linked to the agent (alerts resolve the owner)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "INSERT INTO users (email, password_hash, created_at) "
                "VALUES ('henry@test.dev', 'x', ?)", (_ts(),))
            self.user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (self.user_id, self.agent_id))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        return run_id

    def _set_run(self, run_id, **cols):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            sets = ", ".join(f"{k} = ?" for k in cols)
            cur.execute(f"UPDATE trading_runs SET {sets} WHERE id = ?",
                        (*cols.values(), run_id))
            conn.commit()
        finally:
            conn.close()

    def _row(self, table, where, args):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {table} WHERE {where}", args)
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _enable_prefs(self, category, email=True, sms=False):
        import notifications
        notifications.set_prefs(self.user_id, {
            category: {"enabled": True, "email": email, "sms": sms}})

    # ── categories & kinds ─────────────────────────────────────────────

    def test_new_categories_in_catalog_and_kind_mapping(self):
        import notifications
        self.assertIn("auto_trading_reports", notifications.CATEGORY_CATALOG)
        self.assertIn("auto_trading_safety", notifications.CATEGORY_CATALOG)
        self.assertEqual(notifications.ALERT_KIND_CATEGORY["run_report"],
                         "auto_trading_reports")
        self.assertEqual(notifications.ALERT_KIND_CATEGORY["run_stopped"],
                         "auto_trading_safety")
        import alerts
        for kind in ("run_report", "run_threshold", "run_stopped"):
            self.assertIn(kind, alerts.ALERT_KINDS)

    # ── run_stopped reserve ────────────────────────────────────────────

    def test_run_stopped_bypasses_general_budget_with_own_reserve(self):
        import alerts
        self._enable_prefs("auto_trading_reports")
        self._enable_prefs("auto_trading_safety")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            for i in range(alerts.RATE_LIMIT_PER_HOUR):
                cur.execute(
                    """INSERT INTO alert_log (agent_id, user_id, kind, title,
                       channels_json, created_at) VALUES (?, ?, 'run_report',
                       't', '["email"]', ?)""",
                    (self.agent_id, self.user_id, _ts()))
            conn.commit()
        finally:
            conn.close()
        with patch("alerts._send_email", return_value=True) as email:
            out = alerts.send_alert(self.agent_id, "run_report", "digest", "b")
            self.assertTrue(out.get("rate_limited"))       # general budget spent
            out2 = alerts.send_alert(self.agent_id, "run_stopped", "halted", "b")
            self.assertIn("email", out2["channels"])       # reserve still open
        self.assertTrue(email.called)

    def test_run_stopped_reserve_has_its_own_cap(self):
        import alerts
        self._enable_prefs("auto_trading_safety")
        with patch("alerts._send_email", return_value=True):
            for i in range(alerts.RUN_STOPPED_RESERVE_PER_HOUR):
                out = alerts.send_alert(self.agent_id, "run_stopped", f"s{i}", "b")
                self.assertIn("email", out["channels"])
            out = alerts.send_alert(self.agent_id, "run_stopped", "s-last", "b")
            self.assertTrue(out.get("rate_limited"))

    # ── SMS tier gate in the send path ─────────────────────────────────

    def test_sms_blocked_without_qualifying_plan(self):
        import alerts
        self._enable_prefs("auto_trading_safety", email=False, sms=True)
        self._save_phone()
        with patch("alerts._send_sms", return_value=True) as sms:
            out = alerts.send_alert(self.agent_id, "run_stopped", "t", "b")
        sms.assert_not_called()            # no active plan -> fail closed
        self.assertNotIn("sms", out["channels"])
        with patch("alerts._send_sms", return_value=True) as sms, \
             patch("entitlements.plan_code_for_user", return_value="professional"):
            out = alerts.send_alert(self.agent_id, "run_stopped", "t2", "b")
        self.assertIn("sms", out["channels"])
        sms.assert_called_once()

    def _save_phone(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                """INSERT INTO user_api_settings (user_id, target, config_json,
                   enabled, updated_at) VALUES (?, 'alerts', ?, 1, ?)""",
                (self.user_id, json.dumps({"phone": "+15551234567"}), _ts()))
            conn.commit()
        finally:
            conn.close()

    # ── digest due-math ────────────────────────────────────────────────

    def test_digest_due_math(self):
        base = {"report_frequency": "hourly", "last_report_at": None,
                "report_tz": None, "report_hour_local": None}
        self.assertTrue(run_reports.digest_due(dict(base)))
        base["last_report_at"] = _ts(-1800)
        self.assertFalse(run_reports.digest_due(dict(base)))
        base["last_report_at"] = _ts(-7200)
        self.assertTrue(run_reports.digest_due(dict(base)))

        # daily at 08:00 Asia/Seoul (UTC+9): 2026-07-18 23:30 UTC = 08:30 KST 07-19
        now = datetime(2026, 7, 18, 23, 30, tzinfo=timezone.utc)
        daily = {"report_frequency": "daily", "report_hour_local": 8,
                 "report_tz": "Asia/Seoul", "last_report_at": "2026-07-18T00:10:00Z"}
        self.assertTrue(run_reports.digest_due(dict(daily), now))
        # already reported today (KST): last at 2026-07-18T23:20Z = 08:20 KST 07-19
        daily["last_report_at"] = "2026-07-18T23:20:00Z"
        self.assertFalse(run_reports.digest_due(dict(daily), now))
        # before the local hour -> not due
        early = datetime(2026, 7, 18, 21, 30, tzinfo=timezone.utc)  # 06:30 KST
        daily["last_report_at"] = "2026-07-17T00:00:00Z"
        self.assertFalse(run_reports.digest_due(dict(daily), early))

        # weekly fires Mondays only: 2026-07-20 is a Monday
        weekly = {"report_frequency": "weekly", "report_hour_local": 8,
                  "report_tz": "UTC", "last_report_at": "2026-07-13T09:00:00Z"}
        monday = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 7, 19, 9, 0, tzinfo=timezone.utc)
        self.assertTrue(run_reports.digest_due(dict(weekly), monday))
        self.assertFalse(run_reports.digest_due(dict(weekly), sunday))

    # ── journal-before-send + retry ────────────────────────────────────

    def test_scheduler_tick_queues_and_delivers(self):
        run_id = self._run()
        self._set_run(run_id, report_frequency="hourly")
        calls = []
        with patch("alerts.send_alert",
                   side_effect=lambda *a, **k: calls.append((a, k)) or
                   {"channels": ["inapp", "email"]}):
            out = run_reports.scheduler_tick()
        self.assertEqual(out["queued"], 1)
        self.assertEqual(out["delivered"], 1)
        report = self._row("run_reports", "run_id = ?", (run_id,))
        self.assertEqual(report["status"], "sent")
        self.assertIn("email", report["channels_json"])
        self.assertEqual(calls[0][0][1], "run_report")
        # advanced last_report_at -> not due again immediately
        with patch("alerts.send_alert", return_value={"channels": ["inapp"]}):
            out2 = run_reports.scheduler_tick()
        self.assertEqual(out2["queued"], 0)

    def test_retry_sweep_delivers_stale_pending_and_dedupe_counts_as_sent(self):
        run_id = self._run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                """INSERT INTO run_reports (run_id, user_id, kind, period_start,
                   period_end, pnl, trades, status, created_at)
                   VALUES (?, ?, 'digest', ?, ?, 1.0, 1, 'pending', ?)""",
                (run_id, self.user_id, _ts(-7200), _ts(-3600), _ts(-3600)))
            conn.commit()
        finally:
            conn.close()
        # the original send actually left -> retry comes back deduped
        with patch("alerts.send_alert", return_value={"skipped": "duplicate",
                                                      "channels": []}):
            out = run_reports.scheduler_tick()
        self.assertEqual(out["retried"], 1)
        report = self._row("run_reports", "run_id = ?", (run_id,))
        self.assertEqual(report["status"], "sent")

    # ── thresholds ─────────────────────────────────────────────────────

    def test_loss_threshold_fires_with_daily_dedupe_key(self):
        run_id = self._run(run_budget_usd=1000.0,
                           stop_conditions={"max_loss_usd": 500.0})
        self._set_run(run_id, loss_threshold_pct=5.0)
        run = self._row("trading_runs", "id = ?", (run_id,))
        calls = []
        with patch("alerts.send_alert",
                   side_effect=lambda *a, **k: calls.append((a, k)) or
                   {"channels": ["inapp"]}):
            run_reports.evaluate_thresholds(run, {"total": -60.0})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][1], "run_threshold")
        self.assertTrue(calls[0][1]["dedupe_key"].startswith(f"run:{run_id}:loss:"))
        # under the threshold -> no alert
        calls.clear()
        with patch("alerts.send_alert",
                   side_effect=lambda *a, **k: calls.append((a, k)) or {}):
            run_reports.evaluate_thresholds(run, {"total": -20.0})
        self.assertEqual(calls, [])

    # ── reporting endpoints ────────────────────────────────────────────

    def test_reporting_roundtrip_and_validation(self):
        run_id = self._run()
        resp = self.client.put(
            f"/api/runs/{run_id}/reporting",
            json={"report_frequency": "daily", "report_hour_local": 8,
                  "report_tz": "Asia/Seoul", "notify_on_trade": True,
                  "loss_threshold_pct": 5.0},
            headers=self._h())
        self.assertEqual(resp.status_code, 200, resp.text)
        got = self.client.get(f"/api/runs/{run_id}/reporting",
                              headers=self._h()).json()["reporting"]
        self.assertEqual(got["report_frequency"], "daily")
        self.assertEqual(got["report_tz"], "Asia/Seoul")
        self.assertEqual(got["notify_on_trade"], 1)
        bad = self.client.put(f"/api/runs/{run_id}/reporting",
                              json={"report_frequency": "sometimes"},
                              headers=self._h())
        self.assertEqual(bad.status_code, 422)
        bad_tz = self.client.put(f"/api/runs/{run_id}/reporting",
                                 json={"report_frequency": "daily",
                                       "report_tz": "Mars/Olympus"},
                                 headers=self._h())
        self.assertEqual(bad_tz.status_code, 422)

    # ── notification test endpoint ─────────────────────────────────────

    def test_notification_test_endpoint_throttled(self):
        fake_user = {"id": self.user_id, "email": "henry@test.dev"}
        with patch("routes_support._get_user_by_token", return_value=fake_user), \
             patch("alerts._send_email", return_value=True):
            for _ in range(3):
                resp = self.client.post("/api/notifications/test",
                                        json={"channel": "email"},
                                        headers={"Authorization": "Bearer x"})
                self.assertEqual(resp.status_code, 200, resp.text)
                self.assertTrue(resp.json()["success"])
            resp = self.client.post("/api/notifications/test",
                                    json={"channel": "email"},
                                    headers={"Authorization": "Bearer x"})
            self.assertEqual(resp.status_code, 429)

    def test_notification_test_sms_respects_tier(self):
        self._save_phone()
        fake_user = {"id": self.user_id, "email": "henry@test.dev"}
        with patch("routes_support._get_user_by_token", return_value=fake_user), \
             patch("alerts._send_sms", return_value=True):
            resp = self.client.post("/api/notifications/test",
                                    json={"channel": "sms"},
                                    headers={"Authorization": "Bearer x"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["success"])
        self.assertIn("plan", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
