"""Isolated-margin leverage per position.

Adds positions.leverage (default 1 = the prior fully-funded behavior). The
margin cash model + liquidation-from-leverage live in automation.py /
run_engine.py; this column stores the per-position leverage those paths read.
SQLite mirror is the idempotent ALTER in database.init_database().

Revision ID: 0029
Revises: 0028
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: skip if a prior boot's SQLite-style ALTER already ran.
    op.execute(
        "ALTER TABLE positions "
        "ADD COLUMN leverage DECIMAL(10,4) NOT NULL DEFAULT 1"
    )


def downgrade():
    op.execute("ALTER TABLE positions DROP COLUMN leverage")
