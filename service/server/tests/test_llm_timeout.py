"""Every LLM request must carry an explicit timeout.

Both SDKs default to 600s with automatic retries. Measured on prod
2026-08-08: the research loop went silent 30+ minutes inside ONE stalled
call (claim research:496159 sat empty from 07:17Z) while the provider
answered a fresh probe in 5.7s — the hourly refresh simply never happened.
A bounded timeout turns a stalled request into a failed attempt the calling
loop can retry on its own schedule.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import llm_client
from llm_client import ActiveProvider, ProviderSpec


def _provider(kind: str) -> ActiveProvider:
    return ActiveProvider(
        spec=ProviderSpec(name="test", key_env="X", default_base_url="http://x",
                          base_url_env="XB", default_model="m", kind=kind),
        base_url="http://x", model="m", source="test", api_key="k")


class _Stop(RuntimeError):
    pass


class LlmTimeoutTestCase(unittest.TestCase):
    def test_openai_compatible_client_carries_timeout(self):
        captured: dict = {}

        class FakeClient:
            def __init__(self, **kw):
                captured.update(kw)
                raise _Stop()

        with patch("openai.OpenAI", FakeClient):
            with self.assertRaises(_Stop):
                llm_client._generate_openai_compatible(
                    _provider("openai"), "p", None, 5, 0.0)
        self.assertEqual(captured.get("timeout"), 120.0)
        self.assertEqual(captured.get("max_retries"), 1)

    def test_anthropic_client_carries_timeout(self):
        captured: dict = {}

        class FakeClient:
            def __init__(self, **kw):
                captured.update(kw)
                raise _Stop()

        with patch("anthropic.Anthropic", FakeClient):
            with self.assertRaises(_Stop):
                llm_client._generate_anthropic(
                    _provider("anthropic"), "p", None, 5, 0.0)
        self.assertEqual(captured.get("timeout"), 120.0)
        self.assertEqual(captured.get("max_retries"), 1)

    def test_timeout_env_override(self):
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "45"}):
            self.assertEqual(llm_client._llm_timeout_seconds(), 45.0)
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "junk"}):
            self.assertEqual(llm_client._llm_timeout_seconds(), 120.0)
        # a value below the floor is clamped up — a 1s cap would fail every
        # real completion and look like a dead provider
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "3"}):
            self.assertEqual(llm_client._llm_timeout_seconds(), 10.0)


if __name__ == "__main__":
    unittest.main()
