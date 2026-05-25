"""Phase 4.3 — agent memory layer.

Adds the agent_memory table for per-agent persistent storage with
optional vector embeddings. Embeddings stored as JSON-stringified
float arrays (TEXT in SQLite, JSON in MySQL). Cosine similarity is
computed in Python at query time — brute force within the 10MB
per-agent quota.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-25
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id    INTEGER NOT NULL REFERENCES agents(id),
            content     TEXT    NOT NULL,
            embedding   LONGTEXT,
            metadata    TEXT,
            created_at  VARCHAR(64) NOT NULL DEFAULT ({_NOW}),
            expires_at  VARCHAR(64),
            size_bytes  INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_memory_agent_created
        ON agent_memory(agent_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_memory")
