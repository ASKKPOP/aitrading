"""Arm executor — persist the desk's pre-committed exit level.

`order_intent` has always supported `arm` ("if price_above/price_below
LEVEL then reduce/close size_frac"), but nothing consumed one: 54 arm
intents were emitted lifetime and every single one was discarded, because
there was nowhere to keep the standing order between decision cycles.

Cycle 65 (2026-08-05) measured the cost. Every losing run that day was in
PROFIT first, and for four of seven the profit existed ONLY between
decisions — dwell above half-peak was 5-20 minutes against a ~45 minute
cycle, so runs 967 and 957 never had a single cycle while in profit. The
desk cannot bank what it never sees, and no prompt lesson can reach a
window in which no prompt is rendered.

trading_runs.armed_order_json holds {"arm": {...}, "seq": N,
"armed_at": iso}. NULL means nothing is armed. Each cycle's arm REPLACES
the previous one, the control pass fires it, and it is cleared on firing
or when the position goes flat.
"""
import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("trading_runs")]
    if "armed_order_json" not in cols:
        op.execute("ALTER TABLE trading_runs ADD COLUMN armed_order_json TEXT NULL")


def downgrade():
    op.execute("ALTER TABLE trading_runs DROP COLUMN armed_order_json")
