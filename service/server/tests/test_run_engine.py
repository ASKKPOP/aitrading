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
        src = inspect.getsource(run_engine.run_cycle)
        self.assertIn("_brake_distance_line(run, held)", src,
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


if __name__ == "__main__":
    unittest.main()
