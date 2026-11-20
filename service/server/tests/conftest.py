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
