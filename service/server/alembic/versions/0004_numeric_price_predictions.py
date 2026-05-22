"""Convert remaining monetary/price REAL columns to NUMERIC(20,8).

Finishes the precision sweep started in 0002 and 0003.

  signal_predictions.target_price          — price target (monetary)
  stock_analysis_snapshots.current_price   — snapshot of actual market price

Score, percentage, probability, and config-ratio columns are intentionally
left as REAL throughout the schema — approximate arithmetic is fine there.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_NUMERIC = sa.Numeric(20, 8)
_FLOAT = sa.Float()


def upgrade() -> None:
    op.alter_column(
        "signal_predictions",
        "target_price",
        type_=_NUMERIC,
        existing_type=_FLOAT,
        existing_nullable=True)",
    )
    op.alter_column(
        "stock_analysis_snapshots",
        "current_price",
        type_=_NUMERIC,
        existing_type=_FLOAT,
        existing_nullable=False)",
    )


def downgrade() -> None:
    op.alter_column(
        "stock_analysis_snapshots",
        "current_price",
        type_=_FLOAT,
        existing_type=_NUMERIC,
        existing_nullable=False)
    op.alter_column(
        "signal_predictions",
        "target_price",
        type_=_FLOAT,
        existing_type=_NUMERIC,
        existing_nullable=True)
