"""agents.starting_capital — the capital each agent actually began with.

Profit was measured against a module-level constant (100,000) shared by the
profile endpoint, the leaderboard, the profit-history writer and team matching.
Any agent seeded with a different balance therefore reported a collapse it
never took: cash 1,000 read as -99% on zero trades. The seed now lives on the
row, so profit is measured against the agent's own starting point.

Backfill is the same 100,000 default, which is in fact what every existing
agent was seeded with, so no live figure moves on upgrade.
"""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    agent_cols = [c["name"] for c in sa.inspect(bind).get_columns("agents")]
    if "starting_capital" not in agent_cols:
        op.execute(
            "ALTER TABLE agents ADD COLUMN starting_capital "
            "NUMERIC(20,8) NOT NULL DEFAULT 100000.0"
        )
    # Rows that predate the column take the default; make it explicit so a
    # NULL can never reach the division in profit_percent_for_display.
    op.execute("UPDATE agents SET starting_capital = 100000.0 WHERE starting_capital IS NULL")


def downgrade():
    op.execute("ALTER TABLE agents DROP COLUMN starting_capital")
