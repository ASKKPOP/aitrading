"""crawl_runs — per-pass bookkeeping for the swing-stack collectors.

One row per collector pass (crawl_monitor.track): ok / duration / items /
error. The admin console's existing feed probes only test whether an upstream
URL answers right now; these rows record what OUR crawlers actually did, so a
collector that quietly stopped producing is visible instead of silent.

Idempotent-inspect first, same rationale as 0047/0049/0051/0052/0053: SQLite
databases that ran init_database() already have the table; prod MySQL is
owned by these migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade():
    bind = op.get_bind()
    if _has_table(bind, "crawl_runs"):
        return
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feed", sa.String(48), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("finished_at", sa.String(32), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Integer(), nullable=False),
        sa.Column("items", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_crawl_runs_feed_started", "crawl_runs", ["feed", "started_at"])
    op.create_index("ix_crawl_runs_started", "crawl_runs", ["started_at"])


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "crawl_runs"):
        op.drop_table("crawl_runs")
