"""0018 — admin console identities + paid membership.

New tables: admin_users / admin_tokens / admin_audit_log (real admin accounts
with email+password replacing the shared ADMIN_TOKEN, plus an audit trail),
subscription_plans / user_subscriptions / contract_requests (paid membership:
junior $60, pro $119, professional $199, enterprise = contact), and a
users.status column for member suspend/ban.

DDL mirrors init_database(). Indexed / unique / timestamp columns use
VARCHAR(N) — matching migrations 0007–0017 — because MySQL cannot index or
put a literal default on a TEXT column; freeform content stays TEXT.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-18
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# MySQL expression producing ISO-8601 UTC text matching SQLite's datetime('now').
_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS admin_users (
            id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            email         VARCHAR(255) NOT NULL UNIQUE,
            password_hash MEDIUMTEXT NOT NULL,
            role          VARCHAR(32) NOT NULL DEFAULT 'operator',
            status        VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at    VARCHAR(64) DEFAULT ({_NOW}),
            last_login_at VARCHAR(64)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS admin_tokens (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            admin_id   INTEGER NOT NULL,
            token      VARCHAR(128) NOT NULL UNIQUE,
            expires_at VARCHAR(64) NOT NULL,
            created_at VARCHAR(64) DEFAULT ({_NOW}),
            FOREIGN KEY (admin_id) REFERENCES admin_users(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            admin_id    INTEGER,
            admin_email VARCHAR(255),
            action      VARCHAR(128) NOT NULL,
            target      VARCHAR(255),
            detail      MEDIUMTEXT,
            created_at  VARCHAR(64) DEFAULT ({_NOW}),
            INDEX idx_admin_audit_created (created_at)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscription_plans (
            id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            code         VARCHAR(64) NOT NULL UNIQUE,
            name         VARCHAR(128) NOT NULL,
            price_usd    REAL NOT NULL DEFAULT 0,
            contact_only INTEGER NOT NULL DEFAULT 0,
            active       INTEGER NOT NULL DEFAULT 1,
            sort_order   INTEGER NOT NULL DEFAULT 0
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            plan_code  VARCHAR(64) NOT NULL,
            status     VARCHAR(32) NOT NULL DEFAULT 'pending',
            method     VARCHAR(32),
            reference  MEDIUMTEXT,
            amount_usd REAL,
            started_at VARCHAR(64),
            expires_at VARCHAR(64),
            decided_by INTEGER,
            decided_at VARCHAR(64),
            note       MEDIUMTEXT,
            created_at VARCHAR(64) DEFAULT ({_NOW}),
            INDEX idx_user_subscriptions_user (user_id, status),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS contract_requests (
            id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id    INTEGER,
            name       VARCHAR(255),
            email      VARCHAR(255) NOT NULL,
            company    VARCHAR(255),
            phone      VARCHAR(64),
            message    MEDIUMTEXT,
            status     VARCHAR(32) NOT NULL DEFAULT 'new',
            handled_by INTEGER,
            handled_at VARCHAR(64),
            created_at VARCHAR(64) DEFAULT ({_NOW})
        )
    """)

    # Alias every column: MySQL derives the subquery's column names from the
    # first SELECT's literals, and 'junior' vs 'Junior' collide case-insensitively
    # (error 1060 "Duplicate column name").
    op.execute("""
        INSERT INTO subscription_plans (code, name, price_usd, contact_only, sort_order)
        SELECT code, name, price_usd, contact_only, sort_order FROM (
            SELECT 'junior' AS code, 'Junior' AS name, 60.0 AS price_usd,
                   0 AS contact_only, 1 AS sort_order
            UNION ALL SELECT 'pro', 'Pro', 119.0, 0, 2
            UNION ALL SELECT 'professional', 'Professional', 199.0, 0, 3
            UNION ALL SELECT 'enterprise', 'Enterprise', 0.0, 1, 4
        ) AS seed
        WHERE NOT EXISTS (SELECT 1 FROM subscription_plans)
    """)

    # users.status — ALTER without IF NOT EXISTS; tolerate re-runs like 0017.
    try:
        op.execute("ALTER TABLE users ADD COLUMN status VARCHAR(32) DEFAULT 'active'")
    except Exception:
        pass


def downgrade() -> None:
    for table in (
        "contract_requests",
        "user_subscriptions",
        "subscription_plans",
        "admin_audit_log",
        "admin_tokens",
        "admin_users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    try:
        op.execute("ALTER TABLE users DROP COLUMN status")
    except Exception:
        pass
