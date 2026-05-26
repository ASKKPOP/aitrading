"""Phase 5 — production auth: MFA + OAuth identities.

Adds:
  users.mfa_secret         — base32 TOTP secret (pyotp.random_base32())
  users.mfa_enabled        — 1 when user has completed MFA setup
  users.mfa_backup_codes   — JSON-array of one-time recovery codes
  oauth_identities table   — (provider, provider_user_id) → users.id

When MFA is enabled, /api/users/login returns a short-lived mfa_token
instead of a session; the client posts that + a TOTP code to
/api/auth/mfa/verify to complete the login.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
    op.execute("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN mfa_backup_codes TEXT")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS oauth_identities (
            id                INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            provider          VARCHAR(32) NOT NULL,
            provider_user_id  VARCHAR(255) NOT NULL,
            email             TEXT,
            created_at        VARCHAR(64) NOT NULL DEFAULT ({_NOW}),
            UNIQUE KEY uq_oauth_provider_id (provider, provider_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_identities_user
        ON oauth_identities(user_id, provider)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_identities")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_backup_codes")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret")
