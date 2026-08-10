"""Write-time warm for the desk's written report (AI 분석 30분 주기).

The report is journaled in English (the desk_memory corpus contract) and
localized at read time through the cached translator in market_i18n. Until
now that cache was populated only BY a read — so the AI-analysis panel's
first view of any new report was always English, flipping only if the reader
kept the drawer open past the next 60s poll. Worse, prod runs Redis-less and
the cache was in-process memory: the worker (which writes the journal) and
the backend (which serves the panel) never shared a single warmed string,
and a backend restart wiped everything.

These tests pin the two-part fix:
  * run_engine warms the run OWNER's language the moment the report is
    journaled (unit + real run_cycle wiring — without the wiring test the
    call could be deleted and everything else would stay green);
  * the translation cache has a DB layer, so a warm in the worker process is
    visible to a backend process whose memory cache has never seen the
    string (simulated here by wiping the in-process cache between warm and
    read).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import desk_cycles
import market_i18n
import run_engine
import trading_runs
from routes import create_app

REPORT = "Short WLDUSDT targeting a ~5% pullback with a 2.2% stop above $0.342."


class WarmReportI18nTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "warm-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        with market_i18n._inflight_lock:
            market_i18n._inflight.clear()
        market_i18n._MEM_CACHE.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def _link_owner(self, lang: str) -> None:
        """Give the self-registered agent a user row with a stored language."""
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (email, password_hash, created_at, lang)
                   VALUES (?, ?, ?, ?)""",
                (f"warm-{lang}@test.local", "x",
                 datetime.now(timezone.utc).isoformat(), lang))
            user_id = cursor.lastrowid
            cursor.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                           (user_id, self.agent_id))
            conn.commit()
        finally:
            conn.close()

    # ── the warm helper itself ──────────────────────────────────────────
    def test_warm_targets_owner_language(self):
        self._link_owner("ko")
        with patch.object(market_i18n, "_schedule_warm") as sched:
            run_engine._warm_report_i18n(self.agent_id, "  " + REPORT + "  ")
        sched.assert_called_once()
        self.assertEqual(sched.call_args.args[0], [REPORT])  # stripped, as read
        self.assertEqual(sched.call_args.args[1], "ko")

    def test_no_warm_for_english_owner(self):
        self._link_owner("en")
        with patch.object(market_i18n, "_schedule_warm") as sched:
            run_engine._warm_report_i18n(self.agent_id, REPORT)
        sched.assert_not_called()

    def test_no_warm_for_unlinked_agent_or_empty_report(self):
        # No users row at all — the join finds nothing, lang falls back to en.
        with patch.object(market_i18n, "_schedule_warm") as sched:
            run_engine._warm_report_i18n(self.agent_id, REPORT)
            run_engine._warm_report_i18n(self.agent_id, "")
            run_engine._warm_report_i18n(self.agent_id, None)
        sched.assert_not_called()

    def test_catalogued_report_needs_no_model(self):
        # The platform-authored light-cycle report is a catalogue hit; it must
        # resolve without ever queueing a model translation.
        self._link_owner("ko")
        with patch.object(market_i18n, "_schedule_warm") as sched:
            run_engine._warm_report_i18n(self.agent_id,
                                         "light cycle: no LLM verdict")
        sched.assert_not_called()

    def test_warm_failure_never_raises(self):
        self._link_owner("ko")
        with patch.object(market_i18n, "localize_texts",
                          side_effect=RuntimeError("boom")):
            run_engine._warm_report_i18n(self.agent_id, REPORT)  # must not raise

    # ── run_cycle wiring: the cycle actually calls the warm ─────────────
    def test_run_cycle_warms_the_journaled_report(self):
        self._link_owner("ko")
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.addCleanup(os.environ.pop, "AUTO_TRADING_ENABLED", None)
        with patch("routes_runs._probe_price", return_value=100.0):
            run_id = self.client.post(
                "/api/runs",
                json={"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0},
                headers={"Authorization": f"Bearer {self.token}"}).json()["id"]
            assert self.client.post(
                f"/api/runs/{run_id}/start",
                headers={"Authorization": f"Bearer {self.token}"}).status_code == 200
        analysis = {
            "symbol": "BTC", "market": "crypto",
            "analysts": {"technical": {"brief": "t",
                                       "data": {"sigma_daily_pct": 2.5,
                                                "current_price": 100.0}}},
            "decision": {"action": "hold", "confidence": 0.2,
                         "entry": 100.0, "report": REPORT},
        }
        with patch("analysis_agents.run_analysis", return_value=analysis), \
             patch.object(market_i18n, "_schedule_warm") as sched:
            run_engine.run_cycle(run_id)
        warmed = [c.args for c in sched.call_args_list
                  if REPORT in c.args[0]]
        self.assertEqual(len(warmed), 1,
                         f"decision report was not warmed: {sched.call_args_list}")
        self.assertEqual(warmed[0][1], "ko")

    # ── end to end across the process boundary ──────────────────────────
    def test_first_read_is_localized_after_write_time_warm(self):
        """Worker warms at write time -> backend's FIRST read is Korean.

        The process boundary is simulated by wiping the in-process cache
        between the warm and the read: whatever survives must have come
        through the database layer, which is exactly what prod (Redis-less,
        two processes) relies on.
        """
        self._link_owner("ko")
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            now = datetime(2026, 8, 10, 3, 10, 0, tzinfo=timezone.utc)
            cursor.execute(
                """INSERT INTO trading_runs
                       (id, agent_id, symbol, market, status, created_at)
                   VALUES (901, ?, 'WLD', 'crypto', 'running', ?)""",
                (self.agent_id, now.strftime(trading_runs.TS_FMT)))
            cursor.execute(
                """INSERT INTO run_events (run_id, seq, event_type, ts, payload)
                   VALUES (901, 1, 'decision', ?, ?)""",
                (now.strftime(trading_runs.TS_FMT),
                 json.dumps({"action": "sell", "confidence": 0.6,
                             "report": REPORT})))
            conn.commit()
        finally:
            conn.close()

        # The worker's write-time warm, driven synchronously with a stub model.
        with patch.object(market_i18n, "_schedule_warm",
                          side_effect=market_i18n._warm), \
             patch.object(market_i18n, "llm_configured", return_value=True), \
             patch.object(market_i18n, "generate_text",
                          return_value="1. WLDUSDT 숏 — 5% 하락 목표."):
            run_engine._warm_report_i18n(self.agent_id, REPORT)

        # A different process: no memory cache, no Redis.
        market_i18n._MEM_CACHE.clear()
        with patch.object(market_i18n, "get_json", lambda k: None), \
             patch.object(market_i18n, "set_json",
                          lambda k, v, ttl_seconds=None: False), \
             patch.object(market_i18n, "_schedule_warm") as sched:
            rows = desk_cycles.agent_cycles(self.agent_id, 4, now=now)
            localized = market_i18n.localize_desk_cycles(rows, "ko")
        reports = [r["report"] for c in localized for r in c["runs"]
                   if r.get("report")]
        self.assertIn("WLDUSDT 숏 — 5% 하락 목표.", reports)
        sched.assert_not_called()   # it was a hit — nothing left to warm


if __name__ == "__main__":
    unittest.main()
