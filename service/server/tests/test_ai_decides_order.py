"""Four fixes so the AI's order decision actually reaches the book (2026-07-27).

All four were found by tracing every event of three live runs that produced
6 cycles and 0 trades — every stage working, nothing reaching the book, for
three different reasons.

1. TRUNCATION      the trader's JSON was cut mid-object by the token limit, so
                   `_parse_decision_json` returned None and the caller silently
                   substituted a RULE decision. 3 of 6 live full-path cycles.
2. PROVENANCE      that substitution was unlabelled — a rule decision was
                   indistinguishable from an AI one in the journal, including a
                   confidence the AI never produced (0.6 vs 0.55 in its report).
3. CONVICTION      the full path never asked for component scores, so
                   conviction was None on every expensive cycle while the cheap
                   light path had them.
4. RELATIVE GATE   a purely percentile confidence gate rejects ~30% of
                   decisions however good they are. RUN 115's futures short at
                   0.60 — over its own 0.57 threshold — was refused twice for
                   ranking 52% against a window its own runs dominate.
5. DEAD THESIS     a spot run on a LONG thesis whose desk keeps reading bearish
                   can never act, and burned every cycle to the idle timer.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import analysis_agents as aa
import run_engine

# The exact payload prod run 115 cycle 1 produced and threw away.
RUN115_TRUNCATED = (
    '{"action":"sell","confidence":0.55,"entry":76.3,"target":73.0,"stop":77.7,'
    '"rationale":"Crowded long positioning (2.63x) with thin volume and price '
    'capped under MA20/MA5 matches the desk\'s known squeeze precursor, and '
    'macro risk-off adds downside pressure toward the 74 support br'
)


class TruncatedJsonSalvageTests(unittest.TestCase):
    def test_the_exact_prod_payload_is_recovered(self):
        obj = aa._parse_decision_json(RUN115_TRUNCATED)
        self.assertIsNotNone(obj, "this response was silently replaced by a rule decision")
        self.assertEqual(obj["action"], "sell")
        self.assertEqual(obj["confidence"], 0.55)
        self.assertEqual(obj["stop"], 77.7)
        self.assertEqual(obj["target"], 73.0)

    def test_salvaged_objects_are_flagged(self):
        """A recovered answer is still a damaged one — say so in the payload."""
        self.assertTrue(aa._parse_decision_json(RUN115_TRUNCATED).get("_truncated"))

    def test_complete_json_is_untouched_and_unflagged(self):
        obj = aa._parse_decision_json('{"action":"buy","confidence":0.7,"report":"r"}')
        self.assertEqual(obj["action"], "buy")
        self.assertIsNone(obj.get("_truncated"))

    def test_salvage_never_invents_a_value(self):
        """Only complete key/value pairs survive; the partial trailing one is
        dropped, never guessed."""
        obj = aa._parse_decision_json('{"action":"buy","confidence":0.8,"stop":1')
        self.assertEqual(obj["confidence"], 0.8)
        self.assertNotIn("stop", obj)

    def test_garbage_is_still_rejected(self):
        self.assertIsNone(aa._parse_decision_json("not json at all"))
        self.assertIsNone(aa._parse_decision_json('{"action":"teleport","confidence":0.9}'))
        self.assertIsNone(aa._parse_decision_json('{"confidence":0.9}'))   # no action
        self.assertIsNone(aa._parse_decision_json(""))

    def test_a_fragment_with_nothing_complete_yields_nothing(self):
        self.assertIsNone(aa._parse_decision_json('{"action":"bu'))

    def test_token_budget_covers_the_payload_we_ask_for(self):
        """900 was not enough once the order block joined the request."""
        self.assertGreaterEqual(aa._trader_max_tokens(), 1200)

    def test_token_budget_is_configurable_with_a_floor(self):
        os.environ["RUN_TRADER_MAX_TOKENS"] = "2000"
        self.assertEqual(aa._trader_max_tokens(), 2000)
        os.environ["RUN_TRADER_MAX_TOKENS"] = "10"      # absurd — clamped
        self.assertEqual(aa._trader_max_tokens(), 400)
        os.environ["RUN_TRADER_MAX_TOKENS"] = "junk"
        self.assertEqual(aa._trader_max_tokens(), 1500)
        os.environ.pop("RUN_TRADER_MAX_TOKENS", None)


class DecisionProvenanceTests(unittest.TestCase):
    """A rule decision must never again be indistinguishable from an AI one."""

    def test_rule_fallback_is_labelled(self):
        d = aa._rule_based_decision({"current_price": 100.0}, {"items": []})
        d["decided_by"] = "rule"          # what the caller stamps
        self.assertEqual(d["decided_by"], "rule")

    def test_prompt_requests_component_scores_on_the_full_path(self):
        """Conviction came back None on every full-path cycle because the
        expensive prompt never asked for what the cheap one did."""
        import inspect
        src = inspect.getsource(aa)
        self.assertIn('"scores":{"thesis_alignment"', src)
        for key in ("momentum_quality", "entry_quality", "risk_context"):
            self.assertIn(key, src)

    def test_full_path_scores_match_the_conviction_model(self):
        """The four keys asked for must be exactly the ones conviction weights,
        or the scores parse to nothing and conviction stays None anyway."""
        import inspect
        src = inspect.getsource(aa)
        for key in run_engine.CONVICTION_WEIGHTS:
            self.assertIn(f'"{key}"', src, f"full prompt never asks for {key}")


class ConfidenceGateTests(unittest.TestCase):
    """The percentile is a tie-breaker inside the ambiguous band, not an
    independent hurdle that a consistently-decent desk can never clear."""

    def tearDown(self):
        os.environ.pop("RUN_CONF_ABSOLUTE_MARGIN", None)

    def test_default_margin_is_a_real_but_small_one(self):
        self.assertGreater(run_engine._conf_absolute_override_margin(), 0)
        self.assertLessEqual(run_engine._conf_absolute_override_margin(), 0.10)

    def test_margin_is_configurable_and_zero_restores_pure_relative(self):
        os.environ["RUN_CONF_ABSOLUTE_MARGIN"] = "0"
        self.assertEqual(run_engine._conf_absolute_override_margin(), 0.0)
        os.environ["RUN_CONF_ABSOLUTE_MARGIN"] = "junk"
        self.assertEqual(run_engine._conf_absolute_override_margin(), 0.03)

    def test_run115_would_now_clear_its_own_threshold(self):
        """0.60 against a 0.57 threshold is a 0.03 margin — exactly the case
        that was refused twice in prod for ranking 52%."""
        self.assertGreaterEqual(0.60, 0.57 + run_engine._conf_absolute_override_margin())

    def test_a_marginal_decision_still_faces_the_percentile(self):
        """0.575 over a 0.57 threshold is not a clear reading — the tie-break
        must still apply."""
        self.assertLess(0.575, 0.57 + run_engine._conf_absolute_override_margin())


class ThesisInvalidationTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("RUN_THESIS_INVALIDATION_STRIKES", None)

    def test_default_strikes_is_shorter_than_the_idle_timer(self):
        """The point is to free the slot EARLY — a rail that fires after the
        idle timer would never fire at all."""
        self.assertGreater(run_engine._thesis_invalidation_strikes(), 0)
        self.assertLess(run_engine._thesis_invalidation_strikes(),
                        run_engine._idle_retire_cycles())

    def test_zero_disables_the_rail(self):
        os.environ["RUN_THESIS_INVALIDATION_STRIKES"] = "0"
        self.assertEqual(run_engine._thesis_invalidation_strikes(), 0)

    def test_bad_value_falls_back(self):
        os.environ["RUN_THESIS_INVALIDATION_STRIKES"] = "junk"
        self.assertEqual(run_engine._thesis_invalidation_strikes(), 3)

    def test_the_stop_reason_is_classified_for_replacement(self):
        """fleet_planner's disposition table is ENUMERATED — an unclassified
        stop reason would leave the slot in limbo."""
        import fleet_planner
        self.assertIn("thesis_invalidated", fleet_planner.REPLACE_IMMEDIATE)
        self.assertNotIn("thesis_invalidated", fleet_planner.REPLACE_DEFERRED)
        self.assertNotIn("thesis_invalidated", fleet_planner.REPLACE_NEVER)

    def test_streak_counter_is_failsoft_on_a_missing_run(self):
        """An unreadable journal must report 0 and leave the rail quiet, never
        retire a run on a database hiccup."""
        self.assertEqual(run_engine._unactionable_streak(-1), 0)


if __name__ == "__main__":
    unittest.main()


class SalvageNeverFabricatesTests(unittest.TestCase):
    """`confidence` defaults to 0.5 downstream, so recovering an action without
    one would manufacture a midpoint the model never expressed and feed it
    straight to the gates."""

    def test_action_without_confidence_is_not_salvaged(self):
        self.assertIsNone(aa._parse_decision_json('{"action":"buy",'))

    def test_confidence_without_action_is_not_salvaged(self):
        self.assertIsNone(aa._parse_decision_json('{"confidence":0.8,'))

    def test_both_present_is_salvaged(self):
        obj = aa._parse_decision_json('{"action":"buy","confidence":0.72,"stop":1')
        self.assertIsNotNone(obj)
        self.assertEqual(obj["confidence"], 0.72)

    def test_the_prod_payload_still_qualifies(self):
        """run 115 had both — the case this whole rail exists for."""
        self.assertIsNotNone(aa._parse_decision_json(RUN115_TRUNCATED))
