"""Wiring tests for AI-authored order parameters inside run_cycle.

The rails themselves are unit-tested in test_order_params.py; these prove the
cycle actually CONSULTS them — that shadow mode journals without changing the
order, apply mode moves the real size and bracket, and the R:R floor refuses a
trade whoever authored the bracket. Without these the whole feature could be
deleted from run_cycle and every other test would still pass.
"""

from __future__ import annotations

import json
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
import run_engine
from routes import create_app

ORDER = {"defer": False, "size_frac": 0.20, "leverage": 1.0,
         "stop_pct": 2.0, "target_pct": 6.0, "why": "ATR-anchored"}


def _analysis(order=None, action="buy", confidence=0.9):
    decision = {"action": action, "confidence": confidence,
                "entry": 100.0, "report": "r"}
    if order is not None:
        decision["order"] = order
    return {
        "symbol": "BTC", "market": "crypto",
        "analysts": {"technical": {"brief": "t",
                                   "data": {"sigma_daily_pct": 2.5,
                                            "current_price": 100.0}}},
        "decision": decision,
    }


class RunCycleOrderParamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_CONF_PERCENTILE"] = "false"
        # Prod runs with the risk engine ON — that is what supplies the flat
        # 5%/10% bracket these tests are about (verified on prod run 113:
        # entry 487.25 -> stop 462.888, target 535.975). With it off there is
        # no bracket at all and none of the exit assertions mean anything.
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        # Same reason: prod runs FEE_PER_MARKET on, so the fee floor these
        # tests read is the market's real round trip, not the legacy flat rate.
        os.environ["FEE_PER_MARKET"] = "true"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "op-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for key in ("AUTO_TRADING_ENABLED", "RUN_CONF_PERCENTILE",
                    "RUN_AI_ORDER_PARAMS", "RISK_ENGINE_ENABLED",
                    "FEE_PER_MARKET", "RUN_NULL_SIZE_CAP_FRAC"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        assert self.client.post(f"/api/runs/{run_id}/start",
                                headers=self._h()).status_code == 200
        return run_id

    def _events(self, run_id, kind):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = ?", (run_id, kind))
            return [json.loads(r["payload"]) for r in cur.fetchall()]
        finally:
            conn.close()

    def _fill(self, run_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT quantity, entry_price FROM signals "
                        "WHERE run_id = ? AND executed_at IS NOT NULL", (run_id,))
            fills = [dict(r) for r in cur.fetchall()]
            # The bracket lands on the POSITION, not the signal row.
            cur.execute("SELECT stop_loss, take_profit FROM positions "
                        "WHERE run_id = ?", (run_id,))
            pos = cur.fetchone()
            for f in fills:
                f["stop_loss"] = pos["stop_loss"] if pos else None
                f["take_profit"] = pos["take_profit"] if pos else None
            return fills
        finally:
            conn.close()

    # ── shadow mode: journal everything, change nothing ────────────────

    def test_shadow_journals_the_block_but_does_not_resize(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        evs = self._events(run_id, "order_params")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["mode"], "shadow")
        self.assertFalse(evs[0]["deferred"])
        self.assertEqual(evs[0]["params"]["size_frac"], 0.20)
        # …and the fill is still the FULL configured bet, not 20% of it.
        fills = self._fill(run_id)
        self.assertEqual(len(fills), 1)
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 500.0, places=2)

    def test_shadow_records_a_deferral(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"defer": True})):
            run_engine.run_cycle(run_id)
        evs = self._events(run_id, "order_params")
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["deferred"])
        self.assertEqual(evs[0]["outcome"], "defer")

    def test_an_absent_block_is_distinguished_from_a_deferral(self):
        """Prod journaled 6 straight `deferred: true` and there was no way to
        tell whether the model was choosing the house default or never seeing
        the prompt at all. Those are opposite findings."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "absent")

    def test_a_malformed_block_is_not_reported_as_a_deferral(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"size_frac": "lots"})):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "malformed")

    def test_a_path_that_opts_out_is_marked_not_eligible(self):
        """`not_eligible` is retained for any future path that declines to ask
        for a bracket. The light path no longer sets it."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        opted_out = _analysis()
        opted_out["decision"]["order_eligible"] = False
        with patch("analysis_agents.run_analysis", return_value=opted_out):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "not_eligible")

    def test_off_mode_journals_nothing(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "order_params"), [])

    def test_a_model_that_emits_no_block_is_unaffected(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertTrue(self._events(run_id, "order_params")[0]["deferred"])

    # ── R17: null-size opens are capped, never the full-bet default ────

    def test_null_size_open_is_capped_at_quarter_bet(self):
        """Owner order 2026-08-18 ("make solution for protect profit"):
        default-sized opens realized −$178.69 over 47 runs vs +$5.55 over
        17 desk-sized (runs ≥ 1020). A null size_frac on an OPEN must fall
        to a quarter bet, not the full conviction-scaled default."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={**ORDER, "size_frac": None})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertEqual(len(fills), 1)
        # 0.25 × the $500 configured bet, not $500.
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 125.0,
                               places=2)
        clamps = self._events(run_id, "size_clamp")
        self.assertTrue(any(c.get("stage") == "null_size_cap" and
                            c.get("size_after") == 125.0 for c in clamps),
                        clamps)

    def test_authored_size_is_never_capped_by_null_size_rail(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={**ORDER, "size_frac": 0.6})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        # 0.6 × $500 — well above the 0.25 cap, untouched.
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 300.0,
                               places=2)
        self.assertFalse(any(c.get("stage") == "null_size_cap"
                             for c in self._events(run_id, "size_clamp")))

    def test_null_size_cap_env_one_disables(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        os.environ["RUN_NULL_SIZE_CAP_FRAC"] = "1.0"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={**ORDER, "size_frac": None})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 500.0,
                               places=2)

    # ── apply mode: the desk's numbers reach the book ──────────────────

    def test_apply_resizes_the_order(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        # 20% of the $500 max bet, at $100 → 1.0 unit, not 5.0.
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 100.0, places=2)

    def test_apply_uses_the_desks_bracket_not_the_flat_default(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            run_engine.run_cycle(run_id)
        fill = self._fill(run_id)[0]
        # 2% stop / 6% target off a 100.0 entry — NOT the house 5%/10%.
        self.assertAlmostEqual(float(fill["stop_loss"]), 98.0, places=2)
        self.assertAlmostEqual(float(fill["take_profit"]), 106.0, places=2)

    def test_a_cautious_minimum_size_survives_the_dust_floor(self):
        """Fleet 35 FIL (n=2): the desk authored the schema's advertised
        minimum size_frac 0.05 on a $172 max_bet and the $10 dust floor
        discarded the order both times. The engine must pass the run's
        executable minimum into the rails so the ask is floored UP and the
        order fills at the $10-margin minimum instead of vanishing."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run(max_bet_usd=150.0)
        cautious = {**ORDER, "size_frac": 0.05, "leverage": 1.0}
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=cautious)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        # 0.05 of $150 = $7.50 < $10 floor → raised to 10/150 ≈ 0.0667.
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 10.0,
                               places=2)
        params = self._events(run_id, "order_params")[0]["params"]
        self.assertTrue(any("size_frac 0.05 raised to floor" in n
                            for n in params["notes"]), params["notes"])

    def test_apply_still_rails_a_hostile_block(self):
        """size_frac 50 is 50x the configured bet; the rail must cap it at the
        full bet, never honour it."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        hostile = {**ORDER, "size_frac": 50, "leverage": 99}
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=hostile)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertLessEqual(float(fills[0]["quantity"]) * 100.0, 500.0 + 0.01)

    def test_the_fee_floor_is_priced_at_the_run_s_own_market(self):
        """`fees.fee_rate(market)` exists and the entry gate uses it, but the
        bracket rail was still calling the flat legacy 0.1% for every market —
        20x the real cost of a US equity round trip. A target-only block is
        what exposes it: with a stop present the R:R floor produces the same
        number and the fee rate is invisible.

        Crypto's true round trip is 0.045%, so the floor is 3 x 2 x 0.045 =
        0.27% and a 0.40% target survives. Under the flat rate the floor was
        0.60% and the same target was pushed out to 0.60%.
        """
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"target_pct": 0.40,
                                                 "why": "fee floor probe"})):
            run_engine.run_cycle(run_id)
        params = self._events(run_id, "order_params")[0]["params"]
        self.assertAlmostEqual(params["target_pct"], 0.40, places=6)
        self.assertFalse([n for n in params["notes"] if "fee floor" in n],
                         params["notes"])

    def test_apply_with_a_deferral_falls_back_to_the_house_bracket(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order={"defer": True})):
            run_engine.run_cycle(run_id)
        fill = self._fill(run_id)[0]
        self.assertAlmostEqual(float(fill["stop_loss"]), 95.0, places=2)   # 5%
        self.assertAlmostEqual(float(fill["take_profit"]), 110.0, places=2)  # 10%

    # ── the R:R floor guards both paths ────────────────────────────────

    def test_rr_floor_refuses_an_inverted_bracket_on_the_code_path(self):
        """No AI block at all — a hand-edited risk_limits row that risks 5% to
        win 2% must not trade. This is the rail that would have made last
        week's 10:1 geometry impossible."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        self.client.put("/api/risk/limits",
                        json={"stop_loss_pct": 0.05, "take_profit_pct": 0.02},
                        headers=self._h())
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertFalse(result["executed"])
        self.assertIn("r:r floor", result["skip_reason"])
        skips = [e for e in self._events(run_id, "gate_skip")
                 if e.get("stage") == "rr_floor"]
        self.assertEqual(len(skips), 1, "the refusal must be journaled")

    def test_compliant_house_bracket_still_trades(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))

    # ── R10 stop-coherence clamp (2026-08-14) ──────────────────────────

    def _pin_max_loss(self, run_id: int, max_loss: float,
                      feedback: bool = False):
        """Stamp a USD loss cap (and optionally the fleet's feedback flag,
        which decides WHICH rail binds) the way prod runs carry them."""
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT stop_conditions_json, config_snapshot_json "
                        "FROM trading_runs WHERE id = ?", (run_id,))
            row = cur.fetchone()
            stops = json.loads(row["stop_conditions_json"] or "{}")
            stops["max_loss_usd"] = max_loss
            cfg = json.loads(row["config_snapshot_json"] or "{}")
            if feedback:
                cfg["feedback"] = True
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET stop_conditions_json = ?, "
                        "config_snapshot_json = ? WHERE id = ?",
                        (json.dumps(stops), json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()

    def test_apply_clamps_a_size_whose_stop_overshoots_the_rail(self):
        """SPCX shape on a manual run: the desk's 2% stop on a $100 bet is
        $2 of risk against a $1.50 max_loss rail (feedback off → the full
        cap binds). The clamp shrinks the bet until the stop fits: $75."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        self._pin_max_loss(run_id, 1.5)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 75.0,
                               places=1)
        clamps = self._events(run_id, "size_clamp")
        self.assertEqual(len(clamps), 1)
        self.assertEqual(clamps[0]["stage"], "stop_coherence")
        self.assertAlmostEqual(clamps[0]["size_before"], 100.0, places=1)
        self.assertAlmostEqual(clamps[0]["size_after"], 75.0, places=1)

    def test_a_feedback_run_clamps_at_the_brake_fraction(self):
        """Fleet shape (feedback on): the binding rail is the drawdown
        brake at 0.70 × max_loss — room 0.70 × $2 = $1.40 → $70."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        self._pin_max_loss(run_id, 2.0, feedback=True)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0, 70.0,
                               places=1)

    def test_an_add_budgets_the_held_books_stop_risk(self):
        """R10 adversarial pass (HIGH, reproduced): pricing only the
        increment let a second $100 add rebuild the SPCX/SOL shape — book
        2× notional, whole-book stop-USD past the room. The add's room
        must subtract held_notional × stop%: the whole book's stop-USD
        stays inside the rail after every add."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        self._pin_max_loss(run_id, 3.2)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            first = run_engine.run_cycle(run_id)
            second = run_engine.run_cycle(run_id)
        self.assertTrue(first["executed"], first.get("skip_reason"))
        self.assertTrue(second["executed"], second.get("skip_reason"))
        fills = self._fill(run_id)
        self.assertEqual(len(fills), 2)
        # Entry 1 is coherent unclamped ($2 stop-USD ≤ $3.20 room); the add
        # must be clamped below full size so that the WHOLE book's stop-USD
        # (Σ notional × 2%) stays within the remaining room.
        add_notional = float(fills[1]["quantity"]) * 100.0
        self.assertLess(add_notional, 99.0)
        book_stop_usd = (float(fills[0]["quantity"]) +
                         float(fills[1]["quantity"])) * 100.0 * 0.02
        self.assertLessEqual(book_stop_usd, 3.2 + 0.01)
        clamps = self._events(run_id, "size_clamp")
        self.assertEqual(len(clamps), 1)
        self.assertAlmostEqual(clamps[0]["held_notional"], 100.0, delta=1.0)

    def test_the_clamp_kill_switch_restores_the_old_behavior(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        os.environ["RUN_STOP_COHERENCE"] = "0"
        try:
            run_id = self._run()
            self._pin_max_loss(run_id, 2.0)
            with patch("analysis_agents.run_analysis",
                       return_value=_analysis(order=ORDER)):
                result = run_engine.run_cycle(run_id)
            self.assertTrue(result["executed"], result.get("skip_reason"))
            fills = self._fill(run_id)
            self.assertAlmostEqual(float(fills[0]["quantity"]) * 100.0,
                                   100.0, places=2)
            self.assertEqual(self._events(run_id, "size_clamp"), [])
        finally:
            os.environ.pop("RUN_STOP_COHERENCE", None)

    def test_a_run_without_a_loss_cap_is_never_clamped(self):
        """Unknown room must never clamp — manual runs carry no
        max_loss_usd and their sizing is not this rail's business."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis(order=ORDER)):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertEqual(self._events(run_id, "size_clamp"), [])


if __name__ == "__main__":
    unittest.main()


class LightPathOrderBlockTests(RunCycleOrderParamTests):
    """The light path must ASK for a bracket (2026-07-27).

    100% of live runs routed to `_light_analysis`, whose prompt never
    requested order parameters and whose parser dropped any `order` key. The
    shadow dataset therefore stayed empty while the feature looked deployed.
    It now asks for stop_pct/target_pct only — the two fields the flat 5%/10%
    overrides — so the cheap path stays cheap.

    ORDER_DISCUSSION is disabled here on purpose: these tests own the light
    path's bracket PARSER, and the owner's order-discussion rule (2026-08-13)
    would escalate every mocked buy to the full panel and replace the very
    decision under test. The escalation has its own suite
    (test_order_discussion.py).
    """

    def setUp(self):
        super().setUp()
        os.environ["ORDER_DISCUSSION"] = "0"

    def tearDown(self):
        os.environ.pop("ORDER_DISCUSSION", None)
        super().tearDown()

    def _fleet_light_run(self) -> int:
        """A run the cycle will actually route to _light_analysis.

        The light path is fleet-only (`is_fleet_run`), and the per-run
        cycle_mode pin wins over routing — so stamp both.
        """
        run_id = self._run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_snapshot_json FROM trading_runs WHERE id = ?",
                        (run_id,))
            cfg = json.loads(cur.fetchone()["config_snapshot_json"] or "{}")
            cfg["cycle_mode"] = "light"
            database.begin_write_transaction(cur)
            cur.execute("UPDATE trading_runs SET config_snapshot_json = ?, "
                        "created_via = 'fleet' WHERE id = ?",
                        (json.dumps(cfg), run_id))
            conn.commit()
        finally:
            conn.close()
        return run_id

    def _light(self, reply: str):
        """Drive the real _light_analysis with a canned LLM reply."""
        run_id = self._fleet_light_run()
        with patch("llm_client.generate_text", return_value=reply), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)
        return run_id

    def test_light_prompt_requests_a_bracket(self):
        seen = {}
        def cap(prompt, **kw):
            seen["p"] = prompt
            return '{"action":"hold","confidence":0.5}'
        run_id = self._fleet_light_run()
        with patch("llm_client.generate_text", side_effect=cap), \
             patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]):
            run_engine.run_cycle(run_id)
        prompt = seen.get("p", "")
        # Assert the JSON CONTRACT, not just a prose mention — the model
        # returns the response shape, and prose alone would not make it emit
        # the fields.
        self.assertIn('"stop_pct": number|null', prompt)
        self.assertIn('"target_pct": number|null', prompt)
        # …and the instruction that keeps the bracket sane.
        self.assertIn("at least 2x stop_pct", prompt)

    def test_light_bracket_is_parsed_and_journaled(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._light('{"action":"buy","confidence":0.9,'
                             '"stop_pct":1.5,"target_pct":4.0,"report":"r"}')
        evs = self._events(run_id, "order_params")
        self.assertTrue(evs, "the light cycle must journal an order_params event")
        self.assertEqual(evs[0]["outcome"], "parsed",
                         "was 'not_eligible' — the whole reason shadow collected nothing")
        self.assertEqual(evs[0]["params"]["stop_pct"], 1.5)
        self.assertEqual(evs[0]["params"]["target_pct"], 4.0)

    def test_light_bracket_is_railed_like_any_other(self):
        """An inverted bracket from the cheap path gets the same R:R floor."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._light('{"action":"buy","confidence":0.9,'
                             '"stop_pct":3.0,"target_pct":1.0,"report":"r"}')
        p = self._events(run_id, "order_params")[0]["params"]
        self.assertEqual(p["target_pct"], 6.0)
        self.assertTrue(any("R:R floor" in n for n in p["notes"]))

    def test_light_bracket_reaches_the_book_in_apply_mode(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._light('{"action":"buy","confidence":0.9,'
                             '"stop_pct":2.0,"target_pct":6.0,"report":"r"}')
        fill = self._fill(run_id)
        self.assertTrue(fill, "the cycle should have traded")
        self.assertAlmostEqual(float(fill[0]["stop_loss"]), 98.0, places=2)
        self.assertAlmostEqual(float(fill[0]["take_profit"]), 106.0, places=2)

    def test_omitted_bracket_still_degrades_to_the_house_default(self):
        """"If you have no concrete basis, omit them" must keep working."""
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        run_id = self._light('{"action":"buy","confidence":0.9,"report":"r"}')
        fill = self._fill(run_id)
        self.assertAlmostEqual(float(fill[0]["stop_loss"]), 95.0, places=2)
        self.assertAlmostEqual(float(fill[0]["take_profit"]), 110.0, places=2)

    def test_null_bracket_is_treated_as_omitted(self):
        os.environ["RUN_AI_ORDER_PARAMS"] = "shadow"
        run_id = self._light('{"action":"buy","confidence":0.9,'
                             '"stop_pct":null,"target_pct":null,"report":"r"}')
        self.assertEqual(self._events(run_id, "order_params")[0]["outcome"],
                         "absent")
