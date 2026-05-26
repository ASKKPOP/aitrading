"""
Database Module

数据库初始化、连接和管理
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import urlparse

from config import DATABASE_URL, DB_PATH

try:
    import pymysql
    import pymysql.cursors
except ImportError:  # pragma: no cover - dependency is optional until MySQL is enabled
    pymysql = None


_BASE_DIR = os.path.dirname(__file__)
_DEFAULT_SQLITE_DB_PATH = os.path.join(_BASE_DIR, "data", "sooppiy.db")
_SQLITE_DB_PATH = DB_PATH or _DEFAULT_SQLITE_DB_PATH
# MySQL expression that produces ISO-8601 UTC text matching sqlite's datetime('now').
_MYSQL_NOW_TEXT_SQL = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"
_SQLITE_INTERVAL_PATTERN = re.compile(
    r"datetime\s*\(\s*'now'\s*,\s*'([+-]?\d+)\s+([A-Za-z]+)'\s*\)",
    flags=re.IGNORECASE,
)
_SQLITE_NOW_PATTERN = re.compile(r"datetime\s*\(\s*'now'\s*\)", flags=re.IGNORECASE)
_SQLITE_AUTOINCREMENT_PATTERN = re.compile(
    r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
    flags=re.IGNORECASE,
)
_SQLITE_REAL_PATTERN = re.compile(r"\bREAL\b", flags=re.IGNORECASE)
_ALTER_ADD_COLUMN_PATTERN = re.compile(
    r"\bALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)",
    flags=re.IGNORECASE,
)
# MySQL retryable error numbers
_MYSQL_RETRYABLE_ERRNOS = {
    1205,  # ER_LOCK_WAIT_TIMEOUT
    1213,  # ER_LOCK_DEADLOCK
}


def using_mysql() -> bool:
    return bool(DATABASE_URL)


# Backward-compat alias — callers that still say using_postgres() keep working.
using_postgres = using_mysql


def get_database_backend_name() -> str:
    return "mysql" if using_mysql() else "sqlite"


def begin_write_transaction(cursor: Any) -> None:
    """Start a write transaction using syntax compatible with the active backend."""
    cursor.execute("BEGIN" if using_mysql() else "BEGIN IMMEDIATE")


def is_retryable_db_error(exc: Exception) -> bool:
    """Return True when the error is a transient write conflict worth retrying."""
    if isinstance(exc, sqlite3.OperationalError):
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message

    # PyMySQL / MySQL errors
    if pymysql is not None and isinstance(
        exc, (pymysql.OperationalError, pymysql.InternalError)
    ):
        errno = exc.args[0] if exc.args else None
        if errno in _MYSQL_RETRYABLE_ERRNOS:
            return True

    message = str(exc).lower()
    return any(
        fragment in message
        for fragment in (
            "deadlock detected",
            "lock not available",
            "lock wait timeout",
            "database is locked",
            "database is busy",
        )
    )


def _replace_unquoted_question_marks(sql: str) -> str:
    """Translate sqlite-style placeholders (?) to PyMySQL/psycopg placeholders (%s)."""
    result: list[str] = []
    i = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            result.append(char)
            if char == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            result.append(char)
            if char == "*" and next_char == "/":
                result.append(next_char)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        if not in_single and not in_double and char == "-" and next_char == "-":
            result.append(char)
            result.append(next_char)
            i += 2
            in_line_comment = True
            continue

        if not in_single and not in_double and char == "/" and next_char == "*":
            result.append(char)
            result.append(next_char)
            i += 2
            in_block_comment = True
            continue

        if char == "'" and not in_double:
            result.append(char)
            if in_single and next_char == "'":
                result.append(next_char)
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            result.append(char)
            i += 1
            continue

        if char == "?" and not in_single and not in_double:
            result.append("%s")
            i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


def _escape_percent_literals(sql: str) -> str:
    """Escape literal percent signs before PyMySQL placeholder parsing.

    PyMySQL uses percent-format placeholders (%s), so SQL literals such as
    ``LIKE '%foo%'`` or ``DATE_FORMAT(..., '%Y-%m-%d')`` must be sent as
    ``'%%foo%%'`` / ``'%%Y-%%m-%%d'``.  This runs BEFORE sqlite ``?``
    placeholders are translated to ``%s`` so the new ``%s`` are not doubled.
    """
    result: list[str] = []
    i = 0
    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""
        if char == "%":
            result.append("%%")
            i += 2 if next_char == "%" else 1
            continue
        result.append(char)
        i += 1
    return "".join(result)


# Keep old name as alias for any callers in tests.
_escape_psycopg_percent_literals = _escape_percent_literals


def _replace_sqlite_datetime_functions_mysql(sql: str) -> str:
    _MYSQL_INTERVAL_UNIT_MAP = {
        "SECOND": "SECOND", "SECONDS": "SECOND",
        "MINUTE": "MINUTE", "MINUTES": "MINUTE",
        "HOUR": "HOUR", "HOURS": "HOUR",
        "DAY": "DAY", "DAYS": "DAY",
        "MONTH": "MONTH", "MONTHS": "MONTH",
        "YEAR": "YEAR", "YEARS": "YEAR",
    }

    def replace_interval(match: re.Match[str]) -> str:
        amount = match.group(1)
        unit = _MYSQL_INTERVAL_UNIT_MAP.get(match.group(2).upper(), match.group(2).upper())
        return (
            f"DATE_FORMAT(UTC_TIMESTAMP() + INTERVAL {amount} {unit},"
            f" '%Y-%m-%dT%H:%i:%sZ')"
        )

    sql = _SQLITE_INTERVAL_PATTERN.sub(replace_interval, sql)
    sql = _SQLITE_NOW_PATTERN.sub(_MYSQL_NOW_TEXT_SQL, sql)
    return sql


def _adapt_sql_for_mysql(sql: str) -> str:
    adapted = sql
    # INTEGER PRIMARY KEY AUTOINCREMENT → INT AUTO_INCREMENT PRIMARY KEY
    adapted = _SQLITE_AUTOINCREMENT_PATTERN.sub("INT AUTO_INCREMENT PRIMARY KEY", adapted)
    # Note: MySQL accepts REAL (alias for DOUBLE); no substitution needed.
    # ALTER TABLE ... ADD COLUMN (no IF NOT EXISTS — try/except in init_database handles dups)
    adapted = _ALTER_ADD_COLUMN_PATTERN.sub(r"ALTER TABLE \1 ADD COLUMN ", adapted)
    # Replace sqlite datetime functions
    adapted = _replace_sqlite_datetime_functions_mysql(adapted)
    # Escape literal % signs BEFORE adding %s placeholders
    adapted = _escape_percent_literals(adapted)
    # Replace ? → %s
    adapted = _replace_unquoted_question_marks(adapted)
    return adapted


class DatabaseCursor:
    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self._backend = backend
        self.lastrowid: Optional[int] = None

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        self.lastrowid = None

        if self._backend == "mysql":
            query = _adapt_sql_for_mysql(sql)
            # Always pass tuple (even empty) so PyMySQL mogrifies %% → %
            self._cursor.execute(query, tuple(params or ()))
            self.lastrowid = self._cursor.lastrowid
            return self

        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, tuple(params))
        self.lastrowid = getattr(self._cursor, "lastrowid", None)
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]):
        self.lastrowid = None
        if self._backend == "mysql":
            query = _adapt_sql_for_mysql(sql)
            self._cursor.executemany(query, [tuple(p) for p in seq_of_params])
            return self

        self._cursor.executemany(sql, [tuple(p) for p in seq_of_params])
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


class DatabaseConnection:
    def __init__(self, connection: Any, backend: str):
        self._connection = connection
        self._backend = backend

    @property
    def autocommit(self):
        if self._backend == "mysql":
            return getattr(self._connection, "_autocommit", None)
        return getattr(self._connection, "autocommit", None)

    @autocommit.setter
    def autocommit(self, value):
        if self._backend == "mysql":
            # PyMySQL exposes autocommit as a method, not a property setter
            self._connection.autocommit(value)
        else:
            setattr(self._connection, "autocommit", value)

    def cursor(self):
        return DatabaseCursor(self._connection.cursor(), self._backend)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            try:
                self.rollback()
            finally:
                self.close()
            return False

        self.commit()
        self.close()
        return False

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def get_db_connection():
    """Get database connection. Supports both SQLite and MySQL."""
    if using_mysql():
        if pymysql is None:
            raise RuntimeError(
                "MySQL support requires PyMySQL. Install service requirements first."
            )
        parsed = urlparse(DATABASE_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        user = parsed.username or "root"
        password = parsed.password or ""
        database = parsed.path.lstrip("/")
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        return DatabaseConnection(conn, "mysql")

    db_path = _SQLITE_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    return DatabaseConnection(conn, "sqlite")


def get_database_status() -> dict[str, Any]:
    """Return a small health snapshot for startup logging."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if using_mysql():
            cursor.execute(
                "SELECT DATABASE() AS database_name, USER() AS current_user,"
                " @@hostname AS server_host, @@port AS server_port"
            )
            row = cursor.fetchone()
            return {
                "backend": get_database_backend_name(),
                "database_name": row["database_name"],
                "current_user": row["current_user"],
                "server_host": row["server_host"],
                "server_port": row["server_port"],
            }

        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
        return {
            "backend": get_database_backend_name(),
            "database_path": _SQLITE_DB_PATH,
        }
    finally:
        conn.close()


def init_database():
    """Initialize database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            token TEXT,
            token_expires_at TEXT,
            password_hash TEXT,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            cash REAL DEFAULT 100000.0,
            deposited REAL DEFAULT 0.0,
            reputation_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Agent messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            content TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Agent tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            input_data TEXT,
            result_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Listings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (seller_id) REFERENCES agents(id)
        )
    """)

    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT DEFAULT 'pending_delivery',
            escrow_status TEXT DEFAULT 'held',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (listing_id) REFERENCES listings(id),
            FOREIGN KEY (buyer_id) REFERENCES agents(id),
            FOREIGN KEY (seller_id) REFERENCES agents(id)
        )
    """)

    # Arbitrators table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arbitrators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Dispute votes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dispute_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            arbitrator_id INTEGER NOT NULL,
            vote TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (arbitrator_id) REFERENCES arbitrators(id)
        )
    """)

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            verification_code TEXT,
            code_expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Points transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS points_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # User tokens table (for session management)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Rate limits table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_ip TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            window_start TEXT NOT NULL,
            UNIQUE(client_ip, action)
        )
    """)

    # Signals table - stores trading signals from providers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            message_type TEXT NOT NULL,
            market TEXT NOT NULL,
            signal_type TEXT,
            symbol TEXT,
            token_id TEXT,
            outcome TEXT,
            symbols TEXT,
            side TEXT,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl REAL,
            title TEXT,
            content TEXT,
            tags TEXT,
            timestamp INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            executed_at TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Signal replies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            accepted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (signal_id) REFERENCES signals(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Subscriptions table (for copy trading)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_id INTEGER NOT NULL,
            follower_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (leader_id) REFERENCES agents(id),
            FOREIGN KEY (follower_id) REFERENCES agents(id)
        )
    """)

    # Positions table - stores copied positions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            leader_id INTEGER,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL DEFAULT 'us-stock',
            token_id TEXT,
            outcome TEXT,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            opened_at TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (leader_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_sequence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("SELECT COALESCE(MAX(signal_id), 0) AS max_signal_id FROM signals")
    max_signal_id = int(cursor.fetchone()["max_signal_id"] or 0)
    cursor.execute("SELECT COALESCE(MAX(id), 0) AS max_sequence_id FROM signal_sequence")
    max_sequence_id = int(cursor.fetchone()["max_sequence_id"] or 0)
    if max_sequence_id < max_signal_id:
        cursor.executemany(
            "INSERT INTO signal_sequence DEFAULT VALUES",
            [()] * (max_signal_id - max_sequence_id)
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome TEXT,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            settlement_price REAL NOT NULL,
            proceeds REAL NOT NULL,
            market_slug TEXT,
            resolved_outcome TEXT,
            resolved_at TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            source_data TEXT,
            FOREIGN KEY (position_id) REFERENCES positions(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            actor_agent_id INTEGER,
            target_agent_id INTEGER,
            object_type TEXT,
            object_id TEXT,
            market TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (actor_agent_id) REFERENCES agents(id),
            FOREIGN KEY (target_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            unit_type TEXT DEFAULT 'agent',
            variants_json TEXT,
            start_at TEXT,
            end_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_key TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            unit_id INTEGER NOT NULL,
            variant_key TEXT NOT NULL,
            assignment_reason TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(experiment_key, unit_type, unit_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_reward_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            source_type TEXT,
            source_id TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            status TEXT DEFAULT 'posted',
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            reversed_at TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            market TEXT NOT NULL,
            symbol TEXT,
            challenge_type TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming',
            scoring_method TEXT DEFAULT 'return-only',
            initial_capital REAL DEFAULT 100000.0,
            max_position_pct REAL DEFAULT 100.0,
            max_drawdown_pct REAL DEFAULT 100.0,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_by_agent_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (created_by_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT (datetime('now')),
            starting_cash REAL DEFAULT 100000.0,
            ending_value REAL,
            return_pct REAL,
            max_drawdown REAL,
            trade_count INTEGER DEFAULT 0,
            rank INTEGER,
            disqualified_reason TEXT,
            UNIQUE(challenge_id, agent_id),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            signal_id INTEGER,
            submission_type TEXT NOT NULL,
            content TEXT,
            prediction_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            source_signal_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            executed_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            return_pct REAL,
            max_drawdown REAL,
            risk_adjusted_score REAL,
            quality_score REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            market TEXT,
            symbol TEXT,
            direction TEXT,
            target_price REAL,
            target_probability REAL,
            confidence REAL,
            horizon_start_at TEXT,
            horizon_end_at TEXT,
            invalid_if TEXT,
            evidence_json TEXT,
            extracted_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            verifiability_score REAL DEFAULT 0,
            evidence_score REAL DEFAULT 0,
            specificity_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            review_score REAL DEFAULT 0,
            overall_score REAL DEFAULT 0,
            model_version TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_metric_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            window_key TEXT NOT NULL,
            window_start_at TEXT NOT NULL,
            window_end_at TEXT NOT NULL,
            return_pct REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            trade_count INTEGER DEFAULT 0,
            strategy_count INTEGER DEFAULT 0,
            discussion_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            accepted_reply_count INTEGER DEFAULT 0,
            citation_count INTEGER DEFAULT 0,
            adoption_count INTEGER DEFAULT 0,
            quality_score_avg REAL DEFAULT 0,
            risk_violation_count INTEGER DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS network_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_agent_id INTEGER NOT NULL,
            target_agent_id INTEGER NOT NULL,
            edge_type TEXT NOT NULL,
            signal_id INTEGER,
            weight REAL DEFAULT 1,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (source_agent_id) REFERENCES agents(id),
            FOREIGN KEY (target_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            market TEXT NOT NULL,
            symbol TEXT,
            mission_type TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming',
            team_size_min INTEGER DEFAULT 2,
            team_size_max INTEGER DEFAULT 5,
            assignment_mode TEXT DEFAULT 'random',
            required_roles_json TEXT,
            start_at TEXT NOT NULL,
            submission_due_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'forming',
            formation_method TEXT DEFAULT 'manual',
            variant_key TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_mission_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT (datetime('now')),
            UNIQUE(mission_id, agent_id),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            role TEXT,
            status TEXT DEFAULT 'active',
            joined_at TEXT DEFAULT (datetime('now')),
            UNIQUE(team_id, agent_id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            signal_id INTEGER,
            message_type TEXT NOT NULL,
            content TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            submitted_by_agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            prediction_json TEXT,
            confidence REAL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (submitted_by_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            contribution_type TEXT NOT NULL,
            contribution_score REAL DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            return_pct REAL,
            prediction_score REAL,
            quality_score REAL,
            consensus_gain REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_news_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            snapshot_key TEXT NOT NULL,
            items_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_key TEXT NOT NULL,
            verdict TEXT NOT NULL,
            bullish_count INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0,
            signals_json TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            source_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS etf_flow_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_key TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            etfs_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_analysis_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            analysis_id TEXT NOT NULL,
            current_price REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            signal TEXT NOT NULL,
            signal_score REAL NOT NULL,
            trend_status TEXT NOT NULL,
            support_levels_json TEXT NOT NULL,
            resistance_levels_json TEXT NOT NULL,
            bullish_factors_json TEXT NOT NULL,
            risk_factors_json TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            news_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Add market column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN market TEXT NOT NULL DEFAULT 'us-stock'")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN token_id TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN outcome TEXT")
    except Exception:
        pass

    # Add cash column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN cash REAL DEFAULT 100000.0")
    except Exception:
        pass

    # Add deposited column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN deposited REAL DEFAULT 0.0")
    except Exception:
        pass

    # Add password_reset_token column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN password_reset_token TEXT")
    except Exception:
        pass

    # Add password_reset_expires_at column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN password_reset_expires_at TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN token_id TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN outcome TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN accepted_reply_id INTEGER")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signal_replies ADD COLUMN accepted INTEGER DEFAULT 0")
    except Exception:
        pass

    # Profit history table - tracks agent profit over time
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            position_value REAL NOT NULL,
            profit REAL NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_agent ON profit_history(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_recorded_at
        ON profit_history(recorded_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_agent_recorded_at
        ON profit_history(agent_id, recorded_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_market_symbol
        ON positions(market, symbol)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_polymarket_token
        ON positions(market, token_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_agent_message_type
        ON signals(agent_id, message_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_message_type ON signals(message_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_polymarket_token
        ON signals(market, token_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_polymarket_settlements_agent
        ON polymarket_settlements(agent_id, settled_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_type_created
        ON experiment_events(event_type, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_actor_created
        ON experiment_events(actor_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_target_created
        ON experiment_events(target_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_variant_created
        ON experiment_events(experiment_key, variant_key, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_object
        ON experiment_events(object_type, object_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_variant
        ON experiment_assignments(experiment_key, variant_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_agent_created
        ON agent_reward_ledger(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_source
        ON agent_reward_ledger(source_type, source_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenges_status_end
        ON challenges(status, end_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenges_key
        ON challenges(challenge_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_participants_agent
        ON challenge_participants(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_participants_challenge_rank
        ON challenge_participants(challenge_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_submissions_challenge_created
        ON challenge_submissions(challenge_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_trades_challenge_agent
        ON challenge_trades(challenge_id, agent_id, executed_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_trades_source_signal
        ON challenge_trades(source_signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_results_challenge_rank
        ON challenge_results(challenge_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_predictions_signal
        ON signal_predictions(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_predictions_agent_created
        ON signal_predictions(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_signal
        ON signal_quality_scores(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_agent_created
        ON signal_quality_scores(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_metric_snapshots_agent_window
        ON agent_metric_snapshots(agent_id, window_key, window_end_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_metric_snapshots_window
        ON agent_metric_snapshots(window_key, window_end_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_network_edges_source_created
        ON network_edges(source_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_network_edges_target_created
        ON network_edges(target_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_network_edges_type_created
        ON network_edges(edge_type, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_missions_status_due
        ON team_missions(status, submission_due_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_missions_key
        ON team_missions(mission_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_teams_mission_status
        ON teams(mission_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_teams_key
        ON teams(team_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_mission_participants_agent
        ON team_mission_participants(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_mission_participants_mission
        ON team_mission_participants(mission_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_members_agent
        ON team_members(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_members_team
        ON team_members(team_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_messages_team_created
        ON team_messages(team_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_messages_signal
        ON team_messages(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_submissions_team_created
        ON team_submissions(team_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_submissions_mission
        ON team_submissions(mission_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_contributions_mission_agent
        ON team_contributions(mission_id, agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_contributions_team
        ON team_contributions(team_id, contribution_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_results_mission_rank
        ON team_results(mission_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_news_category_created
        ON market_news_snapshots(category, created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_news_snapshot_key
        ON market_news_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_macro_signal_created
        ON macro_signal_snapshots(created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_macro_signal_snapshot_key
        ON macro_signal_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_flow_created
        ON etf_flow_snapshots(created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_flow_snapshot_key
        ON etf_flow_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_symbol_created
        ON stock_analysis_snapshots(symbol, created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_market_symbol
        ON stock_analysis_snapshots(market, symbol)
    """)

    # Audit log — append-only record of security-relevant actions.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            action TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_agent_created
        ON agent_audit_log(agent_id, created_at)
    """)

    # Token hash column — SHA-256 of the plaintext token.
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN token_hash TEXT")
    except Exception:
        pass

    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_token_hash ON agents(token_hash)")
    except Exception:
        pass

    # ── Phase 2: Broker execution layer ──────────────────────────────────────

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broker_accounts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id         INTEGER NOT NULL,
            broker           TEXT    NOT NULL,
            execution_mode   TEXT    NOT NULL DEFAULT 'paper',
            credentials_enc  TEXT,
            is_active        INTEGER NOT NULL DEFAULT 1,
            created_at       TEXT    DEFAULT (datetime('now')),
            updated_at       TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_accounts_agent
        ON broker_accounts(agent_id, is_active)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broker_orders (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id         INTEGER NOT NULL,
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
            signal_id        INTEGER,
            leader_id        INTEGER,
            token_id         TEXT,
            outcome          TEXT,
            created_at       TEXT    DEFAULT (datetime('now')),
            filled_at        TEXT,
            FOREIGN KEY (agent_id)  REFERENCES agents(id),
            FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_orders_agent_created
        ON broker_orders(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS position_reconciliations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id         INTEGER NOT NULL,
            broker           TEXT    NOT NULL,
            paper_order_id   INTEGER,
            broker_order_id  TEXT,
            symbol           TEXT    NOT NULL,
            paper_qty        NUMERIC(20,8),
            broker_qty       NUMERIC(20,8),
            drift            NUMERIC(20,8),
            status           TEXT    DEFAULT 'ok',
            error_message    TEXT,
            recorded_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (paper_order_id) REFERENCES broker_orders(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broker_live_optins (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id     INTEGER NOT NULL,
            broker       TEXT    NOT NULL,
            tcs_version  TEXT    NOT NULL DEFAULT 'v1',
            ip_address   TEXT,
            user_agent   TEXT,
            created_at   TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # ── Phase 3.5: strategies table ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id              INTEGER NOT NULL,
            name                  TEXT    NOT NULL,
            description           TEXT,
            config                TEXT,
            is_active             INTEGER NOT NULL DEFAULT 1,
            backtest_validated    INTEGER NOT NULL DEFAULT 0,
            last_backtest_sharpe  REAL,
            last_backtest_at      TEXT,
            created_at            TEXT DEFAULT (datetime('now')),
            updated_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategies_agent
        ON strategies(agent_id, is_active)
    """)

    # Add strategy_id FK to signals (idempotent try/except for existing DBs)
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN strategy_id INTEGER")
    except Exception:
        pass

    # ── Phase 3.4: backtest runs table ───────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id     INTEGER NOT NULL,
            strategy_id  INTEGER,
            status       TEXT    NOT NULL DEFAULT 'pending',
            config       TEXT    NOT NULL,
            result       TEXT,
            error_msg    TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            started_at   TEXT,
            completed_at TEXT,
            FOREIGN KEY (agent_id)    REFERENCES agents(id),
            FOREIGN KEY (strategy_id) REFERENCES strategies(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_backtest_runs_agent
        ON backtest_runs(agent_id, created_at)
    """)

    # ── Phase 3.8: tournaments (out-of-sample evaluation) ────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT    NOT NULL,
            description           TEXT,
            status                TEXT    NOT NULL DEFAULT 'open',
            submission_deadline   TEXT    NOT NULL,
            evaluation_start      TEXT    NOT NULL,
            evaluation_end        TEXT    NOT NULL,
            symbol                TEXT,
            market                TEXT    NOT NULL DEFAULT 'us-stock',
            initial_cash          REAL    NOT NULL DEFAULT 100000.0,
            created_by_agent_id   INTEGER REFERENCES agents(id),
            created_at            TEXT DEFAULT (datetime('now')),
            closed_at             TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tournaments_status
        ON tournaments(status, submission_deadline)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tournament_entries (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id     INTEGER NOT NULL REFERENCES tournaments(id),
            agent_id          INTEGER NOT NULL REFERENCES agents(id),
            strategy_id       INTEGER NOT NULL REFERENCES strategies(id),
            config_hash       TEXT    NOT NULL,
            config_snapshot   TEXT    NOT NULL,
            submitted_at      TEXT    NOT NULL,
            backtest_run_id   INTEGER REFERENCES backtest_runs(id),
            final_sharpe      REAL,
            final_return_pct  REAL,
            rank              INTEGER,
            UNIQUE(tournament_id, agent_id, strategy_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tournament_entries_lookup
        ON tournament_entries(tournament_id, rank)
    """)

    # ── Phase 4.7: reputation slashing audit log ──────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reputation_slashes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_id       INTEGER NOT NULL,
            signal_id       INTEGER,
            loss_pct        REAL    NOT NULL,
            follower_count  INTEGER NOT NULL,
            points_deducted INTEGER NOT NULL,
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (leader_id) REFERENCES agents(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reputation_slashes_leader
        ON reputation_slashes(leader_id, created_at)
    """)

    # ── Phase 4.4: materialized leaderboard snapshot ─────────────────────────
    # One row per (metric, rank). The worker rebuilds this every 30s by
    # running the leaderboard aggregate once and writing the result. Read
    # path is O(limit) instead of O(all agents).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard_snapshot (
            metric                  TEXT    NOT NULL,
            rank                    INTEGER NOT NULL,
            agent_id                INTEGER NOT NULL,
            name                    TEXT    NOT NULL,
            deposited               REAL    DEFAULT 0,
            profit                  REAL    DEFAULT 0,
            profit_percent          REAL    DEFAULT 0,
            trade_count             INTEGER DEFAULT 0,
            risk_adjusted_score     REAL    DEFAULT 0,
            collaboration_score     REAL    DEFAULT 0,
            quality_score_avg       REAL    DEFAULT 0,
            max_drawdown            REAL    DEFAULT 0,
            reply_count             INTEGER DEFAULT 0,
            accepted_reply_count    INTEGER DEFAULT 0,
            citation_count          INTEGER DEFAULT 0,
            adoption_count          INTEGER DEFAULT 0,
            metric_snapshot_id      INTEGER,
            metric_window_key       TEXT,
            metric_window_start_at  TEXT,
            metric_window_end_at    TEXT,
            recorded_at             TEXT,
            refreshed_at            TEXT    NOT NULL,
            PRIMARY KEY (metric, rank)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_leaderboard_snapshot_metric_rank
        ON leaderboard_snapshot(metric, rank)
    """)

    # ── Phase 4.4b: materialized signal feed ──────────────────────────────────
    # Pre-computes /api/signals/grouped results for all (message_type × market)
    # combos. rank=0 is a sentinel marking "combo computed but 0 agents"; rank≥1
    # are real agent rows sorted by last_signal_at DESC.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_feed_snapshot (
            message_type      TEXT    NOT NULL,
            market            TEXT    NOT NULL DEFAULT '',
            rank              INTEGER NOT NULL,
            agent_id          INTEGER NOT NULL DEFAULT 0,
            agent_name        TEXT    NOT NULL DEFAULT '',
            signal_count      INTEGER NOT NULL DEFAULT 0,
            total_pnl         REAL    NOT NULL DEFAULT 0,
            position_pnl      REAL    NOT NULL DEFAULT 0,
            position_count    INTEGER NOT NULL DEFAULT 0,
            positions_json    TEXT    NOT NULL DEFAULT '[]',
            last_signal_at    TEXT,
            latest_signal_id  INTEGER,
            latest_signal_type TEXT,
            total_for_filter  INTEGER NOT NULL DEFAULT 0,
            refreshed_at      TEXT    NOT NULL,
            PRIMARY KEY (message_type, market, rank)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_feed_snapshot_combo_rank
        ON signal_feed_snapshot(message_type, market, rank)
    """)

    # ── Phase 4.3: agent memory layer ─────────────────────────────────────────
    # Embeddings stored as JSON-stringified float arrays (TEXT in SQLite,
    # JSON in MySQL via the same column). Cosine similarity is computed
    # in Python at query time — brute force is fine within the 10 MB
    # per-agent quota because that caps the row count low enough.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    INTEGER NOT NULL,
            content     TEXT NOT NULL,
            embedding   TEXT,
            metadata    TEXT,
            created_at  TEXT NOT NULL,
            expires_at  TEXT,
            size_bytes  INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_memory_agent_created
        ON agent_memory(agent_id, created_at)
    """)

    # ── Phase 5: production auth — MFA columns + oauth_identities ────────────
    # MFA columns added idempotently (existing rows keep NULL/0 defaults).
    for sql in (
        "ALTER TABLE users ADD COLUMN mfa_secret TEXT",
        "ALTER TABLE users ADD COLUMN mfa_enabled INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN mfa_backup_codes TEXT",
    ):
        try:
            cursor.execute(sql)
        except Exception:
            pass

    # External-identity mapping: one row per (provider, provider_user_id).
    # A user can have multiple oauth_identities (e.g. Google + Apple) all
    # pointing at the same users.id.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_identities (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            provider          TEXT    NOT NULL,
            provider_user_id  TEXT    NOT NULL,
            email             TEXT,
            created_at        TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE (provider, provider_user_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_identities_user
        ON oauth_identities(user_id, provider)
    """)

    conn.commit()
    conn.close()
    print("[INFO] Database initialized")
