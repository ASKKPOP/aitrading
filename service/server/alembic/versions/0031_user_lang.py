"""Per-user notification language.

Adds users.lang (default 'en'). This is the durable source both request-time
and background senders read to localize email/SMS. SQLite mirror is the
idempotent ALTER in database.init_database().

Revision ID: 0031
Revises: 0030
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN lang VARCHAR(8) NOT NULL DEFAULT 'en'")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN lang")
