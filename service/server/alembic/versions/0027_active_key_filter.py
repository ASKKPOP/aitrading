"""Rewrite active_key to the filter-scoped format.

Exclusivity used to be one active run per agent+market+symbol, stored as the
composite string "agent:market:symbol" in the UNIQUE `active_key` column. It
now includes the run's filter key (instrument type + interval + minimum
confidence + AI provider), so several strategies may run on one symbol and
only an exact duplicate collides.

Runs that were already active when this ships still hold a legacy key. That
matters: `_guard_active_key` short-circuits on any non-NULL key, so those rows
would never upgrade themselves, and a genuinely-duplicate new run would be
written with the new format and slip past the UNIQUE index. Recompute every
active key here so the whole column speaks one language.

Backfilling by hand rather than in SQL because the filter key is a digest of
each run's own config snapshot.

Revision ID: 0027
Revises: 0026
"""
import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _filter_key(market_type, cfg):
    """Mirror of trading_runs.filter_key — kept literal so a later edit to the
    live function cannot silently change what this migration already wrote."""
    parts = (
        (market_type or "spot").strip().lower(),
        str(int(cfg.get("interval_minutes") or 60)),
        f"{float(cfg.get('min_confidence') or 0):.4f}",
        (cfg.get("provider") or "-").strip().lower(),
    )
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, agent_id, market, symbol, market_type, config_snapshot_json "
        "FROM trading_runs WHERE active_key IS NOT NULL"
    )).mappings().all()
    for row in rows:
        try:
            cfg = json.loads(row["config_snapshot_json"] or "{}")
        except Exception:  # noqa: BLE001
            cfg = {}
        key = (f"{row['agent_id']}:{row['market']}:{row['symbol']}:"
               f"{_filter_key(row['market_type'], cfg)}")
        conn.execute(sa.text("UPDATE trading_runs SET active_key = :k WHERE id = :i"),
                     {"k": key, "i": row["id"]})


def downgrade():
    """Back to agent:market:symbol. Two active runs that differ only by filter
    would collide on the UNIQUE index, so the newer of each pair is released
    (its key set NULL) — the engine's guard then pauses it as a duplicate,
    which is the pre-filter behaviour."""
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, agent_id, market, symbol FROM trading_runs "
        "WHERE active_key IS NOT NULL ORDER BY id"
    )).mappings().all()
    seen = set()
    for row in rows:
        key = f"{row['agent_id']}:{row['market']}:{row['symbol']}"
        if key in seen:
            conn.execute(sa.text("UPDATE trading_runs SET active_key = NULL WHERE id = :i"),
                         {"i": row["id"]})
            continue
        seen.add(key)
        conn.execute(sa.text("UPDATE trading_runs SET active_key = :k WHERE id = :i"),
                     {"k": key, "i": row["id"]})
