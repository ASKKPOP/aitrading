"""0015 — leaderboard exclusions table referenced by profit-history recording.

tasks.py has queried agent_leaderboard_exclusions since the leaderboard
opt-out feature landed, but the table was never created anywhere — every
profit-history tick failed with 'no such table'. This creates it.
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_leaderboard_exclusions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id"), nullable=False, unique=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("active", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_leaderboard_exclusions")
