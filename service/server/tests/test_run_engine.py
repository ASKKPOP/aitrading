"""Trading Runs scheduler engine (Plan 10, Phase 2) — exactly-once gates.

Covers the Phase 2 verification gates without a live LLM:
  * a due running run executes exactly one attributed, journaled trade
  * client_order_id idempotency (same seq can never trade twice)
  * fencing: a zombie claimant whose lease was reclaimed cannot trade,
    and a stop pressed mid-cycle prevents the trade
  * lease claim: owner renewal allowed; a live foreign lease blocks
  * crash recovery: an uncleared lease does not wedge the run — the next
    due window reclaims and runs a fresh cycle under a new seq
  * pre-LLM gates: market closed / insufficient cash skip WITHOUT calling
    the analysis (zero LLM cost), journaled as gate_skip telemetry
  * control pass: at_time arming fires; stopping without positions finishes
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
import run_engine
import trading_runs
from routes import create_app

BUY_ANALYSIS = {
    "symbol": "BTC",
    "market": "crypto",
    "analysts": {"technical": {"brief": "t", "data": {"sigma_daily_pct": 2.5,
                                                      "current_price": 100.0}}},
    "decision": {"action": "buy", "confidence": 0.9, "entry": 100.0, "report": "r"},
}


def _ts(dt: datetime) -> str:
    return dt.strftime(trading_runs.TS_FMT)


class RunEngineTests(unittest.TestCase):
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
            json={"name": "engine-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _running_run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        resp = self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        assert resp.status_code == 200, resp.text
        return run_id

    def _row(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
            return dict(cur.fetchone())
        finally:
            conn.close()

    def _set(self, run_id, **cols):
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

    def _signals(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM signals WHERE run_id = ? ORDER BY id", (run_id,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _events(self, run_id):
        resp = self.client.get(f"/api/runs/{run_id}/events?limit=500", headers=self._h())
        return resp.json()["events"]

    # ── happy path ─────────────────────────────────────────────────────

    def test_cycle_executes_one_attributed_journaled_trade(self):
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)

        signals = self._signals(run_id)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["client_order_id"], f"run:{run_id}:cyc:1")
        self.assertAlmostEqual(signals[0]["fee_usd"], 500.0 * 0.001)

        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT run_id, quantity FROM positions WHERE agent_id = ?",
                        (self.agent_id,))
            pos = dict(cur.fetchone())
            self.assertEqual(pos["run_id"], run_id)
            self.assertAlmostEqual(pos["quantity"], 5.0)  # $500 / $100
            cur.execute("SELECT cash FROM agents WHERE id = ?", (self.agent_id,))
            self.assertAlmostEqual(cur.fetchone()["cash"], 100000.0 - 500.0 - 0.5)
        finally:
            conn.close()

        kinds = [e["event_type"] for e in self._events(run_id)]
        self.assertIn("trade", kinds)
        self.assertIn("decision", kinds)
        # lease released after the cycle
        row = self._row(run_id)
        self.assertIsNone(row["claimed_by"])

    def test_duplicate_client_order_id_cannot_trade_twice(self):
        run_id = self._running_run()
        from automation import execute_paper_trade
        first, err = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                         1.0, 100.0, run_id=run_id,
                                         client_order_id=f"run:{run_id}:cyc:7")
        self.assertIsNotNone(first, err)
        second, err2 = execute_paper_trade(self.agent_id, "BTC", "crypto", "buy",
                                           1.0, 100.0, run_id=run_id,
                                           client_order_id=f"run:{run_id}:cyc:7")
        self.assertIsNone(second)
        self.assertIn("duplicate client_order_id", err2)
        self.assertEqual(len(self._signals(run_id)), 1)

    # ── fencing / zombie claimant ──────────────────────────────────────

    def test_zombie_claimant_cannot_trade_after_reclaim(self):
        """SIGSTOP-equivalent: worker A's lease is reclaimed by B while A is
        'inside' its LLM call; A's trade transaction must abort at the fence."""
        run_id = self._running_run()

        def steal_lease_then_decide(*args, **kwargs):
            # B reclaims while A is mid-analysis
            self._set(run_id, claimed_by="worker-B:999",
                      claim_expires_at=_ts(datetime.now(timezone.utc)
                                           + timedelta(seconds=300)))
            return BUY_ANALYSIS

        with patch("analysis_agents.run_analysis",
                   side_effect=steal_lease_then_decide):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("lease reclaimed", result["skip_reason"] or "")
        self.assertEqual(self._signals(run_id), [])

    def test_stop_pressed_mid_cycle_prevents_trade(self):
        run_id = self._running_run()

        def stop_then_decide(*args, **kwargs):
            self._set(run_id, status="stopped", active_key=None)
            return BUY_ANALYSIS

        with patch("analysis_agents.run_analysis", side_effect=stop_then_decide):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("fence: run is stopped", result["skip_reason"] or "")
        self.assertEqual(self._signals(run_id), [])

    def test_live_foreign_lease_blocks_claim(self):
        run_id = self._running_run()
        self._set(run_id, claimed_by="worker-B:999",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       + timedelta(seconds=300)))
        result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("not claimed", result["skip_reason"])

    def test_expired_foreign_lease_is_reclaimed(self):
        run_id = self._running_run()
        self._set(run_id, claimed_by="worker-B:999",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       - timedelta(seconds=10)),
                  cycle_seq=3)
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        # fresh cycle under a NEW seq — never a reuse of the stale one
        self.assertEqual(self._signals(run_id)[0]["client_order_id"],
                         f"run:{run_id}:cyc:4")

    def test_crashed_worker_lease_does_not_wedge_the_run(self):
        """kill -9 equivalent: a cycle that died without releasing its lease.
        The run waits for its due window, then the reclaim path runs a fresh
        cycle — no duplicate of the crashed cycle's trade."""
        run_id = self._running_run()
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            run_engine.run_cycle(run_id)  # cycle 1 trades
        # simulate crash: stale foreign lease left behind, clock in the past
        self._set(run_id,
                  claimed_by=run_engine.WORKER_IDENTITY + ":dead",
                  claim_expires_at=_ts(datetime.now(timezone.utc)
                                       - timedelta(seconds=5)),
                  last_cycle_at=_ts(datetime.now(timezone.utc)
                                    - timedelta(hours=2)))
        self.assertEqual(run_engine.due_run_ids(), [run_id])
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result)
        ids = [s["client_order_id"] for s in self._signals(run_id)]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate keys: {ids}")
        self.assertEqual(len(ids), 2)  # two distinct cycles, one trade each

    # ── pre-LLM gates ──────────────────────────────────────────────────

    def test_market_closed_skips_without_llm(self):
        run_id = self._running_run()
        with patch("routes_shared.is_market_open", return_value=False), \
             patch("analysis_agents.run_analysis") as analysis:
            result = run_engine.run_cycle(run_id)
        analysis.assert_not_called()
        self.assertEqual(result["skip_reason"], "market closed")
        kinds = [(e["event_type"], (e["payload"] or {}).get("stage"))
                 for e in self._events(run_id)]
        self.assertIn(("gate_skip", "pre"), kinds)

    def test_insufficient_cash_skips_without_llm(self):
        run_id = self._running_run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute("UPDATE agents SET cash = 10 WHERE id = ?", (self.agent_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("analysis_agents.run_analysis") as analysis:
            result = run_engine.run_cycle(run_id)
        analysis.assert_not_called()
        self.assertIn("insufficient cash", result["skip_reason"])

    def test_kill_switch_disables_tick(self):
        os.environ["AUTO_TRADING_ENABLED"] = "false"
        import asyncio
        out = asyncio.run(run_engine.tick())
        self.assertEqual(out, {"enabled": False})

    # ── control pass ───────────────────────────────────────────────────

    def test_at_time_arming_fires_when_due(self):
        future = _ts(datetime.now(timezone.utc) + timedelta(days=1))
        run_id = self.client.post(
            "/api/runs",
            json={"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0,
                  "start_condition": {"type": "at_time", "at": future}},
            headers=self._h()).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        self.assertEqual(self._row(run_id)["status"], "armed")

        out = run_engine.control_pass()
        self.assertEqual(out["armed_started"], 0)  # not due yet

        past = _ts(datetime.now(timezone.utc) - timedelta(seconds=5))
        self._set(run_id, start_condition_json=json.dumps(
            {"type": "at_time", "at": past}))
        out = run_engine.control_pass()
        self.assertEqual(out["armed_started"], 1)
        self.assertEqual(self._row(run_id)["status"], "running")

    def test_stopping_without_position_finishes(self):
        run_id = self._running_run()
        self._set(run_id, status="stopping", status_reason="user_stop")
        out = run_engine.control_pass()
        self.assertEqual(out["stopping_finished"], 1)
        row = self._row(run_id)
        self.assertEqual(row["status"], "stopped")
        self.assertIsNone(row["active_key"])

    def test_due_check_respects_interval(self):
        run_id = self._running_run()
        self._set(run_id, last_cycle_at=_ts(datetime.now(timezone.utc)
                                            - timedelta(minutes=2)))
        self.assertEqual(run_engine.due_run_ids(), [])  # 60m interval default
        self._set(run_id, last_cycle_at=_ts(datetime.now(timezone.utc)
                                            - timedelta(minutes=61)))
        self.assertEqual(run_engine.due_run_ids(), [run_id])


class StaleInvalidationScrubTests(unittest.TestCase):
    """A brief whose invalidation level the tape has already passed must not
    reach the desk verbatim.

    Prod 2026-08-03: run 938 USDJPY carried "a break above 152.00" for a SHORT
    while price sat at 156.7 — the level was wrong-side at build time and the
    run never opened a position across 7 cycles. `level-integrity` asks the desk
    to treat such a level as stale and judge on structure, and it did on cycle 5
    ("making the brief stale"), half-did on cycle 6, and fully regressed on
    cycle 7 ("Short thesis is already invalidated (price > 152), so we hold").
    Asking the model to resist text it is shown every cycle is not stable; the
    text should not be shown. Runs 933 and 934 died the same way earlier that
    night, ~20 cycles and zero trades between the three.
    """

    def test_wrong_side_level_is_replaced_with_a_derive_instruction(self):
        thesis = {"direction": "short", "invalidation": "A break above 152.00 ends it.",
                  "rationale": "yen strength"}
        out = run_engine._usable_thesis(thesis, 156.73)
        self.assertNotIn("152", out["invalidation"])
        self.assertIn("stale", out["invalidation"].lower())
        # everything else survives untouched
        self.assertEqual(out["rationale"], "yen strength")
        self.assertEqual(out["direction"], "short")
        self.assertIsNot(out, thesis, "must not mutate the stored thesis")
        self.assertIn("152", thesis["invalidation"])

    def test_absurdly_distant_level_is_replaced(self):
        # run 937: "$18" on a $472 asset — the desk itself called it irrelevant
        thesis = {"direction": "long",
                  "invalidation": "Failure to stay above $18 for 6 hours."}
        out = run_engine._usable_thesis(thesis, 472.29)
        self.assertNotIn("$18", out["invalidation"])

    def test_usable_level_is_left_alone(self):
        thesis = {"direction": "short",
                  "invalidation": "A break above 158.00 ends the short."}
        out = run_engine._usable_thesis(thesis, 156.73)
        self.assertIn("158.00", out["invalidation"])

    def test_relative_level_is_left_alone(self):
        thesis = {"direction": "short",
                  "invalidation": "Price closes above the 20-day moving average."}
        out = run_engine._usable_thesis(thesis, 156.73)
        self.assertIn("20-day moving average", out["invalidation"])

    def test_the_scrub_actually_reaches_the_prompt(self):
        """The helper is worthless if it is not wired in — assert the number is
        absent from the prompt the desk is actually handed."""
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        run = {"id": 1, "agent_id": 1, "symbol": "USDJPY", "market": "forex",
               "market_type": "spot"}
        cfg = {"thesis": {"direction": "short", "horizon_hours": 24,
                          "invalidation": "A break above 152.00 ends the short.",
                          "rationale": "yen strength"}}
        with patch("price_fetcher.get_price_from_market", return_value=156.73), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate), \
                patch.object(run_engine, "_position_quantity", return_value=0.0), \
                patch("trading_skills.skills_block", return_value=""):
            run_engine._light_analysis(run, cfg)

        self.assertIn("prompt", captured, "the desk was never called")
        self.assertNotIn("152.00", captured["prompt"],
                         "the already-passed level reached the desk verbatim")
        self.assertIn("stale", captured["prompt"].lower())

    def test_missing_price_or_direction_changes_nothing(self):
        thesis = {"direction": "short", "invalidation": "A break above 152.00."}
        self.assertEqual(run_engine._usable_thesis(thesis, None), thesis)
        self.assertEqual(run_engine._usable_thesis({"invalidation": "x"}, 100.0),
                         {"invalidation": "x"})
        self.assertEqual(run_engine._usable_thesis({}, 100.0), {})


class EarningsBriefTests(unittest.TestCase):
    """A scheduled print is a session gap with a date, and the us-stock desks
    (939 TSLA / 940 NVDA) held positions with zero knowledge of it — the FMP
    feed that should have supplied the date shipped key-gated and the key was
    never set. The brief line is shown flat AND holding: fresh exposure opened
    into a print is the same unpriced gap as carrying one through it."""

    def _run(self, market="us-stock", symbol="NVDA"):
        return {"id": 1, "agent_id": 1, "symbol": symbol, "market": market,
                "market_type": "spot"}

    def test_near_print_renders_with_day_count(self):
        with patch("fmp_feed.days_to_earnings", return_value=2):
            line = run_engine._earnings_state_line(self._run())
        self.assertIn("NVDA reports earnings in 2 calendar day(s)", line)
        self.assertIn("gap", line)

    def test_print_today_says_today(self):
        with patch("fmp_feed.days_to_earnings", return_value=0):
            line = run_engine._earnings_state_line(self._run(symbol="TSLA"))
        self.assertIn("TSLA reports earnings TODAY", line)

    def test_far_print_and_unknown_render_nothing(self):
        with patch("fmp_feed.days_to_earnings",
                   return_value=run_engine.EARNINGS_BRIEF_DAYS + 1):
            self.assertEqual(run_engine._earnings_state_line(self._run()), "")
        with patch("fmp_feed.days_to_earnings", return_value=None):
            self.assertEqual(run_engine._earnings_state_line(self._run()), "")

    def test_non_us_stock_never_queries_the_feed(self):
        with patch("fmp_feed.days_to_earnings",
                   side_effect=AssertionError("crypto must not query")):
            self.assertEqual(
                run_engine._earnings_state_line(self._run(market="crypto")), "")

    def test_feed_failure_is_silent(self):
        with patch("fmp_feed.days_to_earnings", side_effect=RuntimeError("down")):
            self.assertEqual(run_engine._earnings_state_line(self._run()), "")

    def test_the_line_actually_reaches_the_light_prompt(self):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        run = self._run()
        cfg = {"thesis": {"direction": "long", "horizon_hours": 24,
                          "invalidation": "below the recent swing low",
                          "rationale": "momentum"}}
        with patch("price_fetcher.get_price_from_market", return_value=500.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate), \
                patch.object(run_engine, "_position_quantity", return_value=0.0), \
                patch("trading_skills.skills_block", return_value=""), \
                patch("fmp_feed.days_to_earnings", return_value=2):
            run_engine._light_analysis(run, cfg)

        self.assertIn("prompt", captured, "the desk was never called")
        self.assertIn("NVDA reports earnings in 2 calendar day(s)",
                      captured["prompt"],
                      "the earnings brief never reached the desk (flat run)")


class HoldStreakBriefTests(unittest.TestCase):
    """949 (2026-08-05): NINE consecutive flat holds at conviction
    0.24-0.30 with the flat-retirement clause in context and the retire
    verb untouched — because each cycle's prompt shows only that cycle,
    the desk cannot count its own streak. The brief supplies the fact;
    the skill supplies the judgment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self, actions):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, "
            "created_at) VALUES (1, 's@x.com', 'x', '2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT OR IGNORE INTO agents (id, name, token_hash, cash, "
            "user_id, created_at) "
            "VALUES (1, 'streak', 'th', 1000, 1, '2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, "
            "created_at) VALUES (1, 'HYPEUSDT', 'crypto', 'running', "
            "'2026-08-01T00:00:00Z')")
        run_id = cur.lastrowid
        for i, a in enumerate(actions):
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'decision', ?, ?)",
                (run_id, i + 1, f"2026-08-05T0{i}:00:00Z",
                 json.dumps({"action": a, "confidence": 0.3})))
        conn.commit()
        conn.close()
        return {"id": run_id, "agent_id": 1, "symbol": "HYPEUSDT",
                "market": "crypto"}

    def test_long_flat_streak_renders_the_count(self):
        run = self._seed(["sell"] + ["hold"] * 9)
        line = run_engine._hold_streak_line(run, 0.0)
        self.assertIn("flat with no action for 9 consecutive cycles", line)

    def test_streak_resets_at_the_last_trade_action(self):
        run = self._seed(["hold"] * 6 + ["buy"] + ["hold"] * 2)
        self.assertEqual(run_engine._hold_streak_line(run, 0.0), "")

    def test_short_streak_and_held_position_render_nothing(self):
        run = self._seed(["hold"] * 3)
        self.assertEqual(run_engine._hold_streak_line(run, 0.0), "")
        run9 = self._seed(["hold"] * 9)
        self.assertEqual(run_engine._hold_streak_line(run9, 5.0), "")


class ExitSizeBriefTests(unittest.TestCase):
    """Losing trims averaged -1.53 and were harmless; losing FULL closes
    averaged -6.68 and carried 91% of all loss (84 closes, 08-04/05). The
    desk was never told the SCALE of the move it reacts to, nor that
    'reduce' exists as an alternative to 'close'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    _RUN = {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto"}

    def _pnl(self, ent=523.75, mark=521.16, ok=True):
        return {"mark_age_ok": ok,
                "position": {"entry_price": ent, "current_price": mark}}

    def test_states_the_move_against_an_ordinary_day_and_names_the_verb(self):
        # run 967's real numbers: bought 523.75, sold 521.16 = -0.49%.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl()), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=2.0):
            line = run_engine._exit_size_line(self._RUN, 4.327)
        self.assertIn("move against you is 0.49%", line)
        self.assertIn("ordinary day on this symbol moves 2.00%", line)
        self.assertIn("25% of one ordinary day", line)
        self.assertIn("'reduce'", line)
        self.assertIn("Closing the WHOLE position is the expensive verb", line)

    def test_silent_when_the_position_is_in_profit(self):
        # This brief is about adverse drift; a winner must not be nagged.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(mark=530.0)):
            self.assertEqual(run_engine._exit_size_line(self._RUN, 4.327), "")
        # ...and a SHORT in profit (price fell) is likewise silent.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(mark=500.0)):
            self.assertEqual(run_engine._exit_size_line(self._RUN, -4.327), "")

    def test_short_reads_adverse_in_its_own_direction(self):
        # price ROSE against a short => adverse.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(mark=530.0)), \
             patch.object(run_engine, "_typical_daily_move_pct",
                          return_value=None):
            line = run_engine._exit_size_line(self._RUN, -4.327)
        self.assertIn("move against you is 1.19%", line)
        self.assertNotIn("ordinary day", line)   # no data => no fabricated floor

    def test_fail_soft_on_flat_book_and_stale_mark(self):
        self.assertEqual(run_engine._exit_size_line(self._RUN, 0.0), "")
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(ok=False)):
            self.assertEqual(run_engine._exit_size_line(self._RUN, 4.327), "")

    def test_typical_move_is_a_median_and_needs_enough_history(self):
        import price_fetcher
        bars = [{"close": c} for c in
                (100, 101, 100, 101, 100, 101, 100, 130)]   # one event day
        with patch.object(price_fetcher, "get_daily_candles",
                          return_value=bars):
            v = run_engine._typical_daily_move_pct(self._RUN)
        self.assertLess(v, 2.0, "the 30% event day redefined 'ordinary'")
        with patch.object(price_fetcher, "get_daily_candles",
                          return_value=[{"close": 100}, {"close": 101}]):
            self.assertIsNone(run_engine._typical_daily_move_pct(self._RUN))

    def test_the_line_is_actually_WIRED_into_the_light_prompt(self):
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = dict(self._RUN, market_type="spot")
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=521.16), \
            patch.object(price_fetcher, "get_daily_candles", return_value=[]), \
            patch.object(run_engine, "_position_quantity", return_value=4.327), \
            patch.object(run_engine, "_exit_size_line",
                         return_value="EXITSIZE_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("EXITSIZE_SENTINEL", seen.get("prompt", ""),
                      "exit-size line is not wired into the light prompt")

    def test_the_line_is_actually_WIRED_into_the_full_prompt(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_exit_size_line(run, pos_qty)", src,
                      "exit-size line is not wired into the full prompt")


class BrakeDistanceBriefTests(unittest.TestCase):
    """The desk authors its stop in price %, the platform retires the run on
    equity drawdown in USD, and nothing reconciled the two. Run 971 authored
    a 3.5% stop with its brake 0.72% away and was retired on a -0.62% move.
    The brief supplies the distance; the skill supplies the judgment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *, max_loss=85.26, peak=9.79):
        # size_mult must be a real ladder value: load_state ASSERTS it and
        # silently returns the default state (peak 0.0) otherwise, which
        # would quietly make every case here read a peak it never set.
        return {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
                "stop_conditions_json": json.dumps({"max_loss_usd": max_loss}),
                "adapt_state_json": json.dumps({"v": 1, "peak_total_pnl": peak,
                                                "size_mult": 1.0})}

    def _pnl(self, *, total=-54.50, mark=517.34, ok=True):
        return {"total": total, "mark_age_ok": ok,
                "position": {"current_price": mark, "entry_price": 520.55}}

    def test_renders_the_rail_as_a_price_move(self):
        # 971's real numbers: room = 0.70*85.26 - (9.79 - -54.50) = -4.60 =>
        # already past the rail. Back it off to a live-but-tight case.
        run = self._run(peak=0.0)
        with patch.object(run_engine, "compute_run_pnl",
                               return_value=self._pnl(total=-10.0)):
            line = run_engine._brake_distance_line(run, 15.8115)
        # room = 59.682 - 10 = 49.682 ; notional = 15.8115*517.34 = 8180.0
        self.assertIn("Risk rail", line)
        self.assertIn("0.61% adverse price move", line)
        self.assertIn("adding to the position divides this distance", line)

    def test_add_halves_the_distance(self):
        # Same equity room, double the position => half the price distance.
        run = self._run(peak=0.0)
        with patch.object(run_engine, "compute_run_pnl",
                               return_value=self._pnl(total=-10.0)):
            one = run_engine._brake_distance_line(run, 7.9058)
            two = run_engine._brake_distance_line(run, 15.8115)
        self.assertIn("1.21% adverse price move", one)
        self.assertIn("0.61% adverse price move", two)

    def test_past_the_rail_says_so_without_a_percentage(self):
        run = self._run(peak=9.79)
        with patch.object(run_engine, "compute_run_pnl",
                               return_value=self._pnl(total=-54.50)):
            line = run_engine._brake_distance_line(run, 15.8115)
        self.assertIn("already at or past", line)
        self.assertNotIn("adverse price move", line)

    def test_fail_soft_on_flat_book_stale_mark_and_no_stop(self):
        run = self._run()
        self.assertEqual(run_engine._brake_distance_line(run, 0.0), "")
        with patch.object(run_engine, "compute_run_pnl",
                               return_value=self._pnl(ok=False)):
            self.assertEqual(
                run_engine._brake_distance_line(run, 15.8115), "")
        with patch.object(run_engine, "compute_run_pnl",
                               return_value=self._pnl()):
            self.assertEqual(
                run_engine._brake_distance_line(self._run(max_loss=0),
                                                15.8115), "")

    def test_the_line_is_actually_WIRED_into_the_light_prompt(self):
        # A brief line that renders correctly but is not concatenated into
        # the prompt is a no-op. Unwiring the light path once passed the
        # ENTIRE suite (3313 tests) — this is the guard for that.
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=517.34), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=15.8115), \
            patch.object(run_engine, "_brake_distance_line",
                         return_value="RAIL_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("RAIL_SENTINEL", seen.get("prompt", ""),
                      "brake line is not wired into the light prompt")

    def test_the_line_is_actually_WIRED_into_the_full_prompt(self):
        seen = {}

        def _capture(*a, **kw):
            seen["position_state"] = kw.get("position_state") or ""
            raise RuntimeError("stop here — the kwarg is all we need")

        import analysis_agents
        with patch.object(run_engine, "_brake_distance_line",
                          return_value="RAIL_SENTINEL\n"), \
                patch.object(analysis_agents, "run_analysis", _capture):
            try:
                run_engine.run_cycle(-1)          # no such run: exits early
            except Exception:                      # noqa: BLE001
                pass
        # run_cycle(-1) never reaches the call, so assert on the source wiring
        # of the composed kwarg instead — both sites must carry the line.
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_brake_distance_line(run, pos_qty)", src,
                      "brake line is not wired into the full prompt")

    def test_tracks_the_rail_constant_it_describes(self):
        # Hardcoding 0.70 here would let the line drift out of sync with the
        # brake. It must read the fraction from run_feedback itself.
        import run_feedback
        run = self._run(peak=0.0)
        with patch.dict(run_feedback.ADAPT_BOUNDS,
                             {"retire_drawdown_frac": 0.35}):
            with patch.object(run_engine, "compute_run_pnl",
                                   return_value=self._pnl(total=0.0)):
                line = run_engine._brake_distance_line(run, 15.8115)
        # 0.35*85.26 = 29.841 over notional 8180.0 = 0.36%
        self.assertIn("0.36% adverse price move", line)


class StopCoherenceBriefTests(unittest.TestCase):
    """R10 (2026-08-14): every large entry loss of 08-13 was sized so the
    platform rail HAD to fire before the desk's own stop could — SPCX's
    6.4% stop meant $212 against a $44 budget. The entry line supplies the
    room arithmetic on a FLAT book (where _brake_distance_line is silent),
    and the apply-path clamp enforces it shrink-only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *, max_loss=85.26, peak=0.0, feedback=True):
        # feedback=True is the fleet shape — the drawdown brake exists only
        # for feedback-enabled runs (R10 adversarial pass), so the fixtures
        # here carry it explicitly.
        return {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
                "stop_conditions_json": json.dumps({"max_loss_usd": max_loss}),
                "config_snapshot_json": json.dumps({"feedback": feedback}),
                "adapt_state_json": json.dumps({"v": 1, "peak_total_pnl": peak,
                                                "size_mult": 1.0})}

    def _pnl(self, *, total=0.0, mark=517.34, ok=True):
        return {"total": total, "mark_age_ok": ok,
                "position": {"current_price": mark, "entry_price": 520.55}}

    def test_a_non_feedback_run_rooms_at_the_full_max_loss(self):
        # The drawdown brake never fires for a manual (feedback-off) run —
        # its binding rail is stop_event:max_loss at 100% of the cap. Using
        # the brake fraction over-shrank manual runs ~30% against a rail
        # that does not exist for them.
        run = self._run(feedback=False)
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(total=0.0)):
            room = run_engine._brake_room_usd(run)
        self.assertAlmostEqual(room, 85.26, places=4)

    def test_a_stale_mark_on_a_held_book_yields_no_room(self):
        # An unknown mark must never clamp or render (add path only — a
        # flat book has no mark to be stale).
        run = self._run()
        stale = {"total": -5.0, "mark_age_ok": False,
                 "position": {"quantity": 3.0, "current_price": 500.0,
                              "entry_price": 520.55}}
        with patch.object(run_engine, "compute_run_pnl", return_value=stale):
            self.assertIsNone(run_engine._brake_room_usd(run))

    def test_room_tracks_the_rail_constant_it_pairs_with(self):
        # Hardcoding 0.70 would let the room drift from the brake it
        # describes — same guard as _brake_distance_line's.
        import run_feedback
        run = self._run()
        with patch.dict(run_feedback.ADAPT_BOUNDS,
                        {"retire_drawdown_frac": 0.35}):
            with patch.object(run_engine, "compute_run_pnl",
                              return_value=self._pnl(total=0.0)):
                room = run_engine._brake_room_usd(run)
        self.assertAlmostEqual(room, 0.35 * 85.26, places=4)

    def test_room_agrees_with_the_brake_distance_line(self):
        # The held-book line and the flat-book room must be the same
        # number: pct rendered by the line × notional == room.
        run = self._run(peak=0.0)
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(total=-10.0)):
            room = run_engine._brake_room_usd(run)
            line = run_engine._brake_distance_line(run, 15.8115)
        # room = 0.70*85.26 - 10 = 49.682; notional 15.8115*517.34 = 8180.0
        self.assertAlmostEqual(room, 49.682, places=3)
        self.assertIn("$49.68", line)

    def test_entry_rail_renders_only_on_a_flat_book(self):
        run = self._run()
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(total=0.0)):
            flat = run_engine._entry_rail_line(run, 0.0)
            held = run_engine._entry_rail_line(run, 15.8115)
        self.assertIn("Sizing rail for a NEW entry", flat)
        # room = 59.682; a 1% stop supports room/0.01 = $5,968 of notional
        self.assertIn("$59.68", flat)
        self.assertIn("$5,968", flat)
        self.assertEqual(held, "")

    def test_entry_rail_with_no_room_warns_instead_of_arithmetic(self):
        run = self._run(peak=70.0)
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(total=-10.0)):
            line = run_engine._entry_rail_line(run, 0.0)
        # room = 59.682 - 80 < 0
        self.assertIn("NO remaining loss budget", line)
        self.assertNotIn("supports at most", line)

    def test_entry_rail_fail_soft_without_a_stop_and_kill_switch(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl()):
            self.assertEqual(
                run_engine._entry_rail_line(self._run(max_loss=0), 0.0), "")
        os.environ["RUN_STOP_COHERENCE"] = "0"
        try:
            with patch.object(run_engine, "compute_run_pnl",
                              return_value=self._pnl()):
                self.assertEqual(
                    run_engine._entry_rail_line(self._run(), 0.0), "")
        finally:
            os.environ.pop("RUN_STOP_COHERENCE", None)

    def test_the_entry_line_is_actually_WIRED_into_the_light_prompt(self):
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=517.34), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=0.0), \
            patch.object(run_engine, "_entry_rail_line",
                         return_value="ENTRY_RAIL_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("ENTRY_RAIL_SENTINEL", seen.get("prompt", ""),
                      "entry rail line is not wired into the light prompt")

    def test_the_entry_line_is_WIRED_into_the_full_prompt_source(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_entry_rail_line(run, pos_qty)", src,
                      "entry rail line is not wired into the full prompt")


class LastCycleWordBriefTests(unittest.TestCase):
    """R11 (2026-08-14): QNT bought 29 minutes after its own cycle wrote
    "thesis already invalidated" — nothing showed the desk what it had
    just said. The line quotes the desk's own last decision back to it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _emit(self, run_id: int, payload: dict, seq: int = 0):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'decision', '2026-08-14T00:00:00Z', ?)",
                (run_id, seq, json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def test_quotes_the_desks_own_last_report(self):
        self._emit(7, {"action": "hold",
                       "report": "Long thesis is already invalidated because "
                                 "price is below today's open — no entry."})
        line = run_engine._last_cycle_word_line({"id": 7})
        self.assertIn("Your own last cycle (action: hold", line)
        self.assertIn("already invalidated", line)
        self.assertIn("standing invalidation", line)

    def test_silent_when_there_is_no_history_or_no_report(self):
        self.assertEqual(run_engine._last_cycle_word_line({"id": 99}), "")
        self._emit(8, {"action": "hold", "report": ""})
        self.assertEqual(run_engine._last_cycle_word_line({"id": 8}), "")

    def test_a_long_report_is_truncated_not_dropped(self):
        self._emit(9, {"action": "sell", "report": "word " * 200})
        line = run_engine._last_cycle_word_line({"id": 9})
        self.assertIn("…", line)
        self.assertLess(len(line), 900)

    def test_the_newest_decision_wins(self):
        self._emit(10, {"action": "hold", "report": "older words"}, seq=1)
        self._emit(10, {"action": "buy", "report": "newest words"}, seq=2)
        line = run_engine._last_cycle_word_line({"id": 10})
        self.assertIn("newest words", line)
        self.assertNotIn("older words", line)

    def test_an_errored_cycle_does_not_erase_the_standing_word(self):
        # An analysis failure still emits a decision event with empty
        # action/report; a LIMIT-1 read of that row erased the standing
        # invalidation one failed cycle after it was written (adversarial
        # pass, reproduced). The line must scan back past empty rows.
        self._emit(11, {"action": "hold",
                        "report": "thesis already invalidated"}, seq=1)
        self._emit(11, {"action": None, "report": ""}, seq=2)
        line = run_engine._last_cycle_word_line({"id": 11})
        self.assertIn("already invalidated", line)

    def test_the_line_carries_the_age_of_the_words(self):
        # Words from a fixed 2026-08-14T00:00:00Z stamp are days old by
        # any later clock — quoted undated they would read as one cycle
        # old across a weekend or pause.
        self._emit(12, {"action": "hold", "report": "friday words"})
        line = run_engine._last_cycle_word_line({"id": 12})
        self.assertIn("ago)", line)

    def _emit_skip(self, run_id: int, payload: dict, seq: int = 0):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, 'gate_skip', '2026-08-14T00:00:00Z', ?)",
                (run_id, seq, json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def test_a_discarded_order_is_reported_as_not_executed(self):
        # Fleet 35 UNI (2026-08-15 11:23Z): the desk's sell was dust-skipped,
        # the next cycle read "action: sell" with no outcome, inferred an
        # "existing short position" and held at 0.78 to protect a phantom
        # book. The quote must carry the discard.
        self._emit(20, {"action": "sell", "cycle": 6,
                        "report": "short the breakdown"}, seq=1)
        self._emit_skip(20, {"cycle": 6, "stage": "risk",
                             "reason": "dust order skip (margin $9.25 "
                                       "< floor $10.00)"}, seq=2)
        line = run_engine._last_cycle_word_line({"id": 20})
        self.assertIn("did NOT execute", line)
        self.assertIn("dust order skip", line)
        self.assertIn("book is unchanged", line)

    def test_an_executed_order_carries_no_discard_note(self):
        self._emit(21, {"action": "sell", "cycle": 3,
                        "report": "short the breakdown"}, seq=1)
        line = run_engine._last_cycle_word_line({"id": 21})
        self.assertNotIn("did NOT execute", line)

    def test_a_hold_never_carries_the_discard_note(self):
        # Every hold emits its own gate_skip ("decision is 'hold'") in the
        # same cycle — a hold must never be labelled a discarded order.
        self._emit(22, {"action": "hold", "cycle": 2,
                        "report": "nothing to do"}, seq=1)
        self._emit_skip(22, {"cycle": 2, "stage": "risk",
                             "reason": "decision is 'hold'"}, seq=2)
        line = run_engine._last_cycle_word_line({"id": 22})
        self.assertNotIn("did NOT execute", line)

    def test_an_old_cycles_skip_does_not_taint_a_newer_order(self):
        self._emit(23, {"action": "sell", "cycle": 4,
                        "report": "first try"}, seq=1)
        self._emit_skip(23, {"cycle": 4, "stage": "risk",
                             "reason": "dust order skip (margin $8.62 "
                                       "< floor $10.00)"}, seq=2)
        self._emit(23, {"action": "sell", "cycle": 5,
                        "report": "second try, executed"}, seq=3)
        line = run_engine._last_cycle_word_line({"id": 23})
        self.assertIn("second try", line)
        self.assertNotIn("did NOT execute", line)

    def test_the_line_is_actually_WIRED_into_both_prompts(self):
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=517.34), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=0.0), \
            patch.object(run_engine, "_last_cycle_word_line",
                         return_value="LAST_WORD_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("LAST_WORD_SENTINEL", seen.get("prompt", ""),
                      "last-cycle line is not wired into the light prompt")
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_last_cycle_word_line(run)", src,
                      "last-cycle line is not wired into the full prompt")


class PredecessorRunBriefTests(unittest.TestCase):
    """R16 (2026-08-14): fleet 32 retired NQ citing "no safe bracket",
    rebuilt it 4h later, and the successor re-longed HIGHER with zero
    reference to the predecessor — −$4.57 across the pair. Memory must
    cross runs on the same agent+market+symbol."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _mk_run(self, rid, *, symbol="NQ", agent=7, stopped_at=None,
                reason=None, pnl=0.0):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            cur.execute(
                "INSERT INTO trading_runs (id, agent_id, symbol, market, "
                "status, status_reason, realized_pnl_usd, stopped_at, "
                "created_at) VALUES (?, ?, ?, 'futures', ?, ?, ?, ?, "
                "'2026-08-14T00:00:00Z')",
                (rid, agent, symbol,
                 'stopped' if stopped_at else 'running',
                 reason, pnl, stopped_at))
            conn.commit()
        finally:
            conn.close()

    def _now_iso(self, hours_ago: float) -> str:
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_quotes_the_predecessors_ending(self):
        self._mk_run(100, stopped_at=self._now_iso(4),
                     reason="desk_retired", pnl=-2.42)
        self._mk_run(101)
        line = run_engine._predecessor_run_line(
            {"id": 101, "agent_id": 7, "market": "futures", "symbol": "NQ"})
        self.assertIn("PREVIOUS run on NQ", line)
        self.assertIn("desk_retired", line)
        self.assertIn("-2.42", line.replace("−", "-"))
        self.assertIn("h ago", line)

    def test_silent_without_a_recent_predecessor(self):
        self._mk_run(103)
        line = run_engine._predecessor_run_line(
            {"id": 103, "agent_id": 7, "market": "futures", "symbol": "NQ"})
        self.assertEqual(line, "")
        # A week-old predecessor is stale tape, not memory.
        self._mk_run(104, stopped_at=self._now_iso(100),
                     reason="desk_retired", pnl=-9.0)
        self._mk_run(105)
        self.assertEqual(run_engine._predecessor_run_line(
            {"id": 105, "agent_id": 7, "market": "futures", "symbol": "NQ"}),
            "")

    def test_scoped_to_agent_and_symbol(self):
        self._mk_run(106, stopped_at=self._now_iso(1),
                     reason="desk_retired", pnl=-5.0)
        self._mk_run(107, symbol="ES")
        self.assertEqual(run_engine._predecessor_run_line(
            {"id": 107, "agent_id": 7, "market": "futures", "symbol": "ES"}),
            "")
        self._mk_run(108, agent=8)
        self.assertEqual(run_engine._predecessor_run_line(
            {"id": 108, "agent_id": 8, "market": "futures", "symbol": "NQ"}),
            "")

    def test_the_line_is_actually_WIRED_into_both_prompts(self):
        seen = {}

        def _capture(prompt, **kw):
            seen["prompt"] = prompt
            return '{"action":"hold","confidence":0.5}'

        import llm_client
        import price_fetcher
        run = {"id": 1, "agent_id": 1, "symbol": "ZECUSDT", "market": "crypto",
               "market_type": "spot"}
        with patch.object(price_fetcher, "get_price_from_market",
                          return_value=517.34), \
            patch.object(price_fetcher, "get_daily_candles",
                         return_value=[]), \
            patch.object(run_engine, "_position_quantity",
                         return_value=0.0), \
            patch.object(run_engine, "_predecessor_run_line",
                         return_value="PREDECESSOR_SENTINEL\n"), \
                patch.object(llm_client, "generate_text", _capture):
            run_engine._light_analysis(run, {})
        self.assertIn("PREDECESSOR_SENTINEL", seen.get("prompt", ""),
                      "predecessor line is not wired into the light prompt")
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_predecessor_run_line(run)", src,
                      "predecessor line is not wired into the composed brief")


class BreadthBriefTests(unittest.TestCase):
    """The catalogue teaches distribution counting and follow-through
    confirmation, but the us-stock desks had no market-wide data to apply
    them to — each read only its own symbol's candles. The breadth line
    supplies that evidence, advisory only, and renders "" on any problem."""

    def _run(self, market="us-stock", symbol="NVDA"):
        return {"id": 1, "agent_id": 1, "symbol": symbol, "market": market,
                "market_type": "spot"}

    def _snapshot(self, **over):
        snap = {"date": "2026-07-31", "above_ma200": 0.70,
                "above_ma200_8ema": 0.69, "above_ma200_200ema": 0.62,
                "trend200": 1, "bearish": False, "above_ma50": 0.65,
                "pink_zone": False}
        snap.update(over)
        return snap

    def test_healthy_snapshot_renders_the_numbers(self):
        with patch("breadth_feed.latest_breadth",
                   return_value=self._snapshot()):
            line = run_engine._breadth_state_line(self._run())
        self.assertIn("70% of stocks above their 200-day MA", line)
        self.assertIn("8-day avg 69%", line)
        self.assertIn("long-term breadth trend rising", line)
        self.assertIn("65% above their 50-day MA", line)
        self.assertIn("not as a signal about this symbol", line)
        self.assertNotIn("bearish", line.lower())

    def test_defensive_flags_render_when_set(self):
        with patch("breadth_feed.latest_breadth",
                   return_value=self._snapshot(trend200=-1, bearish=True,
                                              pink_zone=True)):
            line = run_engine._breadth_state_line(self._run())
        self.assertIn("long-term breadth trend falling", line)
        self.assertIn("Structural bearish zone", line)
        self.assertIn("bearish breadth signal is ACTIVE", line)

    def test_bootstrap_trend_zero_omits_the_trend_clause(self):
        with patch("breadth_feed.latest_breadth",
                   return_value=self._snapshot(trend200=0)):
            line = run_engine._breadth_state_line(self._run())
        self.assertNotIn("breadth trend", line)
        self.assertIn("70% of stocks", line)

    def test_non_us_stock_never_queries_the_feed(self):
        with patch("breadth_feed.latest_breadth",
                   side_effect=AssertionError("crypto must not query")):
            self.assertEqual(
                run_engine._breadth_state_line(self._run(market="crypto")), "")

    def test_missing_snapshot_and_feed_failure_are_silent(self):
        with patch("breadth_feed.latest_breadth", return_value=None):
            self.assertEqual(run_engine._breadth_state_line(self._run()), "")
        with patch("breadth_feed.latest_breadth",
                   side_effect=RuntimeError("down")):
            self.assertEqual(run_engine._breadth_state_line(self._run()), "")

    def test_the_line_actually_reaches_the_light_prompt(self):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        run = self._run()
        cfg = {"thesis": {"direction": "long", "horizon_hours": 24,
                          "invalidation": "below the recent swing low",
                          "rationale": "momentum"}}
        with patch("price_fetcher.get_price_from_market", return_value=500.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate), \
                patch.object(run_engine, "_position_quantity", return_value=0.0), \
                patch("trading_skills.skills_block", return_value=""), \
                patch("fmp_feed.days_to_earnings", return_value=None), \
                patch("breadth_feed.latest_breadth",
                      return_value=self._snapshot()):
            run_engine._light_analysis(run, cfg)

        self.assertIn("prompt", captured, "the desk was never called")
        self.assertIn("US market breadth (advisory", captured["prompt"],
                      "the breadth brief never reached the desk")


class PsychRiskBriefTests(unittest.TestCase):
    """Plan 25 Phase B: the Phase-A skills teach the judgment, but until
    these lines existed no us-stock desk read a market-level crowd gauge
    and no forex desk read any psychology at all. Both lines are advisory,
    facts-only, and render "" on any problem."""

    def _run(self, market="us-stock", symbol="NVDA"):
        return {"id": 1, "agent_id": 1, "symbol": symbol, "market": market,
                "market_type": "spot"}

    def _fg(self, **over):
        row = {"value": 84.0, "classification": "Extreme Greed",
               "prev_1w": 71.0}
        row.update(over)
        return row

    def _dxy(self, **over):
        row = {"value": 121.4, "change_1d_pct": 0.42, "date": "2026-08-13"}
        row.update(over)
        return row

    # ── us-stock crowd line ──
    def test_us_line_renders_value_delta_and_restraint(self):
        with patch("psych_feed.us_fear_greed", return_value=self._fg()):
            line = run_engine._us_psych_line(self._run())
        self.assertIn("US crowd psychology (advisory", line)
        self.assertIn("84/100", line)
        self.assertIn("Extreme Greed", line)
        self.assertIn("+13 vs a week ago", line)
        self.assertIn("never the sole reason", line)

    def test_us_line_omits_week_delta_when_absent(self):
        with patch("psych_feed.us_fear_greed",
                   return_value=self._fg(prev_1w=None)):
            line = run_engine._us_psych_line(self._run())
        self.assertIn("84/100", line)
        self.assertNotIn("week ago", line)

    def test_us_line_market_gate_and_fail_soft(self):
        with patch("psych_feed.us_fear_greed",
                   side_effect=AssertionError("crypto must not query")):
            self.assertEqual(
                run_engine._us_psych_line(self._run(market="crypto")), "")
        with patch("psych_feed.us_fear_greed", return_value=None):
            self.assertEqual(run_engine._us_psych_line(self._run()), "")
        with patch("psych_feed.us_fear_greed",
                   side_effect=RuntimeError("down")):
            self.assertEqual(run_engine._us_psych_line(self._run()), "")

    # ── forex risk-sentiment line ──
    def test_fx_line_renders_fg_and_dxy(self):
        with patch("psych_feed.us_fear_greed",
                   return_value=self._fg(value=18.0,
                                         classification="Extreme Fear",
                                         prev_1w=34.0)), \
                patch("cross_market.dollar_index_cached",
                      return_value=self._dxy()):
            line = run_engine._fx_risk_line(self._run(market="forex",
                                                      symbol="EURUSD"))
        self.assertIn("FX risk sentiment (advisory", line)
        self.assertIn("18/100", line)
        self.assertIn("Extreme Fear", line)
        self.assertIn("+0.42%", line)
        self.assertIn("one signal alone is no trade", line)

    def test_fx_line_renders_without_dxy(self):
        with patch("psych_feed.us_fear_greed", return_value=self._fg()), \
                patch("cross_market.dollar_index_cached", return_value=None):
            line = run_engine._fx_risk_line(self._run(market="forex",
                                                      symbol="EURUSD"))
        self.assertIn("FX risk sentiment (advisory", line)
        self.assertIn("84/100", line)
        self.assertNotIn("dollar index", line)

    def test_fx_line_market_gate_and_fail_soft(self):
        with patch("psych_feed.us_fear_greed",
                   side_effect=AssertionError("us-stock must not use fx line")):
            self.assertEqual(run_engine._fx_risk_line(self._run()), "")
        with patch("psych_feed.us_fear_greed", return_value=None), \
                patch("cross_market.dollar_index_cached", return_value=None):
            self.assertEqual(
                run_engine._fx_risk_line(self._run(market="forex")), "")
        with patch("psych_feed.us_fear_greed",
                   side_effect=RuntimeError("down")), \
                patch("cross_market.dollar_index_cached",
                      side_effect=RuntimeError("down")):
            self.assertEqual(
                run_engine._fx_risk_line(self._run(market="forex")), "")

    # ── VIX-source variant (CNN refuses cloud IPs with 418) ──
    def _vix(self, **over):
        row = {"source": "vix", "value": 27.4, "prev_1w": 24.2}
        row.update(over)
        return row

    def test_us_line_renders_the_vix_variant(self):
        with patch("psych_feed.us_fear_greed", return_value=self._vix()):
            line = run_engine._us_psych_line(self._run())
        self.assertIn("VIX", line)
        self.assertIn("27.4", line)
        self.assertIn("+3.2 vs a week ago", line)
        self.assertIn("never the sole reason", line)
        self.assertNotIn("/100", line)

    def test_fx_line_renders_the_vix_variant(self):
        with patch("psych_feed.us_fear_greed", return_value=self._vix()), \
                patch("cross_market.dollar_index_cached", return_value=None):
            line = run_engine._fx_risk_line(self._run(market="forex",
                                                      symbol="EURUSD"))
        self.assertIn("FX risk sentiment (advisory", line)
        self.assertIn("VIX 27.4", line)
        self.assertIn("one signal alone is no trade", line)
        self.assertNotIn("/100", line)

    # ── wiring: the lines must reach the actual desk prompt ──
    def _light_prompt(self, run):
        captured = {}

        def fake_generate(prompt, **kw):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5}'

        cfg = {"thesis": {"direction": "long", "horizon_hours": 24,
                          "invalidation": "below the recent swing low",
                          "rationale": "momentum"}}
        with patch("price_fetcher.get_price_from_market", return_value=500.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate), \
                patch.object(run_engine, "_position_quantity",
                             return_value=0.0), \
                patch("trading_skills.skills_block", return_value=""), \
                patch("fmp_feed.days_to_earnings", return_value=None), \
                patch("breadth_feed.latest_breadth", return_value=None), \
                patch("psych_feed.us_fear_greed", return_value=self._fg()), \
                patch("cross_market.dollar_index_cached",
                      return_value=self._dxy()):
            run_engine._light_analysis(run, cfg)
        return captured.get("prompt", "")

    def test_us_line_reaches_the_light_prompt(self):
        prompt = self._light_prompt(self._run())
        self.assertIn("US crowd psychology (advisory", prompt,
                      "the crowd brief never reached the us-stock desk")
        self.assertNotIn("FX risk sentiment", prompt)

    def test_fx_line_reaches_the_light_prompt(self):
        prompt = self._light_prompt(self._run(market="forex",
                                              symbol="EURUSD"))
        self.assertIn("FX risk sentiment (advisory", prompt,
                      "the risk brief never reached the forex desk")
        self.assertNotIn("US crowd psychology", prompt)



if __name__ == "__main__":
    unittest.main()


class ArmExecutorTests(unittest.TestCase):
    """The desk pre-commits an exit level; the CONTROL PASS fires it between
    decision cycles. 54 arm intents were emitted lifetime and every one was
    discarded before this existed — and cycle 65 measured the cost: on
    2026-08-05 every losing run was in profit first, and for four of seven
    that profit existed ONLY between cycles (5-20 min dwell vs a ~45 min
    cycle), so the desk never saw it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "arm-agent", "password": "pw123",
                                   "initial_balance": 100000.0})
        self.token = r.json()["token"]
        self.agent_id = r.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _run_with_position(self, qty=5.0, entry=100.0):
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0},
            headers={"Authorization": f"Bearer {self.token}"}).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start",
                         headers={"Authorization": f"Bearer {self.token}"})
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            run_engine.run_cycle(run_id)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantity FROM positions WHERE run_id = ?", (run_id,))
        held = float(cur.fetchone()["quantity"])
        conn.close()
        return run_id, held

    def _row(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    def _pos_qty(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT quantity FROM positions WHERE run_id = ?", (run_id,))
        r = cur.fetchone()
        conn.close()
        return float(r["quantity"]) if r else 0.0

    def test_armed_reduce_fires_on_the_control_pass_and_sheds_half(self):
        run_id, held = self._run_with_position()
        self.assertGreater(held, 0)
        run_engine._store_armed_order(
            run_id, {"if": "price_above", "then": "reduce",
                     "level": 110.0, "size_frac": 0.5}, 1)
        out = {}
        pnl = {"mark_age_ok": True,
               "position": {"quantity": held, "current_price": 111.0}}
        run_engine._fire_armed_order(self._row(run_id), pnl, out)
        self.assertEqual(out.get("armed_exits_fired"), 1)
        self.assertAlmostEqual(self._pos_qty(run_id), held * 0.5, places=6)
        # one-shot: the arm is cleared so the next tick cannot re-fire
        self.assertIsNone(self._row(run_id)["armed_order_json"])

    def test_it_does_not_fire_before_the_level(self):
        run_id, held = self._run_with_position()
        run_engine._store_armed_order(
            run_id, {"if": "price_above", "then": "reduce",
                     "level": 110.0, "size_frac": 0.5}, 1)
        out = {}
        run_engine._fire_armed_order(
            self._row(run_id), {"mark_age_ok": True,
                                "position": {"quantity": held,
                                             "current_price": 109.0}}, out)
        self.assertEqual(out.get("armed_exits_fired"), None)
        self.assertAlmostEqual(self._pos_qty(run_id), held, places=6)
        self.assertIsNotNone(self._row(run_id)["armed_order_json"])

    def test_a_stale_mark_never_fires(self):
        # The stop_eval_failed lesson: never price an exit on data we have
        # already declared untrustworthy.
        run_id, held = self._run_with_position()
        run_engine._store_armed_order(
            run_id, {"if": "price_above", "then": "close", "level": 110.0}, 1)
        out = {}
        run_engine._fire_armed_order(
            self._row(run_id), {"mark_age_ok": False,
                                "position": {"quantity": held,
                                             "current_price": 999.0}}, out)
        self.assertEqual(out.get("armed_exits_fired"), None)
        self.assertAlmostEqual(self._pos_qty(run_id), held, places=6)

    def test_going_flat_clears_a_standing_arm(self):
        run_id, _ = self._run_with_position()
        run_engine._store_armed_order(
            run_id, {"if": "price_above", "then": "close", "level": 110.0}, 1)
        run_engine._fire_armed_order(
            self._row(run_id),
            {"mark_age_ok": True, "position": {"quantity": 0.0,
                                               "current_price": 111.0}}, {})
        self.assertIsNone(self._row(run_id)["armed_order_json"])

    def test_it_fires_through_a_gap_and_journals_the_slippage(self):
        # ARM_THEN is exits-only, so an arm can only shed risk and is never
        # refused — the module's own doctrine. Distance is reported, not vetoed.
        run_id, held = self._run_with_position()
        run_engine._store_armed_order(
            run_id, {"if": "price_below", "then": "close", "level": 90.0}, 3)
        out = {}
        run_engine._fire_armed_order(
            self._row(run_id), {"mark_age_ok": True,
                                "position": {"quantity": held,
                                             "current_price": 45.0}}, out)
        self.assertEqual(out.get("armed_exits_fired"), 1)
        self.assertAlmostEqual(self._pos_qty(run_id), 0.0, places=6)
        evs = self.client.get(
            f"/api/runs/{run_id}/events?limit=500",
            headers={"Authorization": f"Bearer {self.token}"}).json()["events"]
        fired = [e for e in evs if e["event_type"] == "armed_exit"]
        self.assertEqual(len(fired), 1)
        payload = json.loads(fired[0]["payload"]) \
            if isinstance(fired[0]["payload"], str) else fired[0]["payload"]
        self.assertTrue(payload["executed"])
        self.assertAlmostEqual(payload["slippage_pct"], -50.0, places=2)

    def test_the_executor_is_WIRED_into_the_control_pass(self):
        # An executor nothing calls is the exact bug this feature fixes.
        import inspect
        self.assertIn("_fire_armed_order(run, pnl, out)",
                      inspect.getsource(run_engine._control_active))


class BreakevenRatchetTests(unittest.TestCase):
    """The configured trailing lock NEVER ARMS: trail.activate_usd is set
    equal to max_loss_usd ($78-81 live) while the best peak any run reached
    in two days was $22.07. The desk cannot cover the gap either — it armed
    on 37 of 133 held cycles. This rail needs nothing from either."""

    ARM = 5.0   # ~= a 2500 notional round trip at 0.001/side

    def setUp(self):
        self._env = {k: os.environ.get(k)
                     for k in ("BREAKEVEN_RATCHET", "BREAKEVEN_ARM_FEES",
                               "BREAKEVEN_FEE_RATE")}
        for k in self._env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_a_peaked_position_may_not_go_negative(self):
        # run 971: peak +16.15, then -54.50. Fires the moment it crosses 0.
        self.assertTrue(
            run_engine._breakeven_floor_hit(16.15, -0.01, self.ARM))
        self.assertTrue(
            run_engine._breakeven_floor_hit(16.15, -54.50, self.ARM))

    def test_it_does_not_cut_a_winner_that_never_breaches(self):
        # run 969 — the day's BEST at +19.11 — armed and never went <= 0.
        self.assertFalse(
            run_engine._breakeven_floor_hit(22.07, 19.11, self.ARM))
        self.assertFalse(
            run_engine._breakeven_floor_hit(22.07, 0.01, self.ARM))

    def test_a_peak_that_never_paid_its_round_trip_never_arms(self):
        # runs 957 (+2.60) and 962 (+1.94): below the fee floor, so their
        # small losses are left alone rather than churned.
        self.assertFalse(run_engine._breakeven_floor_hit(2.60, -13.51, self.ARM))
        self.assertFalse(run_engine._breakeven_floor_hit(1.94, -6.44, self.ARM))

    def test_arm_is_the_positions_own_round_trip_not_a_constant(self):
        pnl = {"position": {"quantity": 5.0, "current_price": 500.0}}
        # 2500 notional * 0.001 * 2 sides = 5.00
        self.assertAlmostEqual(run_engine._breakeven_arm_usd(pnl), 5.0)
        # it SCALES with the book — a constant would be noise on small
        # positions and inert on large ones
        big = {"position": {"quantity": 50.0, "current_price": 500.0}}
        self.assertAlmostEqual(run_engine._breakeven_arm_usd(big), 50.0)
        for bad in ({}, {"position": {}},
                    {"position": {"quantity": 0, "current_price": 500.0}}):
            self.assertEqual(run_engine._breakeven_arm_usd(bad), 0.0)

    def test_the_floor_fires_before_the_exit_fee_eats_the_bank(self):
        # JTO 1304 (2026-08-15): floor at total <= 0 GROSS means every fire
        # nets a loss — best case is exactly -1 exit fee, while the label
        # reports a banked winner. With the exit fee passed, the floor
        # fires while closing still nets >= 0.
        self.assertTrue(run_engine._breakeven_floor_hit(
            16.15, 0.009, self.ARM, exit_fee_usd=0.011))
        self.assertTrue(run_engine._breakeven_floor_hit(
            16.15, 0.011, self.ARM, exit_fee_usd=0.011))
        # comfortably above the fee: no fire.
        self.assertFalse(run_engine._breakeven_floor_hit(
            16.15, 0.05, self.ARM, exit_fee_usd=0.011))

    def test_the_fee_floor_defaults_off_for_old_callers(self):
        # without exit_fee_usd the boundary is the old gross zero.
        self.assertFalse(run_engine._breakeven_floor_hit(16.15, 0.009, self.ARM))

    def test_the_ratchet_fire_is_discriminated_on_the_tape(self):
        # Two mechanisms share the stop_event:trailing_lock label (the real
        # trail and this ratchet) — B's attribution ran into it. The ratchet
        # branch must emit a telemetry discriminator.
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn("breakeven_ratchet", src)
        self.assertIn("stop_mechanism", src)
        # and the call site must actually pass the fee — dropping it
        # silently reverts to the guaranteed-negative gross-zero floor.
        self.assertIn("exit_fee_usd=_be_fee", src)

    def test_a_reduce_cannot_retro_arm_the_floor(self):
        # Run 976 (2026-08-06): entered 1.3166 GC ~4317, peaked +7.22 while
        # the full-book arm was 11.36 — never armed. The desk then reduced
        # half; sized off the CURRENT book the arm fell to 5.68 < 7.22 and
        # the floor fired the same second at -5.10, flattening a position
        # that then recovered (its replacement caught +16.9 of the move).
        # Anchored to the largest book ever held, the bar stays 11.36 and
        # the floor stays quiet.
        reduced = {"position": {"quantity": 0.658, "current_price": 4314.1}}
        arm = run_engine._breakeven_arm_usd(reduced, floor_qty=1.3166)
        self.assertAlmostEqual(arm, 1.3166 * 4314.1 * 0.002, places=4)
        self.assertFalse(run_engine._breakeven_floor_hit(7.22, -5.10, arm))

    def test_current_book_sizing_is_the_pinned_defect(self):
        # The same inputs WITHOUT the anchor DO fire — kept as the
        # fail-before record of the 976 bug. If this ever stops firing,
        # the default sizing changed and the anchor above needs a re-think.
        reduced = {"position": {"quantity": 0.658, "current_price": 4314.1}}
        arm = run_engine._breakeven_arm_usd(reduced)
        self.assertTrue(run_engine._breakeven_floor_hit(7.22, -5.10, arm))

    def test_a_constant_book_is_unchanged_by_the_anchor(self):
        # 973-class fire: the book never changed size, so floor_qty equals
        # the current qty and behaviour is identical to pre-fix.
        pnl = {"position": {"quantity": 5.0, "current_price": 500.0}}
        self.assertAlmostEqual(
            run_engine._breakeven_arm_usd(pnl, floor_qty=5.0),
            run_engine._breakeven_arm_usd(pnl))

    def test_an_add_still_fires_at_the_bigger_books_bar(self):
        # 971-class: an add makes the max book THE current book; a peak
        # that cleared that bar still fires the floor at <= 0.
        pnl = {"position": {"quantity": 50.0, "current_price": 500.0}}
        arm = run_engine._breakeven_arm_usd(pnl, floor_qty=50.0)
        self.assertAlmostEqual(arm, 50.0)
        self.assertTrue(run_engine._breakeven_floor_hit(60.0, -0.01, arm))

    def test_floor_qty_is_fail_soft(self):
        pnl = {"position": {"quantity": 5.0, "current_price": 500.0}}
        # 0.0 (the helper's failure value) falls back to the current book
        self.assertAlmostEqual(run_engine._breakeven_arm_usd(pnl, floor_qty=0.0), 5.0)
        self.assertAlmostEqual(run_engine._breakeven_arm_usd(pnl, floor_qty=None), 5.0)
        # a flat book never arms, whatever the history says
        flat = {"position": {"quantity": 0, "current_price": 500.0}}
        self.assertEqual(run_engine._breakeven_arm_usd(flat, floor_qty=9.9), 0.0)

    def test_fail_closed_on_missing_inputs(self):
        self.assertFalse(run_engine._breakeven_floor_hit(None, -50.0, self.ARM))
        self.assertFalse(run_engine._breakeven_floor_hit(16.15, -50.0, 0.0))
        self.assertFalse(run_engine._breakeven_floor_hit("x", -50.0, self.ARM))

    def test_the_kill_switch_disables_it(self):
        os.environ["BREAKEVEN_RATCHET"] = "0"
        self.assertFalse(
            run_engine._breakeven_floor_hit(16.15, -54.50, self.ARM))
        os.environ["BREAKEVEN_RATCHET"] = "1"
        self.assertTrue(
            run_engine._breakeven_floor_hit(16.15, -54.50, self.ARM))

    def test_it_is_WIRED_into_stop_evaluation(self):
        # A rail nothing calls is the exact bug this fixes — the configured
        # trailing lock has never fired once. The max-book anchor must be
        # wired too: an anchor computed but not passed is the 976 bug back.
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn("_breakeven_floor_hit(", src)
        self.assertIn("_breakeven_arm_usd(pnl, _run_max_abs_qty(run))", src)

    def test_it_works_with_NO_trail_config_at_all(self):
        # run 961 carries stop_conditions_json = {} and therefore had no peak
        # protection of any kind. The ratchet must not depend on `trail`.
        self.assertFalse(run_engine._trailing_lock_hit(16.15, -54.50, None))
        self.assertTrue(run_engine._breakeven_floor_hit(16.15, -54.50, self.ARM))


class RunMaxQtyReplayTests(unittest.TestCase):
    """_run_max_abs_qty replays the run's own trade events with the same
    signed-qty convention as pnl_audit (buy/cover build a long, sell/short
    build a short). It anchors the breakeven floor's arm threshold so a
    reduce cannot lower the bar under an already-earned peak (run 976)."""

    RUN_ID = 424242

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_events(self, events):
        # Direct inserts with explicit seq — run_events.seq is NOT NULL and
        # UNIQUE per run, and _emit_event needs a trading_runs row to track
        # it, which this test deliberately does not create.
        conn = database.get_db_connection()
        try:
            cursor = conn.cursor()
            database.begin_write_transaction(cursor)
            for seq, (event_type, payload) in enumerate(events, start=1):
                cursor.execute(
                    "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.RUN_ID, seq, event_type,
                     f"2026-08-06T00:00:{seq:02d}Z", json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def _seed_trades(self, legs):
        self._seed_events([("trade", {"side": side, "quantity": qty,
                                      "price": 100.0})
                           for side, qty in legs])

    def test_replay_tracks_the_largest_book_not_the_last(self):
        # 976's shape: build 1.3166, reduce half, flatten the rest. The
        # largest book is the entry-sized one even though the run ends flat.
        self._seed_trades([("buy", 1.0), ("buy", 0.3166),
                           ("sell", 0.658), ("sell", 0.6586)])
        self.assertAlmostEqual(
            run_engine._run_max_abs_qty({"id": self.RUN_ID}), 1.3166, places=6)

    def test_shorts_replay_with_the_same_convention(self):
        # sell/short grow a short book; cover shrinks it. Max is 3.0.
        self._seed_trades([("sell", 2.0), ("short", 1.0), ("cover", 2.5)])
        self.assertAlmostEqual(
            run_engine._run_max_abs_qty({"id": self.RUN_ID}), 3.0, places=6)

    def test_non_trade_events_and_garbage_are_ignored(self):
        self._seed_events([
            ("equity", {"total": 5.0}),
            ("trade", {"side": "buy", "quantity": "not-a-number"}),
            ("trade", {"side": "buy", "quantity": 2.0}),
        ])
        self.assertAlmostEqual(
            run_engine._run_max_abs_qty({"id": self.RUN_ID}), 2.0, places=6)

    def test_no_history_and_db_failure_are_fail_soft_zero(self):
        self.assertEqual(run_engine._run_max_abs_qty({"id": self.RUN_ID}), 0.0)
        with patch.object(run_engine, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(
                run_engine._run_max_abs_qty({"id": self.RUN_ID}), 0.0)


class FlattenRealizedJournalTests(unittest.TestCase):
    """FINDING 1: a forced flatten emitted a `trade` event and nothing else,
    while every ordinary close emits an `adapt` carrying `realized` — so the
    standard realized-P&L query silently omitted every flatten. It
    understated losses exactly on the worst days: 08-04 read -20.61 against
    a true -62.57, 08-05 read +73.21 against a true +8.62."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "flat-agent", "password": "pw123",
                                   "initial_balance": 100000.0})
        self.token = r.json()["token"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        self.tmp.cleanup()

    def _row(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM trading_runs WHERE id = ?", (run_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row

    def _flattened_run(self, exit_price):
        h = {"Authorization": f"Bearer {self.token}"}
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0}, headers=h).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=h)
        with patch("analysis_agents.run_analysis", return_value=BUY_ANALYSIS):
            run_engine.run_cycle(run_id)
        conn = database.get_db_connection()
        cur = conn.cursor()
        database.begin_write_transaction(cur)
        cur.execute("UPDATE positions SET current_price = ? WHERE run_id = ?",
                    (exit_price, run_id))
        conn.commit()
        conn.close()
        ok, err = run_engine._flatten_run(self._row(run_id))
        self.assertTrue(ok, err)
        evs = self.client.get(f"/api/runs/{run_id}/events?limit=500",
                              headers=h).json()["events"]
        out = []
        for e in evs:
            if e["event_type"] != "adapt":
                continue
            p = json.loads(e["payload"]) if isinstance(e["payload"], str) \
                else e["payload"]
            out.append(p)
        return out

    def test_a_losing_flatten_journals_its_realized_loss(self):
        # Bought 5 @ 100 (fee 0.50); flatten at 90 => -50 price, -0.45 fee.
        adapts = [a for a in self._flattened_run(90.0)
                  if a.get("trigger") == "flatten_close"]
        self.assertEqual(len(adapts), 1, "the flatten was not journalled")
        self.assertLess(adapts[0]["realized"], -50.0)
        self.assertEqual(adapts[0]["side"], "sell")

    def test_the_standard_pnl_query_now_SEES_the_flatten(self):
        # This is the actual defect: the reporting query sums adapt events
        # carrying `realized`, and a flatten contributed nothing to it.
        adapts = self._flattened_run(90.0)
        with_realized = [a for a in adapts if a.get("realized") is not None]
        self.assertTrue(with_realized,
                        "no adapt carries `realized` — the query stays blind")
        self.assertLess(sum(a["realized"] for a in with_realized), -50.0)

    def test_a_winning_flatten_is_journalled_too(self):
        adapts = [a for a in self._flattened_run(110.0)
                  if a.get("trigger") == "flatten_close"]
        self.assertEqual(len(adapts), 1)
        self.assertGreater(adapts[0]["realized"], 45.0)

    def test_a_flat_run_journals_nothing(self):
        h = {"Authorization": f"Bearer {self.token}"}
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 500.0}, headers=h).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=h)
        ok, _ = run_engine._flatten_run(self._row(run_id))
        self.assertTrue(ok)
        evs = self.client.get(f"/api/runs/{run_id}/events?limit=500",
                              headers=h).json()["events"]
        self.assertFalse([e for e in evs if e["event_type"] == "adapt"])


class PendingCloseFlushTests(unittest.TestCase):
    """Cycle 79. #249 fixed the forced flatten's missing `adapt` and its own
    comment named the mechanism — "no later cycle ever processes this leg".
    That is equally true of every OTHER close still pending when a run stops.
    Measured 08-06: 960's reduce (-4.3752) and 976's reduce (-2.3142) never
    reached the adapt stream at all — 70% of that day's ledger-vs-adapt
    drift, a bigger hole than the one #249 was raised for."""

    RUN_ID = 960

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO users (id, email, "
                        "password_hash, created_at) VALUES (1, 'p@x.com', "
                        "'x', '2026-01-01T00:00:00Z')")
            cur.execute("INSERT OR IGNORE INTO agents (id, name, token_hash, "
                        "cash, user_id, created_at) VALUES (7, 'pf', 'th', "
                        "1000, 1, '2026-01-01T00:00:00Z')")
            cur.execute("INSERT INTO trading_runs (id, agent_id, symbol, "
                        "market, status, created_at) VALUES (?, 7, 'SI', "
                        "'futures', 'stopping', '2026-08-06T00:00:00Z')",
                        (self.RUN_ID,))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _signal(self, sid, side, price, qty, fee, coid):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO signals (id, signal_id, agent_id, "
                "message_type, market, symbol, side, entry_price, quantity, "
                "fee_usd, run_id, client_order_id, timestamp, created_at) "
                "VALUES (?, ?, 7, 'operation', 'futures', 'SI', ?, ?, ?, ?, "
                "?, ?, '2026-08-06T00:00:00Z', '2026-08-06T00:00:00Z')",
                (sid, f"sig-{sid}", side, price, qty, fee, self.RUN_ID, coid))
            conn.commit()
        finally:
            conn.close()

    def _adapts(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = 'adapt' ORDER BY seq",
                        (self.RUN_ID,))
            return [json.loads(dict(r)["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def _open_and_reduce(self):
        # 960's shape: open, then a reduce whose adapt never fired.
        self._signal(1, "buy", 100.0, 10.0, 0.0, "run:960:cyc:1")
        self._signal(2, "sell", 90.0, 5.0, 0.0, "run:960:cyc:32")

    def test_a_close_the_next_cycle_never_ingested_is_journalled(self):
        self._open_and_reduce()
        self.assertEqual(
            run_engine._flush_pending_close_adapts({"id": self.RUN_ID}), 1)
        rows = self._adapts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trigger"], "pending_close")
        self.assertEqual(rows[0]["signal_id"], 2)
        self.assertAlmostEqual(rows[0]["realized"], -50.0, places=4)

    def test_a_close_already_journalled_is_not_journalled_twice(self):
        self._open_and_reduce()
        emit = run_engine.emit_telemetry_event
        emit(self.RUN_ID, "adapt", {"trigger": "losing_close",
                                    "signal_id": 2, "realized": -50.0})
        self.assertEqual(
            run_engine._flush_pending_close_adapts({"id": self.RUN_ID}), 0)
        self.assertEqual(len(self._adapts()), 1)

    def test_the_flatten_leg_is_left_to_249_and_never_double_journalled(self):
        # #249's flatten_close carries NO signal_id, so an id-only watermark
        # would miss it and re-journal the flatten on the bounded retry.
        self._signal(1, "buy", 100.0, 10.0, 0.0, "run:960:cyc:1")
        self._signal(2, "sell", 90.0, 10.0, 0.0, "run:960:flatten")
        run_engine.emit_telemetry_event(
            self.RUN_ID, "adapt", {"trigger": "flatten_close",
                                   "realized": -100.0})
        self.assertEqual(
            run_engine._flush_pending_close_adapts({"id": self.RUN_ID}), 0)
        self.assertEqual([r["trigger"] for r in self._adapts()],
                         ["flatten_close"])

    def test_running_it_twice_is_idempotent(self):
        # _control_stopping retries a failed flatten; the watermark is read
        # from the run's OWN adapt events, so a second pass emits nothing.
        self._open_and_reduce()
        first = run_engine._flush_pending_close_adapts({"id": self.RUN_ID})
        second = run_engine._flush_pending_close_adapts({"id": self.RUN_ID})
        self.assertEqual((first, second), (1, 0))
        self.assertEqual(len(self._adapts()), 1)

    def test_an_opening_leg_is_not_a_close(self):
        self._signal(1, "buy", 100.0, 10.0, 0.0, "run:960:cyc:1")
        self.assertEqual(
            run_engine._flush_pending_close_adapts({"id": self.RUN_ID}), 0)
        self.assertEqual(self._adapts(), [])

    def test_a_db_failure_never_wedges_the_stop(self):
        self._open_and_reduce()
        with patch.object(run_engine, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(
                run_engine._flush_pending_close_adapts({"id": self.RUN_ID}), 0)

    def test_it_is_actually_WIRED_into_the_stopping_path(self):
        # A flush that renders but is never called is a no-op that looks
        # fully tested — the _brake_distance_line lesson. Assert both that
        # _control_stopping calls it AND that the call precedes the flatten,
        # since the flatten leg must not exist as a signal yet.
        import inspect
        src = inspect.getsource(run_engine._control_stopping)
        self.assertIn("_flush_pending_close_adapts(run)", src)
        self.assertLess(src.index("_flush_pending_close_adapts"),
                        src.index("_flatten_run"),
                        "flush must run BEFORE the flatten leg is created")


class MarkFreshnessBriefTests(unittest.TestCase):
    """Cycle 82: `mark_age_ok` checks price_updated_at, not whether the value
    moved. GC printed 4320.700195 for 2h26m and SI 62.099998 for 2h05m while
    their marks were 91 SECONDS "fresh" — invisible to every staleness check
    in the engine. This hands the desk the observable."""

    RUN_ID = 828282

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _equity(self, unrealized_series):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            for seq, u in enumerate(unrealized_series, start=1):
                cur.execute(
                    "INSERT INTO run_events (run_id, seq, event_type, ts, "
                    "payload) VALUES (?, ?, 'equity', ?, ?)",
                    (self.RUN_ID, seq, f"2026-08-06T09:{seq:02d}:00Z",
                     json.dumps({"unrealized": u, "total": u})))
            conn.commit()
        finally:
            conn.close()

    def test_a_motionless_tape_is_stated(self):
        self._equity([1.0] * 8)
        line = run_engine._mark_freshness_line({"id": self.RUN_ID}, 5.0)
        self.assertIn("SAME price for 8 straight reads", line)

    def test_a_moving_mark_says_nothing(self):
        self._equity([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        self.assertEqual(
            run_engine._mark_freshness_line({"id": self.RUN_ID}, 5.0), "")

    def test_a_short_quiet_patch_is_below_the_floor(self):
        self._equity([1.0] * 3)
        self.assertEqual(
            run_engine._mark_freshness_line({"id": self.RUN_ID}, 5.0), "")

    def test_a_reduce_resets_the_count_rather_than_inventing_a_freeze(self):
        # unrealized = (mark - avg) * qty, so a size change moves it even
        # under a frozen mark. Under-reporting is the safe direction.
        self._equity([9.0] * 4 + [1.0] * 4)   # newest first = four 9.0s
        self.assertEqual(
            run_engine._mark_freshness_line({"id": self.RUN_ID}, 5.0), "")

    def test_a_flat_book_never_reports(self):
        self._equity([0.0] * 30)
        self.assertEqual(
            run_engine._mark_freshness_line({"id": self.RUN_ID}, 0.0), "")

    def test_a_db_failure_renders_nothing_rather_than_breaking_the_cycle(self):
        with patch.object(run_engine, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(
                run_engine._mark_freshness_line({"id": self.RUN_ID}, 5.0), "")

    def test_it_is_WIRED_into_both_prompt_paths(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_mark_freshness_line", src,
                      "missing from the composed brief (both paths)")


class ReduceGeometryBriefTests(unittest.TestCase):
    """Fleet 35 UNI (2026-08-15): the desk authored 'reduce half' on a $20
    book; the dust-remainder rail escalated it to a full close because the
    $10 remainder sat under the $25 floor. The desk did not know its book
    was all-or-nothing — _exit_size_line even told it 'reduce keeps the
    thesis alive'. This line states the reduce geometry the rail enforces."""

    def _pnl(self, entry, mark, ok=True):
        return {"mark_age_ok": ok,
                "position": {"entry_price": entry, "current_price": mark}}

    def test_a_sub_floor_book_is_named_all_or_nothing(self):
        # 6.148 UNI @ 3.2655 ≈ $20.08 notional < $25 floor.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(3.253, 3.2655)), \
                patch.dict(os.environ, {"RUN_DUST_REMAINDER_USD": "25"}):
            line = run_engine._reduce_geometry_line({"id": 1}, -6.148)
        self.assertIn("ANY 'reduce'", line)
        self.assertIn("FULL close", line)

    def test_a_mid_band_book_states_the_surviving_fraction(self):
        # 49.7 FIL @ 0.6935 ≈ $34.5: a half-reduce leaves $17 < $25 and
        # escalates, but a reduce under ~27% survives.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(0.6935, 0.6935)), \
                patch.dict(os.environ, {"RUN_DUST_REMAINDER_USD": "25"}):
            line = run_engine._reduce_geometry_line({"id": 1}, -49.7)
        self.assertIn("larger than", line)
        self.assertIn("FULL close", line)
        self.assertNotIn("ANY 'reduce'", line)
        # $34.47 notional, $25 floor: the surviving bound is 1 - 25/34.47
        # ≈ 27%, NOT the kept fraction 73% — the number must be the bound.
        self.assertIn("27%", line)

    def test_a_large_book_says_nothing(self):
        # $100 notional: half leaves $50 ≥ $25 — geometry unremarkable.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(10.0, 10.0)), \
                patch.dict(os.environ, {"RUN_DUST_REMAINDER_USD": "25"}):
            self.assertEqual(
                run_engine._reduce_geometry_line({"id": 1}, 10.0), "")

    def test_a_flat_book_says_nothing(self):
        self.assertEqual(run_engine._reduce_geometry_line({"id": 1}, 0.0), "")

    def test_a_pnl_failure_renders_nothing_rather_than_breaking_the_cycle(self):
        with patch.object(run_engine, "compute_run_pnl",
                          side_effect=RuntimeError("down")):
            self.assertEqual(
                run_engine._reduce_geometry_line({"id": 1}, -6.148), "")

    def test_it_is_WIRED_into_the_composed_brief(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_reduce_geometry_line", src,
                      "missing from the composed brief (both paths)")


class StandingArmBriefTests(unittest.TestCase):
    """Cycle 82: _store_armed_order runs ONLY on intent == 'arm', so a reduce
    or hold cycle leaves the arm standing. The skill claimed the opposite and
    the desk was never shown the arm it already had — 968 armed close 1.0 at
    09:27, reduced at 10:12 without restating, and it stood on."""

    ARM = ('{"arm": {"if": "price_above", "level": 1447.0, "then": "close", '
           '"size_frac": 1.0}, "seq": 28, "armed_at": "2026-08-06T09:27:18Z"}')

    def test_the_standing_arm_is_stated_with_its_size(self):
        line = run_engine._standing_arm_line({"armed_order_json": self.ARM}, 5.0)
        self.assertIn("price_above 1447.0 then close", line)
        self.assertIn("100% of the book", line)
        self.assertIn("stays in force until you arm a different one", line)

    def test_no_arm_says_nothing(self):
        self.assertEqual(
            run_engine._standing_arm_line({"armed_order_json": None}, 5.0), "")

    def test_a_flat_book_says_nothing(self):
        self.assertEqual(
            run_engine._standing_arm_line({"armed_order_json": self.ARM}, 0.0), "")

    def test_garbage_json_renders_nothing_rather_than_raising(self):
        self.assertEqual(
            run_engine._standing_arm_line({"armed_order_json": "{oops"}, 5.0), "")

    def test_a_partial_arm_renders_its_own_fraction(self):
        arm = ('{"arm": {"if": "price_below", "level": 4285.0, "then": '
               '"reduce", "size_frac": 0.5}, "seq": 7}')
        line = run_engine._standing_arm_line({"armed_order_json": arm}, 5.0)
        self.assertIn("price_below 4285.0 then reduce", line)
        self.assertIn("50% of the book", line)

    def test_it_is_WIRED_into_both_prompt_paths(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_standing_arm_line", src,
                      "missing from the composed brief (both paths)")


class FloorStatusBriefTests(unittest.TestCase):
    """24-hour sweep, 2026-08-06. The breakeven floor arms only once a run's
    peak clears its own round-trip cost. Across the 22 runs closed in that
    window the split was 13 of 13: all ten losers had a peak BELOW their arm
    threshold, all three winners above it. The threshold scales with book
    size, so protection arms LAST exactly where it would save most — run 971
    needed $16.36, reached $16.15, and lost -$58.18. The desk sees its peak
    and has never been told where protection begins."""

    RUN_ID = 919191

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            # 15.811514-unit book, the shape of run 971.
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, 1, 'trade', '2026-08-05T10:00:00Z', ?)",
                (self.RUN_ID, json.dumps({"side": "buy", "quantity": 15.811514,
                                          "price": 517.3})))
            conn.commit()
        finally:
            conn.close()
        self.pnl = {"position": {"quantity": 15.811514, "current_price": 517.3}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_peak_short_of_the_threshold_says_NOT_ARMED(self):
        # 971's real numbers: arm 16.36, peak 16.15 — short by 0.21.
        line = run_engine._floor_status_line({"id": self.RUN_ID}, self.pnl, 16.15)
        self.assertIn("NOT ARMED", line)
        self.assertIn("$16.36", line)
        self.assertIn("$16.15", line)
        self.assertIn("nothing exits this position automatically", line)

    def test_a_peak_over_the_threshold_says_ARMED(self):
        line = run_engine._floor_status_line({"id": self.RUN_ID}, self.pnl, 42.84)
        self.assertIn("ARMED", line)
        self.assertNotIn("NOT ARMED", line)
        self.assertIn("give-back to breakeven", line)

    def test_the_threshold_is_anchored_to_the_LARGEST_book_not_the_current(self):
        # Same #251 anchor the floor itself uses: a reduce must not lower the
        # bar the desk is being shown.
        reduced = {"position": {"quantity": 1.0, "current_price": 517.3}}
        line = run_engine._floor_status_line({"id": self.RUN_ID}, reduced, 5.0)
        self.assertIn("$16.36", line)

    def test_a_flat_book_renders_nothing(self):
        flat = {"position": {"quantity": 0.0, "current_price": 517.3}}
        self.assertEqual(
            run_engine._floor_status_line({"id": self.RUN_ID}, flat, 5.0), "")

    def test_a_missing_peak_still_reports_the_threshold(self):
        line = run_engine._floor_status_line({"id": self.RUN_ID}, self.pnl, None)
        self.assertIn("NOT ARMED", line)
        self.assertIn("$0.00", line)

    def test_a_db_failure_renders_nothing_rather_than_breaking_the_cycle(self):
        with patch.object(run_engine, "_run_max_abs_qty",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(
                run_engine._floor_status_line({"id": self.RUN_ID}, self.pnl, 5.0), "")

    def test_it_is_WIRED_into_the_position_brief(self):
        import inspect
        src = inspect.getsource(run_engine._position_state_line)
        self.assertIn("_floor_status_line(run, pnl, peak)", src,
                      "floor status not wired into the position brief")


class LossVerdictBriefTests(unittest.TestCase):
    """OWNER RULE 2026-08-06: 'if got more -0.99 then clean that RUN, and make
    RUN again by AI Analysis ... It's make decision by sooppiy AI.'

    The raw dollar figure cannot stand alone. Measured before writing this:
    -$0.99 is 3.7% of one ordinary day for GC and 0.23x its own round-trip
    cost, and three runs today (971, 967, 955) were already past the floor
    from their ENTRY FEE alone. A bare threshold would retire runs on noise
    and pay a round trip each time."""

    RUN_ID = 990099

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ.pop("RUN_LOSS_FLOOR_USD", None)

    def tearDown(self):
        os.environ.pop("RUN_LOSS_FLOOR_USD", None)
        self.tmp.cleanup()

    def _pnl(self, total, qty=0.495, mark=4300.0):
        return {"total": total,
                "position": {"quantity": qty, "current_price": mark}}

    def test_a_run_above_the_floor_says_nothing(self):
        self.assertEqual(
            run_engine._loss_verdict_line({"id": self.RUN_ID}, self._pnl(-0.50)), "")

    def test_a_loss_inside_the_round_trip_is_named_a_tick_not_a_wound(self):
        # GC's real shape: $2,128 notional, round trip ~$4.26. A -$1.50 loss
        # costs more to exit than it is worth.
        line = run_engine._loss_verdict_line({"id": self.RUN_ID}, self._pnl(-1.50))
        self.assertIn("past the $-0.99 floor", line)
        self.assertIn("round-trip cost", line)
        self.assertIn("it is a tick, not a wound.", line)
        # Two sentences in a prompt must not run together — the first draft
        # rendered "...not a wound The house rule..." on prod.
        self.assertNotIn("wound The house rule", line)
        self.assertIn("wound. The house rule", line)

    def test_a_loss_past_the_round_trip_is_named_real(self):
        line = run_engine._loss_verdict_line({"id": self.RUN_ID}, self._pnl(-25.0))
        self.assertIn("this loss has cleared the cost of leaving", line)
        self.assertIn("so it is real. The house rule", line)
        self.assertNotIn("tick, not a wound", line)

    def test_the_house_rule_and_its_escape_clause_are_always_stated(self):
        line = run_engine._loss_verdict_line({"id": self.RUN_ID}, self._pnl(-25.0))
        self.assertIn("CLOSE a run that is genuinely past the floor", line)
        self.assertIn("hand its slot back for a fresh thesis", line)
        self.assertIn("name the specific condition that reverses it", line)

    def test_the_floor_is_env_overridable(self):
        os.environ["RUN_LOSS_FLOOR_USD"] = "5"
        self.assertEqual(
            run_engine._loss_verdict_line({"id": self.RUN_ID}, self._pnl(-2.0)), "")
        self.assertIn("past the $-5.00 floor",
                      run_engine._loss_verdict_line({"id": self.RUN_ID},
                                                    self._pnl(-25.0)))

    def test_a_flat_book_still_reports_the_floor_without_dividing_by_zero(self):
        line = run_engine._loss_verdict_line(
            {"id": self.RUN_ID}, {"total": -3.0, "position": {"quantity": 0}})
        self.assertIn("past the $-0.99 floor", line)
        self.assertIn("CLOSE a run", line)

    def test_a_broken_pnl_renders_nothing_rather_than_breaking_the_cycle(self):
        self.assertEqual(
            run_engine._loss_verdict_line({"id": self.RUN_ID}, {"total": "oops"}), "")

    def test_it_is_WIRED_into_the_position_brief(self):
        import inspect
        src = inspect.getsource(run_engine._position_state_line)
        self.assertIn("_loss_verdict_line(run, pnl, cfg)", src,
                      "loss verdict not wired into the position brief")


class AdherenceStampTests(unittest.TestCase):
    """Measured 2026-08-17: of 24 `plan_adherence: "revised"` stamps since the
    Plan 26 flag went on, **15 (63%) sat on conf-0.0 cycles where the desk
    produced no verdict at all**. The journal stamps every decision and
    `_parse_plan_adherence` degrades a missing key to "revised", so a silent
    cycle is recorded as having revised its plan.

    §3.7 judges the flag on exactly this statistic. A fabricated stamp is not
    a conservative default; it is noise in the number that decides whether
    the flag stays on."""

    NO_VERDICT = "light cycle: no LLM verdict"

    def test_a_silent_cycle_records_no_adherence(self):
        self.assertEqual(
            run_engine._adherence_stamp({"action": "hold", "confidence": 0.0,
                                         "report": self.NO_VERDICT}), {})

    def test_a_real_verdict_missing_the_key_still_degrades_to_revised(self):
        self.assertEqual(
            run_engine._adherence_stamp({"action": "hold", "confidence": 0.55,
                                         "report": "waiting for the breakout"}),
            {"plan_adherence": "revised"})

    def test_an_authored_stamp_is_preserved(self):
        for value in ("followed", "revised", "deviated"):
            self.assertEqual(
                run_engine._adherence_stamp(
                    {"report": "a real report", "plan_adherence": value}),
                {"plan_adherence": value})

    def test_a_salvaged_verdict_still_gets_stamped(self):
        # #462 recovers truncated verdicts; those ARE authored decisions and
        # must keep counting toward the statistic.
        self.assertEqual(
            run_engine._adherence_stamp(
                {"action": "sell", "confidence": 0.66,
                 "report": "recovered from a truncated verdict — the desk's "
                           "reasoning was cut off, the decision was not"}),
            {"plan_adherence": "revised"})

    def test_it_is_WIRED_into_the_decision_journal(self):
        import inspect
        # Scope to run_cycle, which owns the decision journal — asserting on
        # the whole module would match the helper's own body and pass for
        # the wrong reason.
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_adherence_stamp(decision)", src,
                      "the journal is not routed through the stamp rule")
        # The bug WAS a direct parse at the journal site, stamping every
        # decision including silent ones. Assert that shape is gone.
        self.assertNotIn("_parse_plan_adherence(", src,
                         "the journal still stamps silent cycles directly")


class TruncatedVerdictSalvageTests(unittest.TestCase):
    """Measured 2026-08-17, AVAX run 1335 cycle 16.

    The light prompt asks for keys in this order: action, confidence, scores,
    stop_pct/target_pct, order_intent, outlook, plan_adherence, report. A cut
    inside the tail therefore loses only narrative — the whole traded decision
    is already on the wire. That cycle authored a partial reduce, was cut at
    1052 chars inside `plan_adherence`, and the platform discarded the entire
    object and journaled `hold, confidence 0.0`. Seven and a half minutes
    later a rail flattened the book at a worse price for a realized loss.
    """

    # The real shape from the tape: complete through `outlook`, severed
    # exactly at `"plan_adherence":`.
    REAL_TAIL = (
        '{"action": "sell", "confidence": 0.66, '
        '"scores": {"thesis_alignment": 0.7, "momentum_quality": 0.55, '
        '"entry_quality": 0.6, "risk_context": 0.5}, '
        '"stop_pct": 2.2, "target_pct": 7.0, '
        '"order_intent": {"intent": "reduce", "size_frac": 0.5, "arm": null}, '
        '"outlook": {"bias": "short", "exit": {"target_px": 5.9}, '
        '"basis": {"verdict": "adjusted", "discussion": "partial reduction '
        'secures gains and respects the planned invalidation trigger"}}, '
        '"plan_adherence":')

    def test_it_recovers_the_decision_from_the_real_severed_payload(self):
        obj = run_engine._salvage_truncated_json(self.REAL_TAIL)
        self.assertIsNotNone(obj, "the verdict was on the wire and was lost")
        self.assertEqual(obj["action"], "sell")
        self.assertAlmostEqual(obj["confidence"], 0.66)
        self.assertEqual(obj["order_intent"]["intent"], "reduce")
        self.assertAlmostEqual(obj["order_intent"]["size_frac"], 0.5)
        self.assertEqual(obj["scores"]["thesis_alignment"], 0.7)

    def test_a_verdict_without_a_verb_is_not_a_verdict(self):
        self.assertIsNone(
            run_engine._salvage_truncated_json('{"scores": {"a": 1}, "conf'))
        self.assertIsNone(
            run_engine._salvage_truncated_json('{"action": "sell", "sco'))

    def test_it_never_touches_well_formed_or_junk_input(self):
        for junk in ("", "I cannot answer", "{", "{]", None):
            self.assertIsNone(run_engine._salvage_truncated_json(junk))

    def test_a_severed_value_is_never_half_parsed(self):
        # Cut in the MIDDLE of confidence's number: the last complete
        # top-level pair is `action`, which alone is not a verdict.
        self.assertIsNone(
            run_engine._salvage_truncated_json('{"action": "buy", "confidence": 0.6'))
        # Cut inside a string containing a brace must not be mistaken for
        # structure.
        obj = run_engine._salvage_truncated_json(
            '{"action": "hold", "confidence": 0.4, "report": "a } brace", "x')
        self.assertEqual(obj["report"], "a } brace")

    def test_it_is_WIRED_into_the_light_path(self):
        import inspect
        src = inspect.getsource(run_engine._light_analysis)
        self.assertIn("_salvage_truncated_json(text)", src,
                      "a recoverable verdict is still being discarded")
        self.assertIn("salvaged", src)


class BriefJournalTests(unittest.TestCase):
    """Which brief lines rendered — journaled onto the decision event.

    R16's first live scenario (run 1285, 2026-08-15) could not be judged:
    `_predecessor_run_line` is wired into both prompt paths, but prompts are
    not journaled, so whether the line actually rendered was not determinable
    from the tape. Every one of the ~19 brief lines has the same blindness,
    and it has already bitten once — a line was unwired and every test passed
    (memory: brief-line wiring is untested by default)."""

    def tearDown(self):
        run_engine._BRIEF_JOURNAL.clear()

    _RUN = {"id": 77, "agent_id": 1, "symbol": "SLV", "market": "us-stock"}

    def test_rendered_lines_are_journaled_by_name(self):
        with patch.object(run_engine, "_stop_hit_line",
                          return_value="STOP HIT: x\n"), \
             patch.object(run_engine, "_predecessor_run_line",
                          return_value="Your predecessor...\n"):
            out = run_engine._compose_position_state(self._RUN, {}, 0, {})
        names = run_engine._take_brief_journal(77)
        self.assertIn("stop_hit", names)
        self.assertIn("predecessor_run", names)
        self.assertIn("STOP HIT: x", out)
        self.assertIn("Your predecessor", out)

    def test_a_silent_line_is_not_journaled(self):
        with patch.object(run_engine, "_predecessor_run_line",
                          return_value=""):
            run_engine._compose_position_state(self._RUN, {}, 0, {})
        names = run_engine._take_brief_journal(77) or []
        self.assertNotIn("predecessor_run", names)

    def test_the_journal_is_popped_not_read(self):
        """A cycle that composed but never reached a decision must not have
        its lines attributed to the NEXT decision — same trap as recall."""
        run_engine._compose_position_state(self._RUN, {}, 0, {})
        self.assertIsNotNone(run_engine._take_brief_journal(77))
        self.assertIsNone(run_engine._take_brief_journal(77))

    def test_composition_is_byte_identical_to_the_old_concatenation(self):
        """The journal must be a pure observer: the composed brief is the
        SAME string the old inline `+` chain produced, line for line."""
        run = dict(self._RUN)
        out = run_engine._compose_position_state(run, {}, 0, {})
        old = (run_engine._position_state_line(run, {}, 0, {})
               + run_engine._stop_hit_line(run)
               + run_engine._opening_window_line(run)
               + run_engine._young_exit_brief(run, {}, 0)
               + run_engine._contradiction_line(run, 0)
               + run_engine._last_cycle_word_line(run)
               + run_engine._predecessor_run_line(run)
               + run_engine._earnings_state_line(run)
               + run_engine._breadth_state_line(run)
               + run_engine._us_psych_line(run)
               + run_engine._fx_risk_line(run)
               + run_engine._hold_streak_line(run, 0)
               + run_engine._brake_distance_line(run, 0)
               + run_engine._entry_rail_line(run, 0)
               + run_engine._exit_size_line(run, 0)
               + run_engine._mark_freshness_line(run, 0)
               + run_engine._big_trader_line(run)
               + run_engine._ordinary_day_line(run)
               + run_engine._standing_arm_line(run, 0))
        self.assertEqual(out, old)

    def test_both_prompt_paths_use_the_composer(self):
        import inspect
        light = inspect.getsource(run_engine._light_analysis)
        full = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_compose_position_state(", light,
                      "light path bypasses the composer — its lines are "
                      "invisible on the tape again")
        self.assertIn("_compose_position_state(", full,
                      "full path bypasses the composer")
        self.assertNotIn("+ _predecessor_run_line(run)", light,
                         "old inline concatenation still present alongside "
                         "the composer")
        self.assertNotIn("+ _predecessor_run_line(run)", full)

    def test_the_decision_event_carries_the_brief(self):
        import inspect
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_take_brief_journal(run_id)", src,
                      "the journal is captured but never attached to the "
                      "decision event — still invisible on the tape")


class DeskRecallTests(unittest.TestCase):
    """Owner, 2026-08-07: "from tomorrow sooppiy and this session must be ref
    RAG". Until now the corpus only accumulated — the desk filled it and never
    read it back."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "r.db")
        database.init_database()
        import desk_memory
        self.mem = desk_memory
        self.mem.remember(
            "monitoring", "notes.md#giveback", "Give-back",
            "Every losing run was in profit first: peaks of 34-49% were given "
            "back before the loss, and the arm that would have banked them sat "
            "further away than the tape had ever moved.")
        self.mem.remember(
            "monitoring", "notes.md#fees", "Fee hurdle",
            "A flat fee needs a move of at least 2.40% before a round trip "
            "pays for itself, so a thesis under that is not an opportunity.")

    def tearDown(self):
        os.environ.pop("DESK_RECALL_ENABLED", None)
        self.tmp.cleanup()

    def test_a_giving_back_position_recalls_the_give_back_lesson(self):
        run = {"market": "crypto", "peak_pnl_usd": 1.0}
        line = run_engine._recall_line(run, {"unrealized": 0.2}, pos_qty=5)
        self.assertIn("given back", line)
        self.assertIn("NOT live tape", line,
                      "past findings must never read as current tape")

    def test_a_flat_run_recalls_the_entry_question_not_the_exit_one(self):
        run = {"market": "crypto"}
        line = run_engine._recall_line(run, {}, pos_qty=0)
        self.assertIn("2.40%", line, "the fee hurdle is the flat-run lesson")

    def test_the_query_is_built_from_situation_not_symbol(self):
        """Keying on the symbol would return notes about that ticker and miss
        every lesson that actually applies."""
        run = {"market": "crypto", "symbol": "ZC", "peak_pnl_usd": 1.0}
        q = run_engine._recall_query(run, {"unrealized": 0.2}, pos_qty=5)
        self.assertNotIn("ZC", q)
        self.assertIn("give-back", q)

    def test_an_empty_corpus_is_silent(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM desk_memory")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(
            run_engine._recall_line({"market": "crypto"}, {}, 0), "")

    def test_recall_can_be_switched_off(self):
        os.environ["DESK_RECALL_ENABLED"] = "0"
        self.assertEqual(
            run_engine._recall_line({"market": "crypto"}, {}, 0), "")

    def test_a_broken_corpus_never_blocks_a_cycle(self):
        with patch("desk_memory.search", side_effect=RuntimeError("corpus down")):
            self.assertEqual(
                run_engine._recall_line({"market": "crypto"}, {}, 0), "")

    def test_recall_prefers_lessons_and_outcomes_over_monitoring_prose(self):
        """Measured on prod 2026-08-15: monitoring chunks outscore lessons in
        every (market x situation) cell — 12-22 against 6-12 — because a
        monitoring section is long, term-dense prose written WHILE analysing a
        losing shape, so it is term-dense for exactly the query a losing run
        generates. Merging the kinds into one pool therefore does NOT fix
        anything: monitoring still takes every slot. The corpus the desk reads
        has to be chosen, not ranked."""
        self.mem.remember(
            "monitoring", "notes.md#ladder",
            "The ladder that never ends - quantified, and NOT shipped",
            "the position was losing and the desk had to cut or hold; cutting "
            "the loser in a ladder cost drag against holding the whole "
            "position, and the cause is not mechanical greed, and that is why "
            "nothing ships; cut or hold, losing, stop distance, reduce")
        self.mem.remember(
            "lesson", "skill:exit-discipline#4", "Exit discipline",
            "when a position is losing, cut it")
        line = run_engine._recall_line(
            {"id": 11, "market": "crypto"}, {"unrealized": -1.0}, pos_qty=5)
        self.assertIn("when a position is losing, cut it", line,
                      "the curated lesson was not what the desk read")
        self.assertNotIn("that is why nothing ships", line,
                         "unshipped engineering commentary reached the desk")
        rec = run_engine._take_recall_journal(11)
        self.assertTrue(rec["chunks"], "recall was injected but not journaled")
        self.assertEqual({c["kind"] for c in rec["chunks"]}, {"lesson"})

    def test_recall_falls_back_to_monitoring_when_no_lesson_or_outcome(self):
        """The corpus must be able to hold nothing but monitoring without the
        desk losing its memory altogether — fail-soft, not fail-silent."""
        line = run_engine._recall_line(
            {"id": 12, "market": "crypto", "peak_pnl_usd": 1.0},
            {"unrealized": 0.2}, pos_qty=5)
        self.assertIn("given back", line)
        rec = run_engine._take_recall_journal(12)
        self.assertEqual({c["kind"] for c in rec["chunks"]}, {"monitoring"})

    def test_recall_is_bounded(self):
        for i in range(20):
            self.mem.remember("monitoring", f"n{i}.md#x", f"n{i}",
                              "the run gave back its peak and the arm was too "
                              f"far away to bank anything at all, case {i}")
        line = run_engine._recall_line(
            {"market": "crypto", "peak_pnl_usd": 1.0}, {"unrealized": 0.2}, 5)
        self.assertLessEqual(line.count("\n- "), run_engine._RECALL_MAX)
        self.assertLess(len(line), run_engine._RECALL_MAX * (run_engine._RECALL_CHARS + 200))

    def test_it_is_wired_into_the_brief(self):
        import inspect
        src = inspect.getsource(run_engine._position_state_line)
        self.assertIn("_recall_line(run, pnl, pos_qty)", src,
                      "corpus recall not wired into the position brief")


class RecallJournalTests(unittest.TestCase):
    """Plan 22 Phase 3(a). Weights can only be learned from VARIANCE in what
    was retrieved, and nothing recorded WHICH chunks a decision actually saw.
    Journal-only: no prompt, gate or order reads any of this."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "j.db")
        database.init_database()
        import desk_memory
        self.mem = desk_memory
        self.mem.remember(
            "monitoring", "notes.md#fees", "Fee hurdle",
            "A flat fee needs a move of at least 2.40% before a round trip "
            "pays for itself, so a thesis under that is not an opportunity.")
        run_engine._RECALL_JOURNAL.clear()

    def tearDown(self):
        os.environ.pop("DESK_RECALL_ENABLED", None)
        run_engine._RECALL_JOURNAL.clear()
        self.tmp.cleanup()

    def test_it_records_the_chunks_the_brief_actually_carried(self):
        line = run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0)
        self.assertIn("2.40%", line)
        rec = run_engine._take_recall_journal(7)
        self.assertIsNotNone(rec, "recall was injected but never journaled")
        shas = [c["sha"] for c in rec["chunks"]]
        self.assertTrue(shas and all(len(s) == 64 for s in shas),
                        f"chunk identities missing: {rec}")
        stored = self.mem.search("fee hurdle round trip", kind="monitoring",
                                 limit=5)
        self.assertIn(shas[0], {h["sha"] for h in stored},
                      "journaled sha does not match a stored chunk")
        self.assertEqual(rec["chunks"][0]["source"], "notes.md#fees")

    def test_the_query_is_journaled_beside_the_chunks(self):
        run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0)
        rec = run_engine._take_recall_journal(7)
        self.assertIn("fee hurdle", rec["query"],
                      "without the query the retrieval cannot be reproduced")

    def test_recalling_nothing_is_journaled_as_empty_not_as_absent(self):
        """A decision that recalled nothing is the CONTROL GROUP the
        attribution needs. It must be distinguishable from a cycle where
        recall never ran at all."""
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM desk_memory")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(
            run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0), "")
        rec = run_engine._take_recall_journal(7)
        self.assertIsNotNone(rec, "an empty recall must still be journaled")
        self.assertEqual(rec["chunks"], [])

    def test_a_cycle_that_never_recalled_journals_nothing(self):
        run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0)
        run_engine._recall_reset(7)
        self.assertIsNone(run_engine._take_recall_journal(7),
                          "a flat cycle would inherit the previous cycle's "
                          "chunks and mislabel the dataset")

    def test_taking_the_journal_clears_it(self):
        run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0)
        self.assertIsNotNone(run_engine._take_recall_journal(7))
        self.assertIsNone(run_engine._take_recall_journal(7),
                          "a cycle that recalled but never decided must not "
                          "have its chunks attributed to the NEXT decision")

    def test_journaling_off_keeps_the_recall_line(self):
        with patch.object(run_engine, "_recall_capture",
                          side_effect=RuntimeError("journal down")):
            line = run_engine._recall_line({"id": 7, "market": "crypto"}, {}, 0)
        self.assertIn("2.40%", line,
                      "a broken journal must never cost the desk its brief")

    def test_it_is_wired_into_the_cycle(self):
        import inspect
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_recall_reset(run_id)", src,
                      "stale recall is not cleared before the brief is built")
        self.assertIn('"recall"', src,
                      "the recall journal is never emitted beside the "
                      "decision event")
        self.assertIn("_take_recall_journal(run_id)", src)


class RecallExploreTests(unittest.TestCase):
    """Plan 22 Phase 3(a2). Measured on prod 2026-08-10: 262 `recall` events
    across 14 (market x situation) cells, and EVERY cell returned exactly one
    chunk-pair — zero within-class variance, so "chunk c is harmful" and "this
    situation loses" are the same number wearing two labels. Weights cannot be
    learned from that; only a logged counterfactual fixes it.

    Default-off, and the propensity is journaled on every row — without it
    none of the off-policy estimators (c) needs can be computed offline."""

    def _hits(self, *scores):
        return [{"sha": f"{i:064d}", "kind": "monitoring",
                 "source": f"note{i}.md", "score": s, "body": f"body {i}",
                 "title": f"t{i}"} for i, s in enumerate(scores)]

    def tearDown(self):
        os.environ.pop("DESK_RECALL_EXPLORE", None)

    def test_exploration_is_off_by_default(self):
        self.assertFalse(run_engine._recall_explore_enabled(),
                         "a behaviour change on the trading path must ship "
                         "default-off")

    def test_off_emits_the_incumbent_head_at_propensity_one(self):
        hits = self._hits(30.0, 22.0, 21.0, 20.0, 19.0)
        chosen, meta = run_engine._recall_select(hits, False)
        self.assertEqual([c["sha"] for c in chosen],
                         [hits[0]["sha"], hits[1]["sha"]])
        self.assertEqual(meta["scheme"], "deterministic-top2")
        self.assertEqual(meta["propensity"], 1.0)
        self.assertFalse(meta["explore"])

    def test_the_scheme_and_propensity_are_journaled_even_when_off(self):
        """A deterministic row pooled with epsilon rows UNLABELLED would
        silently corrupt every estimate (c) computes."""
        chosen, meta = run_engine._recall_select(self._hits(30.0, 22.0), False)
        self.assertIn("scheme", meta)
        self.assertIn("propensity", meta)

    def test_on_it_varies_the_second_slot_and_never_the_first(self):
        hits = self._hits(30.0, 22.0, 21.0, 20.0, 19.0)
        firsts, seconds = set(), set()
        for _ in range(400):
            chosen, _meta = run_engine._recall_select(hits, True)
            self.assertEqual(len(chosen), 2)
            firsts.add(chosen[0]["sha"])
            seconds.add(chosen[1]["sha"])
        self.assertEqual(firsts, {hits[0]["sha"]},
                         "the rank-1 chunk must never be displaced — "
                         "exploration's blast radius is one slot")
        self.assertGreaterEqual(
            len(seconds), 4,
            "without >=3 distinct chunk-pairs per class the corrected (b) "
            "variance gate can never open")

    def test_the_logged_propensity_matches_the_scheme(self):
        hits = self._hits(30.0, 22.0, 21.0, 20.0, 19.0)
        explored = 0
        for _ in range(600):
            chosen, meta = run_engine._recall_select(hits, True)
            self.assertEqual(meta["scheme"], "eps-head-fixed-v1")
            self.assertEqual(meta["pool"], 3)
            if meta["explore"]:
                explored += 1
                self.assertAlmostEqual(meta["propensity"], 0.25 / 3, places=5)
            else:
                self.assertAlmostEqual(meta["propensity"], 0.75, places=5)
            self.assertGreaterEqual(meta["propensity"], 0.05,
                                    "IPS blows up on small propensities")
        self.assertTrue(60 < explored < 240,
                        f"explore rate {explored / 600:.2f} is not ~0.25")

    def test_chunks_below_the_relevance_floor_are_never_drawn(self):
        """Exploration compares PLAUSIBLE lessons. A near-irrelevant chunk
        costs prompt budget and desk attention and can never win weight
        honestly (deep analysis §3.2)."""
        hits = self._hits(30.0, 22.0, 21.0, 3.0, 1.0)
        drawn = set()
        for _ in range(400):
            chosen, meta = run_engine._recall_select(hits, True)
            self.assertEqual(meta["pool"], 1)
            drawn.add(chosen[1]["sha"])
        self.assertEqual(drawn, {hits[1]["sha"], hits[2]["sha"]},
                         "a chunk under 60% of the head's score was drawn")

    def test_the_floor_is_relative_because_score_scales_differ_by_class(self):
        """Measured on prod: the 'winning' class heads at 15.0 while the
        'gave-back' class's EIGHTH chunk scores 17.2. An absolute floor would
        mean two different things in two situations."""
        _c, low = run_engine._recall_select(self._hits(15.0, 14.3, 11.2, 9.9),
                                            True)
        _c, high = run_engine._recall_select(
            self._hits(30.3, 22.5, 22.0, 21.2), True)
        self.assertEqual(low["pool"], 2)
        self.assertEqual(high["pool"], 2)

    def test_a_losing_position_is_never_explored(self):
        """The mandate's asymmetry — never loosen an unproven thing on the
        losing side — applies to advice as much as to rails."""
        self.assertFalse(run_engine._recall_explore_allowed(
            {"unrealized": -0.42}, 3.0))
        self.assertTrue(run_engine._recall_explore_allowed(
            {"unrealized": 0.42}, 3.0))
        self.assertTrue(run_engine._recall_explore_allowed({}, 0))

    def test_the_label_and_the_gate_cannot_disagree_about_losing(self):
        """The safety property is a COUPLING, and nothing pinned it.

        `_recall_query` decides what a decision is CALLED and
        `_recall_explore_allowed` decides whether it may be explored. They were
        written separately and both read `pnl["unrealized"]`. The test above
        checks the gate on three hand-picked values; that cannot catch the two
        drifting apart — and the drift is exactly the bug that matters, because
        a run journalled as `losing` while being explored would corrupt the
        attribution dataset with the one class the mandate forbids loosening.

        Verified on prod 2026-08-11 00:53Z (run 1056, unrealized −1.33 →
        `deterministic-top2`, propensity 1.0), but one live row samples one
        input. Sweep it instead, including the values a live book rarely
        reaches.
        """
        upnls = [-100.0, -1.0, -0.01, -1e-9, 0.0, 1e-9, 0.01, 1.0, 100.0,
                 None, "", "abc", float("nan")]
        checked = 0
        for upnl in upnls:
            for peak in (None, 0.0, 5.0):
                for qty in (3.0, -3.0, 0.0):     # long, SHORT, flat
                    pnl = {"unrealized": upnl}
                    run = {"market": "crypto", "peak_pnl_usd": peak}
                    query = run_engine._recall_query(run, pnl, qty)
                    allowed = run_engine._recall_explore_allowed(pnl, qty)
                    checked += 1
                    if "losing" in query:
                        self.assertFalse(
                            allowed,
                            f"query says losing but exploration is allowed "
                            f"(unrealized={upnl!r} peak={peak!r} qty={qty!r})")
        self.assertEqual(checked, len(upnls) * 9)

    def test_a_short_is_holding_not_flat(self):
        """`positions.quantity` is SIGNED. A gate written `pos_qty > 0` would
        read every short as flat and hand the whole short book to the explorer
        — including shorts that are underwater. The falsy test is load-bearing,
        so pin it rather than trusting it to survive an edit."""
        self.assertFalse(run_engine._recall_explore_allowed(
            {"unrealized": -0.42}, -3.0),
            "a LOSING short must be excluded exactly like a losing long")
        self.assertTrue(run_engine._recall_explore_allowed(
            {"unrealized": 0.42}, -3.0),
            "a winning short is still explorable")

    def test_no_alternatives_is_an_honest_propensity_of_one(self):
        chosen, meta = run_engine._recall_select(self._hits(30.0, 22.0), True)
        self.assertEqual(meta["pool"], 0)
        self.assertEqual(meta["propensity"], 1.0)
        self.assertFalse(meta["explore"])

    def test_it_is_wired_into_the_line_and_the_cycle(self):
        import inspect
        src = inspect.getsource(run_engine._recall_line)
        self.assertIn("_recall_select", src,
                      "the selector is never called — exploration would be a "
                      "no-op that still logs a scheme")
        self.assertIn("_recall_explore_allowed", src,
                      "losing positions are not excluded at the call site")
        # Comments stripped on purpose: a source grep that a PROSE mention
        # satisfies is not a wiring test. Caught by mutation — dropping
        # "propensity" from the emitted tuple left this green.
        cyc = "\n".join(ln.split("#")[0]
                        for ln in inspect.getsource(run_engine.run_cycle)
                        .splitlines())
        for field in ("propensity", "scheme", "explore"):
            self.assertIn(field, cyc,
                          f"{field} never reaches run_events, so (c) cannot "
                          f"be computed offline — and it cannot be "
                          f"retrofitted onto rows already written")


class RecallExploreWiringTests(unittest.TestCase):
    """(a2) through the real corpus and the real journal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "x.db")
        database.init_database()
        import desk_memory
        self.mem = desk_memory
        for i in range(6):
            self.mem.remember(
                "monitoring", f"notes.md#give{i}", f"Give-back {i}",
                "A position that gave back its peak should bank the gain or "
                f"arm the level rather than hold for a full round trip {i}. "
                + "trailing partial profit winning " * (6 - i))
        run_engine._RECALL_JOURNAL.clear()

    def tearDown(self):
        os.environ.pop("DESK_RECALL_EXPLORE", None)
        run_engine._RECALL_JOURNAL.clear()
        self.tmp.cleanup()

    def _run(self):
        return {"id": 11, "market": "crypto", "peak_pnl_usd": 5.0}

    def test_the_journal_carries_the_scheme_when_exploration_is_off(self):
        run_engine._recall_line(self._run(), {"unrealized": 1.0}, 3.0)
        rec = run_engine._take_recall_journal(11)
        self.assertEqual(rec["scheme"], "deterministic-top2")
        self.assertEqual(rec["propensity"], 1.0)

    def test_exploring_journals_the_scheme_and_widens_the_pool(self):
        os.environ["DESK_RECALL_EXPLORE"] = "1"
        seconds, schemes = set(), set()
        for _ in range(60):
            run_engine._recall_reset(11)
            line = run_engine._recall_line(self._run(), {"unrealized": 1.0},
                                           3.0)
            self.assertIn("past findings", line)
            rec = run_engine._take_recall_journal(11)
            schemes.add(rec["scheme"])
            self.assertGreaterEqual(rec["propensity"], 0.05)
            if len(rec["chunks"]) > 1:
                seconds.add(rec["chunks"][1]["sha"])
        self.assertEqual(schemes, {"eps-head-fixed-v1"})
        self.assertGreater(len(seconds), 1,
                           "exploration produced no within-class variance — "
                           "the whole point of (a2)")

    def test_a_losing_run_keeps_the_deterministic_ranking(self):
        os.environ["DESK_RECALL_EXPLORE"] = "1"
        run_engine._recall_line(self._run(), {"unrealized": -1.0}, 3.0)
        rec = run_engine._take_recall_journal(11)
        self.assertEqual(rec["scheme"], "deterministic-top2")

    def test_a_broken_draw_never_costs_the_desk_its_brief(self):
        """A selector that raises must fall back to the INCUMBENT ranking.
        Reaching `_recall_line`'s outer handler would strip the recall
        entirely — a degradation, not the no-op fail-soft demands."""
        os.environ["DESK_RECALL_EXPLORE"] = "1"
        with patch.object(run_engine.random, "random",
                          side_effect=RuntimeError("rng down")):
            line = run_engine._recall_line(self._run(), {"unrealized": 1.0},
                                           3.0)
        self.assertIn("past findings", line,
                      "a failed draw stripped the desk's recall")
        rec = run_engine._take_recall_journal(11)
        self.assertEqual(rec["scheme"], "deterministic-top2")
        self.assertEqual(rec["propensity"], 1.0)


class ExcursionScaleBriefTests(unittest.TestCase):
    """Peak reaches the desk in DOLLARS; an arm is a PRICE. Without the
    conversion the desk armed levels 12-13x beyond anything its tape had done
    (measured 2026-08-07 on runs 983 and 984)."""

    def _pnl(self, entry, mark, qty):
        return {"position": {"entry_price": entry, "current_price": mark,
                             "quantity": qty}}

    def test_states_the_peak_as_a_percentage_of_price(self):
        # 984 HG: peak $0.103 on a $49.42 book = 0.208% of price.
        run = {"armed_order_json": None}
        line = run_engine._excursion_scale_line(
            run, self._pnl(6.7185, 6.7155, 7.3557), 0.103)
        self.assertIn("0.21% of price", line)
        self.assertIn("$0.10", line)
        self.assertIn("No level is armed", line)

    def test_compares_the_standing_arm_in_the_same_unit(self):
        # arm at 6.89 vs mark 6.7155 = 2.60% away, against a 0.21% excursion.
        run = {"armed_order_json": json.dumps(
            {"arm": {"if": "price_above", "level": 6.89, "then": "reduce",
                     "size_frac": 0.5}})}
        line = run_engine._excursion_scale_line(
            run, self._pnl(6.7185, 6.7155, 7.3557), 0.103)
        self.assertIn("2.60% away", line)
        self.assertIn("12.5x that", line,
                      "the desk is not told how far beyond its own range the "
                      "arm sits")

    def test_a_reachable_arm_reads_as_a_small_multiple(self):
        # 981 SI: arm 0.50% away against a 0.297% excursion -> 1.7x.
        run = {"armed_order_json": json.dumps(
            {"arm": {"if": "price_above", "level": 62.05}})}
        line = run_engine._excursion_scale_line(
            run, self._pnl(61.845, 61.74, 0.61), 0.112)
        self.assertIn("1.7x that", line)

    def test_silent_before_any_favourable_excursion(self):
        """Nothing to calibrate against until the tape has moved for you."""
        run = {"armed_order_json": None}
        self.assertEqual(
            run_engine._excursion_scale_line(run, self._pnl(10.0, 9.9, 5), 0), "")
        self.assertEqual(
            run_engine._excursion_scale_line(run, self._pnl(10.0, 9.9, 5), None), "")

    def test_never_blocks_a_cycle(self):
        for bad in ({}, {"position": {}}, {"position": {"entry_price": 0,
                                                        "quantity": 0}}):
            self.assertEqual(
                run_engine._excursion_scale_line({}, bad, 1.0), "")

    def test_it_is_wired_into_the_brief(self):
        """A brief line unwired from the prompt passes every other test —
        helpers are tested for rendering, never for being concatenated."""
        import inspect
        src = inspect.getsource(run_engine._position_state_line)
        self.assertIn("_excursion_scale_line(run, pnl, peak)", src,
                      "excursion scale not wired into the position brief")

    def test_the_brief_reaches_both_prompt_paths(self):
        import inspect
        # Both prompt paths route through the composer now; the module
        # carries the def, the composer's call, and BriefJournalTests pins
        # both paths onto _compose_position_state.
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_position_state_line(run, cfg, pos_qty, thesis)", src,
                      "the position brief is not in the composed prompt")


class CycleCadenceTests(unittest.TestCase):
    """Owner, 2026-08-06: "Sooppiy AI analysis each run 30 min (make time gap
    each)". Two mechanisms — a scheduling-time cap on how long a live run may
    go unanalysed, and a per-run slot on the absolute clock grid."""

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
            json={"name": "cadence-agent", "password": "pw123",
                  "initial_balance": 1000.0})
        self.token = resp.json()["token"]

    def tearDown(self):
        self.probe.stop()
        os.environ.pop("AUTO_TRADING_ENABLED", None)
        os.environ.pop("RUN_INTERVAL_CAP_MIN", None)
        self.tmp.cleanup()

    def _run_at(self, interval_minutes, minutes_ago):
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 50.0},
            headers={"Authorization": f"Bearer {self.token}"}).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start",
                         headers={"Authorization": f"Bearer {self.token}"})
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs WHERE id = ?",
                        (run_id,))
            cfg = json.loads(cur.fetchone()[0] or "{}")
            cfg["interval_minutes"] = interval_minutes
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ?, "
                        "last_cycle_at = ? WHERE id = ?",
                        (json.dumps(cfg),
                         _ts(datetime.now(timezone.utc)
                             - timedelta(minutes=minutes_ago)), run_id))
            conn.commit()
        finally:
            conn.close()
        return run_id

    def test_cap_analyses_a_45_minute_run_within_30(self):
        """A run the desk built at 45m must still be looked at every 30m."""
        run_id = self._run_at(45, minutes_ago=31)
        self.assertEqual(run_engine.due_run_ids(), [run_id])

    def test_cap_is_env_overridable(self):
        """Elapsed 20m: under the raised cap the interval is 45m, so 20m is
        below the half-interval floor and the run is deterministically NOT
        due. (Assertions here stay either above a full interval or below half
        of one — in between, whether a slot boundary was crossed depends on
        the wall-clock time of day, which would make the test flaky.)"""
        os.environ["RUN_INTERVAL_CAP_MIN"] = "60"
        self.assertEqual(run_engine._interval_cap_min(), 60)
        self._run_at(45, minutes_ago=20)
        self.assertEqual(run_engine.due_run_ids(), [])

    def test_never_fires_before_half_an_interval(self):
        """The one early fire that snaps a run onto its slot is bounded."""
        self._run_at(30, minutes_ago=14)
        self.assertEqual(run_engine.due_run_ids(), [])

    def test_lockstep_fleet_separates_into_distinct_slots(self):
        """Six runs born in one pass shared last_cycle_at 22:57:00 on prod.
        A plain elapsed>=interval test can never separate them: once a full
        interval has passed the slot has always advanced too, so the run keeps
        its inherited phase forever."""
        ids = [980, 981, 982, 983, 984, 985]
        iv = 30
        last = {r: datetime(2026, 8, 6, 22, 57, tzinfo=timezone.utc) for r in ids}
        fires = {r: [] for r in ids}
        t = datetime(2026, 8, 6, 22, 57, tzinfo=timezone.utc)
        for _ in range(24 * 60):
            t += timedelta(minutes=1)
            for r in ids:
                off = run_engine._phase_offset_min(r, iv)
                if (run_engine._slot(t, iv, off)
                        > run_engine._slot(last[r], iv, off)
                        and t - last[r] >= timedelta(minutes=iv / 2)):
                    fires[r].append(t)
                    last[r] = t
        for r in ids:
            gaps = {(fires[r][i + 1] - fires[r][i]).total_seconds() / 60
                    for i in range(2, len(fires[r]) - 1)}
            self.assertEqual(gaps, {float(iv)},
                             f"run {r} settled period {gaps}, want {iv}m")
            self.assertGreaterEqual(len(fires[r]), 47, f"run {r} starved")
        minutes = [f.strftime("%H:%M") for r in ids for f in fires[r][3:]]
        self.assertEqual(len(minutes), len(set(minutes)),
                         "two runs still cycle in the same minute")

    def test_offsets_separate_consecutive_run_ids(self):
        offs = [run_engine._phase_offset_min(r, 30) for r in range(980, 986)]
        self.assertEqual(len(set(offs)), 6, f"offsets collide: {offs}")
        self.assertTrue(all(0 <= o < 30 for o in offs))


class RunExpiryBriefTests(unittest.TestCase):
    """Fleet 35 SUI (2026-08-15): the desk authored a 24h/6% thesis on a
    run whose build-time at_time killed it 1h57m later — no composer line
    carried the TTL, so the desk structurally could not know. This line
    hands the desk the run's hard end-of-life."""

    def test_a_future_at_time_renders_the_remaining_life(self):
        run = {"id": 1, "stop_conditions_json":
               '{"at_time": "2030-01-01T00:00:00Z"}'}
        line = run_engine._run_expiry_line(run)
        self.assertIn("HARD-ENDS at 2030-01-01T00:00:00Z", line)
        self.assertIn("remaining", line)
        self.assertIn("fee donation", line)

    def test_a_past_at_time_renders_nothing(self):
        run = {"id": 1, "stop_conditions_json":
               '{"at_time": "2020-01-01T00:00:00Z"}'}
        self.assertEqual(run_engine._run_expiry_line(run), "")

    def test_no_at_time_renders_nothing(self):
        self.assertEqual(run_engine._run_expiry_line(
            {"id": 1, "stop_conditions_json": "{}"}), "")
        self.assertEqual(run_engine._run_expiry_line({"id": 1}), "")

    def test_garbage_stop_conditions_render_nothing(self):
        self.assertEqual(run_engine._run_expiry_line(
            {"id": 1, "stop_conditions_json": "not json"}), "")
        self.assertEqual(run_engine._run_expiry_line(
            {"id": 1, "stop_conditions_json": '{"at_time": "garbage"}'}), "")

    def test_it_is_WIRED_into_the_composed_brief(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_run_expiry_line", src,
                      "missing from the composed brief (both paths)")


class TrailPositionScopedTests(unittest.TestCase):
    """FIL run 1305 (2026-08-16): the run banked +$3.0368, re-entered, and
    the trail flattened the NEW position for -$0.68 while that position's
    own best unrealized profit was $0.019 — 0.89% of the $2.089 arming
    floor. `activate_usd` is POSITION-scaled (2% of notional) but
    `peak_pnl_usd` is RUN-scoped and carries banked realized cash, so
    banked cash armed a lock the live position never earned, and gave it
    0.5365% of adverse room against its own 2.00% stop (3.73x tighter).
    Worse, the replacement run started with peak 0 and an inert trail —
    the rail punished the run for having banked a winner.

    Fix: measure the EXCURSION (peak - baseline), where baseline is the
    banked realized P&L that cannot round-trip. Textbook trailing stop."""

    TRAIL = {"activate_usd": 2.089, "giveback_frac": 0.2}

    def test_banked_cash_alone_does_not_arm_the_lock(self):
        # The exact prod numbers: peak 3.036759 = banked; live position's
        # own excursion 0.047 (its entry fee) — nowhere near the 2.089 arm.
        self.assertFalse(run_engine._trailing_lock_hit(
            3.036759, 2.403265, self.TRAIL, baseline_pnl=2.989755))

    def test_a_single_position_run_is_unchanged(self):
        # baseline 0 -> excursion == peak, identical to the old behaviour.
        self.assertTrue(run_engine._trailing_lock_hit(
            10.0, 7.9, self.TRAIL, baseline_pnl=0.0))
        self.assertFalse(run_engine._trailing_lock_hit(
            10.0, 8.1, self.TRAIL, baseline_pnl=0.0))

    def test_the_default_baseline_keeps_old_callers_identical(self):
        self.assertTrue(run_engine._trailing_lock_hit(10.0, 7.9, self.TRAIL))
        self.assertFalse(run_engine._trailing_lock_hit(10.0, 8.1, self.TRAIL))

    def test_a_second_position_that_truly_earns_still_locks(self):
        # banked 3.0, position earns 5.0 of its own -> peak 8.0,
        # excursion 5.0 >= arm; lock = 8.0 - 0.2*5.0 = 7.0.
        self.assertFalse(run_engine._trailing_lock_hit(
            8.0, 7.1, self.TRAIL, baseline_pnl=3.0))
        self.assertTrue(run_engine._trailing_lock_hit(
            8.0, 6.9, self.TRAIL, baseline_pnl=3.0))

    def test_the_lock_defends_its_line_after_the_exit_fee(self):
        # Prod: the fired lock landed $0.073 BELOW the level it defended
        # because no exit fee is modelled (the ratchet models one, #449).
        # Firing at lock + fee makes the post-fee landing hit the line.
        # lock = 10 - 0.2*10 = 8.00; 8.05 sits between lock and lock+fee.
        self.assertTrue(run_engine._trailing_lock_hit(
            10.0, 8.05, self.TRAIL, baseline_pnl=0.0, exit_fee_usd=0.10))
        self.assertFalse(run_engine._trailing_lock_hit(
            10.0, 8.05, self.TRAIL, baseline_pnl=0.0))

    def test_the_call_site_passes_baseline_and_fee(self):
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn("_trailing_lock_hit", src)
        # the VALUE matters: zeroing it silently restores the defect.
        self.assertIn('baseline_pnl=float(pnl.get("realized") or 0)', src)
        self.assertIn("exit_fee_usd=_exit_fee", src)


class SideCoherenceTests(unittest.TestCase):
    """FIL 1322 cycle 9 (2026-08-16): the desk closed a WINNING, correctly
    directed SHORT because it believed it had opened a long — three
    falsehoods in one cycle ("current long trade", "opening a long",
    "lock profit before a likely further drop" — a drop PAYS a short).
    Same day, run 1305 cycle 9: "Given we are long" on a -304 short.
    LTC 1297 closed a short citing bearish confluence. The desk infers
    its side from the action verb, not from position_state.

    Latent hazard on the same tape: cycle 9 emitted legacy_action
    'short' to CLOSE a short — only the intent compiler prevented a
    DOUBLED position."""

    def test_a_long_claim_on_a_short_book_is_caught(self):
        for text in ("Given we are long, the prudent move is to exit",
                     "limited upside for the current long trade",
                     "closing corrects the mis-direction after opening a long",
                     "Close the existing long position"):
            self.assertIsNotNone(
                run_engine._side_contradiction(text, -304.0), text)

    def test_a_short_claim_on_a_long_book_is_caught(self):
        self.assertIsNotNone(
            run_engine._side_contradiction("our existing short position", 12.5))

    def test_a_correct_claim_is_silent(self):
        self.assertIsNone(
            run_engine._side_contradiction("our existing short position", -304.0))
        self.assertIsNone(
            run_engine._side_contradiction("we are long and holding", 12.5))

    def test_a_flat_book_is_never_flagged(self):
        # No position: either side is a PLAN, not a contradiction. A short
        # claim is the case that actually exercises the exemption (qty 0
        # otherwise reads as LONG, which silences long-claims anyway).
        self.assertIsNone(
            run_engine._side_contradiction("we open a short here", 0.0))
        self.assertIsNone(
            run_engine._side_contradiction("our existing short position", 0.0))
        self.assertIsNone(
            run_engine._side_contradiction("we open a long here", 0.0))

    def test_text_without_a_side_claim_is_silent(self):
        self.assertIsNone(
            run_engine._side_contradiction(
                "momentum is weak and volume is thin", -304.0))

    def test_the_quote_names_both_sides(self):
        out = run_engine._side_contradiction("Given we are long, exit", -304.0)
        self.assertIn("long", out)
        self.assertIn("SHORT", out)

    def test_it_fails_soft_on_junk(self):
        for bad in (None, 12345, {"a": 1}):
            self.assertIsNone(run_engine._side_contradiction(bad, -1.0))

    def test_the_brief_line_quotes_the_contradiction_back(self):
        line = run_engine._side_contradiction_line(
            "Given we are long, the prudent move is to exit", -304.0)
        self.assertIn("YOUR OWN LAST CYCLE", line)
        self.assertIn("SHORT", line)

    def test_it_is_WIRED_into_the_composed_brief_and_the_decision(self):
        import inspect
        comp = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_side_contradiction_line", comp)
        dec = inspect.getsource(run_engine.run_cycle)
        self.assertIn("side_contradiction", dec)

    def test_the_brief_line_is_silent_when_coherent(self):
        self.assertEqual(run_engine._side_contradiction_line(
            "our existing short position", -304.0), "")


class NetOfFeesExitTests(unittest.TestCase):
    """2026-08-16, three runs, 3/3: the desk REASONS IN GROSS and BOOKS IN
    NET. FIL 1322 cyc9 wrote "Lock the $0.10 profit" — net was +$0.0143.
    SUI 1306 cyc11 wrote "captures the $0.12 gain" — net +$0.0164. DOT
    1308's first bank captured $0.0311 gross and paid $0.0303 in fees:
    net +$0.0008. Across six profitable staged tranches that day fees ate
    54% of gross. Every staging decision was taken on a number 3-7x the
    one that reached the ledger.

    This line puts the round trip in front of the desk BEFORE it authors
    the exit: what the open P&L is worth net, and what a tranche must
    clear to be worth taking at all."""

    def _pnl(self, unreal, qty, mark):
        return {"mark_age_ok": True, "unrealized": unreal,
                "position": {"quantity": qty, "current_price": mark}}

    def test_it_states_the_net_and_the_round_trip(self):
        # 76.66 @ 0.68 = $52.1288 notional. With a pinned 0.001/side rate
        # the round trip is BOTH legs: 52.1288 x 0.001 x 2 = $0.1043.
        # Pinning the NUMBER is what catches a single-leg round trip.
        import fees
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(0.10, -76.66, 0.68)), \
                patch.object(fees, "fee_rate", return_value=0.001):
            line = run_engine._net_of_fees_line({"id": 1, "market": "crypto"},
                                                -76.66)
        self.assertIn("round trip", line)
        self.assertIn("$0.1043", line)          # both legs, not $0.0521
        self.assertIn("-$0.0043", line)         # 0.10 gross - 0.1043 net

    def test_a_gain_under_its_round_trip_is_named_as_such(self):
        # gross $0.02 on a $52 book: the round trip is larger than the gain.
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(0.02, -76.66, 0.68)):
            line = run_engine._net_of_fees_line({"id": 1, "market": "crypto"},
                                                -76.66)
        self.assertIn("does NOT cover", line)

    def test_a_gain_well_clear_of_fees_is_not_warned(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value=self._pnl(3.20, -304.0, 0.68)):
            line = run_engine._net_of_fees_line({"id": 1, "market": "crypto"},
                                                -304.0)
        self.assertNotIn("does NOT cover", line)

    def test_a_flat_book_says_nothing(self):
        self.assertEqual(
            run_engine._net_of_fees_line({"id": 1, "market": "crypto"}, 0.0), "")

    def test_a_stale_mark_says_nothing(self):
        with patch.object(run_engine, "compute_run_pnl",
                          return_value={"mark_age_ok": False}):
            self.assertEqual(run_engine._net_of_fees_line(
                {"id": 1, "market": "crypto"}, -76.66), "")

    def test_it_fails_soft(self):
        with patch.object(run_engine, "compute_run_pnl",
                          side_effect=RuntimeError("down")):
            self.assertEqual(run_engine._net_of_fees_line(
                {"id": 1, "market": "crypto"}, -76.66), "")

    def test_it_is_WIRED_into_the_composed_brief(self):
        import inspect
        src = inspect.getsource(run_engine._compose_position_state)
        self.assertIn("_net_of_fees_line", src)


class NoVerdictDiagnosticTests(unittest.TestCase):
    """Measured 2026-08-16/17: the `conf 0.0 / "light cycle: no LLM verdict"`
    rate rose from 2.0% (8/405) before the Plan 26 flag flip to 10.8%
    (26/240) after — 5.4x on 645 decisions, concentrated on runs that have
    already traded (15.6% vs 6.2%). Not an outage (16x HTTP 200, zero
    timeouts), and the obvious truncation mechanism is already guarded
    (max_tokens += 180 when outlook is on). CAUSE UNEXPLAINED.

    Three candidates are indistinguishable from the current tape because a
    parse failure and an empty response produce the identical event. This
    records which one happened, so one day of tape decides it instead of
    another round of guessing."""

    def test_an_empty_response_is_labelled(self):
        d = run_engine._no_verdict_diagnostic(None)
        self.assertEqual(d["kind"], "empty")
        self.assertEqual(d["chars"], 0)

    def test_a_response_with_no_json_object_is_labelled(self):
        d = run_engine._no_verdict_diagnostic("I cannot answer that.")
        self.assertEqual(d["kind"], "no_json")
        self.assertEqual(d["chars"], 21)

    def test_truncated_json_is_distinguished_from_malformed(self):
        # Unbalanced braces = the model was cut off mid-object.
        d = run_engine._no_verdict_diagnostic('{"action": "hold", "sc')
        self.assertEqual(d["kind"], "truncated")
        self.assertTrue(d["chars"] > 0)

    def test_balanced_but_invalid_json_is_malformed(self):
        d = run_engine._no_verdict_diagnostic('{"action": hold,}')
        self.assertEqual(d["kind"], "malformed")

    def test_the_tail_is_captured_and_bounded(self):
        d = run_engine._no_verdict_diagnostic("x" * 5000)
        self.assertLessEqual(len(d["tail"]), 200)
        self.assertEqual(d["chars"], 5000)

    def test_it_fails_soft_on_junk(self):
        for bad in (123, {"a": 1}, []):
            self.assertEqual(
                run_engine._no_verdict_diagnostic(bad)["kind"], "empty")

    def test_it_is_WIRED_into_the_light_path(self):
        import inspect
        src = inspect.getsource(run_engine._light_analysis)
        # assert the CALL, not the bare name — a comment mentioning the
        # helper made this test tautological on its first writing.
        self.assertIn("_no_verdict_diagnostic(text)", src)
        self.assertIn('"no_verdict"', src)
