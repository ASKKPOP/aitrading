"""Phase 3.8 — out-of-sample tournament infrastructure.

Adds two new tables:
  tournaments         — out-of-sample challenge windows
  tournament_entries  — frozen strategy snapshots + per-entry evaluation results

Neither table existed in earlier migrations, so all operations are safe
CREATE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-25
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS tournaments (
            id                    INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name                  TEXT    NOT NULL,
            description           TEXT,
            status                TEXT    NOT NULL DEFAULT 'open',
            submission_deadline   TEXT    NOT NULL,
            evaluation_start      TEXT    NOT NULL,
            evaluation_end        TEXT    NOT NULL,
            symbol                TEXT,
            market                TEXT    NOT NULL DEFAULT 'us-stock',
            initial_cash          NUMERIC(20,8) NOT NULL DEFAULT 100000.0,
            created_by_agent_id   INTEGER REFERENCES agents(id),
            created_at            TEXT DEFAULT ({_NOW}),
            closed_at             TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tournaments_status
        ON tournaments(status, submission_deadline)
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS tournament_entries (
            id                INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            tournament_id     INTEGER NOT NULL REFERENCES tournaments(id),
            agent_id          INTEGER NOT NULL REFERENCES agents(id),
            strategy_id       INTEGER NOT NULL REFERENCES strategies(id),
            config_hash       TEXT    NOT NULL,
            config_snapshot   TEXT    NOT NULL,
            submitted_at      TEXT    NOT NULL,
            backtest_run_id   INTEGER REFERENCES backtest_runs(id),
            final_sharpe      NUMERIC(20,8),
            final_return_pct  NUMERIC(20,8),
            `rank`            INTEGER,
            UNIQUE KEY uq_tournament_entry (tournament_id, agent_id, strategy_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tournament_entries_lookup
        ON tournament_entries(tournament_id, `rank`)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tournament_entries")
    op.execute("DROP TABLE IF EXISTS tournaments")
