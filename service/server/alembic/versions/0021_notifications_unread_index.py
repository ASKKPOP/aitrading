"""0021 — index for the per-member unread-notification count.

Every logged-in member polls /api/notifications/summary (COUNT(*) WHERE
user_id = ? AND read_at IS NULL) on a 60s cadence; the feed has no
retention, so without (user_id, read_at) the count degrades into an
ever-growing row scan. Mirrors init_database().

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-18
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX idx_user_notifications_unread
        ON user_notifications (user_id, read_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX idx_user_notifications_unread ON user_notifications")
