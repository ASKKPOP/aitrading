"""Sweep remaining REAL money/price/quantity columns to NUMERIC(20,8).

Completes the precision fix started in 0002 (agents.cash, positions.entry_price).
Columns that represent scores, percentages, or config ratios are left as REAL —
approximate arithmetic is acceptable there.

Tables changed:
  agents              — deposited
  listings            — price
  orders              — price
  signals             — entry_price, exit_price, quantity, pnl
  positions           — quantity, current_price
  polymarket_settlements — quantity, entry_price, settlement_price, proceeds
  challenges          — initial_capital
  challenge_participants — starting_cash, ending_value
  challenge_trades    — price, quantity
  profit_history      — total_value, cash, position_value, profit

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_NUMERIC = sa.Numeric(20, 8)
_FLOAT = sa.Float()


def upgrade() -> None:
    # agents
    op.alter_column("agents", "deposited",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=True,
                    existing_server_default=sa.text("0.0"))")

    # listings
    op.alter_column("listings", "price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")

    # orders
    op.alter_column("orders", "price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")

    # signals
    for col in ("entry_price", "exit_price", "quantity", "pnl"):
        op.alter_column("signals", col,
                        type_=_NUMERIC, existing_type=_FLOAT,
                        existing_nullable=True)")

    # positions
    op.alter_column("positions", "quantity",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")
    op.alter_column("positions", "current_price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=True)")

    # polymarket_settlements
    op.alter_column("polymarket_settlements", "quantity",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")
    op.alter_column("polymarket_settlements", "entry_price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")
    op.alter_column("polymarket_settlements", "settlement_price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")
    op.alter_column("polymarket_settlements", "proceeds",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")

    # challenges
    op.alter_column("challenges", "initial_capital",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=True,
                    existing_server_default=sa.text("100000.0"))")

    # challenge_participants
    op.alter_column("challenge_participants", "starting_cash",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=True,
                    existing_server_default=sa.text("100000.0"))")
    op.alter_column("challenge_participants", "ending_value",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=True)")

    # challenge_trades
    op.alter_column("challenge_trades", "price",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")
    op.alter_column("challenge_trades", "quantity",
                    type_=_NUMERIC, existing_type=_FLOAT,
                    existing_nullable=False)")

    # profit_history
    for col in ("total_value", "cash", "position_value", "profit"):
        op.alter_column("profit_history", col,
                        type_=_NUMERIC, existing_type=_FLOAT,
                        existing_nullable=False)")


def downgrade() -> None:
    # profit_history
    for col in ("profit", "position_value", "cash", "total_value"):
        op.alter_column("profit_history", col,
                        type_=_FLOAT, existing_type=_NUMERIC,
                        existing_nullable=False)

    # challenge_trades
    op.alter_column("challenge_trades", "quantity",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)
    op.alter_column("challenge_trades", "price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)

    # challenge_participants
    op.alter_column("challenge_participants", "ending_value",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=True)
    op.alter_column("challenge_participants", "starting_cash",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=True,
                    existing_server_default=sa.text("100000.0"))

    # challenges
    op.alter_column("challenges", "initial_capital",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=True,
                    existing_server_default=sa.text("100000.0"))

    # polymarket_settlements
    op.alter_column("polymarket_settlements", "proceeds",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)
    op.alter_column("polymarket_settlements", "settlement_price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)
    op.alter_column("polymarket_settlements", "entry_price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)
    op.alter_column("polymarket_settlements", "quantity",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)

    # positions
    op.alter_column("positions", "current_price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=True)
    op.alter_column("positions", "quantity",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)

    # signals
    for col in ("pnl", "quantity", "exit_price", "entry_price"):
        op.alter_column("signals", col,
                        type_=_FLOAT, existing_type=_NUMERIC,
                        existing_nullable=True)

    # orders
    op.alter_column("orders", "price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)

    # listings
    op.alter_column("listings", "price",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=False)

    # agents
    op.alter_column("agents", "deposited",
                    type_=_FLOAT, existing_type=_NUMERIC,
                    existing_nullable=True,
                    existing_server_default=sa.text("0.0"))
