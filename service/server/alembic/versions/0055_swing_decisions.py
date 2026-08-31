"""swing_decisions — persisted output of the live swing signal stack.

swing_pipeline.py writes one row per symbol per pass: the five processor
scores, the composite, the two-axis state, and the decision the risk gate
allowed. A NULL score means that feed had no coverage on the pass (its weight
renormalized away) — deliberately distinct from a 0.0 neutral reading.

Idempotent-inspect first, same rationale as 0047/0049/0051..0054.
"""
from alembic import op
import sqlalchemy as sa


revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade():
    bind = op.get_bind()
    if _has_table(bind, "swing_decisions"):
        return
    op.create_table(
        "swing_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("market", sa.String(24), nullable=True),
        sa.Column("computed_at", sa.String(32), nullable=False),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("macro", sa.Float(), nullable=True),
        sa.Column("thesis", sa.Float(), nullable=True),
        sa.Column("smart_money", sa.Float(), nullable=True),
        sa.Column("technical", sa.Float(), nullable=True),
        sa.Column("composite", sa.Float(), nullable=True),
        sa.Column("axis", sa.String(32), nullable=True),
        sa.Column("action", sa.String(8), nullable=True),
        sa.Column("veto", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("coverage", sa.Integer(), nullable=True),
        sa.Column("hours_to_event", sa.Float(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_swing_decisions_symbol", "swing_decisions", ["symbol", "id"])
    op.create_index("ix_swing_decisions_computed", "swing_decisions", ["computed_at"])


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "swing_decisions"):
        op.drop_table("swing_decisions")
