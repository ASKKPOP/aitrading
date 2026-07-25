"""Server-side analysis pipeline jobs — detached from the HTTP connection.

The Analyst / Automation pages used to consume POST /api/analysis/run/stream
(SSE): closing the page aborted the stream, which cancelled the run and lost
all progress. A job instead runs in a daemon thread on the server and persists
every step event plus the final result to the analysis_jobs table, so leaving
the page loses nothing and returning restores the exact same monitor state.

One job per agent runs at a time; the newest row is "current". A job left in
status 'running' by a server restart is marked as error at startup
(mark_stale_jobs) or lazily by start_job once it exceeds STALE_MINUTES.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from analysis_agents import run_analysis
from database import begin_write_transaction, get_db_connection, using_mysql

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None so a job result survives
    Starlette's allow_nan=False JSON renderer. A technical indicator that is
    undefined (ma200 on <200 bars, sigma on a gappy feed) arrives here as NaN;
    left in place it 500s /api/analysis/jobs/current on every poll. null is the
    correct wire value for "not computable"."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj

# A running job older than this is presumed dead (crashed thread / killed
# process) and is replaced instead of blocking new runs forever.
STALE_MINUTES = 15


def _now_iso() -> str:
    # Same format as notifications.py / alerts.py so stored timestamps stay uniform.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_config(agent_id: int, config_id: int) -> Optional[dict]:
    """The caller's automation rule, or None when absent / not theirs."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_configs WHERE id = ? AND agent_id = ?",
                       (config_id, agent_id))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _finish_job(job_id: int, status: str, *, result: Optional[dict] = None,
                gates: Optional[dict] = None, error: Optional[str] = None) -> None:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE analysis_jobs SET status = ?, result_json = ?, gates_json = ?,
               error = ?, finished_at = ? WHERE id = ?""",
            (status,
             json.dumps(_json_safe(result), ensure_ascii=False, default=str) if result else None,
             json.dumps(_json_safe(gates), ensure_ascii=False, default=str) if gates else None,
             error, _now_iso(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _run_job(job_id: int, agent_id: int, symbol: str, market: str, lang: str,
             provider: Optional[str], config_id: Optional[int]) -> None:
    """Thread body: run the pipeline, persisting each step event as it happens."""
    events: list[dict] = []
    lock = threading.Lock()

    def progress(evt: dict) -> None:
        # Called from worker threads inside the pipeline. Each event is tiny
        # and a full run emits ~25, so persisting on every event is cheap.
        with lock:
            events.append(evt)
            payload = json.dumps(events, ensure_ascii=False, default=str)
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("UPDATE analysis_jobs SET events_json = ? WHERE id = ?",
                               (payload, job_id))
                conn.commit()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 — progress persistence must not kill the run
            logger.exception("failed to persist progress for analysis job %s", job_id)

    try:
        result = run_analysis(symbol, market, lang, provider, agent_id,
                              progress=progress)
    except Exception as exc:  # noqa: BLE001
        _finish_job(job_id, "error", error=str(exc)[:500])
        return

    # Automation test-run: report whether the worker's execution gates would
    # have placed this trade. Fail-soft — a preview problem never hides the result.
    gates = None
    if config_id:
        try:
            config = _load_config(agent_id, config_id)
            if config is not None:
                from automation import preview_rule_execution
                gates = preview_rule_execution(config, result)
        except Exception:  # noqa: BLE001
            logger.exception("gate preview failed for analysis job %s", job_id)
    _finish_job(job_id, "done", result=result, gates=gates)


def start_job(agent_id: int, symbol: str, market: str, lang: str,
              provider: Optional[str] = None,
              config_id: Optional[int] = None) -> dict[str, Any]:
    """Start a pipeline run for this agent, or return the one already running."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Single-flight guard: serialize the check-then-insert so two
        # concurrent POSTs cannot both start a pipeline run. SQLite: BEGIN
        # IMMEDIATE takes the write lock up front; MySQL: FOR UPDATE makes
        # the check a locking read (gap lock blocks the racing insert).
        begin_write_transaction(cursor)
        cursor.execute(
            """SELECT id, created_at FROM analysis_jobs
               WHERE agent_id = ? AND status = 'running'
               ORDER BY id DESC LIMIT 1"""
            + (" FOR UPDATE" if using_mysql() else ""),
            (agent_id,))
        running = cursor.fetchone()
        if running:
            running = dict(running)
            age_min = None
            try:
                created = datetime.fromisoformat(running["created_at"])
                age_min = (datetime.now(timezone.utc) - created).total_seconds() / 60
            except (TypeError, ValueError):
                pass
            if age_min is not None and age_min < STALE_MINUTES:
                return {"job_id": running["id"], "status": "running",
                        "already_running": True}
            cursor.execute(
                """UPDATE analysis_jobs SET status = 'error',
                   error = 'job abandoned (server restart or crash)', finished_at = ?
                   WHERE id = ?""",
                (_now_iso(), running["id"]))
        cursor.execute(
            """INSERT INTO analysis_jobs
               (agent_id, symbol, market, lang, provider, config_id, status,
                events_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', '[]', ?)""",
            (agent_id, symbol, market, lang, provider, config_id, _now_iso()))
        job_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    threading.Thread(
        target=_run_job,
        args=(job_id, agent_id, symbol, market, lang, provider, config_id),
        name=f"analysis-job-{job_id}", daemon=True,
    ).start()
    return {"job_id": job_id, "status": "running", "already_running": False}


def get_current_job(agent_id: int) -> Optional[dict[str, Any]]:
    """The agent's newest job (running or finished), events/result parsed."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM analysis_jobs WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
            (agent_id,))
        row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    row = dict(row)

    def parse(text: Optional[str], fallback: Any) -> Any:
        if not text:
            return fallback
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return fallback

    # _json_safe also on read: rows persisted before the write-side guard (or by
    # json.dumps' default allow_nan=True) hold literal NaN that json.loads
    # restores as float nan — sanitise so the endpoint never 500s on old data.
    return _json_safe({
        "job_id": row["id"],
        "symbol": row["symbol"],
        "market": row["market"],
        "lang": row["lang"],
        "provider": row["provider"],
        "config_id": row["config_id"],
        "status": row["status"],
        "events": parse(row.get("events_json"), []),
        "result": parse(row.get("result_json"), None),
        "gates": parse(row.get("gates_json"), None),
        "error": row.get("error"),
        "created_at": row["created_at"],
        "finished_at": row.get("finished_at"),
    })


def mark_stale_jobs() -> int:
    """Startup cleanup: any job still 'running' belongs to a dead process."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE analysis_jobs SET status = 'error',
               error = 'job abandoned (server restart)', finished_at = ?
               WHERE status = 'running'""",
            (_now_iso(),))
        count = cursor.rowcount or 0
        conn.commit()
        return count
    finally:
        conn.close()
