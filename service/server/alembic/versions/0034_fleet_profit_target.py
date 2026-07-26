"""Fleet take-profit goal + successor link (2026-07-26).

fleets.profit_target_frac: NULL = run until the user stops; a fraction of the
total budget at which the fleet banks everything and auto-starts a successor.
fleets.successor_fleet_id: the spawned successor (idempotency + chain audit).
SQLite mirror is the inline CREATE/ALTER in database.init_database().

Revision ID: 0034
Revises: 0033
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("fleets")]
    if "profit_target_frac" not in cols:
        op.execute("ALTER TABLE fleets ADD COLUMN profit_target_frac DOUBLE NULL")
    if "successor_fleet_id" not in cols:
        op.execute("ALTER TABLE fleets ADD COLUMN successor_fleet_id BIGINT NULL")


def downgrade():
    op.execute("ALTER TABLE fleets DROP COLUMN successor_fleet_id")
    op.execute("ALTER TABLE fleets DROP COLUMN profit_target_frac")
