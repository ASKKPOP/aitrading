"""users.region / timezone / locale_confirmed_at

Region is a COUNTRY and is deliberately not derived from users.lang — English
alone serves US, CA, AU and SG. See regions.py.

All three are NULLABLE on purpose. Existing members have never been asked, so
they are `unknown` until they answer; back-filling region from lang would put
every English speaker in the United States, which is exactly the mistake the
separate field exists to prevent.

`locale_confirmed_at` is the flag the first-run prompt reads: NULL means the
member has not chosen yet, and it stays NULL no matter what geolocation
guessed. A guess is not a confirmation.
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "region" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN region VARCHAR(2) NULL")
    if "timezone" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN timezone VARCHAR(64) NULL")
    if "locale_confirmed_at" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN locale_confirmed_at VARCHAR(32) NULL")
    if "geo_country" not in cols:
        # What IP geolocation guessed at signup. Kept separate from `region`
        # so a guess can never be mistaken for the member's own answer, and so
        # the prompt has something to pre-select.
        op.execute("ALTER TABLE users ADD COLUMN geo_country VARCHAR(2) NULL")


def downgrade():
    for col in ("geo_country", "locale_confirmed_at", "timezone", "region"):
        op.execute(f"ALTER TABLE users DROP COLUMN {col}")
