"""oauth_identities.display_name — the one shot Apple gives us at the name.

Apple sends the member's name exactly once, in the `user` form field of the
first-ever authorization, and never again. There is no endpoint to ask later:
miss it and the only recovery is the member removing the app from their Apple
ID settings and re-authorizing. So it is captured onto the identity row at
link time.

Why this migration exists at all: PR #354 added the column with the
idempotent-ALTER pattern used elsewhere in `database.init_database()`. That
works on SQLite, which is what the tests run on — and did nothing on prod
MySQL, where the schema is owned by these migrations. The result was a green
test suite and a 500 on the first real Apple sign-in:

    pymysql.err.OperationalError:
        (1054, "Unknown column 'display_name' in 'field list'")

Idempotent on purpose: the column already exists on any SQLite database that
ran `init_database()`, so a blind ADD COLUMN would fail there. Inspect first,
add only if missing — that makes this safe to run against either dialect and
against a prod box that was hot-fixed by hand.
"""
from alembic import op
import sqlalchemy as sa


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind, "oauth_identities", "display_name"):
        op.add_column(
            "oauth_identities",
            sa.Column("display_name", sa.String(length=255), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "oauth_identities", "display_name"):
        op.drop_column("oauth_identities", "display_name")
