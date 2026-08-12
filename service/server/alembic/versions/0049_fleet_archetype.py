"""fleets.archetype — Plan 23 Phase A: the swing slot archetype.

'short' (default) is today's intraday-crypto behavior, byte-for-byte; 'swing'
is the US-stock overnight-hold archetype (market_scope pinned ["us-stock"] at
create, 240-min desk cadence, later phases condition briefs/rails on it via
the run config snapshot). Default 'short' makes this migration inert for
every existing fleet.

Idempotent-inspect first, same rationale as 0047: SQLite databases that ran
init_database() already have the column; prod MySQL is owned by these
migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "fleets", "archetype"):
        op.add_column(
            "fleets",
            sa.Column("archetype", sa.String(length=16), nullable=False,
                      server_default="short"),
        )


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "fleets", "archetype"):
        op.drop_column("fleets", "archetype")
