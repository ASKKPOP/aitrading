"""Plan 26 Phase 1 (write side) — the slot strategy outlook.

Wiring-first (the brief-line lesson: helpers tested for rendering, not
concatenation, let an unwired line pass every test): a full run_cycle against
a mocked LLM must land an `outlook` row in run_events, and a seeded outlook
must reach the next cycle's prompt as the standing_plan brief line. Parser
clamps are unit-tested beside that, because NaN in a persisted JSON column
permanently 500s reads. No test here may reach a live LLM or the network.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import trading_runs
import trading_skills
from routes import create_app

VALID_OUTLOOK = {
    "bias": "short",
    "entry": {"kind": "zone", "low": 2.80, "high": 2.96,
              "trigger": None},
    "exit": {"target_px": 2.84, "stop_ref_px": 3.47,
             "time_exit": "2026-08-16T14:00Z"},
    "invalidation": "daily close above 3.47",
    "horizon_hours": 18,
    "narrative": "Hold the short; cover into the zone.",
}

ALGO_CANDIDATE = {"entry_low": 2.90, "entry_high": 3.00, "target_px": 2.70,
                  "stop_ref_px": 3.40, "time_exit": "2026-08-16T12:00Z"}


def _analysis(decision_extra=None, action="buy", confidence=0.9):
    decision = {"action": action, "confidence": confidence,
                "entry": 100.0, "report": "r"}
    decision.update(decision_extra or {})
    return {
        "symbol": "BTC", "market": "crypto",
        "analysts": {"technical": {"brief": "t",
                                   "data": {"sigma_daily_pct": 2.5,
                                            "current_price": 100.0}}},
        "decision": decision,
    }


def _stub_refresher():
    """A stand-in outlook_refresher module: the real one ships from a
    parallel phase, so the lazy import is exercised against a stub."""
    mod = types.ModuleType("outlook_refresher")
    mod.algo_candidate = lambda *a, **k: dict(ALGO_CANDIDATE)
    return mod


class _ParserTests(unittest.TestCase):
    """Pure clamps — no DB, no LLM."""

    def test_valid_outlook_round_trips(self):
        out = run_engine._parse_outlook(VALID_OUTLOOK)
        self.assertEqual(out["bias"], "short")
        self.assertEqual(out["entry"]["kind"], "zone")
        self.assertEqual(out["entry"]["low"], 2.80)
        self.assertEqual(out["exit"]["stop_ref_px"], 3.47)
        self.assertEqual(out["invalidation"], "daily close above 3.47")
        self.assertEqual(out["horizon_hours"], 18.0)
        self.assertEqual(out["narrative"],
                         "Hold the short; cover into the zone.")

    def test_missing_object_is_no_event_not_a_crash(self):
        for raw in (None, "", 42, [], "long"):
            self.assertIsNone(run_engine._parse_outlook(raw))

    def test_junk_types_degrade_to_safe_defaults(self):
        out = run_engine._parse_outlook(
            {"bias": 7, "entry": "zone", "exit": ["x"],
             "invalidation": {"a": 1}, "horizon_hours": "soon",
             "narrative": 123})
        self.assertEqual(out["bias"], "flat")
        self.assertEqual(out["entry"],
                         {"kind": "none", "low": None, "high": None,
                          "trigger": None})
        self.assertEqual(out["exit"],
                         {"target_px": None, "stop_ref_px": None,
                          "time_exit": None})
        self.assertIsNone(out["invalidation"])
        self.assertIsNone(out["horizon_hours"])
        self.assertEqual(out["narrative"], "")

    def test_nan_and_inf_are_scrubbed_to_null(self):
        # json.loads happily produces NaN/Infinity floats — the exact shape
        # that permanently 500s reads once persisted.
        raw = json.loads(
            '{"bias": "long", "entry": {"kind": "zone", "low": NaN, '
            '"high": Infinity}, "exit": {"target_px": -Infinity, '
            '"stop_ref_px": NaN}, "horizon_hours": NaN, "narrative": "n"}')
        out = run_engine._parse_outlook(raw)
        self.assertIsNone(out["entry"]["low"])
        self.assertIsNone(out["entry"]["high"])
        self.assertIsNone(out["exit"]["target_px"])
        self.assertIsNone(out["exit"]["stop_ref_px"])
        self.assertIsNone(out["horizon_hours"])
        # …and nothing non-finite survives anywhere in the payload.
        def _no_nan(node):
            if isinstance(node, float):
                self.assertTrue(math.isfinite(node))
            elif isinstance(node, dict):
                for v in node.values():
                    _no_nan(v)
        _no_nan(out)

    def test_bool_is_not_a_number(self):
        self.assertIsNone(run_engine._outlook_num(True))

    def test_oversized_prose_is_capped(self):
        out = run_engine._parse_outlook(
            {"bias": "long", "narrative": "n" * 5000,
             "invalidation": "i" * 5000,
             "basis": {"verdict": "adopted", "discussion": "d" * 5000}})
        self.assertEqual(len(out["narrative"]), 600)
        self.assertEqual(len(out["invalidation"]), 300)
        self.assertEqual(len(out["basis"]["discussion"]), 300)

    def test_plan_adherence_junk_defaults_to_revised(self):
        self.assertEqual(run_engine._parse_plan_adherence("followed"),
                         "followed")
        self.assertEqual(run_engine._parse_plan_adherence("DEVIATED"),
                         "deviated")
        for junk in (None, "", "yes", 3, {"a": 1}, ["followed"]):
            self.assertEqual(run_engine._parse_plan_adherence(junk),
                             "revised")

    def test_basis_verdict_junk_defaults_to_adjusted(self):
        self.assertEqual(run_engine._parse_outlook_verdict("Adopted"),
                         "adopted")
        self.assertEqual(run_engine._parse_outlook_verdict("overridden"),
                         "overridden")
        for junk in (None, "", "kept", 1, []):
            self.assertEqual(run_engine._parse_outlook_verdict(junk),
                             "adjusted")


class _Db(unittest.TestCase):
    """run_cycle fixture — same shape as test_run_cycle_order_params."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        os.environ.pop("OUTLOOK_ENABLED", None)
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "outlook-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]

    def tearDown(self):
        self.probe.stop()
        # Env hygiene: these leak across pytest otherwise.
        for key in ("AUTO_TRADING_ENABLED", "RISK_ENGINE_ENABLED",
                    "OUTLOOK_ENABLED"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _run(self, **overrides) -> int:
        payload = {"symbol": "BTC", "market": "crypto", "max_bet_usd": 500.0}
        payload.update(overrides)
        run_id = self.client.post(
            "/api/runs", json=payload,
            headers={"Authorization": f"Bearer {self.token}"}).json()["id"]
        assert self.client.post(
            f"/api/runs/{run_id}/start",
            headers={"Authorization": f"Bearer {self.token}"}
        ).status_code == 200
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


class OutlookEmissionWiringTests(_Db):
    def test_flag_on_lands_an_outlook_row(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        # Candidate module forced absent so this test is about the event
        # itself; basis coverage lives in BasisTests.
        with patch.dict(sys.modules, {"outlook_refresher": None}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis({"outlook": dict(VALID_OUTLOOK),
                                              "plan_adherence": "followed"})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        evs = self._events(run_id, "outlook")
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual(ev["source"], "cycle")
        self.assertEqual(ev["symbol"], "BTC")
        self.assertEqual(ev["market"], "crypto")
        self.assertIsInstance(ev["cycle"], int)
        self.assertEqual(ev["bias"], "short")
        # The model's 3.47 stop echo is DISCARDED: with no live stop on
        # this run the recorded reference is null, never the model's word.
        self.assertIsNone(ev["exit"]["stop_ref_px"])
        # No candidate module → no basis at all.
        self.assertNotIn("basis", ev)

    def test_model_stop_echo_is_replaced_by_the_real_live_stop(self):
        # Write-once stop rule: a hallucinated wider stop must not even be
        # DISPLAYED as the plan — the stored payload carries the book's own
        # stop_loss, whatever the model returned.
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO positions (agent_id, symbol, market, side,
                       quantity, entry_price, current_price, opened_at,
                       run_id, stop_loss)
                   VALUES (?, 'BTC', 'crypto', 'long', 1.0, 100.0, 100.0,
                       '2026-08-15T00:00:00Z', ?, 95.0)""",
                (self.agent_id, run_id))
            conn.commit()
        finally:
            conn.close()
        wider = dict(VALID_OUTLOOK)
        wider["exit"] = {"target_px": 120.0, "stop_ref_px": 40.0,
                        "time_exit": None}
        with patch.dict(sys.modules, {"outlook_refresher": None}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis({"outlook": wider},
                                             action="hold")):
            run_engine.run_cycle(run_id)
        ev = self._events(run_id, "outlook")[0]
        self.assertEqual(ev["exit"]["stop_ref_px"], 95.0)

    def test_flag_off_emits_nothing_even_when_the_model_offers_a_plan(self):
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"outlook": dict(VALID_OUTLOOK)})):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "outlook"), [])

    def test_flag_on_but_no_outlook_in_the_answer_emits_nothing(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch("analysis_agents.run_analysis", return_value=_analysis()):
            run_engine.run_cycle(run_id)
        self.assertEqual(self._events(run_id, "outlook"), [])

    def test_junk_outlook_never_crashes_the_cycle(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"outlook": "tomorrow up"})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertEqual(self._events(run_id, "outlook"), [])

    def test_nan_never_reaches_the_persisted_payload(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        poisoned = dict(VALID_OUTLOOK)
        poisoned["horizon_hours"] = float("nan")
        poisoned["exit"] = {"target_px": float("inf"), "stop_ref_px": 3.47}
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"outlook": poisoned})):
            run_engine.run_cycle(run_id)
        raw_rows = self._events(run_id, "outlook")
        self.assertEqual(len(raw_rows), 1)
        # json.loads in _events would resurrect NaN — check the raw text.
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = 'outlook'", (run_id,))
            text = cur.fetchone()["payload"]
        finally:
            conn.close()
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        self.assertIsNone(raw_rows[0]["horizon_hours"])
        self.assertIsNone(raw_rows[0]["exit"]["target_px"])


class PlanAdherenceRoundTripTests(_Db):
    def test_valid_value_rides_the_decision_event(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"plan_adherence": "followed"})):
            run_engine.run_cycle(run_id)
        decisions = self._events(run_id, "decision")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["plan_adherence"], "followed")

    def test_junk_defaults_to_revised_and_never_crashes(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"plan_adherence": {"huh": 1}})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertEqual(self._events(run_id, "decision")[0]["plan_adherence"],
                         "revised")

    def test_flag_off_stamps_nothing(self):
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis({"plan_adherence": "followed"})):
            run_engine.run_cycle(run_id)
        self.assertNotIn("plan_adherence", self._events(run_id, "decision")[0])


class BasisTests(_Db):
    def test_emission_includes_basis_with_candidate_and_parsed_verdict(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        outlook = dict(VALID_OUTLOOK)
        outlook["basis"] = {"verdict": "adopted",
                            "discussion": "algo target is inside my zone"}
        with patch.dict(sys.modules, {"outlook_refresher": _stub_refresher()}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis({"outlook": outlook})):
            run_engine.run_cycle(run_id)
        ev = self._events(run_id, "outlook")[0]
        self.assertEqual(ev["basis"]["algo"], ALGO_CANDIDATE)
        self.assertEqual(ev["basis"]["verdict"], "adopted")
        self.assertEqual(ev["basis"]["discussion"],
                         "algo target is inside my zone")

    def test_junk_verdict_defaults_to_adjusted(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        outlook = dict(VALID_OUTLOOK)
        outlook["basis"] = {"verdict": "kept it", "discussion": 42}
        with patch.dict(sys.modules, {"outlook_refresher": _stub_refresher()}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis({"outlook": outlook})):
            run_engine.run_cycle(run_id)
        ev = self._events(run_id, "outlook")[0]
        self.assertEqual(ev["basis"]["verdict"], "adjusted")
        self.assertIsNone(ev["basis"]["discussion"])

    def test_import_failure_emits_the_outlook_without_basis(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        outlook = dict(VALID_OUTLOOK)
        outlook["basis"] = {"verdict": "adopted", "discussion": "d"}
        # None in sys.modules makes `import outlook_refresher` raise
        # ImportError deterministically, whether or not the real module
        # exists by the time this suite runs.
        with patch.dict(sys.modules, {"outlook_refresher": None}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis({"outlook": outlook})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        evs = self._events(run_id, "outlook")
        self.assertEqual(len(evs), 1)
        self.assertNotIn("basis", evs[0])

    def test_vacuous_candidate_is_treated_as_absent(self):
        # The real algo_candidate returns an all-None dict when thesis
        # inputs are missing — that is no candidate: no prompt line, no
        # basis, never "entry zone None-None" in a decision prompt.
        vacuous = types.ModuleType("outlook_refresher")
        vacuous.algo_candidate = lambda *a, **k: {
            "entry_low": None, "entry_high": None, "target_px": None,
            "stop_ref_px": None, "time_exit": None}
        with patch.dict(sys.modules, {"outlook_refresher": vacuous}):
            self.assertIsNone(run_engine._outlook_algo_candidate(
                {"id": 1, "stop_conditions_json": "{}"}, {"thesis": {}}))

    def test_candidate_call_failure_is_fail_soft(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        broken = types.ModuleType("outlook_refresher")

        def _boom(*a, **k):
            raise RuntimeError("candidate exploded")
        broken.algo_candidate = _boom
        with patch.dict(sys.modules, {"outlook_refresher": broken}), \
                patch("analysis_agents.run_analysis",
                      return_value=_analysis(
                          {"outlook": dict(VALID_OUTLOOK)})):
            result = run_engine.run_cycle(run_id)
        self.assertTrue(result["executed"], result.get("skip_reason"))
        self.assertNotIn("basis", self._events(run_id, "outlook")[0])


class PromptContractTests(_Db):
    """The instruction reaches (or stays out of) the actual prompts."""

    def _light_prompt(self, run_id):
        run = {"id": run_id, "agent_id": self.agent_id, "symbol": "BTC",
               "market": "crypto", "market_type": "spot",
               "stop_conditions_json": "{}"}
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            captured["max_tokens"] = kwargs.get("max_tokens")
            return '{"action": "hold", "confidence": 0.5, "report": "r"}'

        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate):
            run_engine._light_analysis(run, {"thesis": {}})
        return captured

    def test_light_prompt_gains_the_contract_only_with_the_flag(self):
        run_id = self._run()
        off = self._light_prompt(run_id)
        self.assertNotIn("outlook", off["prompt"])
        self.assertNotIn("plan_adherence", off["prompt"])
        self.assertNotIn("forward plan", off["prompt"])
        os.environ["OUTLOOK_ENABLED"] = "1"
        on = self._light_prompt(run_id)
        self.assertIn('"outlook"', on["prompt"])
        self.assertIn("plan_adherence", on["prompt"])
        self.assertIn("forward plan", on["prompt"])
        # …and the completion budget grows so the JSON is not cut off.
        self.assertGreater(on["max_tokens"], off["max_tokens"])

    def test_light_prompt_shows_the_algo_candidate_when_available(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch.dict(sys.modules, {"outlook_refresher": _stub_refresher()}):
            on = self._light_prompt(run_id)
        self.assertIn("Algorithmic candidate plan:", on["prompt"])
        self.assertIn("adopt, adjust, or override", on["prompt"])
        with patch.dict(sys.modules, {"outlook_refresher": None}):
            without = self._light_prompt(run_id)
        self.assertNotIn("Algorithmic candidate plan:", without["prompt"])

    def test_full_path_prompt_mirrors_the_contract(self):
        import analysis_agents
        briefs = {"news": "n", "sentiment": "s",
                  "fundamentals_macro": "f", "technical": "t"}
        technical = {"current_price": 100.0}
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5, "report": "r"}'

        def _call():
            with patch("analysis_agents.llm_configured", return_value=True), \
                    patch("analysis_agents.generate_text",
                          side_effect=fake_generate):
                analysis_agents._trader_risk_decision(
                    "BTC", "crypto", briefs, technical, {"articles": []}, "en")
            return captured["prompt"]

        off_prompt = _call()
        self.assertNotIn('"outlook"', off_prompt)
        self.assertNotIn("plan_adherence", off_prompt)
        os.environ["OUTLOOK_ENABLED"] = "1"
        on_prompt = _call()
        self.assertIn('"outlook"', on_prompt)
        self.assertIn("plan_adherence", on_prompt)
        self.assertIn("For the outlook:", on_prompt)


class StandingPlanLoopTests(_Db):
    """§3.6 closed loop: the kept plan reaches the next analysis prompt."""

    def _seed_outlook(self, run_id, payload=None):
        base = {"cycle": 1, "symbol": "BTC", "market": "crypto",
                "source": "cycle", **run_engine._parse_outlook(VALID_OUTLOOK)}
        base.pop("basis", None)
        base.update(payload or {})
        trading_runs.emit_telemetry_event(run_id, "outlook", base)

    def test_seeded_plan_reaches_the_next_cycles_prompt(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        self._seed_outlook(run_id)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis()) as mocked:
            run_engine.run_cycle(run_id)
        state = mocked.call_args.kwargs["position_state"]
        self.assertIn("Your standing plan", state)
        self.assertIn("short bias", state)
        self.assertIn("entry zone 2.8-2.96", state)
        self.assertIn("stop ref 3.47", state)
        self.assertIn("invalidation: daily close above 3.47", state)
        self.assertIn("horizon 18h", state)

    def test_no_prior_outlook_renders_no_line(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis()) as mocked:
            run_engine.run_cycle(run_id)
        self.assertNotIn("standing plan",
                         mocked.call_args.kwargs["position_state"])

    def test_flag_off_hides_the_line_even_with_a_seeded_plan(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        self._seed_outlook(run_id)
        os.environ["OUTLOOK_ENABLED"] = "0"
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis()) as mocked:
            run_engine.run_cycle(run_id)
        self.assertNotIn("standing plan",
                         mocked.call_args.kwargs["position_state"])

    def test_light_prompt_carries_the_line_too(self):
        # The light path composes its own position_state — the same seeded
        # plan must reach the cheap prompt, not only the escalated one.
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        self._seed_outlook(run_id)
        run = {"id": run_id, "agent_id": self.agent_id, "symbol": "BTC",
               "market": "crypto", "market_type": "spot",
               "stop_conditions_json": "{}"}
        captured = {}

        def fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"action": "hold", "confidence": 0.5, "report": "r"}'

        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
                patch("price_fetcher.get_daily_candles", return_value=[]), \
                patch("llm_client.generate_text", side_effect=fake_generate):
            run_engine._light_analysis(run, {"thesis": {}})
        self.assertIn("Your standing plan", captured["prompt"])

    def test_newest_event_wins(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        self._seed_outlook(run_id)
        newer = run_engine._parse_outlook(
            {**VALID_OUTLOOK, "bias": "long",
             "invalidation": "weekly close below 2.50"})
        newer.pop("basis", None)
        self._seed_outlook(run_id, newer)
        line = run_engine._standing_plan_line({"id": run_id})
        self.assertIn("long bias", line)
        self.assertIn("weekly close below 2.50", line)

    def test_decision_journal_names_the_rendered_line(self):
        # R16 discipline: whether the line rendered must be answerable from
        # the tape — the decision event's brief journal carries its name.
        os.environ["OUTLOOK_ENABLED"] = "1"
        run_id = self._run()
        self._seed_outlook(run_id)
        with patch("analysis_agents.run_analysis",
                   return_value=_analysis()):
            run_engine.run_cycle(run_id)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM run_events WHERE run_id = ? "
                        "AND event_type = 'decision'", (run_id,))
            payload = json.loads(cur.fetchone()["payload"])
        finally:
            conn.close()
        self.assertIn("standing_plan", payload.get("brief") or [])


class StandingPlanSkillTests(_Db):
    """The discipline skill renders only while the feature is live."""

    def test_skill_is_gated_by_the_flag(self):
        trading_skills.invalidate_trading_skills_cache()
        off = trading_skills.skills_block("light", market="crypto")
        self.assertNotIn("Standing Plan Discipline", off)
        os.environ["OUTLOOK_ENABLED"] = "1"
        on = trading_skills.skills_block("light", market="crypto")
        self.assertIn("Standing Plan Discipline", on)
        self.assertIn("plan_adherence", on)
        # Flag off again: byte-identical to the pre-plan block.
        os.environ.pop("OUTLOOK_ENABLED", None)
        self.assertEqual(trading_skills.skills_block("light", market="crypto"),
                         off)

    def test_skill_rides_both_decision_sites(self):
        os.environ["OUTLOOK_ENABLED"] = "1"
        trading_skills.invalidate_trading_skills_cache()
        for site in ("light", "trader"):
            slugs = [s["slug"] for s in trading_skills.skills_for_prompt(site)]
            self.assertIn("standing-plan-discipline", slugs, site)
        self.assertNotIn(
            "standing-plan-discipline",
            [s["slug"] for s in trading_skills.skills_for_prompt("planner")])


class OutlookI18nWarmTests(_Db):
    """Copied contract from the desk-report warm: non-English owner gets a
    write-time warm of narrative + invalidation; English warms nothing."""

    def _set_lang(self, lang):
        # A self-registered claw agent carries no users row — give it one,
        # same as the desk-report warm tests do.
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users (email, password_hash, created_at, lang)
                   VALUES (?, 'x', '2026-08-15T00:00:00Z', ?)""",
                (f"outlook-{lang}@test.local", lang))
            user_id = cur.lastrowid
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (user_id, self.agent_id))
            conn.commit()
        finally:
            conn.close()

    def test_warms_narrative_and_invalidation_for_the_owner_lang(self):
        self._set_lang("ko")
        with patch("market_i18n.localize_texts") as warm:
            run_engine._warm_outlook_i18n(
                self.agent_id, run_engine._parse_outlook(VALID_OUTLOOK))
        warm.assert_called_once_with(
            ["Hold the short; cover into the zone.",
             "daily close above 3.47"], "ko")

    def test_english_owner_warms_nothing(self):
        self._set_lang("en")
        with patch("market_i18n.localize_texts") as warm:
            run_engine._warm_outlook_i18n(
                self.agent_id, run_engine._parse_outlook(VALID_OUTLOOK))
        warm.assert_not_called()

    def test_warm_failure_never_raises(self):
        self._set_lang("ko")
        with patch("market_i18n.localize_texts",
                   side_effect=RuntimeError("i18n down")):
            run_engine._warm_outlook_i18n(
                self.agent_id, run_engine._parse_outlook(VALID_OUTLOOK))


if __name__ == "__main__":
    unittest.main()
