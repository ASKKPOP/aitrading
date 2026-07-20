"""Several runs on one symbol, told apart by their filter key.

Exclusivity used to be one active run per agent+market+symbol, which made
"another active run already owns this agent+market+symbol" the answer to a
perfectly reasonable request: run a 30-minute scalp and a 4-hour swing on BTC
at the same time. The key now includes filter_key() — instrument type,
interval, minimum confidence, AI provider — so different strategies coexist
and only exact duplicates are refused.

That is only safe because `positions` rows became per-book (`run_id`): two
runs sharing a symbol keep separate rows, so entry price, stops, flatten and
P&L stay attributable. These tests pin both halves, and the boundary with the
unowned book that manual signals and automation rules trade.
"""

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
import trading_runs
from routes import create_app


class ParallelStrategyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "parallel-a", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token, self.agent = resp.json()["token"], resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _create(self, **overrides):
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        r = self.client.post("/api/runs", json=payload, headers=self._h())
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def _start(self, run_id):
        return self.client.post(f"/api/runs/{run_id}/start", headers=self._h())

    def _positions(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT run_id, quantity, entry_price, stop_loss FROM positions
                   WHERE agent_id = ? AND symbol = 'BTC' ORDER BY id""",
                (self.agent,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── the filter key ─────────────────────────────────────────────────

    def test_same_symbol_different_interval_both_start(self):
        scalp = self._create(interval_minutes=30)
        swing = self._create(interval_minutes=240)
        self.assertEqual(self._start(scalp).status_code, 200)
        r = self._start(swing)
        self.assertEqual(r.status_code, 200, r.text)

    def test_same_symbol_different_confidence_both_start(self):
        a = self._create(min_confidence=0.60)
        b = self._create(min_confidence=0.85)
        self.assertEqual(self._start(a).status_code, 200)
        self.assertEqual(self._start(b).status_code, 200)

    def test_same_symbol_different_market_type_both_start(self):
        spot = self._create(market_type="spot")
        fut = self._create(market_type="futures")
        self.assertEqual(self._start(spot).status_code, 200)
        self.assertEqual(self._start(fut).status_code, 200)

    def test_exact_duplicate_is_still_refused(self):
        first = self._create(interval_minutes=60, min_confidence=0.65)
        dupe = self._create(interval_minutes=60, min_confidence=0.65)
        self.assertEqual(self._start(first).status_code, 200)
        r = self._start(dupe)
        self.assertEqual(r.status_code, 409)
        # the message must tell the user how to make it start
        self.assertIn("settings", r.json()["detail"]["message"])

    def test_active_keys_are_distinct_per_filter(self):
        a = self._create(interval_minutes=30)
        b = self._create(interval_minutes=240)
        self._start(a)
        self._start(b)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, active_key FROM trading_runs ORDER BY id")
            keys = {r["id"]: r["active_key"] for r in cur.fetchall()}
        finally:
            conn.close()
        self.assertNotEqual(keys[a], keys[b])
        for k in (keys[a], keys[b]):
            self.assertTrue(k.startswith(f"{self.agent}:crypto:BTC:"), k)

    def test_filter_key_ignores_size_and_stops(self):
        """Bet size is not strategy shape — two runs differing only in
        max_bet_usd are the same strategy twice and must not both start."""
        a = self._create(max_bet_usd=500.0)
        b = self._create(max_bet_usd=900.0)
        self.assertEqual(self._start(a).status_code, 200)
        self.assertEqual(self._start(b).status_code, 409)

    # ── per-run position books ─────────────────────────────────────────

    def test_two_runs_keep_separate_position_rows(self):
        from automation import execute_paper_trade
        a, b = self._create(interval_minutes=30), self._create(interval_minutes=240)
        self._start(a)
        self._start(b)
        sid_a, err_a = execute_paper_trade(
            self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=a,
            stop_loss=90.0)
        sid_b, err_b = execute_paper_trade(
            self.agent, "BTC", "crypto", "buy", 2.0, 200.0, run_id=b,
            stop_loss=180.0)
        self.assertIsNotNone(sid_a, err_a)
        self.assertIsNotNone(sid_b, err_b)

        rows = self._positions()
        self.assertEqual(len(rows), 2, f"expected one row per run, got {rows}")
        by_run = {r["run_id"]: r for r in rows}
        self.assertEqual(by_run[a]["quantity"], 1.0)
        self.assertEqual(by_run[a]["entry_price"], 100.0)
        self.assertEqual(by_run[b]["quantity"], 2.0)
        self.assertEqual(by_run[b]["entry_price"], 200.0)
        # stops must not leak across books (the never-loosen max() used to run
        # against whichever row came first)
        self.assertEqual(by_run[a]["stop_loss"], 90.0)
        self.assertEqual(by_run[b]["stop_loss"], 180.0)

    def test_selling_one_run_leaves_the_other_untouched(self):
        from automation import execute_paper_trade
        a, b = self._create(interval_minutes=30), self._create(interval_minutes=240)
        self._start(a)
        self._start(b)
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=a)
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 2.0, 100.0, run_id=b)
        sid, err = execute_paper_trade(
            self.agent, "BTC", "crypto", "sell", 1.0, 120.0, run_id=a)
        self.assertIsNotNone(sid, err)

        rows = self._positions()
        self.assertEqual(len(rows), 1, f"run A's row should be gone: {rows}")
        self.assertEqual(rows[0]["run_id"], b)
        self.assertEqual(rows[0]["quantity"], 2.0)

    def test_run_cannot_sell_a_position_it_does_not_own(self):
        from automation import execute_paper_trade
        a, b = self._create(interval_minutes=30), self._create(interval_minutes=240)
        self._start(a)
        self._start(b)
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=a)
        sid, reason = execute_paper_trade(
            self.agent, "BTC", "crypto", "sell", 1.0, 120.0, run_id=b)
        self.assertIsNone(sid)
        self.assertEqual(reason, "no long position to sell")

    # ── boundary with the unowned book ─────────────────────────────────

    def test_another_runs_position_does_not_block_a_start(self):
        from automation import execute_paper_trade
        a = self._create(interval_minutes=30)
        self._start(a)
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=a)
        b = self._create(interval_minutes=240)
        r = self._start(b)
        self.assertEqual(r.status_code, 200, r.text)

    def test_unowned_position_still_blocks_a_start(self):
        """A manual or rule-owned book is not a run's to adopt."""
        from automation import execute_paper_trade
        sid, err = execute_paper_trade(
            self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=None)
        self.assertIsNotNone(sid, err)
        run = self._create()
        r = self._start(run)
        self.assertEqual(r.status_code, 409)
        self.assertIn("outside any run", r.json()["detail"]["message"])

    def test_run_trade_does_not_touch_the_unowned_book(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 5.0, 50.0, run_id=None)
        run = self._create(symbol="ETH")
        self._start(run)
        execute_paper_trade(self.agent, "ETH", "crypto", "buy", 1.0, 100.0, run_id=run)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT run_id, symbol, quantity FROM positions WHERE agent_id = ? ORDER BY id",
                (self.agent,))
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
        self.assertEqual(len(rows), 2)
        unowned = [r for r in rows if r["run_id"] is None]
        self.assertEqual(len(unowned), 1)
        self.assertEqual(unowned[0]["quantity"], 5.0)

    def test_stop_releases_a_held_position_to_the_unowned_book(self):
        """run_id means 'an ACTIVE run owns this'. A stopped run must hand a
        held position back, or it becomes invisible to manual selling."""
        from automation import execute_paper_trade
        run = self._create()
        self._start(run)
        execute_paper_trade(self.agent, "BTC", "crypto", "buy", 1.0, 100.0, run_id=run)
        self.client.post(f"/api/runs/{run}/stop", json={"flatten": False},
                         headers=self._h())
        # a run holding a position stops via `stopping`; the engine finishes it
        import run_engine
        run_engine.control_pass()
        rows = self._positions()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["run_id"],
                          "held position stayed locked to the stopped run")

    def test_stopped_run_frees_its_filter_slot(self):
        a = self._create()
        self._start(a)
        self.client.post(f"/api/runs/{a}/stop", json={"flatten": False},
                         headers=self._h())
        b = self._create()  # identical settings
        self.assertEqual(self._start(b).status_code, 200)

    # ── upgrading keys written before the filter shipped ───────────────

    def test_legacy_key_is_upgraded_by_the_control_pass(self):
        """A run already active at deploy time holds `agent:market:symbol`.
        A legacy key can never collide with a new-format one, so leaving it
        would let a genuine duplicate start alongside it."""
        import run_engine
        run = self._create()
        self._start(run)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET active_key = ? WHERE id = ?",
                        (f"{self.agent}:crypto:BTC", run))
            conn.commit()
        finally:
            conn.close()
        with patch.object(run_engine, "_evaluate_stop", return_value=None):
            run_engine.control_pass()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT active_key, status FROM trading_runs WHERE id = ?", (run,))
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["active_key"].count(":"), 3, row["active_key"])
        self.assertEqual(row["status"], trading_runs.STATUS_RUNNING)

    def test_duplicate_holding_a_legacy_key_is_still_halted(self):
        """Upgrading must not become a way to smuggle a duplicate through:
        when the correctly-formatted slot is taken, the legacy run halts."""
        import run_engine
        keeper = self._create()
        self._start(keeper)
        stray = self._create()          # identical settings -> refused a start
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            # force it active with a legacy key, as a pre-deploy row would be
            cur.execute(
                "UPDATE trading_runs SET status = ?, active_key = ? WHERE id = ?",
                (trading_runs.STATUS_RUNNING, f"{self.agent}:crypto:BTC", stray))
            conn.commit()
        finally:
            conn.close()
        with patch.object(run_engine, "_evaluate_stop", return_value=None):
            out = run_engine.control_pass()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, status_reason FROM trading_runs WHERE id = ?", (stray,))
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["status"], trading_runs.STATUS_PAUSED)
        self.assertEqual(row["status_reason"], "duplicate_active_key")
        self.assertEqual(out["keys_conflicted"], 1)

    # ── the digest itself ──────────────────────────────────────────────

    def test_filter_key_is_stable_and_field_sensitive(self):
        base = {"interval_minutes": 60, "min_confidence": 0.65, "provider": None}
        k = trading_runs.filter_key("spot", base)
        self.assertEqual(k, trading_runs.filter_key("spot", dict(base)))
        self.assertNotEqual(k, trading_runs.filter_key("futures", base))
        self.assertNotEqual(k, trading_runs.filter_key("spot", {**base, "interval_minutes": 30}))
        self.assertNotEqual(k, trading_runs.filter_key("spot", {**base, "min_confidence": 0.7}))
        self.assertNotEqual(k, trading_runs.filter_key("spot", {**base, "provider": "openai"}))
        # irrelevant fields must not move it
        self.assertEqual(k, trading_runs.filter_key("spot", {**base, "max_bet_usd": 9999}))


if __name__ == "__main__":
    unittest.main()
