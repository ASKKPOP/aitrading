"""swing_decisions.sentiment_shadow — the per-symbol sentiment blend, measured.

The stack's sentiment processor is MARKET-level (a Fear & Greed gauge), so
every symbol scores identically on a day. swing_stack.blended_sentiment_score
folds in per-symbol news/social readings, but that blend has no vendor history
to backtest against — market_news_snapshots and social_snapshots are
retention-pruned local tables. The only honest evidence is live-forward
disagreement, so both values are recorded per decision (SWING_SENTIMENT_BLEND
= shadow) and the blend is promoted to `live` only on that evidence.

Same live-forward rationale as factor_snapshots.
"""
from alembic import op
import sqlalchemy as sa


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "swing_decisions", "sentiment_shadow"):
        op.add_column("swing_decisions",
                      sa.Column("sentiment_shadow", sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "swing_decisions", "sentiment_shadow"):
        op.drop_column("swing_decisions", "sentiment_shadow")
