"""
Configuration module.

All environment variables are loaded once at startup via pydantic-settings.
The module-level constants below are backward-compatible with the previous
os.getenv()-based config — no other files need to change.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings.  Loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Database ----
    database_url: str = ""
    db_path: str = ""

    # ---- Redis ----
    redis_enabled: bool = False
    redis_url: SecretStr = SecretStr("")
    redis_prefix: str = "ai_trader"

    # ---- API Keys ----
    alpha_vantage_api_key: SecretStr = SecretStr("demo")

    # ---- Market endpoints ----
    hyperliquid_api_url: str = "https://api.hyperliquid.xyz/info"

    # ---- Email ----
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = "noreply@sooppiy.com"

    # ---- Broker execution layer ----
    # Alpaca
    alpaca_key:    SecretStr = SecretStr("")
    alpaca_secret: SecretStr = SecretStr("")
    alpaca_paper:  bool      = True   # True → paper sandbox; False → live

    # Binance
    binance_key:     SecretStr = SecretStr("")
    binance_secret:  SecretStr = SecretStr("")
    binance_testnet: bool      = True  # True → testnet; False → live

    # Credential encryption (AES-GCM).  Generate with:
    #   python -c "from execution.crypto import generate_key_b64; print(generate_key_b64())"
    execution_encryption_key: SecretStr = SecretStr("")

    # ---- CORS ----
    sooppiy_cors_origins: str = ""

    # ---- Runtime ----
    environment: str = "development"

    @field_validator("redis_prefix", mode="before")
    @classmethod
    def _nonempty_redis_prefix(cls, v: object) -> str:
        return (str(v).strip() or "ai_trader")


# Singleton — created once at import time.
settings = Settings()

# ── Backward-compatible module-level exports ───────────────────────────────────
# Other modules import these names directly; keep them to avoid a wide diff.

DATABASE_URL: str = settings.database_url
DB_PATH: str = settings.db_path  # empty → database.py falls back to its local default

REDIS_ENABLED: bool = settings.redis_enabled
REDIS_URL: str = settings.redis_url.get_secret_value()
REDIS_PREFIX: str = settings.redis_prefix

ALPHA_VANTAGE_API_KEY: str = settings.alpha_vantage_api_key.get_secret_value()

HYPERLIQUID_API_URL: str = settings.hyperliquid_api_url

CORS_ORIGINS: list[str] = (
    [o.strip() for o in settings.sooppiy_cors_origins.split(",") if o.strip()]
    if settings.sooppiy_cors_origins
    else ["http://localhost:3000"]
)

ENVIRONMENT: str = settings.environment

# ── Broker execution ──────────────────────────────────────────────────────────
ALPACA_KEY:    str  = settings.alpaca_key.get_secret_value()
ALPACA_SECRET: str  = settings.alpaca_secret.get_secret_value()
ALPACA_PAPER:  bool = settings.alpaca_paper

BINANCE_KEY:     str  = settings.binance_key.get_secret_value()
BINANCE_SECRET:  str  = settings.binance_secret.get_secret_value()
BINANCE_TESTNET: bool = settings.binance_testnet

EXECUTION_ENCRYPTION_KEY: str = settings.execution_encryption_key.get_secret_value()

# Reward constants — not env-driven, kept here for co-location.
SIGNAL_PUBLISH_REWARD = 10
SIGNAL_ADOPT_REWARD = 1
DISCUSSION_PUBLISH_REWARD = 4
REPLY_PUBLISH_REWARD = 2
