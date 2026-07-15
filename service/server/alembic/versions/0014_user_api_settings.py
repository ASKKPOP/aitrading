"""0014 — per-user API target configuration (settings page)."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_api_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("api_key", sa.Text, nullable=True),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("enabled", sa.Integer, server_default="1"),
        sa.Column("updated_at", sa.Text, nullable=True),
        sa.UniqueConstraint("user_id", "target", name="uq_user_api_settings"),
    )


def downgrade() -> None:
    op.drop_table("user_api_settings")
