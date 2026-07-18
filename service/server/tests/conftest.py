"""Shared test configuration.

The test suite validates *production* behaviour, so force all dev-only conveniences
off regardless of what the container's ``.env`` sets. These flags are read at request
time (via ``os.getenv``), so setting them here — before any TestClient is created —
takes effect for every test.
"""
import os

os.environ["DEV_LOGIN_ANY_PASSWORD"] = "false"
os.environ["DEV_MARKET_INTEL_SEED"] = "false"
os.environ["ALLOW_SYNC_PRICE_FETCH_IN_API"] = "false"

# Signal-collection phase flags default off in tests regardless of the local
# .env — a developer's enabled flags must not make tests hit live OKX/StockTwits.
os.environ["RISK_ENGINE_ENABLED"] = "false"
os.environ["PSYCH_FEED_ENABLED"] = "false"
os.environ["QUANT_CRYPTO_ENABLED"] = "false"
os.environ["SCANNER_ENABLED"] = "false"

# Notification-delivery tests exercise alerts/notifications with external=True;
# blank the provider credentials so no machine's .env can make a test send a
# real SendGrid email or Twilio SMS.
for _key in ("SENDGRID_API_KEY", "ALERT_FROM_EMAIL",
             "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"):
    os.environ[_key] = ""
