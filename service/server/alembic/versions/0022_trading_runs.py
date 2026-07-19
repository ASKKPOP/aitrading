"""0022 — Trading Runs (Plan 10): run lifecycle, event journal, report journal.

New tables: trading_runs (the run state machine — lease-claimed by the
worker's scheduler loop), run_events (append-only per-run journal,
UNIQUE(run_id, seq)), run_reports (delivery journal, pending -> sent).
ALTERs: signals gains run_id / client_order_id (UNIQUE, idempotency key
"run:{id}:cyc:{seq}") / fee_usd; positions gains run_id (ownership for
watcher-close attribution) and price_updated_at (mark age — stale marks are
an evaluation FAILURE for fail-closed stop conditions).

active_key emulates a partial unique index: it holds "agent:market:symbol"
only while the run is active and NULL otherwise, so one-active-run-per-tuple
is a DB constraint (MySQL allows multiple NULLs in a unique index).

DDL mirrors init_database(). Indexed / unique / timestamp columns use
VARCHAR(N) per migrations 0007–0021 (MySQL cannot index TEXT); money is
NUMERIC(20,8); timestamps are ISO-8601 UTC strings "%Y-%m-%dT%H:%M:%SZ".
No MySQL reserved words are used as column names.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-19
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS trading_runs (
            id                      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id                INTEGER NOT NULL,
            symbol                  VARCHAR(20) NOT NULL,
            market                  VARCHAR(16) NOT NULL DEFAULT 'crypto',
            market_type             VARCHAR(10) NOT NULL DEFAULT 'spot',
            status                  VARCHAR(16) NOT NULL DEFAULT 'draft',
            status_reason           VARCHAR(255),
            active_key              VARCHAR(80),
            config_snapshot_json    MEDIUMTEXT,
            start_condition_json    MEDIUMTEXT,
            stop_conditions_json    MEDIUMTEXT,
            stop_flatten            INTEGER NOT NULL DEFAULT 1,
            report_frequency        VARCHAR(16) NOT NULL DEFAULT 'off',
            report_hour_local       INTEGER,
            report_tz               VARCHAR(64),
            notify_on_trade         INTEGER NOT NULL DEFAULT 0,
            profit_threshold_pct    NUMERIC(20,8),
            loss_threshold_pct      NUMERIC(20,8),
            drawdown_threshold_pct  NUMERIC(20,8),
            last_report_at          VARCHAR(32),
            max_trades_per_day      INTEGER NOT NULL DEFAULT 50,
            consecutive_errors      INTEGER NOT NULL DEFAULT 0,
            consecutive_infeasible  INTEGER NOT NULL DEFAULT 0,
            paused_reason           VARCHAR(64),
            started_at              VARCHAR(32),
            stopped_at              VARCHAR(32),
            last_cycle_at           VARCHAR(32),
            cycle_seq               INTEGER NOT NULL DEFAULT 0,
            last_event_seq          INTEGER NOT NULL DEFAULT 0,
            claimed_by              VARCHAR(64),
            claim_expires_at        VARCHAR(32),
            realized_pnl_usd        NUMERIC(20,8) NOT NULL DEFAULT 0,
            created_at              VARCHAR(32) NOT NULL,
            UNIQUE KEY uq_trading_runs_active_key (active_key),
            INDEX idx_trading_runs_agent (agent_id, status),
            INDEX idx_trading_runs_status (status),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS run_events (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            run_id     INTEGER NOT NULL,
            seq        INTEGER NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            ts         VARCHAR(32) NOT NULL,
            payload    MEDIUMTEXT,
            UNIQUE KEY uq_run_events_run_seq (run_id, seq),
            INDEX idx_run_events_type_ts (event_type, ts),
            FOREIGN KEY (run_id) REFERENCES trading_runs(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS run_reports (
            id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            run_id        INTEGER NOT NULL,
            user_id       INTEGER,
            kind          VARCHAR(16) NOT NULL,
            period_start  VARCHAR(32),
            period_end    VARCHAR(32),
            pnl           NUMERIC(20,8),
            trades        INTEGER,
            status        VARCHAR(12) NOT NULL DEFAULT 'pending',
            sent_at       VARCHAR(32),
            channels_json MEDIUMTEXT,
            created_at    VARCHAR(32) NOT NULL,
            INDEX idx_run_reports_run (run_id, created_at),
            FOREIGN KEY (run_id) REFERENCES trading_runs(id)
        )
    """)

    op.execute("ALTER TABLE signals ADD COLUMN run_id INTEGER NULL")
    op.execute("ALTER TABLE signals ADD COLUMN client_order_id VARCHAR(64) NULL")
    op.execute("ALTER TABLE signals ADD COLUMN fee_usd NUMERIC(20,8) NULL")
    op.execute("""
        CREATE UNIQUE INDEX uq_signals_client_order_id
        ON signals (client_order_id)
    """)

    op.execute("ALTER TABLE positions ADD COLUMN run_id INTEGER NULL")
    op.execute("ALTER TABLE positions ADD COLUMN price_updated_at VARCHAR(32) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE positions DROP COLUMN price_updated_at")
    op.execute("ALTER TABLE positions DROP COLUMN run_id")
    op.execute("DROP INDEX uq_signals_client_order_id ON signals")
    op.execute("ALTER TABLE signals DROP COLUMN fee_usd")
    op.execute("ALTER TABLE signals DROP COLUMN client_order_id")
    op.execute("ALTER TABLE signals DROP COLUMN run_id")
    for table in ("run_reports", "run_events", "trading_runs"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
