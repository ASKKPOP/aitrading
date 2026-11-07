"""positions.handoff_run_id + trend_events — loss analysis 2026-11-06 §5 #4/#5.

#4  `handoff_run_id`: the run that released this position on its terminal
    (`positions_held`). Three positions on the 10-05→11-06 tape sat 39–75 h
    after a `stop_eval_failed` stop with the reclaim sweep running every
    15 minutes: they wore a stop (not bare) and refused no fleet slot (not
    blocking), so the sweep held them on every pass. The stamp lets the
    sweep read the desk on them at once and journal on the run's tape.

#5  `trend_events`: the trend module has no trading run, so its closes by
    the SL/TP watcher had no row anywhere (−$51.31 on 10-08, zero
    telemetry). One row per module event and per watcher close of a module
    position.

Idempotent-inspect first, same rationale as 0047/0049/0051/0052/0053/0054:
SQLite databases that ran init_database() already have both; prod MySQL is
owned by these migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "positions", "handoff_run_id"):
        op.add_column("positions", sa.Column("handoff_run_id", sa.Integer(),
                                             nullable=True))
    if not _has_table(bind, "trend_events"):
        op.create_table(
            "trend_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("ts", sa.String(32), nullable=False),
            sa.Column("event_type", sa.String(48), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
        )
        op.create_index("ix_trend_events_agent_ts", "trend_events",
                        ["agent_id", "ts"])


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "trend_events"):
        op.drop_table("trend_events")
    if _has_column(bind, "positions", "handoff_run_id"):
        op.drop_column("positions", "handoff_run_id")
