"""0023 — broker_orders.filled_qty for the order reconciler.

A live/shadow order the broker answers with SUBMITTED gets its final state
confirmed later by the order-reconciler sweep (execution/gateway.py
reconcile_orders_tick). That sweep records the broker-confirmed fill quantity
here; `quantity` stays the REQUESTED size, so drift between the two is
observable instead of overwritten.

DDL mirrors init_database(). Money is NUMERIC(20,8) per migrations 0005+.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-19
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE broker_orders ADD COLUMN filled_qty NUMERIC(20,8) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE broker_orders DROP COLUMN filled_qty")
