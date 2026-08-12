"""us_stock_factor_snapshots — Plan 23 Phase D.

US-equity positioning history for the v2 crowd-fade, self-accrued
live-forward (no vendor sells it — the same rationale as the crypto
factor_snapshots table). short_volume_ratio ships NULL until the FINRA
daily short-volume fetcher lands, so history is never re-keyed later.

Idempotent-inspect first, same as 0047/0049.
"""
from alembic import op
import sqlalchemy as sa


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "us_stock_factor_snapshots" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "us_stock_factor_snapshots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("putcall_oi_ratio", sa.Float, nullable=True),
            sa.Column("short_volume_ratio", sa.Float, nullable=True),
            sa.Column("stocktwits_tilt", sa.Float, nullable=True),
            sa.Column("tilt_n", sa.Integer, nullable=True),
            sa.Column("created_at", sa.String(length=32), nullable=False),
        )


def downgrade():
    bind = op.get_bind()
    if "us_stock_factor_snapshots" in sa.inspect(bind).get_table_names():
        op.drop_table("us_stock_factor_snapshots")
