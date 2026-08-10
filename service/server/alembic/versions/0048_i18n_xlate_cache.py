"""i18n_xlate_cache — the durable tier of the translation cache.

The AI-analysis panel (AI 분석, 30분 주기) localizes the desk's written report
through market_i18n's cached LLM translator. That cache had two tiers — an
in-process dict and a Redis KV that prod does not run — so a translation
warmed in one process was invisible to the other (the worker journals the
report, the backend serves the panel) and a backend restart wiped the lot:
every first view of a new report rendered English and only flipped if the
reader kept the drawer open past the next 60-second poll.

This table is the tier that crosses both boundaries. run_engine now warms the
run owner's language at journal-write time, the warm lands here, and the
backend's FIRST read of the cycle list comes back already localized.

`cache_key` is market_i18n._cache_key (mktxlate:{lang}:{sha16}); `created_at`
is epoch seconds, so TTL math needs no dialect-sensitive datetime parsing.
Rows expire on read and are pruned opportunistically on write (30 days).

Idempotent on purpose, like 0046: the table already exists on any SQLite
database that ran `init_database()`, and prod MySQL's schema is owned by
these migrations — both must be safe to run.
"""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "i18n_xlate_cache" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "i18n_xlate_cache",
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
    )
    op.create_index("ix_i18n_xlate_created", "i18n_xlate_cache", ["created_at"])


def downgrade():
    op.drop_table("i18n_xlate_cache")
