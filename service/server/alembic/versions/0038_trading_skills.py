"""Plan 20 — trading skills registry.

House decision-method packages injected into the desk's decision prompts
(light / trader / verifier / planner). Bodies live in the DB because the
repo's skills/ directory is excluded from the Docker image; base skills are
seeded insert-if-missing by trading_skills.py at first read, so this
migration only creates the empty table.
"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("trading_skills"):
        op.execute(
            """CREATE TABLE trading_skills (
                   id           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                   slug         VARCHAR(48) NOT NULL UNIQUE,
                   name         VARCHAR(120) NOT NULL,
                   description  TEXT NOT NULL,
                   body         TEXT NOT NULL,
                   prompts_json TEXT NOT NULL,
                   markets_json TEXT NULL,
                   priority     INT NOT NULL DEFAULT 100,
                   enabled      TINYINT NOT NULL DEFAULT 1,
                   is_base      TINYINT NOT NULL DEFAULT 0,
                   updated_by   VARCHAR(190) NULL,
                   created_at   VARCHAR(32) NOT NULL,
                   updated_at   VARCHAR(32) NOT NULL
               )"""
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS trading_skills")
