"""
routes_backtest.py — Backtest runs API.

Endpoints:
  POST   /api/backtest/runs               create a run (async background execution)
  GET    /api/backtest/runs               list runs for the authenticated agent
  GET    /api/backtest/runs/{run_id}      get run status + result
  GET    /api/backtest/runs/{run_id}/trades  closed trades from a completed run
  DELETE /api/backtest/runs/{run_id}      delete a run
  POST   /api/backtest/runs/{run_id}/promote  link run result to a strategy

Background execution: uses FastAPI BackgroundTasks so the POST returns immediately
with status=pending and the backtest completes asynchronously.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

import database
from backtest import run_backtest
from routes_shared import RouteContext, utc_now_iso_z

_logger = logging.getLogger(__name__)


# ── Request models ────────────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    start_at:     str
    end_at:       str
    initial_cash: float        = Field(default=100_000.0, gt=0)
    market:       Optional[str] = None
    symbol:       Optional[str] = None
    strategy_id:  Optional[int] = None


class PromoteRunRequest(BaseModel):
    strategy_id: int


# ── Background task ───────────────────────────────────────────────────────────

def _execute_run(run_id: int, agent_id: int, config: dict) -> None:
    """Run the backtest synchronously and persist the result."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE backtest_runs SET status='running', started_at=? WHERE id=?",
        (utc_now_iso_z(), run_id),
    )
    conn.commit()
    conn.close()

    try:
        from dataclasses import asdict
        result = run_backtest(
            agent_id=agent_id,
            start_at=config["start_at"],
            end_at=config["end_at"],
            initial_cash=config.get("initial_cash", 100_000.0),
            market=config.get("market"),
            symbol=config.get("symbol"),
        )
        result_json = json.dumps({
            "summary": {
                "initial_cash":      result.initial_cash,
                "final_value":       result.final_value,
                "total_return_pct":  result.total_return_pct,
                "max_drawdown_pct":  result.max_drawdown_pct,
                "trade_count":       result.trade_count,
                "winning_trades":    result.winning_trades,
                "losing_trades":     result.losing_trades,
                "win_rate":          result.win_rate,
                "sharpe_ratio":      result.sharpe_ratio,
            },
            "closed_trades":  [asdict(t) for t in result.closed_trades],
            "open_positions": result.open_positions,
            "curve":          [asdict(p) for p in result.curve],
        })
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE backtest_runs
               SET status='completed', result=?, completed_at=? WHERE id=?""",
            (result_json, utc_now_iso_z(), run_id),
        )
        conn.commit()
        conn.close()
        _logger.info("[backtest] run %s completed for agent %s", run_id, agent_id)
    except Exception as exc:  # noqa: BLE001
        _logger.exception("[backtest] run %s failed", run_id)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE backtest_runs
               SET status='failed', error_msg=?, completed_at=? WHERE id=?""",
            (str(exc), utc_now_iso_z(), run_id),
        )
        conn.commit()
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_agent(req: Request) -> dict:
    from services import _get_agent_by_token
    auth = req.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required")
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _get_run_or_404(run_id: int, agent_id: int) -> dict:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM backtest_runs WHERE id=? AND agent_id=?",
        (run_id, agent_id),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(row)


def _row_to_response(row: dict) -> dict:
    result = None
    if row.get("result"):
        try:
            result = json.loads(row["result"])
        except Exception:
            pass
    config = {}
    if row.get("config"):
        try:
            config = json.loads(row["config"])
        except Exception:
            pass
    return {
        "run_id":       row["id"],
        "agent_id":     row["agent_id"],
        "strategy_id":  row.get("strategy_id"),
        "status":       row["status"],
        "config":       config,
        "result":       result,
        "error_msg":    row.get("error_msg"),
        "created_at":   row["created_at"],
        "started_at":   row.get("started_at"),
        "completed_at": row.get("completed_at"),
    }


# ── Route registration ────────────────────────────────────────────────────────

def register_backtest_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/backtest/runs", status_code=201)
    def create_run(req: Request, body: BacktestRunRequest, bg: BackgroundTasks):
        agent = _require_agent(req)
        config = {
            "start_at":     body.start_at,
            "end_at":       body.end_at,
            "initial_cash": body.initial_cash,
            "market":       body.market,
            "symbol":       body.symbol,
            "strategy_id":  body.strategy_id,
        }
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO backtest_runs (agent_id, strategy_id, status, config, created_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (agent["id"], body.strategy_id, json.dumps(config), utc_now_iso_z()),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        bg.add_task(_execute_run, run_id, agent["id"], config)
        return {"run_id": run_id, "status": "pending"}

    @app.get("/api/backtest/runs")
    def list_runs(req: Request, limit: int = 50, offset: int = 0):
        agent = _require_agent(req)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM backtest_runs WHERE agent_id=?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (agent["id"], limit, offset),
        )
        rows = [_row_to_response(dict(r)) for r in cursor.fetchall()]
        conn.close()
        return {"runs": rows}

    @app.get("/api/backtest/runs/{run_id}")
    def get_run(run_id: int, req: Request):
        agent = _require_agent(req)
        row = _get_run_or_404(run_id, agent["id"])
        return _row_to_response(row)

    @app.get("/api/backtest/runs/{run_id}/trades")
    def get_run_trades(run_id: int, req: Request):
        agent = _require_agent(req)
        row = _get_run_or_404(run_id, agent["id"])
        trades = []
        if row.get("result"):
            try:
                result = json.loads(row["result"])
                trades = result.get("closed_trades", [])
            except Exception:
                pass
        return {"run_id": run_id, "trades": trades}

    @app.delete("/api/backtest/runs/{run_id}", status_code=204)
    def delete_run(run_id: int, req: Request):
        agent = _require_agent(req)
        _get_run_or_404(run_id, agent["id"])  # 404 if not found / wrong agent
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM backtest_runs WHERE id=? AND agent_id=?",
            (run_id, agent["id"]),
        )
        conn.commit()
        conn.close()

    @app.post("/api/backtest/runs/{run_id}/promote")
    def promote_run(run_id: int, req: Request, body: PromoteRunRequest):
        agent = _require_agent(req)
        run = _get_run_or_404(run_id, agent["id"])

        # Verify the strategy belongs to this agent
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM strategies WHERE id=? AND agent_id=? AND is_active=1",
            (body.strategy_id, agent["id"]),
        )
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Derive backtest_validated from Sharpe ratio in the result
        sharpe = None
        if run.get("result"):
            try:
                r = json.loads(run["result"])
                sharpe = r.get("summary", {}).get("sharpe_ratio")
            except Exception:
                pass

        validated = 1 if (sharpe is not None and sharpe > 0) else 0
        now = utc_now_iso_z()
        cursor.execute(
            """UPDATE strategies
               SET backtest_validated=?, last_backtest_sharpe=?,
                   last_backtest_at=?, updated_at=?
               WHERE id=? AND agent_id=?""",
            (validated, sharpe, now, now, body.strategy_id, agent["id"]),
        )
        conn.commit()
        conn.close()

        return {
            "run_id":             run_id,
            "strategy_id":        body.strategy_id,
            "backtest_validated": bool(validated),
            "last_backtest_sharpe": sharpe,
        }
