"""0025 — social_posts + social_snapshots (Plan 11 F5).

Raw collected posts (Facebook for SEA, X elsewhere) and the derived per-symbol
sentiment snapshots. Raw rows are pruned to SOCIAL_RAW_RETENTION_DAYS (default
7) by the collector at the end of each cycle; snapshots are small and survive
that window so sentiment history outlives the raw data.

unique(platform, post_id) makes re-collection idempotent — every 30-minute
cycle overlaps the previous one's window.

DDL mirrors init_database(). created_at is VARCHAR ISO-8601 (MySQL cannot
index TEXT).

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-19
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            platform        VARCHAR(16)  NOT NULL,
            region          VARCHAR(16)  NOT NULL,
            topic           VARCHAR(32)  NOT NULL,
            post_id         VARCHAR(128) NOT NULL,
            author          VARCHAR(128) NULL,
            text            MEDIUMTEXT   NULL,
            engagement_json MEDIUMTEXT   NULL,
            posted_at       VARCHAR(40)  NULL,
            created_at      VARCHAR(32)  NOT NULL,
            UNIQUE KEY uq_social_posts_platform_post (platform, post_id),
            INDEX idx_social_posts_topic_created (topic, created_at),
            INDEX idx_social_posts_created (created_at)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_snapshots (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            snapshot_key VARCHAR(64) NOT NULL,
            summary_json MEDIUMTEXT  NULL,
            created_at   VARCHAR(32) NOT NULL,
            INDEX idx_social_snapshots_key_created (snapshot_key, created_at)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_snapshots")
    op.execute("DROP TABLE IF EXISTS social_posts")
