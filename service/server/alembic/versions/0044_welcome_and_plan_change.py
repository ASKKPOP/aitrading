"""users.welcome_dismissed_at — the first-run /welcome page stops appearing
once the member ticks "do not show next time" (two-way: unticking clears it).
user_subscriptions.pending_plan_code + change_kind — subscription changes on
the manual rails: an upgrade row is tagged change_kind='upgrade' (prorated,
admin-approved, expires_at untouched); a downgrade stamps pending_plan_code
on the ACTIVE row and takes effect at renewal."""
import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    user_cols = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "welcome_dismissed_at" not in user_cols:
        op.execute("ALTER TABLE users ADD COLUMN welcome_dismissed_at VARCHAR(32) NULL")
    sub_cols = [c["name"] for c in sa.inspect(bind).get_columns("user_subscriptions")]
    if "pending_plan_code" not in sub_cols:
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN pending_plan_code VARCHAR(32) NULL")
    if "change_kind" not in sub_cols:
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN change_kind VARCHAR(16) NULL")


def downgrade():
    op.execute("ALTER TABLE user_subscriptions DROP COLUMN change_kind")
    op.execute("ALTER TABLE user_subscriptions DROP COLUMN pending_plan_code")
    op.execute("ALTER TABLE users DROP COLUMN welcome_dismissed_at")
