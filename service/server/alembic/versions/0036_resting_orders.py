"""resting_orders — GTC limit orders for the spot/futures terminals.

One row per order; the worker's resting_orders tick fills crossed rows through
the paper executor (simulator only — never the live gateway). MySQL mirror of
the CREATE TABLE in database.init_database.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "resting_orders" not in sa.inspect(bind).get_table_names():
        op.execute("""
            CREATE TABLE resting_orders (
                id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                agent_id     INTEGER NOT NULL,
                market       VARCHAR(32) NOT NULL,
                symbol       VARCHAR(32) NOT NULL,
                side         VARCHAR(8) NOT NULL,
                quantity     DOUBLE NOT NULL,
                limit_price  DOUBLE NOT NULL,
                stop_loss    DOUBLE NULL,
                take_profit  DOUBLE NULL,
                status       VARCHAR(16) NOT NULL DEFAULT 'open',
                reason       TEXT NULL,
                signal_id    INTEGER NULL,
                content      TEXT NULL,
                created_at   VARCHAR(32) NOT NULL,
                updated_at   VARCHAR(32) NULL,
                INDEX idx_resting_orders_status (status),
                INDEX idx_resting_orders_agent (agent_id, status)
            )
        """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS resting_orders")
