"""Trailing profit lock high-water mark (exit management, 2026-07-25).

trading_runs.peak_pnl_usd: NULL until a trail-configured run is first in
profit; ratcheted each control scan by run_engine._ratchet_peak_pnl and read
by the trailing lock (_trailing_lock_hit). SQLite mirror is the idempotent
ALTER in database.init_database().

IDEMPOTENT: prod received this column via a manual ALTER on 2026-07-25
(the inline database.py DDL does not run on MySQL), so the upgrade guards on
information_schema before adding — re-running is a no-op.

Revision ID: 0031
Revises: 0030
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("trading_runs")]
    if "peak_pnl_usd" not in cols:
        op.execute("ALTER TABLE trading_runs ADD COLUMN peak_pnl_usd DOUBLE NULL")


def downgrade():
    op.execute("ALTER TABLE trading_runs DROP COLUMN peak_pnl_usd")
