"""Plan 19 — regional trading gateway.

broker_orders gains the FX-capture pair for non-USD venues (Upbit/KRW): the
quote currency of the fill and the rate used to convert it into the USD
ledger, persisted at fill time and never recomputed.

broker_nonces is Kraken's monotonic nonce source. Kraken permanently
invalidates an API key on nonce regression, and prod runs a worker plus an
API process — time.time() in two processes WILL regress. One counter per
broker account, bumped inside a transaction, is the only safe source.
"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("broker_orders")]
    if "quote_currency" not in cols:
        op.execute("ALTER TABLE broker_orders ADD COLUMN quote_currency VARCHAR(8) NULL")
    if "fx_rate_usd" not in cols:
        op.execute("ALTER TABLE broker_orders ADD COLUMN fx_rate_usd DOUBLE NULL")
    if not sa.inspect(bind).has_table("broker_nonces"):
        op.execute(
            """CREATE TABLE broker_nonces (
                   account_id BIGINT NOT NULL PRIMARY KEY,
                   nonce      BIGINT NOT NULL DEFAULT 0
               )"""
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_nonces")
    op.execute("ALTER TABLE broker_orders DROP COLUMN fx_rate_usd")
    op.execute("ALTER TABLE broker_orders DROP COLUMN quote_currency")
