"""Auto-renew billing: Stripe/PayPal ids on users + plans + subscriptions,
billing_events webhook-idempotency table.

expires_at remains the ONLY field entitlements reads; auto_renew rows just
keep pushing it forward (period_end + 3-day grace) on each paid invoice.
"""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def cols(table):
        return [c["name"] for c in insp.get_columns(table)]

    if "stripe_customer_id" not in cols("users"):
        op.execute("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(64) NULL")
    if "stripe_price_id" not in cols("subscription_plans"):
        op.execute("ALTER TABLE subscription_plans ADD COLUMN stripe_price_id VARCHAR(64) NULL")
    if "paypal_plan_id" not in cols("subscription_plans"):
        op.execute("ALTER TABLE subscription_plans ADD COLUMN paypal_plan_id VARCHAR(64) NULL")
    if "external_id" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN external_id VARCHAR(128) NULL")
    if "auto_renew" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN auto_renew TINYINT NOT NULL DEFAULT 0")
    if "cancel_at_period_end" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN cancel_at_period_end TINYINT NOT NULL DEFAULT 0")

    if "billing_events" not in insp.get_table_names():
        op.execute("""
            CREATE TABLE billing_events (
                id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                provider     VARCHAR(16) NOT NULL,
                event_id     VARCHAR(128) NOT NULL,
                type         VARCHAR(80),
                payload      MEDIUMTEXT,
                processed_at VARCHAR(32),
                UNIQUE KEY uq_billing_events (provider, event_id)
            )
        """)
        op.execute("CREATE INDEX idx_user_subscriptions_external "
                   "ON user_subscriptions(method, external_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS billing_events")
    for col in ("cancel_at_period_end", "auto_renew", "external_id"):
        op.execute(f"ALTER TABLE user_subscriptions DROP COLUMN {col}")
    op.execute("ALTER TABLE subscription_plans DROP COLUMN paypal_plan_id")
    op.execute("ALTER TABLE subscription_plans DROP COLUMN stripe_price_id")
    op.execute("ALTER TABLE users DROP COLUMN stripe_customer_id")
