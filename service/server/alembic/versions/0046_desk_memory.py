"""desk_memory — the durable corpus of what has been learned about this desk.

Two kinds of knowledge were being lost:

1. **Monitoring analysis.** The operating model rotates the Claude account every
   ~3 days, so every finding, trap and verdict had to be re-derived unless it
   was written to repo markdown — and even that was only partly true: the
   handoff, the snapshot and six days of cycle notes had never been committed
   to main at all (fixed 2026-08-06).
2. **The desk's own reasoning.** `run_events` holds the decisions, but a
   decision and the outcome it produced are separate rows minutes-to-days
   apart, joined by nothing that says "this is what happened because of that".

This table holds both, as retrievable chunks, so a future session (or the desk
itself) can ask what was already learned instead of rediscovering it.

Deliberately dialect-neutral: no FTS5, no FULLTEXT. The corpus is small
(hundreds to low thousands of chunks) and scoring happens in Python, which
behaves identically on SQLite and MySQL. `sha` makes re-ingest idempotent.
"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "desk_memory" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "desk_memory",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # 'monitoring' (a human/agent finding) | 'decision' (what the desk
        # decided and why) | 'outcome' (what that decision produced)
        sa.Column("kind", sa.String(24), nullable=False),
        # Where it came from, and the dedupe identity together with sha:
        # 'docs/reports/2026-08-06-automation-monitoring.md#Losses' or
        # 'run:980:cycle:3'.
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("ts", sa.String(32), nullable=False),
        sa.Column("run_id", sa.Integer, nullable=True),
        sa.Column("symbol", sa.String(32), nullable=True),
        sa.Column("market", sa.String(32), nullable=True),
        # JSON list of situation tags, stored as TEXT for dialect neutrality
        # (the codebase already uses *_json TEXT columns for this).
        sa.Column("tags_json", sa.Text, nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
    )
    op.create_index("ix_desk_memory_sha", "desk_memory", ["sha"], unique=True)
    op.create_index("ix_desk_memory_kind_ts", "desk_memory", ["kind", "ts"])
    op.create_index("ix_desk_memory_run", "desk_memory", ["run_id"])


def downgrade():
    op.drop_table("desk_memory")
