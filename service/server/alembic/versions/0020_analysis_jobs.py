"""0020 — server-side analysis pipeline jobs.

An Analyst/Automation page run persists here (step events + final result) so
it survives the page being closed; the newest row per agent is "current"
(see analysis_jobs.py).

DDL mirrors init_database(). Indexed / timestamp columns use VARCHAR(N) —
matching migrations 0007–0019 — because MySQL cannot index or put a literal
default on a TEXT column; freeform content stays TEXT/MEDIUMTEXT.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-18
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS analysis_jobs (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id    INTEGER NOT NULL,
            symbol      VARCHAR(32) NOT NULL,
            market      VARCHAR(32) NOT NULL,
            lang        VARCHAR(8)  NOT NULL DEFAULT 'en',
            provider    VARCHAR(32),
            config_id   INTEGER,
            status      VARCHAR(16) NOT NULL DEFAULT 'running',
            events_json MEDIUMTEXT,
            result_json MEDIUMTEXT,
            gates_json  MEDIUMTEXT,
            error       TEXT,
            created_at  VARCHAR(64) NOT NULL,
            finished_at VARCHAR(64),
            INDEX idx_analysis_jobs_agent (agent_id, id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analysis_jobs")
