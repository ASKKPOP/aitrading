"""0026 — platform_settings key/value store.

Operator-editable configuration that must change without a deploy. First
tenant: the USDT receiving address and network, which the manager console
edits directly — an address that can only be rotated by editing .env and
restarting is an address nobody rotates.

DDL mirrors init_database(). Values are plain text; nothing secret belongs
here (a receiving address is public by nature — secrets stay in .env).

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-20
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            setting_key   VARCHAR(64)  NOT NULL PRIMARY KEY,
            setting_value TEXT         NULL,
            updated_by    VARCHAR(255) NULL,
            updated_at    VARCHAR(32)  NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_settings")
