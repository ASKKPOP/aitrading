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
