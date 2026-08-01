"""resting_orders.leverage — futures limit orders carry the slider leverage.

The fill threads it to execute_paper_trade (margin = notional/L + fee at the
observed price); closes keep returning escrow at the POSITION's leverage.
DEFAULT 1 = the legacy fully-funded fill, so every existing row (and the spot
terminal, which never sends leverage) is unchanged. SQLite mirror is the
idempotent ALTER in database.init_database().

Revision ID: 0039
Revises: 0038
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("resting_orders")]
    if "leverage" not in cols:
        op.execute(
            "ALTER TABLE resting_orders "
            "ADD COLUMN leverage DOUBLE NOT NULL DEFAULT 1")


def downgrade():
    op.execute("ALTER TABLE resting_orders DROP COLUMN leverage")
