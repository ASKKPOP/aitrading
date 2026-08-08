"""Every decision event records which model authored it.

Owner A/B (2026-08-08): compare Claude vs local ollama on realized profit.
Wall-clock attribution breaks the moment a Settings-page provider is flipped
mid-window; the stamp makes each decision self-documenting. The wiring test
exists because a helper that renders correctly but is never concatenated
passes every other test (see the brief-line trap, 2026-08-05).
"""
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine


class _Ap:
    class spec:
        name = "anthropic"
    model = "claude-opus-4-8"
    source = "user"


class DecisionLlmStampTestCase(unittest.TestCase):
    def test_stamp_carries_provider_model_source(self):
        with patch("llm_client.resolve_provider", return_value=_Ap()):
            self.assertEqual(run_engine._llm_stamp(),
                             {"provider": "anthropic",
                              "model": "claude-opus-4-8",
                              "source": "user"})

    def test_stamp_is_empty_not_broken_when_unresolvable(self):
        with patch("llm_client.resolve_provider",
                   side_effect=RuntimeError("down")):
            self.assertEqual(run_engine._llm_stamp(), {})

    def test_stamp_is_wired_into_the_decision_event(self):
        """A stamp that is never emitted attributes nothing."""
        src = inspect.getsource(run_engine)
        self.assertIn('"llm": _llm_stamp()', src,
                      "decision event no longer carries the model stamp")


if __name__ == "__main__":
    unittest.main()
