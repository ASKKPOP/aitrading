"""0010 — signal_feed_snapshot materialized view table."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_feed_snapshot",
        sa.Column("message_type", sa.Text, nullable=False),
        sa.Column("market", sa.Text, nullable=False, server_default=""),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("agent_name", sa.Text, nullable=False, server_default=""),
        sa.Column("signal_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("position_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("position_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("positions_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("last_signal_at", sa.Text, nullable=True),
        sa.Column("latest_signal_id", sa.Integer, nullable=True),
        sa.Column("latest_signal_type", sa.Text, nullable=True),
        sa.Column("total_for_filter", sa.Integer, nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("message_type", "market", "rank"),
    )
    op.create_index(
        "idx_signal_feed_snapshot_combo_rank",
        "signal_feed_snapshot",
        ["message_type", "market", "rank"],
    )


def downgrade() -> None:
    op.drop_index("idx_signal_feed_snapshot_combo_rank", table_name="signal_feed_snapshot")
    op.drop_table("signal_feed_snapshot")
