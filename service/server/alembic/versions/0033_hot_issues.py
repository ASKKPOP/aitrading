"""Hot-issue daemon journal (E2, 2026-07-25).

hot_issues: one row per detected issue per (market, symbol); read by the
per-symbol cooldown and by the E1 situation classifier (recent_hot_issue)
to escalate affected runs' next cycle to the full analyst pipeline.
SQLite mirror is the CREATE in database.init_database().

Revision ID: 0033
Revises: 0032
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE TABLE IF NOT EXISTS hot_issues (
               id            BIGINT AUTO_INCREMENT PRIMARY KEY,
               market        VARCHAR(32)  NOT NULL,
               symbol        VARCHAR(64)  NOT NULL,
               triggers_json TEXT         NOT NULL,
               severity      VARCHAR(16)  NOT NULL DEFAULT 'medium',
               created_at    VARCHAR(32)  NOT NULL,
               INDEX idx_hot_issues_tuple (market, symbol, created_at)
           )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS hot_issues")
