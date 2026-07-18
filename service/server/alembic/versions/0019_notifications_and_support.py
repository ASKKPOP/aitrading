"""0019 — member notification centre + member ⇄ administrator chat.

New tables: user_notifications (the in-app feed each member sees),
support_threads / support_messages (one support conversation per member,
with per-side unread counters).

Per-category notification switches need no table — they live in
user_api_settings under target 'notifications' (see notifications.py).

DDL mirrors init_database(). Indexed / unique / timestamp columns use
VARCHAR(N) — matching migrations 0007–0018 — because MySQL cannot index or
put a literal default on a TEXT column; freeform content stays TEXT.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-18
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_notifications (
            id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            category      VARCHAR(32) NOT NULL,
            title         VARCHAR(255) NOT NULL,
            body          MEDIUMTEXT,
            link          VARCHAR(255),
            channels_json MEDIUMTEXT,
            read_at       VARCHAR(64),
            created_at    VARCHAR(64) NOT NULL,
            INDEX idx_user_notifications_user (user_id, id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS support_threads (
            id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id         INTEGER NOT NULL UNIQUE,
            subject         VARCHAR(255),
            status          VARCHAR(32) NOT NULL DEFAULT 'open',
            user_unread     INTEGER NOT NULL DEFAULT 0,
            admin_unread    INTEGER NOT NULL DEFAULT 0,
            last_message_at VARCHAR(64),
            created_at      VARCHAR(64) NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            thread_id   INTEGER NOT NULL,
            sender      VARCHAR(16) NOT NULL,
            admin_id    INTEGER,
            admin_email VARCHAR(255),
            body        MEDIUMTEXT NOT NULL,
            created_at  VARCHAR(64) NOT NULL,
            INDEX idx_support_messages_thread (thread_id, id),
            FOREIGN KEY (thread_id) REFERENCES support_threads(id)
        )
    """)


def downgrade() -> None:
    for table in ("support_messages", "support_threads", "user_notifications"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
