"""Shared test configuration.

The test suite validates *production* behaviour, so force all dev-only conveniences
off regardless of what the container's ``.env`` sets. These flags are read at request
time (via ``os.getenv``), so setting them here — before any TestClient is created —
takes effect for every test.
"""
import os

# site_config.site_url() deliberately has NO default — an unset value raises
# rather than silently redirecting members to localhost (2026-08-13 defect).
# The suite therefore has to supply it, exactly as a real deploy does.
os.environ.setdefault("SOOPPIY_FRONTEND_URL", "https://sooppiy.test")

os.environ["DEV_LOGIN_ANY_PASSWORD"] = "false"
os.environ["DEV_MARKET_INTEL_SEED"] = "false"
os.environ["ALLOW_SYNC_PRICE_FETCH_IN_API"] = "false"

# Signal-collection phase flags default off in tests regardless of the local
# .env — a developer's enabled flags must not make tests hit live OKX/StockTwits.
os.environ["RISK_ENGINE_ENABLED"] = "false"
os.environ["PSYCH_FEED_ENABLED"] = "false"
os.environ["QUANT_CRYPTO_ENABLED"] = "false"
os.environ["SCANNER_ENABLED"] = "false"
# The breadth feed is keyless, so without this it would fetch a LIVE public
# CSV from inside any test that renders a us-stock decision prompt.
os.environ["BREADTH_FEED_ENABLED"] = "false"

# Notification-delivery tests exercise alerts/notifications with external=True;
# blank the provider credentials so no machine's .env can make a test send a
# real SendGrid email or Twilio SMS.
for _key in ("SENDGRID_API_KEY", "ALERT_FROM_EMAIL",
             "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
             "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
             "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"):
    os.environ[_key] = ""

# Three-agent desk discussion (owner 2026-09-02) is ON in production by
# default, but the suite's many light-path tests script a SINGLE trader
# reply and assert on that one prompt/call — the risk+chair calls would
# consume their stubs. Stage-isolation tests therefore run with the
# discussion off; test_three_agent_desk.py re-enables it explicitly and
# separately asserts the production default (by unsetting the variable).
os.environ["DESK_THREE_AGENT"] = "0"

# Platform-wide futures block (owner 2026-11-20) is ON in production by
# default (futures_policy: unset = blocked). Hundreds of pre-existing tests
# exercise the futures/short/leverage paths the block refuses, so the suite
# runs with it OFF; tests/test_futures_block.py turns it back on per test
# and separately asserts the production default by unsetting the variable.
os.environ["FUTURES_TRADING_BLOCKED"] = "0"

# Long exit policy (owner 2026-11-21) is ON in production by default
# (long_exit_policy: unset = on). Many pre-existing tests exercise the long
# rails it suspends (ratchet, max_loss, at_time, stop-loss fills), so the
# suite runs with it OFF; tests/test_long_exit_policy*.py turn it back on
# per test and assert the production default by unsetting the variable.
os.environ["LONG_EXIT_POLICY"] = "0"

# No test may reach a real LLM. config.py mirrors the developer's .env into
# os.environ, so without this a dev machine resolves a live provider and
# tests marked "deterministic" are decided by a model (2026-07-27, PR #120).
# Importing llm_client runs that mirror first; the blanking then wins, and the
# key list is derived from the provider registry so a new provider is covered.
import anthropic  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402

import llm_client  # noqa: E402

for _spec in llm_client._PROVIDERS.values():
    os.environ[_spec.key_env] = ""
    os.environ[_spec.base_url_env] = ""
for _aliases in llm_client._KEY_ALIASES.values():
    for _key in _aliases:
        os.environ[_key] = ""
for _key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_MODEL_BRIEF",
             "LLM_MODEL_DECISION", "LOCAL_LLM_MODEL"):
    os.environ[_key] = ""

# Keys are not the only road to a model: an admin-console tier set to `local`
# needs no key and defaults to http://localhost:11434, a live Ollama on a dev
# box. So the SDK clients themselves refuse in tests. Tests that exercise the
# client path patch openai.OpenAI / anthropic.Anthropic, which replaces this.
LIVE_LLM_CLIENTS: list[str] = []


class _LiveLlmClientBlocked:
    def __init__(self, *args, base_url=None, **kwargs):
        LIVE_LLM_CLIENTS.append(f"{type(self).__name__} base_url={base_url}")
        raise RuntimeError("a test constructed a live LLM client; stub generate_text "
                           "or patch openai.OpenAI / anthropic.Anthropic")


class OpenAIBlocked(_LiveLlmClientBlocked):
    pass


class AnthropicBlocked(_LiveLlmClientBlocked):
    pass


openai.OpenAI = OpenAIBlocked
anthropic.Anthropic = AnthropicBlocked


@pytest.fixture(autouse=True)
def _no_live_llm_client():
    LIVE_LLM_CLIENTS.clear()
    yield
    assert not LIVE_LLM_CLIENTS, (
        "This test reached a live LLM client (" + "; ".join(LIVE_LLM_CLIENTS) + "). "
        "generate_text swallows the failure and the test passes on a fallback, so "
        "stub generate_text or patch openai.OpenAI / anthropic.Anthropic explicitly.")
