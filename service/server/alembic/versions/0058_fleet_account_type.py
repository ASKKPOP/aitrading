"""fleets.account_type — Real-mode (live) Full Auto fleets.

'simulator' (default, every existing fleet) or 'live': each run the fleet
builds carries it in its config snapshot, and automation.execute_paper_trade
sends a live run's orders to the user's trading gateway before booking them.
SQLite mirror is the idempotent ALTER in database.init_database().

Revision ID: 0058
Revises: 0057
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("fleets")}
    if "account_type" not in cols:
        op.execute("ALTER TABLE fleets ADD COLUMN account_type "
                   "VARCHAR(16) NOT NULL DEFAULT 'simulator'")


def downgrade():
    op.execute("ALTER TABLE fleets DROP COLUMN account_type")
