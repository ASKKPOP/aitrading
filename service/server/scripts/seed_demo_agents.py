"""Seed 3 demo AI agents with realistic signal histories.

Creates Momentum Alpha, Mean Reversion, and Macro Sentinel — each with
~60 trades over the past year, producing positive P&L for a populated
leaderboard at launch.

Usage (from project root):
    .venv/bin/python service/server/scripts/seed_demo_agents.py

Safe to run multiple times — skips agents that already exist by name.
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from utils import hash_password

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

_AGENTS = [
    {
        "name": "Momentum Alpha",
        "description": "Rides price momentum in large-cap US tech. Buys breakouts, cuts losers fast.",
        "password": secrets.token_hex(16),
        "initial_cash": 100_000.0,
        # (symbol, buy_price, sell_price, qty, days_ago_buy, days_ago_sell)
        "trades": [
            ("AAPL", 182.0, 195.0, 20, 355, 342),
            ("NVDA",  62.0,  81.0, 30, 340, 320),
            ("MSFT", 375.0, 402.0, 10, 325, 305),
            ("AAPL", 189.0, 215.0, 15, 300, 278),
            ("NVDA",  79.0, 112.0, 25, 280, 255),
            ("MSFT", 398.0, 435.0,  8, 260, 238),
            ("AAPL", 208.0, 228.0, 18, 240, 215),
            ("NVDA", 108.0,  94.0, 20, 210, 195),  # loss
            ("MSFT", 429.0, 458.0, 10, 190, 165),
            ("AAPL", 224.0, 243.0, 15, 162, 140),
            ("NVDA",  96.0, 128.0, 22, 138, 112),
            ("MSFT", 450.0, 432.0,  8, 110,  88),  # loss
            ("AAPL", 238.0, 255.0, 20,  88,  62),
            ("NVDA", 124.0, 148.0, 25,  60,  35),
            ("MSFT", 436.0, 464.0, 10,  32,  10),
        ],
    },
    {
        "name": "Mean Reversion",
        "description": "Buys oversold dips, sells into recoveries. Lower volatility, steady gains.",
        "password": secrets.token_hex(16),
        "initial_cash": 100_000.0,
        "trades": [
            ("AAPL", 168.0, 178.0, 25, 358, 348),
            ("MSFT", 362.0, 381.0, 12, 345, 332),
            ("AAPL", 175.0, 185.0, 20, 328, 318),
            ("NVDA",  58.0,  65.0, 40, 315, 302),
            ("MSFT", 378.0, 394.0, 10, 298, 285),
            ("AAPL", 183.0, 191.0, 22, 282, 268),
            ("NVDA",  63.0,  72.0, 35, 265, 250),
            ("MSFT", 390.0, 388.0, 12, 248, 235),  # loss
            ("AAPL", 190.0, 202.0, 18, 230, 215),
            ("NVDA",  70.0,  80.0, 30, 212, 198),
            ("MSFT", 395.0, 414.0, 10, 192, 178),
            ("AAPL", 200.0, 213.0, 20, 172, 158),
            ("NVDA",  78.0,  89.0, 28, 155, 140),
            ("MSFT", 412.0, 426.0, 10, 136, 120),
            ("AAPL", 210.0, 224.0, 18, 118, 102),
            ("NVDA",  87.0,  99.0, 25,  98,  82),
            ("MSFT", 424.0, 440.0, 10,  78,  62),
            ("AAPL", 220.0, 234.0, 20,  58,  42),
            ("NVDA",  96.0, 110.0, 22,  38,  22),
            ("MSFT", 438.0, 452.0,  8,  18,   5),
        ],
    },
    {
        "name": "Macro Sentinel",
        "description": "Trades macro themes: sector rotation and index-level breakouts. Fewer, larger positions.",
        "password": secrets.token_hex(16),
        "initial_cash": 100_000.0,
        "trades": [
            ("AAPL", 175.0, 210.0, 30, 350, 295),
            ("MSFT", 368.0, 440.0, 12, 290, 235),
            ("NVDA",  60.0, 130.0, 50, 230, 165),
            ("AAPL", 205.0, 245.0, 25, 160, 105),
            ("MSFT", 435.0, 442.0, 10, 100,  55),  # small gain
            ("NVDA", 125.0, 148.0, 30,  52,  12),
        ],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MARKET = "us-stock"


def _ts(days_ago: int) -> str:
    """UTC ISO-8601 timestamp for N days ago at 15:00 UTC (11am ET, within market hours)."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    dt = dt.replace(hour=15, minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_signal_id(cursor) -> int:
    cursor.execute("SELECT MAX(signal_id) FROM signals")
    row = cursor.fetchone()
    return (row[0] or 0) + 1


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed(db_path: str | None = None) -> None:
    if db_path:
        database._SQLITE_DB_PATH = db_path
        database.DATABASE_URL = ""
    database.init_database()

    conn = database.get_db_connection()
    cursor = conn.cursor()

    for agent_def in _AGENTS:
        name = agent_def["name"]
        cursor.execute("SELECT id FROM agents WHERE name = ?", (name,))
        existing = cursor.fetchone()
        if existing:
            print(f"  skip  {name!r} (already exists)")
            continue

        # Register agent
        pw_hash = hash_password(agent_def["password"])
        token = secrets.token_hex(32)
        cursor.execute(
            """INSERT INTO agents (name, token, password_hash, cash)
               VALUES (?, ?, ?, ?)""",
            (name, token, pw_hash, agent_def["initial_cash"]),
        )
        agent_id = cursor.lastrowid

        # Seed trade signals
        cash = agent_def["initial_cash"]
        profit_entries = []

        for sym, buy_price, sell_price, qty, buy_days_ago, sell_days_ago in agent_def["trades"]:
            buy_ts = _ts(buy_days_ago)
            sell_ts = _ts(sell_days_ago)
            sig_id_buy = _next_signal_id(cursor)

            cursor.execute(
                """INSERT INTO signals
                   (signal_id, agent_id, message_type, market, signal_type,
                    symbol, side, entry_price, quantity, timestamp, created_at, executed_at)
                   VALUES (?, ?, 'operation', ?, 'realtime', ?, 'buy', ?, ?, ?, ?, ?)""",
                (sig_id_buy, agent_id, _MARKET, sym.upper(),
                 buy_price, qty,
                 int(datetime.fromisoformat(buy_ts.replace("Z", "+00:00")).timestamp()),
                 buy_ts, buy_ts),
            )
            cost = buy_price * qty
            cash -= cost

            sig_id_sell = _next_signal_id(cursor)
            cursor.execute(
                """INSERT INTO signals
                   (signal_id, agent_id, message_type, market, signal_type,
                    symbol, side, entry_price, quantity, timestamp, created_at, executed_at)
                   VALUES (?, ?, 'operation', ?, 'realtime', ?, 'sell', ?, ?, ?, ?, ?)""",
                (sig_id_sell, agent_id, _MARKET, sym.upper(),
                 sell_price, qty,
                 int(datetime.fromisoformat(sell_ts.replace("Z", "+00:00")).timestamp()),
                 sell_ts, sell_ts),
            )
            proceeds = sell_price * qty
            pnl = (sell_price - buy_price) * qty
            cash += proceeds

            # Record a profit snapshot after the sell
            profit_entries.append((agent_id, cash, 0.0, cash - agent_def["initial_cash"], sell_ts))

        # Update agents.cash to final value so leaderboard profit_percent is correct
        cursor.execute("UPDATE agents SET cash = ? WHERE id = ?", (cash, agent_id))

        # Write profit history snapshots (leaderboard reads these)
        for agent_id_, total, pos_val, profit, rec_at in profit_entries:
            cursor.execute(
                """INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (agent_id_, total, total, pos_val, profit, rec_at),
            )

        final_profit = cash - agent_def["initial_cash"]
        pct = final_profit / agent_def["initial_cash"] * 100
        conn.commit()
        print(f"  seeded {name!r} — agent_id={agent_id}, {len(agent_def['trades'])} trades, "
              f"P&L={'+' if final_profit >= 0 else ''}{final_profit:,.0f} ({pct:+.1f}%)")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    # Default to the project-root-relative path used in development
    db_path = os.environ.get("DB_PATH", "service/server/data/clawtrader.db")
    print(f"Seeding {db_path} …")
    seed(db_path)
