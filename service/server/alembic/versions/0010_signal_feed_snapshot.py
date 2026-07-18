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
        # message_type + market are part of the PK / index → VARCHAR (MySQL can't key TEXT).
        sa.Column("message_type", sa.String(191), nullable=False),
        sa.Column("market", sa.String(191), nullable=False, server_default=""),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("agent_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("signal_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("position_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("position_count", sa.Integer, nullable=False, server_default="0"),
        # Long JSON stays TEXT; MySQL literal TEXT defaults are illegal, so use the
        # parenthesised expression-default form (valid on MySQL 8.0.13+).
        sa.Column("positions_json", sa.Text(16777215), nullable=False, server_default=sa.text("('[]')")),
        sa.Column("last_signal_at", sa.Text(16777215), nullable=True),
        sa.Column("latest_signal_id", sa.Integer, nullable=True),
        sa.Column("latest_signal_type", sa.Text(16777215), nullable=True),
        sa.Column("total_for_filter", sa.Integer, nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.Text(16777215), nullable=False),
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
