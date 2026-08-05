"""users.phone + phone_verified_at — verified-phone identity for SMS
password reset. UNIQUE(phone): reset-by-phone must map to one account.
NULLs are unlimited on both dialects, so members without phones are
unaffected. Verification gates reset + badge only — SMS alert delivery
still reads the alerts settings target (see spec §2)."""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "phone" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL")
    if "phone_verified_at" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN phone_verified_at VARCHAR(32) NULL")
    indexes = [i["name"] for i in sa.inspect(bind).get_indexes("users")]
    if "idx_users_phone" not in indexes:
        op.execute("CREATE UNIQUE INDEX idx_users_phone ON users(phone)")


def downgrade():
    op.execute("DROP INDEX idx_users_phone ON users")
    op.execute("ALTER TABLE users DROP COLUMN phone_verified_at")
    op.execute("ALTER TABLE users DROP COLUMN phone")
