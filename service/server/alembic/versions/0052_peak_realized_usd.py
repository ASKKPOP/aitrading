"""trading_runs.peak_realized_usd — realized P&L at the peak epoch (R21).

Measured live 2026-08-18 (run 1417, two-agent cross-checked): the breakeven
ratchet's position-scoped baseline used CURRENT realized, so every partial
cover booked at a loss inflated the phantom peak by the loss it realized —
1417's true position excursion peaked at +$0.1015, under its $0.2549 arm,
yet the rail armed on a manufactured 0.4614 and flattened the remainder 9
seconds after the desk's own reduce. The baseline must be the realized value
AT THE MOMENT the peak was stamped, so it is now stored beside the peak.

Idempotent-inspect first, same rationale as 0047/0049/0051: SQLite databases
that ran init_database() already have the column; prod MySQL is owned by
these migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "trading_runs", "peak_realized_usd"):
        op.add_column("trading_runs", sa.Column("peak_realized_usd", sa.Float(),
                                                nullable=True))


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "trading_runs", "peak_realized_usd"):
        op.drop_column("trading_runs", "peak_realized_usd")
