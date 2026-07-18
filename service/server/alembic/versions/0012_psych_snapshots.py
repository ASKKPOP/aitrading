"""0012 — psychology feed snapshots (Phase 2): F&G, spikes, shock proxy, odds."""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "psych_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_key", sa.Text, nullable=False),
        sa.Column("fng_json", sa.Text, nullable=True),
        sa.Column("spikes_json", sa.Text, nullable=True),
        sa.Column("shock_json", sa.Text, nullable=True),
        sa.Column("anticipation_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("idx_psych_snapshots_created", "psych_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_psych_snapshots_created", table_name="psych_snapshots")
    op.drop_table("psych_snapshots")
