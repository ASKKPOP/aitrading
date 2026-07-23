"""Fleet-level leverage override.

fleets.leverage: NULL ⇒ auto leverage by risk tier (fleet_planner
FLEET_BOUNDS['auto_leverage']); a number (1–10) overrides it for every run
the fleet builds. SQLite mirror is the idempotent ALTER in
database.init_database().

Revision ID: 0030
Revises: 0029
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE fleets ADD COLUMN leverage DECIMAL(10,4) NULL")


def downgrade():
    op.execute("ALTER TABLE fleets DROP COLUMN leverage")
