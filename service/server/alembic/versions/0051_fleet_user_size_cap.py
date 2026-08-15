"""fleets.user_size_cap — a user resize pins the size against auto-tune.

Owner decision 2026-08-15, from live evidence on fleet 34: the user resized
25 → 10 at 03:21:42Z and `auto_tune_slots` raised it straight back to 25 at
03:49:14Z — the second override of an explicit user size in one day, and the
nine runs it then built sat in slots the user had just deleted.
`recommended_max_slots(budget)` knows the budget, not the intent.

A size set through the resize API is now a CAP: auto-tune may still LOWER
below it (the fee-viability shrink is safety) but never raise above it, until
the user resizes again. NULL = never user-resized = the old behaviour,
byte-for-byte, for every existing fleet.

Idempotent-inspect first, same rationale as 0047/0049: SQLite databases that
ran init_database() already have the column; prod MySQL is owned by these
migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "fleets", "user_size_cap"):
        op.add_column("fleets", sa.Column("user_size_cap", sa.Integer(),
                                          nullable=True))


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "fleets", "user_size_cap"):
        op.drop_column("fleets", "user_size_cap")
