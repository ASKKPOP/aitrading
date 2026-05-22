"""Phase 2 broker execution tables + Phase 3.5 strategies table.

Adds the four tables introduced by the broker execution layer (Phase 2)
and the strategies table + signals.strategy_id column (Phase 3.5).
None of these existed in the baseline migration (0001) so they are safe
CREATE IF NOT EXISTS operations.

New tables:
  broker_accounts          — per-agent broker credential vault
  broker_orders            — order lifecycle log (paper/shadow/live)
  position_reconciliations — shadow-mode drift records
  broker_live_optins       — immutable T&Cs acceptance audit log
  strategies               — named strategy definitions with backtest metadata

New columns:
  signals.strategy_id      — optional FK to strategies(id)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    # ── broker_accounts ───────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS broker_accounts (
            id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id        INTEGER NOT NULL REFERENCES agents(id),
            broker          TEXT    NOT NULL,
            execution_mode  TEXT    NOT NULL DEFAULT 'paper',
            credentials_enc TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT DEFAULT ({_NOW}),
            updated_at      TEXT DEFAULT ({_NOW})
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_accounts_agent
        ON broker_accounts(agent_id, is_active)
    """)

    # ── broker_orders ─────────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS broker_orders (
            id               INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id         INTEGER NOT NULL REFERENCES agents(id),
            symbol           TEXT    NOT NULL,
            market           TEXT    NOT NULL DEFAULT 'us-stock',
            side             TEXT    NOT NULL,
            quantity         NUMERIC(20,8) NOT NULL,
            price            NUMERIC(20,8) NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'pending',
            execution_mode   TEXT    NOT NULL DEFAULT 'paper',
            broker           TEXT    NOT NULL DEFAULT 'paper',
            broker_order_id  TEXT,
            error_message    TEXT,
            signal_id        INTEGER REFERENCES signals(signal_id),
            leader_id        INTEGER,
            token_id         TEXT,
            outcome          TEXT,
            created_at       TEXT DEFAULT ({_NOW}),
            filled_at        TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_orders_agent_created
        ON broker_orders(agent_id, created_at)
    """)

    # ── position_reconciliations ──────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS position_reconciliations (
            id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id        INTEGER NOT NULL REFERENCES agents(id),
            symbol          TEXT    NOT NULL,
            paper_qty       NUMERIC(20,8),
            broker_qty      NUMERIC(20,8),
            drift           NUMERIC(20,8),
            paper_order_id  INTEGER REFERENCES broker_orders(id),
            broker          TEXT,
            recorded_at     TEXT DEFAULT ({_NOW})
        )
    """)

    # ── broker_live_optins ────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS broker_live_optins (
            id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id     INTEGER NOT NULL REFERENCES agents(id),
            broker       TEXT    NOT NULL,
            tcs_version  TEXT    NOT NULL DEFAULT 'v1',
            ip_address   TEXT,
            user_agent   TEXT,
            created_at   TEXT DEFAULT ({_NOW})
        )
    """)

    # ── strategies ────────────────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS strategies (
            id                    INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id              INTEGER NOT NULL REFERENCES agents(id),
            name                  TEXT    NOT NULL,
            description           TEXT,
            config                TEXT,
            is_active             INTEGER NOT NULL DEFAULT 1,
            backtest_validated    INTEGER NOT NULL DEFAULT 0,
            last_backtest_sharpe  REAL,
            last_backtest_at      TEXT,
            created_at            TEXT DEFAULT ({_NOW}),
            updated_at            TEXT DEFAULT ({_NOW})
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategies_agent
        ON strategies(agent_id, is_active)
    """)

    # ── signals.strategy_id column ────────────────────────────────────────────
    op.execute("""
        ALTER TABLE signals ADD COLUMN strategy_id INTEGER
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS strategy_id")
    op.execute("DROP TABLE IF EXISTS strategies")
    op.execute("DROP TABLE IF EXISTS broker_live_optins")
    op.execute("DROP TABLE IF EXISTS position_reconciliations")
    op.execute("DROP TABLE IF EXISTS broker_orders")
    op.execute("DROP TABLE IF EXISTS broker_accounts")
