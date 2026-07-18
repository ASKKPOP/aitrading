"""0013 — which-coin scanner snapshots (Phase 4)."""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanner_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_key", sa.Text(16777215), nullable=False),
        sa.Column("candidates_json", sa.Text(16777215), nullable=True),
        sa.Column("mentions_json", sa.Text(16777215), nullable=True),
        sa.Column("instruments_json", sa.Text(16777215), nullable=True),
        sa.Column("created_at", sa.String(64), nullable=False),
    )
    op.create_index("idx_scanner_snapshots_created", "scanner_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_scanner_snapshots_created", table_name="scanner_snapshots")
    op.drop_table("scanner_snapshots")
