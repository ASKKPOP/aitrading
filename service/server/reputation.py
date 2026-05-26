"""Phase 4.7 — reputation slashing.

A signal publisher's reputation_score is decremented when a published signal
produces a loss greater than SLASH_THRESHOLD_PCT for their copiers.
Deduction is proportional to active follower count at the time of the slash.
"""
from __future__ import annotations

import database

SLASH_THRESHOLD_PCT: float = 2.0
SLASH_POINTS_PER_FOLLOWER: int = 1


def compute_slash_points(loss_pct: float, follower_count: int) -> int:
    """Return points to deduct from the signal publisher's reputation.

    loss_pct: absolute loss percentage (positive; e.g. 5.0 means a 5% loss).
    follower_count: number of active copiers at evaluation time.
    Returns 0 when loss is at or below SLASH_THRESHOLD_PCT.
    """
    if loss_pct <= SLASH_THRESHOLD_PCT:
        return 0
    return follower_count * SLASH_POINTS_PER_FOLLOWER


def count_active_followers(leader_id: int) -> int:
    """Count active subscriptions for a leader agent."""
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE leader_id=? AND status='active'",
        (leader_id,),
    )
    n = cur.fetchone()["n"]
    conn.close()
    return n


def apply_reputation_slash(
    leader_id: int,
    signal_id: int | None,
    loss_pct: float,
    follower_count: int,
) -> int:
    """Apply a reputation slash to leader_id and record it in reputation_slashes.

    Returns the number of points deducted (0 if below threshold or no followers).
    """
    points = compute_slash_points(loss_pct, follower_count)

    conn = database.get_db_connection()
    cur = conn.cursor()
    if points > 0:
        cur.execute(
            "UPDATE agents SET reputation_score = reputation_score - ? WHERE id=?",
            (points, leader_id),
        )
    cur.execute(
        """INSERT INTO reputation_slashes
           (leader_id, signal_id, loss_pct, follower_count, points_deducted)
           VALUES (?, ?, ?, ?, ?)""",
        (leader_id, signal_id, loss_pct, follower_count, points),
    )
    conn.commit()
    conn.close()
    return points
