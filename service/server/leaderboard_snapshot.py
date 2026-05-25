"""leaderboard_snapshot.py — Phase 4.4 materialized leaderboard.

The /api/profit/history endpoint historically re-ran a 100-line CTE on
every request, then enriched per-agent. This module precomputes the
aggregate once and writes a sorted-by-metric snapshot to
`leaderboard_snapshot`. Reads become O(limit) instead of O(all agents).

Public surface:
  refresh_leaderboard_snapshot(top_n: int = 200) -> dict
      Sync. Computes once, writes 4 metric orderings (return / risk /
      collaboration / quality), returns a per-metric row-count summary.
      Atomic per-metric: DELETE then INSERT inside a single transaction
      so reads never see a half-built table.

  read_leaderboard_snapshot(metric, limit, offset) -> list[dict] | None
      Read a page of the snapshot. Returns None when no snapshot row
      exists for this metric (signalling the caller to fall back to the
      live aggregate). Returns [] when the table has rows for the metric
      but the page is past the end.

  snapshot_freshness_seconds() -> float | None
      Age of the most-recent refresh, or None when empty.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

import database

# Pulled in from routes_trading at the call site to avoid an import cycle
# (routes_trading imports from this module via the endpoint hot path).
INITIAL_CAPITAL = 100_000.0

METRICS: tuple[str, ...] = ("return", "risk", "collaboration", "quality")


def _utc_now_iso_z() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_agent_rows() -> list[dict[str, Any]]:
    """Run the leaderboard aggregate once, return all agents un-sorted.

    All four metric orderings are derived from this same row set in
    Python — running the SQL once instead of four times.
    """
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest_snapshots AS (
            SELECT ams.*
            FROM agent_metric_snapshots ams
            JOIN (
                SELECT agent_id, MAX(window_end_at) AS latest_window_end_at
                FROM agent_metric_snapshots
                GROUP BY agent_id
            ) latest
              ON latest.agent_id = ams.agent_id
             AND latest.latest_window_end_at = ams.window_end_at
        ),
        agent_profit AS (
            SELECT
                a.id AS agent_id,
                a.name,
                COALESCE(a.deposited, 0) AS deposited,
                (
                    COALESCE(a.cash, 0) +
                    COALESCE(
                        SUM(
                            CASE
                                WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                            END
                        ),
                        0
                    ) -
                    (? + COALESCE(a.deposited, 0))
                ) AS profit,
                (
                    (
                        COALESCE(a.cash, 0) +
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                    WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                    ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                                END
                            ),
                            0
                        ) -
                        (? + COALESCE(a.deposited, 0))
                    ) / NULLIF((? + COALESCE(a.deposited, 0)), 0) * 100
                ) AS profit_percent,
                (
                    SELECT COUNT(*)
                    FROM signals ops
                    WHERE ops.agent_id = a.id AND ops.message_type = 'operation'
                ) AS trade_count
            FROM agents a
            LEFT JOIN positions p ON p.agent_id = a.id
            GROUP BY a.id, a.name, a.cash, a.deposited
        )
        SELECT
            ap.*,
            COALESCE(ls.max_drawdown, 0) AS max_drawdown,
            COALESCE(ls.reply_count, 0) AS reply_count,
            COALESCE(ls.accepted_reply_count, 0) AS accepted_reply_count,
            COALESCE(ls.citation_count, 0) AS citation_count,
            COALESCE(ls.adoption_count, 0) AS adoption_count,
            COALESCE(ls.quality_score_avg, 0) AS quality_score_avg,
            ls.id AS metric_snapshot_id,
            ls.window_key AS metric_window_key,
            ls.window_start_at AS metric_window_start_at,
            ls.window_end_at AS metric_window_end_at,
            (ap.profit_percent - COALESCE(ls.max_drawdown, 0)) AS risk_adjusted_score,
            (
                COALESCE(ls.reply_count, 0) +
                COALESCE(ls.accepted_reply_count, 0) * 2 +
                COALESCE(ls.citation_count, 0) +
                COALESCE(ls.adoption_count, 0)
            ) AS collaboration_score
        FROM agent_profit ap
        LEFT JOIN latest_snapshots ls ON ls.agent_id = ap.agent_id
        """,
        (INITIAL_CAPITAL, INITIAL_CAPITAL, INITIAL_CAPITAL),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _sort_key(metric: str):
    """Sort key function — primary by metric DESC, tiebreak by profit_percent DESC, agent_id ASC.

    Matches the live endpoint's ORDER BY exactly so snapshot order is
    indistinguishable from a fresh live computation.
    """
    primary = {
        "return":        lambda r: float(r.get("profit_percent") or 0),
        "risk":          lambda r: float(r.get("risk_adjusted_score") or 0),
        "collaboration": lambda r: float(r.get("collaboration_score") or 0),
        "quality":       lambda r: float(r.get("quality_score_avg") or 0),
    }[metric]
    return lambda r: (
        -primary(r),
        -float(r.get("profit_percent") or 0),
        int(r.get("agent_id") or 0),
    )


def refresh_leaderboard_snapshot(top_n: int = 200) -> dict[str, Any]:
    """Recompute the snapshot. Returns a per-metric row-count summary."""
    agent_rows = _compute_agent_rows()
    now = _utc_now_iso_z()

    counts: dict[str, int] = {}
    conn = database.get_db_connection()
    cur = conn.cursor()
    try:
        for metric in METRICS:
            sorted_rows = sorted(agent_rows, key=_sort_key(metric))[:top_n]

            # Atomic-per-metric swap: same transaction as the delete.
            cur.execute(
                "DELETE FROM leaderboard_snapshot WHERE metric = ?",
                (metric,),
            )
            for rank_idx, row in enumerate(sorted_rows, start=1):
                cur.execute(
                    """
                    INSERT INTO leaderboard_snapshot (
                        metric, rank, agent_id, name, deposited,
                        profit, profit_percent, trade_count,
                        risk_adjusted_score, collaboration_score,
                        quality_score_avg, max_drawdown,
                        reply_count, accepted_reply_count,
                        citation_count, adoption_count,
                        metric_snapshot_id, metric_window_key,
                        metric_window_start_at, metric_window_end_at,
                        recorded_at, refreshed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        metric,
                        rank_idx,
                        row.get("agent_id"),
                        row.get("name") or "",
                        float(row.get("deposited") or 0),
                        float(row.get("profit") or 0),
                        float(row.get("profit_percent") or 0),
                        int(row.get("trade_count") or 0),
                        float(row.get("risk_adjusted_score") or 0),
                        float(row.get("collaboration_score") or 0),
                        float(row.get("quality_score_avg") or 0),
                        float(row.get("max_drawdown") or 0),
                        int(row.get("reply_count") or 0),
                        int(row.get("accepted_reply_count") or 0),
                        int(row.get("citation_count") or 0),
                        int(row.get("adoption_count") or 0),
                        row.get("metric_snapshot_id"),
                        row.get("metric_window_key"),
                        row.get("metric_window_start_at"),
                        row.get("metric_window_end_at"),
                        row.get("recorded_at"),
                        now,
                    ),
                )
            counts[metric] = len(sorted_rows)
        conn.commit()
    finally:
        conn.close()
    return {"refreshed_at": now, "rows": counts, "total_agents": len(agent_rows)}


def read_leaderboard_snapshot(
    metric: str,
    limit: int,
    offset: int = 0,
) -> Optional[list[dict[str, Any]]]:
    """Read a page of the snapshot.

    Returns None when no rows exist for this metric at all (snapshot not
    yet populated) — the caller should fall back to a live computation.
    Returns [] when the page is past the end of an otherwise-populated
    snapshot (no fallback needed).
    """
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM leaderboard_snapshot WHERE metric = ?",
        (metric,),
    )
    total_for_metric = cur.fetchone()
    total = total_for_metric["cnt"] if total_for_metric else 0
    if total == 0:
        conn.close()
        return None

    cur.execute(
        """
        SELECT *
        FROM leaderboard_snapshot
        WHERE metric = ?
        ORDER BY rank ASC
        LIMIT ? OFFSET ?
        """,
        (metric, limit, offset),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def snapshot_freshness_seconds() -> Optional[float]:
    """Seconds since the most recent refresh, or None when snapshot is empty."""
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT MAX(refreshed_at) AS r FROM leaderboard_snapshot")
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
    now = _dt.datetime.now(_dt.timezone.utc)
    return (now - refreshed).total_seconds()
