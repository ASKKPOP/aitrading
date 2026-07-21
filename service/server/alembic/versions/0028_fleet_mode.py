"""Plan 14 — Full Auto Trading (fleet mode): the ONE combined revision.

All fleet-mode DDL ships together (the plan's §8): fleets + fleet_events +
fleet_slots + fleet_candidates + fleet_symbol_cooldowns + research_theses +
research_batches, plus the trading_runs / users / automation_configs columns.
One revision, not several — two parallel sessions each minting a number was
the exact alembic-fork hazard the plan's QA rounds flagged.

MySQL DDL here; the SQLite mirror lives in database.init_database() per the
0022 convention.

Revision ID: 0028
Revises: 0027
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS fleets (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            name VARCHAR(80),
            status VARCHAR(16) NOT NULL DEFAULT 'draft',
            status_reason VARCHAR(255),
            active_fleet_key VARCHAR(64) NULL,
            idempotency_key VARCHAR(64) NULL,
            n_runs INTEGER NOT NULL,
            total_budget_usd NUMERIC(20,8) NOT NULL,
            risk_appetite VARCHAR(12) NOT NULL DEFAULT 'balanced',
            market_scope_json MEDIUMTEXT,
            warn_loss_frac NUMERIC(20,8) NOT NULL DEFAULT 0.30,
            stop_loss_frac NUMERIC(20,8) NOT NULL DEFAULT 0.40,
            warn_latched_at VARCHAR(32) NULL,
            warn_acked_at VARCHAR(32) NULL,
            warn_level_frac NUMERIC(20,8) NULL,
            warn_episode INTEGER NOT NULL DEFAULT 0,
            entry_paused_reason VARCHAR(24) NULL,
            held_by_master INTEGER NOT NULL DEFAULT 0,
            rotation_enabled INTEGER NOT NULL DEFAULT 1,
            build_attempts INTEGER NOT NULL DEFAULT 0,
            last_event_seq INTEGER NOT NULL DEFAULT 0,
            provider VARCHAR(16),
            lang VARCHAR(8) NOT NULL DEFAULT 'en',
            claimed_by VARCHAR(64),
            claim_expires_at VARCHAR(32),
            last_supervise_at VARCHAR(32),
            created_at VARCHAR(32) NOT NULL,
            started_at VARCHAR(32),
            stopped_at VARCHAR(32),
            UNIQUE KEY uq_fleets_active (active_fleet_key),
            INDEX idx_fleets_agent (agent_id, status),
            INDEX idx_fleets_status (status),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS fleet_events (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            fleet_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            ts VARCHAR(32) NOT NULL,
            event_type VARCHAR(32) NOT NULL,
            payload MEDIUMTEXT,
            UNIQUE KEY uq_fleet_events (fleet_id, seq),
            FOREIGN KEY (fleet_id) REFERENCES fleets(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS fleet_slots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            fleet_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,
            original_allocation_usd NUMERIC(20,8) NOT NULL,
            state VARCHAR(12) NOT NULL DEFAULT 'active',
            zombie_baseline_qty NUMERIC(28,10) NULL,
            current_run_id INTEGER NULL,
            updated_at VARCHAR(32) NOT NULL,
            UNIQUE KEY uq_fleet_slots (fleet_id, slot_index),
            FOREIGN KEY (fleet_id) REFERENCES fleets(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS fleet_candidates (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            fleet_id INTEGER NOT NULL,
            thesis_key VARCHAR(80) NOT NULL,
            slot_index INTEGER NULL,
            allocation_usd NUMERIC(20,8),
            state VARCHAR(16) NOT NULL DEFAULT 'selected',
            run_id INTEGER NULL,
            created_at VARCHAR(32) NOT NULL,
            INDEX idx_fleet_candidates (fleet_id),
            FOREIGN KEY (fleet_id) REFERENCES fleets(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS fleet_symbol_cooldowns (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            market VARCHAR(16) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            until_ts VARCHAR(32) NOT NULL,
            source_run_id INTEGER,
            INDEX idx_symbol_cooldowns (agent_id, market, symbol)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS research_theses (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            batch_id VARCHAR(48) NOT NULL,
            market VARCHAR(16) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            market_type VARCHAR(10) NOT NULL DEFAULT 'spot',
            direction VARCHAR(8) NOT NULL,
            factor_scores_json MEDIUMTEXT NOT NULL,
            thesis TEXT,
            risks TEXT,
            invalidation TEXT,
            expected_move_pct NUMERIC(20,8),
            horizon_hours NUMERIC(20,8),
            confidence NUMERIC(20,8),
            ev_per_day_pct NUMERIC(20,8),
            final_score NUMERIC(20,8),
            selectable INTEGER NOT NULL DEFAULT 1,
            planner VARCHAR(16) NOT NULL,
            llm_model VARCHAR(64),
            created_at VARCHAR(32) NOT NULL,
            expires_at VARCHAR(32) NOT NULL,
            UNIQUE KEY uq_research_batch_symbol (batch_id, market, symbol),
            INDEX idx_research_batch (batch_id),
            INDEX idx_research_symbol (market, symbol, created_at)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS research_batches (
            batch_id VARCHAR(48) NOT NULL PRIMARY KEY,
            created_at VARCHAR(32) NOT NULL
        )
    """)
    for ddl in (
        "ALTER TABLE trading_runs ADD COLUMN fleet_id INTEGER NULL",
        "ALTER TABLE trading_runs ADD COLUMN created_via VARCHAR(16) NOT NULL DEFAULT 'user'",
        "ALTER TABLE trading_runs ADD COLUMN adapt_state_json MEDIUMTEXT NULL",
        "ALTER TABLE users ADD COLUMN ai_automation_state VARCHAR(12) NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN ai_automation_held_at VARCHAR(32) NULL",
        "ALTER TABLE automation_configs ADD COLUMN held_by_master INTEGER NOT NULL DEFAULT 0",
        "CREATE INDEX idx_trading_runs_fleet ON trading_runs (fleet_id)",
    ):
        try:
            op.execute(ddl)
        except Exception:  # noqa: BLE001 — dup-tolerant re-run
            pass


def downgrade():
    for ddl in (
        "DROP INDEX idx_trading_runs_fleet ON trading_runs",
        "ALTER TABLE automation_configs DROP COLUMN held_by_master",
        "ALTER TABLE users DROP COLUMN ai_automation_held_at",
        "ALTER TABLE users DROP COLUMN ai_automation_state",
        "ALTER TABLE trading_runs DROP COLUMN adapt_state_json",
        "ALTER TABLE trading_runs DROP COLUMN created_via",
        "ALTER TABLE trading_runs DROP COLUMN fleet_id",
        "DROP TABLE IF EXISTS research_batches",
        "DROP TABLE IF EXISTS research_theses",
        "DROP TABLE IF EXISTS fleet_symbol_cooldowns",
        "DROP TABLE IF EXISTS fleet_candidates",
        "DROP TABLE IF EXISTS fleet_slots",
        "DROP TABLE IF EXISTS fleet_events",
        "DROP TABLE IF EXISTS fleets",
    ):
        try:
            op.execute(ddl)
        except Exception:  # noqa: BLE001
            pass
