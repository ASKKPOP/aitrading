"""signal_feed_snapshot.py — Phase 4.4b materialized signal feed.

The /api/signals/grouped endpoint joins signals + agents + positions on every
request and relies on a short-lived Redis/in-process cache that is cold on
the first hit after each TTL expiry. This module pre-computes all
(message_type × market) filter combinations once and writes rank-ordered rows
to `signal_feed_snapshot`. Reads become O(limit) instead of O(all agents ×
positions).

Public surface:
  refresh_signal_feed_snapshot(top_n: int = 200) -> dict
      Sync. Computes every filter combo, writes rows sorted by
      last_signal_at DESC. Atomic per-combo: DELETE then INSERT so reads
      never see a half-built result. rank=0 rows are sentinels marking "combo
      computed but 0 agents" so callers can distinguish empty-snapshot from
      snapshot-not-yet-populated.

  read_signal_feed_snapshot(message_type, market, limit, offset)
        -> tuple[list[dict], int] | None
      Read a page from the snapshot. Returns None when the combo has no rows
      at all (snapshot not yet populated — caller should fall back to live
      query). Returns (rows, total) when populated; rows may be [] when the
      requested page is past the end.

  snapshot_freshness_seconds() -> float | None
      Age of the most recent refresh, or None when the table is empty.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Optional

import database

# All (message_type, market) combinations pre-computed each refresh cycle.
# market='' means no market filter ("all markets").
FILTER_COMBOS: tuple[tuple[str, str], ...] = (
    ("operation", ""),
    ("operation", "us-stock"),
    ("operation", "crypto"),
    ("operation", "polymarket"),
    ("strategy", ""),
    ("strategy", "us-stock"),
    ("strategy", "crypto"),
    ("strategy", "polymarket"),
    ("discussion", ""),
    ("discussion", "us-stock"),
    ("discussion", "crypto"),
    ("discussion", "polymarket"),
)


def _utc_now_iso_z() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_agents_for_combo(
    cursor: Any,
    message_type: str,
    market: str,
    top_n: int,
) -> tuple[list[dict[str, Any]], int]:
    """Run the grouped-signals aggregate for one filter combo.

    Returns (agent_rows, total_agent_count) sorted by last_signal_at DESC,
    capped at top_n. agent_rows includes positions with PnL computation.
    """
    conditions: list[str] = []
    params: list[Any] = []
    if message_type:
        conditions.append("s.message_type = ?")
        params.append(message_type)
    if market:
        conditions.append("s.market = ?")
        params.append(market)
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Count agents that have at least one matching signal.
    cursor.execute(
        f"""
        SELECT COUNT(*) AS total FROM (
            SELECT a.id
            FROM agents a
            LEFT JOIN signals s ON s.agent_id = a.id AND {where_clause}
            GROUP BY a.id
            HAVING COUNT(s.id) > 0
        ) grouped_agents
        """,
        params,
    )
    row = cursor.fetchone()
    total = row["total"] if row else 0

    if total == 0:
        return [], 0

    cursor.execute(
        f"""
        SELECT
            a.id AS agent_id,
            a.name AS agent_name,
            COUNT(s.id) AS signal_count,
            COALESCE(SUM(s.pnl), 0) AS total_pnl,
            MAX(s.created_at) AS last_signal_at,
            (SELECT s2.signal_id FROM signals s2
             WHERE s2.agent_id = a.id
             ORDER BY s2.created_at DESC LIMIT 1) AS latest_signal_id,
            (SELECT s3.message_type FROM signals s3
             WHERE s3.agent_id = a.id
             ORDER BY s3.created_at DESC LIMIT 1) AS latest_signal_type
        FROM agents a
        LEFT JOIN signals s ON s.agent_id = a.id AND {where_clause}
        GROUP BY a.id
        HAVING COUNT(s.id) > 0
        ORDER BY last_signal_at DESC
        LIMIT ?
        """,
        params + [top_n],
    )
    rows = [dict(r) for r in cursor.fetchall()]

    # Batch-load positions for all returned agents.
    agent_ids = [r["agent_id"] for r in rows]
    positions_by_agent: dict[int, list[dict]] = {}
    if agent_ids:
        placeholders = ",".join("?" for _ in agent_ids)
        cursor.execute(
            f"""
            SELECT agent_id, symbol, market, token_id, outcome,
                   side, quantity, entry_price, current_price
            FROM positions
            WHERE agent_id IN ({placeholders})
            ORDER BY opened_at DESC
            """,
            agent_ids,
        )
        for pos in cursor.fetchall():
            positions_by_agent.setdefault(pos["agent_id"], []).append(dict(pos))

    # Build enriched agent payload with position PnL.
    agents: list[dict[str, Any]] = []
    for r in rows:
        aid = r["agent_id"]
        pos_list = positions_by_agent.get(aid, [])
        total_pos_pnl = 0.0
        positions = []
        for p in pos_list:
            pnl = None
            if p.get("current_price") and p.get("entry_price"):
                if p["side"] == "long":
                    pnl = (p["current_price"] - p["entry_price"]) * abs(p["quantity"])
                else:
                    pnl = (p["entry_price"] - p["current_price"]) * abs(p["quantity"])
            if pnl:
                total_pos_pnl += pnl
            positions.append({
                "symbol": p.get("symbol"),
                "market": p.get("market"),
                "token_id": p.get("token_id"),
                "outcome": p.get("outcome"),
                "side": p.get("side"),
                "quantity": p.get("quantity"),
                "current_price": p.get("current_price"),
                "pnl": pnl,
            })
        agents.append({
            "agent_id": aid,
            "agent_name": r["agent_name"],
            "signal_count": r["signal_count"],
            "total_pnl": float(r.get("total_pnl") or 0),
            "position_pnl": total_pos_pnl,
            "position_count": len(pos_list),
            "positions": positions,
            "last_signal_at": r.get("last_signal_at"),
            "latest_signal_id": r.get("latest_signal_id"),
            "latest_signal_type": r.get("latest_signal_type"),
        })
    return agents, total


def refresh_signal_feed_snapshot(top_n: int = 200) -> dict[str, Any]:
    """Recompute and persist the snapshot for all filter combos.

    Uses two separate connections so the heavy read queries don't share a
    transaction with the write side. Atomic per combo: DELETE then INSERT.
    """
    now = _utc_now_iso_z()
    read_conn = database.get_db_connection()
    read_cur = read_conn.cursor()
    write_conn = database.get_db_connection()
    write_cur = write_conn.cursor()

    combo_counts: dict[str, int] = {}
    try:
        for message_type, market in FILTER_COMBOS:
            agents, total = _compute_agents_for_combo(read_cur, message_type, market, top_n)
            combo_key = f"{message_type}:{market or 'all'}"

            write_cur.execute(
                "DELETE FROM signal_feed_snapshot WHERE message_type = ? AND market = ?",
                (message_type, market),
            )
            # Sentinel row (rank=0) records that this combo has been computed and
            # stores the total count so readers don't need a second COUNT query.
            write_cur.execute(
                """
                INSERT INTO signal_feed_snapshot (
                    message_type, market, rank,
                    agent_id, agent_name,
                    signal_count, total_pnl, position_pnl, position_count,
                    positions_json, last_signal_at,
                    latest_signal_id, latest_signal_type,
                    total_for_filter, refreshed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (message_type, market, 0, 0, "_sentinel_",
                 0, 0.0, 0.0, 0, "[]", None, None, None, total, now),
            )
            for rank_idx, agent in enumerate(agents, start=1):
                write_cur.execute(
                    """
                    INSERT INTO signal_feed_snapshot (
                        message_type, market, rank,
                        agent_id, agent_name,
                        signal_count, total_pnl, position_pnl, position_count,
                        positions_json, last_signal_at,
                        latest_signal_id, latest_signal_type,
                        total_for_filter, refreshed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        message_type, market, rank_idx,
                        agent["agent_id"], agent["agent_name"],
                        agent["signal_count"], agent["total_pnl"],
                        agent["position_pnl"], agent["position_count"],
                        json.dumps(agent["positions"]),
                        agent.get("last_signal_at"),
                        agent.get("latest_signal_id"),
                        agent.get("latest_signal_type"),
                        total, now,
                    ),
                )
            combo_counts[combo_key] = len(agents)
        write_conn.commit()
    finally:
        read_conn.close()
        write_conn.close()

    return {"refreshed_at": now, "rows": combo_counts}


def read_signal_feed_snapshot(
    message_type: str,
    market: str,
    limit: int,
    offset: int = 0,
) -> Optional[tuple[list[dict[str, Any]], int]]:
    """Read a page of the materialized signal feed.

    Returns None when the combo has no rows at all (snapshot not yet
    populated) — the caller should fall back to a live DB query.
    Returns (rows, total) when populated. rows is [] when the requested
    page is past the end of the data (no live fallback needed).
    """
    conn = database.get_db_connection()
    cur = conn.cursor()

    # Check for the sentinel row that marks this combo as computed.
    cur.execute(
        "SELECT total_for_filter FROM signal_feed_snapshot"
        " WHERE message_type = ? AND market = ? AND rank = 0",
        (message_type, market),
    )
    sentinel = cur.fetchone()
    if sentinel is None:
        conn.close()
        return None

    total = sentinel["total_for_filter"]

    cur.execute(
        """
        SELECT *
        FROM signal_feed_snapshot
        WHERE message_type = ? AND market = ? AND rank > 0
        ORDER BY rank ASC
        LIMIT ? OFFSET ?
        """,
        (message_type, market, limit, offset),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["positions"] = json.loads(d.get("positions_json") or "[]")
        rows.append(d)

    conn.close()
    return rows, total


def snapshot_freshness_seconds() -> Optional[float]:
    """Seconds since the most recent refresh, or None when table is empty."""
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT MAX(refreshed_at) AS r FROM signal_feed_snapshot")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    refreshed_at = row["r"]
    if not refreshed_at:
        return None
    try:
        refreshed = _dt.datetime.fromisoformat(str(refreshed_at).replace("Z", "+00:00"))
    except Exception:
        return None
    return (_dt.datetime.now(_dt.timezone.utc) - refreshed).total_seconds()
