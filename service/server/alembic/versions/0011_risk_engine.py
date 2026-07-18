"""0011 — risk engine (Phase 1): risk_limits, breaker_state, positions SL/TP."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_limits",
        sa.Column("agent_id", sa.Integer, primary_key=True),
        sa.Column("max_daily_loss_usd", sa.Float, nullable=False, server_default="1000"),
        sa.Column("max_symbol_exposure_usd", sa.Float, nullable=False, server_default="10000"),
        sa.Column("stop_loss_pct", sa.Float, nullable=False, server_default="0.05"),
        sa.Column("take_profit_pct", sa.Float, nullable=False, server_default="0.10"),
        sa.Column("use_kelly", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.Text, nullable=True),
    )
    op.create_table(
        "breaker_state",
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("tripped_at", sa.Text, nullable=True),
        sa.Column("updated_at", sa.Text, nullable=True),
    )
    op.add_column("positions", sa.Column("stop_loss", sa.Float, nullable=True))
    op.add_column("positions", sa.Column("take_profit", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "take_profit")
    op.drop_column("positions", "stop_loss")
    op.drop_table("breaker_state")
    op.drop_table("risk_limits")
