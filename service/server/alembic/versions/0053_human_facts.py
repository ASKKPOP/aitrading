"""human_facts — Tier-4 crowd readings storage (Research 07 §9).

Owner direction 2026-08-24: one service collects human-factor facts
(telegram / youtube / discord / naver; tiktok registered-unavailable) as
numeric readings the Sooppiy AI can consume. Rows are keyed by
(source, scope, metric, bucket) so a collection re-run inside one interval
upserts instead of duplicating.

Idempotent-inspect first, same rationale as 0047/0049/0051/0052: SQLite
databases that ran init_database() already have the table; prod MySQL is
owned by these migrations.
"""
from alembic import op
import sqlalchemy as sa


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade():
    bind = op.get_bind()
    if _has_table(bind, "human_facts"):
        return
    op.create_table(
        "human_facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("bucket", sa.String(32), nullable=False),
        sa.Column("ts", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("meta", sa.Text(), nullable=True),
    )
    op.create_index("ix_human_facts_key", "human_facts",
                    ["source", "scope", "metric", "bucket"], unique=True)
    op.create_index("ix_human_facts_ts", "human_facts", ["ts"])


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "human_facts"):
        op.drop_table("human_facts")
