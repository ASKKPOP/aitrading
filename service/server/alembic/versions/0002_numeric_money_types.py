"""Change agents.cash and positions.entry_price from REAL to NUMERIC(20,8).

REAL (float) loses precision on repeated arithmetic. NUMERIC stores exact
decimal values, which matters for cash balances and trade entry prices.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agents",
        "cash",
        type_=sa.Numeric(20, 8),
        existing_type=sa.Float(),
        existing_nullable=True,
        existing_server_default=sa.text("100000.0"))",
    )
    op.alter_column(
        "positions",
        "entry_price",
        type_=sa.Numeric(20, 8),
        existing_type=sa.Float(),
        existing_nullable=False)",
    )


def downgrade() -> None:
    op.alter_column(
        "positions",
        "entry_price",
        type_=sa.Float(),
        existing_type=sa.Numeric(20, 8),
        existing_nullable=False)
    op.alter_column(
        "agents",
        "cash",
        type_=sa.Float(),
        existing_type=sa.Numeric(20, 8),
        existing_nullable=True,
        existing_server_default=sa.text("100000.0"))
