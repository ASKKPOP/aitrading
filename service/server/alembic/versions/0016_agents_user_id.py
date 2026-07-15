"""0016 — agents.user_id: link auto-provisioned agents to human user accounts."""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("user_id", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "user_id")
