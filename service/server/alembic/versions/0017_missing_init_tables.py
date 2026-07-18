"""0017 — backfill the 12 tables init_database() creates but alembic lacked.

These tables (automation, agent-mode, backtest, chat, config profiles, factor/
regime snapshots, reputation slashes, alerts, watches) are created by
init_database() on the SQLite path but had no alembic migration, so a MySQL
deployment (which builds schema via `alembic upgrade head`, not init_database)
was missing them and crashed at runtime on every feature that touched them.

DDL mirrors init_database()'s current column set (including the ALTER-added
`automation_runs.confluence_json`). Indexed / unique / timestamp columns use
VARCHAR(N) — matching migrations 0007–0009 — because MySQL cannot index or
put a literal default on a TEXT column; freeform content stays TEXT.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-17
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# MySQL expression producing ISO-8601 UTC text matching SQLite's datetime('now').
_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    # ── automation_configs (parent of automation_runs & agent_mode_decisions) ──
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS automation_configs (
            id               INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id         INTEGER NOT NULL,
            symbol           MEDIUMTEXT    NOT NULL,
            market           VARCHAR(32) NOT NULL DEFAULT 'crypto',
            provider         MEDIUMTEXT,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            min_confidence   REAL    NOT NULL DEFAULT 0.65,
            size_usd         REAL    NOT NULL DEFAULT 500,
            auto_execute     INTEGER NOT NULL DEFAULT 0,
            account_type     VARCHAR(32) NOT NULL DEFAULT 'simulator',
            enabled          INTEGER NOT NULL DEFAULT 1,
            lang             VARCHAR(16) NOT NULL DEFAULT 'en',
            risk_level       MEDIUMTEXT,
            mode             VARCHAR(32) NOT NULL DEFAULT 'manual',
            budget_usd       REAL,
            schedule_json    MEDIUMTEXT,
            last_run_at      VARCHAR(64),
            created_at       VARCHAR(64) DEFAULT ({_NOW}),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS automation_runs (
            id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            config_id       INTEGER NOT NULL,
            agent_id        INTEGER NOT NULL,
            ran_at          VARCHAR(64) DEFAULT ({_NOW}),
            action          MEDIUMTEXT,
            confidence      REAL,
            executed        INTEGER NOT NULL DEFAULT 0,
            skip_reason     MEDIUMTEXT,
            signal_id       INTEGER,
            report          MEDIUMTEXT,
            confluence_json MEDIUMTEXT,
            FOREIGN KEY (config_id) REFERENCES automation_configs(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_mode_decisions (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            config_id   INTEGER NOT NULL,
            agent_id    INTEGER NOT NULL,
            decided_at  VARCHAR(64) NOT NULL,
            params_json MEDIUMTEXT    NOT NULL,
            rationale   MEDIUMTEXT,
            llm_model   MEDIUMTEXT,
            planner     VARCHAR(32) NOT NULL DEFAULT 'llm',
            FOREIGN KEY (config_id) REFERENCES automation_configs(id)
        )
    """)

    # ── backtest_runs (FK strategies from 0005) ────────────────────────────────
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id     INTEGER NOT NULL,
            strategy_id  INTEGER,
            status       VARCHAR(32) NOT NULL DEFAULT 'pending',
            config       MEDIUMTEXT    NOT NULL,
            result       MEDIUMTEXT,
            error_msg    MEDIUMTEXT,
            created_at   VARCHAR(64) DEFAULT ({_NOW}),
            started_at   VARCHAR(64),
            completed_at VARCHAR(64),
            FOREIGN KEY (agent_id)    REFERENCES agents(id),
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
    """)

    # ── chat_sessions / chat_messages ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id   INTEGER NOT NULL,
            symbol     MEDIUMTEXT,
            market     VARCHAR(32) NOT NULL DEFAULT 'crypto',
            title      MEDIUMTEXT,
            created_at VARCHAR(64) NOT NULL,
            updated_at VARCHAR(64),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            session_id INTEGER NOT NULL,
            role       VARCHAR(16) NOT NULL,
            content    MEDIUMTEXT NOT NULL,
            llm_model  MEDIUMTEXT,
            created_at VARCHAR(64) NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)

    # ── config_profiles (UNIQUE(agent_id, name) → name must be VARCHAR) ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS config_profiles (
            id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id     INTEGER NOT NULL,
            name         VARCHAR(191) NOT NULL,
            payload_json MEDIUMTEXT    NOT NULL,
            created_at   VARCHAR(64),
            updated_at   VARCHAR(64),
            UNIQUE KEY uq_config_profiles_agent_name (agent_id, name),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # ── factor_snapshots (indexed on symbol, created_at → both VARCHAR) ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS factor_snapshots (
            id                 INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            symbol             VARCHAR(64) NOT NULL,
            funding_rate       REAL,
            open_interest_usd  REAL,
            long_short_ratio   REAL,
            stocktwits_tilt    REAL,
            stocktwits_n       INTEGER,
            basis_pct          REAL,
            kimchi_premium_pct REAL,
            etf_flow_usd       REAL,
            whale_net_flow_usd REAL,
            created_at         VARCHAR(64) NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS regime_snapshots (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            regime      VARCHAR(32) NOT NULL,
            detail_json MEDIUMTEXT,
            created_at  VARCHAR(64) NOT NULL
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS reputation_slashes (
            id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            leader_id       INTEGER NOT NULL,
            signal_id       INTEGER,
            loss_pct        REAL    NOT NULL,
            follower_count  INTEGER NOT NULL,
            points_deducted INTEGER NOT NULL,
            created_at      VARCHAR(64) DEFAULT ({_NOW}),
            FOREIGN KEY (leader_id) REFERENCES agents(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id      INTEGER NOT NULL,
            user_id       INTEGER,
            kind          VARCHAR(64) NOT NULL,
            title         MEDIUMTEXT    NOT NULL,
            body          MEDIUMTEXT,
            channels_json MEDIUMTEXT,
            dedupe_key    VARCHAR(191),
            created_at    VARCHAR(64) NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_watches (
            id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id      INTEGER NOT NULL,
            name VARCHAR(255)    NOT NULL,
            metric        VARCHAR(64) NOT NULL,
            symbol        MEDIUMTEXT,
            comparator    VARCHAR(8) NOT NULL,
            threshold     REAL    NOT NULL,
            enabled       INTEGER NOT NULL DEFAULT 1,
            cooldown_min  INTEGER NOT NULL DEFAULT 60,
            last_fired_at VARCHAR(64),
            created_at    VARCHAR(64) NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # ── indexes (match init_database()) ────────────────────────────────────────
    op.execute("CREATE INDEX idx_automation_configs_agent ON automation_configs(agent_id, enabled)")
    op.execute("CREATE INDEX idx_automation_runs_config ON automation_runs(config_id, ran_at)")
    op.execute("CREATE INDEX idx_backtest_runs_agent ON backtest_runs(agent_id, created_at)")
    op.execute("CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, id)")
    op.execute("CREATE INDEX idx_factor_snapshots_symbol_created ON factor_snapshots(symbol, created_at)")
    op.execute("CREATE INDEX idx_regime_snapshots_created ON regime_snapshots(created_at)")
    op.execute("CREATE INDEX idx_reputation_slashes_leader ON reputation_slashes(leader_id, created_at)")
    op.execute("CREATE INDEX idx_alert_log_agent ON alert_log(agent_id, created_at)")
    op.execute("CREATE INDEX idx_user_watches_agent ON user_watches(agent_id, enabled)")

    # ── columns init_database() adds via guarded ALTERs but alembic never mirrored ──
    # (same init↔alembic drift as the tables above; the base tables exist by now).
    op.execute("ALTER TABLE positions ADD COLUMN first_opened_at VARCHAR(64)")
    op.execute("ALTER TABLE positions ADD COLUMN exit_policy VARCHAR(32)")
    op.execute("ALTER TABLE risk_limits ADD COLUMN max_portfolio_exposure_pct DOUBLE NOT NULL DEFAULT 60")
    op.execute("ALTER TABLE risk_limits ADD COLUMN max_concurrent_positions INT NOT NULL DEFAULT 8")
    op.execute("ALTER TABLE risk_limits ADD COLUMN use_trailing INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE risk_limits ADD COLUMN trail_pct DOUBLE NOT NULL DEFAULT 0.05")
    op.execute("ALTER TABLE risk_limits ADD COLUMN time_stop_days INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN trading_guidelines TEXT")
    op.execute("ALTER TABLE breaker_state ADD COLUMN tripped_by TEXT")
    op.execute("ALTER TABLE breaker_state ADD COLUMN expires_at VARCHAR(64)")
    op.execute("ALTER TABLE position_reconciliations ADD COLUMN broker_order_id VARCHAR(191)")
    op.execute("ALTER TABLE position_reconciliations ADD COLUMN status VARCHAR(32) DEFAULT 'ok'")
    op.execute("ALTER TABLE position_reconciliations ADD COLUMN error_message TEXT")


def downgrade() -> None:
    for tbl, col in (
        ("position_reconciliations", "error_message"),
        ("position_reconciliations", "status"),
        ("position_reconciliations", "broker_order_id"),
        ("breaker_state", "expires_at"),
        ("breaker_state", "tripped_by"),
        ("users", "trading_guidelines"),
        ("risk_limits", "time_stop_days"),
        ("risk_limits", "trail_pct"),
        ("risk_limits", "use_trailing"),
        ("risk_limits", "max_concurrent_positions"),
        ("risk_limits", "max_portfolio_exposure_pct"),
        ("positions", "exit_policy"),
        ("positions", "first_opened_at"),
    ):
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
    for tbl in (
        "user_watches",
        "alert_log",
        "reputation_slashes",
        "regime_snapshots",
        "factor_snapshots",
        "config_profiles",
        "chat_messages",
        "chat_sessions",
        "backtest_runs",
        "agent_mode_decisions",
        "automation_runs",
        "automation_configs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl}")
