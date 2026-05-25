"""Phase 4.4 — materialized leaderboard snapshot table.

A worker (refresh_leaderboard_snapshot_loop in tasks.py) rebuilds this
table every 30s by running the heavy aggregate query once and writing
the result. The /api/profit/history endpoint reads `WHERE metric=?
ORDER BY rank LIMIT ? OFFSET ?` — O(limit) instead of O(all agents).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-25
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS leaderboard_snapshot (
            metric                  VARCHAR(32) NOT NULL,
            `rank`                  INTEGER NOT NULL,
            agent_id                INTEGER NOT NULL,
            name                    TEXT    NOT NULL,
            deposited               NUMERIC(20,8) DEFAULT 0,
            profit                  NUMERIC(20,8) DEFAULT 0,
            profit_percent          NUMERIC(20,8) DEFAULT 0,
            trade_count             INTEGER DEFAULT 0,
            risk_adjusted_score     NUMERIC(20,8) DEFAULT 0,
            collaboration_score     NUMERIC(20,8) DEFAULT 0,
            quality_score_avg       NUMERIC(20,8) DEFAULT 0,
            max_drawdown            NUMERIC(20,8) DEFAULT 0,
            reply_count             INTEGER DEFAULT 0,
            accepted_reply_count    INTEGER DEFAULT 0,
            citation_count          INTEGER DEFAULT 0,
            adoption_count          INTEGER DEFAULT 0,
            metric_snapshot_id      INTEGER,
            metric_window_key       VARCHAR(64),
            metric_window_start_at  VARCHAR(64),
            metric_window_end_at    VARCHAR(64),
            recorded_at             VARCHAR(64),
            refreshed_at            VARCHAR(64) NOT NULL DEFAULT ({_NOW}),
            PRIMARY KEY (metric, `rank`)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leaderboard_snapshot_metric_rank
        ON leaderboard_snapshot(metric, `rank`)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leaderboard_snapshot")
