"""0024 — llm_usage metering table (Plan 11 F2).

One row per generate_text call: identity (user/agent from the LlmContext),
provider/model/tier, token counts from the SDK usage objects, and an estimated
USD cost from llm_usage.py's static price table. The Settings page reads
monthly aggregates per user; system-wide totals are owner-only
(DOCS_OWNER_EMAILS).

DDL mirrors init_database(). created_at is VARCHAR ISO-8601 like the other
metering tables (MySQL cannot index TEXT).

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-19
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id                INT AUTO_INCREMENT PRIMARY KEY,
            user_id           INT NULL,
            agent_id          INT NULL,
            provider          VARCHAR(32)  NOT NULL,
            model             VARCHAR(128) NOT NULL,
            tier              VARCHAR(16)  NOT NULL,
            key_source        VARCHAR(16)  NOT NULL DEFAULT 'system',
            prompt_tokens     INT NOT NULL DEFAULT 0,
            completion_tokens INT NOT NULL DEFAULT 0,
            cost_usd          DOUBLE NOT NULL DEFAULT 0,
            created_at        VARCHAR(32) NOT NULL,
            INDEX idx_llm_usage_user_created (user_id, created_at),
            INDEX idx_llm_usage_created (created_at)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_usage")
