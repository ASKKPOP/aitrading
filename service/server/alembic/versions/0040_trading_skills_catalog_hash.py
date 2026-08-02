"""Plan 20 — catalogue auto-upgrade fingerprint.

trading_skills.catalog_hash records what the in-code base catalogue last
wrote to the row. On every registry read, rows still matching their hash
(nobody edited them) are upgraded in place when the catalogue changes;
admin-edited rows no longer match and are left alone until an explicit
reset. Backfill happens in code (trading_skills._sync_catalogue), not
here: a NULL hash is only stamped when the row's content matches the
current catalogue byte-for-byte, so a pre-existing admin edit can never
be mistaken for catalogue content.
"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("trading_skills")]
    if "catalog_hash" not in cols:
        op.execute(
            "ALTER TABLE trading_skills ADD COLUMN catalog_hash VARCHAR(64) NULL")


def downgrade():
    op.execute("ALTER TABLE trading_skills DROP COLUMN catalog_hash")
