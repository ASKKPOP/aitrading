"""Server-side background analysis jobs (analysis_jobs.py + routes).

A job runs the pipeline in a daemon thread detached from the HTTP request:
POST /api/analysis/jobs returns immediately, per-step progress events and the
final result persist to the analysis_jobs table, and GET
/api/analysis/jobs/current restores the exact monitor state — so the member
can close /analyst mid-run and re-attach later.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import os
import tempfile

import database
import analysis_jobs
from routes import create_app

AGENT = {"id": 1, "name": "tester"}


def _join_job_threads(timeout: float = 10.0) -> None:
    for t in threading.enumerate():
        if t.name.startswith("analysis-job-"):
            t.join(timeout)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        _join_job_threads()
        self.tmp.cleanup()

    def _wait_status(self, agent_id: int, status: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = analysis_jobs.get_current_job(agent_id)
            if job and job["status"] == status:
                return job
            time.sleep(0.02)
        self.fail(f"job never reached status {status!r}")

    @staticmethod
    def _insert_running(agent_id: int, minutes_ago: float = 0.0) -> int:
        created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO analysis_jobs
               (agent_id, symbol, market, lang, status, events_json, created_at)
               VALUES (?, 'BTC', 'crypto', 'en', 'running', '[]', ?)""",
            (agent_id, created.isoformat()))
        job_id = cur.lastrowid
        conn.commit()
        conn.close()
        return job_id


class JobLifecycleTests(_Base):
    """The core promise: the run is detached from any connection and its
    mid-run state is recoverable at any moment."""

    def test_start_returns_immediately_and_midrun_state_is_visible(self):
        release = threading.Event()
        first_event_written = threading.Event()

        def slow_run(symbol, market, lang, provider, agent_id, progress=None):
            progress({"step": "gather:news", "status": "start", "ts": "t0"})
            first_event_written.set()
            assert release.wait(timeout=10), "test never released the run"
            progress({"step": "gather:news", "status": "done", "ts": "t1"})
            return {"symbol": symbol, "market": market,
                    "decision": {"action": "hold", "confidence": 0.5},
                    "analysts": {}}

        with patch.object(analysis_jobs, "run_analysis", side_effect=slow_run):
            out = analysis_jobs.start_job(1, "BTC", "crypto", "en")
            self.assertEqual(out["status"], "running")
            self.assertFalse(out["already_running"])

            # Mid-run: the job is 'running' with the events emitted so far.
            self.assertTrue(first_event_written.wait(timeout=5))
            job = self._wait_status(1, "running")
            deadline = time.time() + 5
            while time.time() < deadline and len(job["events"]) < 1:
                time.sleep(0.02)
                job = analysis_jobs.get_current_job(1)
            self.assertEqual(job["events"][0]["step"], "gather:news")
            self.assertIsNone(job["result"])

            release.set()
            job = self._wait_status(1, "done")

        self.assertEqual(len(job["events"]), 2)
        self.assertEqual(job["result"]["decision"]["action"], "hold")
        self.assertIsNone(job["error"])
        self.assertIsNotNone(job["finished_at"])

    def test_second_start_while_running_reattaches(self):
        release = threading.Event()

        def slow_run(*args, progress=None, **kwargs):
            assert release.wait(timeout=10)
            return {"decision": {"action": "hold", "confidence": 0.5}, "analysts": {}}

        with patch.object(analysis_jobs, "run_analysis", side_effect=slow_run):
            first = analysis_jobs.start_job(1, "BTC", "crypto", "en")
            second = analysis_jobs.start_job(1, "ETH", "crypto", "en")
            self.assertTrue(second["already_running"])
            self.assertEqual(second["job_id"], first["job_id"])
            release.set()
        self._wait_status(1, "done")

    def test_pipeline_error_is_persisted(self):
        with patch.object(analysis_jobs, "run_analysis",
                          side_effect=RuntimeError("boom")):
            analysis_jobs.start_job(1, "BTC", "crypto", "en")
            job = self._wait_status(1, "error")
        self.assertIn("boom", job["error"])
        self.assertIsNone(job["result"])

    def test_config_id_persists_gate_verdict(self):
        def fast_run(*args, progress=None, **kwargs):
            return {"symbol": "BTC", "market": "crypto",
                    "decision": {"action": "buy", "confidence": 0.9}, "analysts": {}}

        import automation
        with patch.object(analysis_jobs, "run_analysis", side_effect=fast_run), \
             patch.object(analysis_jobs, "_load_config",
                          return_value={"id": 7, "agent_id": 1}), \
             patch.object(automation, "preview_rule_execution",
                          return_value={"would_execute": True}):
            analysis_jobs.start_job(1, "BTC", "crypto", "en", config_id=7)
            job = self._wait_status(1, "done")
        self.assertEqual(job["gates"], {"would_execute": True})
        self.assertEqual(job["config_id"], 7)


class StaleJobTests(_Base):
    def test_startup_sweep_marks_running_jobs_as_error(self):
        self._insert_running(1)
        self.assertEqual(analysis_jobs.mark_stale_jobs(), 1)
        job = analysis_jobs.get_current_job(1)
        self.assertEqual(job["status"], "error")
        self.assertIn("abandoned", job["error"])

    def test_stale_running_job_does_not_block_new_runs(self):
        stale_id = self._insert_running(1, minutes_ago=analysis_jobs.STALE_MINUTES + 5)

        def fast_run(*args, progress=None, **kwargs):
            return {"decision": {"action": "hold", "confidence": 0.5}, "analysts": {}}

        with patch.object(analysis_jobs, "run_analysis", side_effect=fast_run):
            out = analysis_jobs.start_job(1, "BTC", "crypto", "en")
            self.assertFalse(out["already_running"])
            self.assertNotEqual(out["job_id"], stale_id)
            self._wait_status(1, "done")


class JobEndpointTests(_Base):
    def _client(self):
        return TestClient(create_app())

    def test_post_starts_job_and_current_returns_it(self):
        import routes_analysis

        def fast_run(symbol, market, lang, provider, agent_id, progress=None):
            progress({"step": "gather:news", "status": "start", "ts": "t0"})
            return {"symbol": symbol, "market": market,
                    "decision": {"action": "hold", "confidence": 0.5}, "analysts": {}}

        with patch.object(routes_analysis, "_get_agent_by_token", return_value=AGENT), \
             patch.object(analysis_jobs, "run_analysis", side_effect=fast_run):
            client = self._client()
            res = client.post("/api/analysis/jobs",
                              json={"symbol": "BTC", "market": "crypto"},
                              headers={"Authorization": "Bearer x"})
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertEqual(body["status"], "running")
            self._wait_status(1, "done")

            res = client.get("/api/analysis/jobs/current",
                             headers={"Authorization": "Bearer x"})
            self.assertEqual(res.status_code, 200)
            job = res.json()["job"]
            self.assertEqual(job["job_id"], body["job_id"])
            self.assertEqual(job["status"], "done")
            self.assertEqual(job["events"][0]["step"], "gather:news")
            self.assertEqual(job["result"]["decision"]["action"], "hold")

    def test_current_is_null_without_history(self):
        import routes_analysis
        with patch.object(routes_analysis, "_get_agent_by_token", return_value=AGENT):
            res = self._client().get("/api/analysis/jobs/current",
                                     headers={"Authorization": "Bearer x"})
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()["job"])

    def test_requires_auth(self):
        import routes_analysis
        with patch.object(routes_analysis, "_get_agent_by_token", return_value=None):
            client = self._client()
            self.assertEqual(client.post("/api/analysis/jobs",
                                         json={"symbol": "BTC"}).status_code, 401)
            self.assertEqual(client.get("/api/analysis/jobs/current").status_code, 401)

    def test_symbol_required(self):
        import routes_analysis
        with patch.object(routes_analysis, "_get_agent_by_token", return_value=AGENT):
            res = self._client().post("/api/analysis/jobs",
                                      json={"symbol": "  "},
                                      headers={"Authorization": "Bearer x"})
        self.assertEqual(res.status_code, 400)


class NaNSerializationTests(_Base):
    """A technical analyst can emit NaN indicators (ma200 on <200 bars,
    sigma on a gappy feed). Those must not 500 the current-job endpoint —
    Starlette renders with allow_nan=False, so a stored NaN is fatal."""

    def test_json_safe_replaces_nan_and_inf_with_none(self):
        out = analysis_jobs._json_safe(
            {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": float("-inf")},
             "e": "ok", "f": 3})
        self.assertEqual(out, {"a": None, "b": [1.0, None], "c": {"d": None},
                               "e": "ok", "f": 3})
        import json as _json
        _json.dumps(out, allow_nan=False)  # must not raise

    def test_current_endpoint_survives_nan_indicators(self):
        import routes_analysis

        def nan_run(symbol, market, lang, provider, agent_id, progress=None):
            return {"symbol": symbol, "market": market,
                    "decision": {"action": "hold", "confidence": 0.5},
                    "analysts": {"technical": {"data": {
                        "moving_averages": {"ma50": float("nan"),
                                            "ma200": float("nan")},
                        "sigma_daily_pct": float("nan")}}}}

        with patch.object(routes_analysis, "_get_agent_by_token", return_value=AGENT), \
             patch.object(analysis_jobs, "run_analysis", side_effect=nan_run):
            client = TestClient(create_app(), raise_server_exceptions=False)
            client.post("/api/analysis/jobs",
                        json={"symbol": "BTC", "market": "crypto"},
                        headers={"Authorization": "Bearer x"})
            self._wait_status(1, "done")
            res = client.get("/api/analysis/jobs/current",
                             headers={"Authorization": "Bearer x"})

        self.assertEqual(res.status_code, 200)
        data = res.json()["job"]["result"]["analysts"]["technical"]["data"]
        self.assertIsNone(data["moving_averages"]["ma50"])
        self.assertIsNone(data["moving_averages"]["ma200"])
        self.assertIsNone(data["sigma_daily_pct"])


if __name__ == "__main__":
    unittest.main()
