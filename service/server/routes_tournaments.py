"""
routes_tournaments.py — Out-of-sample tournament infrastructure (Phase 3.8).

Tournaments lock strategies at submission time T, then evaluate every entry
against the same date window [T, T+N] — data the entrant could not have
seen when committing. The submitted strategy.config is hashed and snapshot
into tournament_entries so post-submission mutation cannot bias the result.

Endpoints:
  POST /api/tournaments                            create (any authed agent)
  GET  /api/tournaments                            list, optional ?status=
  GET  /api/tournaments/{id}                       detail
  POST /api/tournaments/{id}/entries               submit (auth, before deadline)
  GET  /api/tournaments/{id}/entries               list entries
  POST /api/tournaments/{id}/evaluate              run backtests + rank + close
  GET  /api/tournaments/{id}/leaderboard           ranked entries
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

import database
from backtest import run_backtest
from routes_shared import RouteContext, utc_now_iso_z

_logger = logging.getLogger(__name__)


# ── Pydantic ─────────────────────────────────────────────────────────────────

class CreateTournamentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    submission_deadline: str
    evaluation_start:    str
    evaluation_end:      str
    symbol:              Optional[str] = None
    market:              str = "us-stock"
    initial_cash:        float = Field(default=100_000.0, gt=0)


class SubmitEntryRequest(BaseModel):
    strategy_id: int


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _tournament_row(tid: int) -> Optional[dict]:
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tournaments WHERE id=?", (tid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def _row_to_response(row: dict) -> dict:
    return {
        "tournament_id":       row["id"],
        "name":                row["name"],
        "description":         row.get("description"),
        "status":              row["status"],
        "submission_deadline": row["submission_deadline"],
        "evaluation_start":    row["evaluation_start"],
        "evaluation_end":      row["evaluation_end"],
        "symbol":              row.get("symbol"),
        "market":              row["market"],
        "initial_cash":        row["initial_cash"],
        "created_by_agent_id": row.get("created_by_agent_id"),
        "created_at":          row.get("created_at"),
        "closed_at":           row.get("closed_at"),
    }


def _entry_to_response(row: dict, include_snapshot: bool = True) -> dict:
    snap = row.get("config_snapshot")
    if include_snapshot and snap:
        try:
            snap = json.loads(snap)
        except Exception:
            pass
    out = {
        "entry_id":         row["id"],
        "tournament_id":    row["tournament_id"],
        "agent_id":         row["agent_id"],
        "strategy_id":      row["strategy_id"],
        "config_hash":      row["config_hash"],
        "submitted_at":     row["submitted_at"],
        "backtest_run_id":  row.get("backtest_run_id"),
        "final_sharpe":     row.get("final_sharpe"),
        "final_return_pct": row.get("final_return_pct"),
        "rank":             row.get("rank"),
    }
    if include_snapshot:
        out["config_snapshot"] = snap
    return out


# ── Routes ───────────────────────────────────────────────────────────────────

def register_tournament_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post("/api/tournaments", status_code=201)
    def create_tournament(req: Request, body: CreateTournamentRequest):
        agent = _require_agent(req)

        # Invariants: deadline must be < eval start; eval window must be ordered
        if body.submission_deadline >= body.evaluation_start:
            raise HTTPException(
                status_code=400,
                detail="submission_deadline must be earlier than evaluation_start",
            )
        if body.evaluation_end <= body.evaluation_start:
            raise HTTPException(
                status_code=400,
                detail="evaluation_end must be later than evaluation_start",
            )

        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tournaments
               (name, description, status, submission_deadline,
                evaluation_start, evaluation_end, symbol, market,
                initial_cash, created_by_agent_id, created_at)
               VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                body.name, body.description,
                body.submission_deadline, body.evaluation_start, body.evaluation_end,
                body.symbol, body.market, body.initial_cash,
                agent["id"], utc_now_iso_z(),
            ),
        )
        tid = cur.lastrowid
        conn.commit()
        conn.close()

        row = _tournament_row(tid)
        assert row is not None
        return _row_to_response(row)

    @app.get("/api/tournaments")
    def list_tournaments(status: Optional[str] = None):
        conn = database.get_db_connection()
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM tournaments WHERE status=? ORDER BY submission_deadline DESC",
                (status,),
            )
        else:
            cur.execute("SELECT * FROM tournaments ORDER BY submission_deadline DESC")
        rows = [_row_to_response(dict(r)) for r in cur.fetchall()]
        conn.close()
        return {"tournaments": rows}

    @app.get("/api/tournaments/{tid}")
    def get_tournament(tid: int):
        row = _tournament_row(tid)
        if not row:
            raise HTTPException(status_code=404, detail="Tournament not found")
        return _row_to_response(row)

    @app.post("/api/tournaments/{tid}/entries", status_code=201)
    def submit_entry(tid: int, req: Request, body: SubmitEntryRequest):
        agent = _require_agent(req)

        tournament = _tournament_row(tid)
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if tournament["status"] != "open":
            raise HTTPException(status_code=403, detail="Tournament is closed for submissions")
        now = utc_now_iso_z()
        if now >= tournament["submission_deadline"]:
            raise HTTPException(status_code=403, detail="Submission deadline has passed")

        # verify strategy belongs to caller + read its config
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, config FROM strategies WHERE id=? AND agent_id=? AND is_active=1",
            (body.strategy_id, agent["id"]),
        )
        strat = cur.fetchone()
        if not strat:
            conn.close()
            raise HTTPException(status_code=404, detail="Strategy not found")

        # freeze the config snapshot + hash
        snapshot = strat["config"] if strat["config"] is not None else "null"
        if not isinstance(snapshot, str):
            snapshot = json.dumps(snapshot)
        config_hash = hashlib.sha256(snapshot.encode()).hexdigest()

        try:
            cur.execute(
                """INSERT INTO tournament_entries
                   (tournament_id, agent_id, strategy_id,
                    config_hash, config_snapshot, submitted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tid, agent["id"], body.strategy_id, config_hash, snapshot, now),
            )
            eid = cur.lastrowid
            conn.commit()
        except Exception as exc:
            conn.close()
            msg = str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                raise HTTPException(status_code=409, detail="Strategy already entered")
            raise
        conn.close()

        return {
            "entry_id":      eid,
            "tournament_id": tid,
            "strategy_id":   body.strategy_id,
            "config_hash":   config_hash,
            "submitted_at":  now,
        }

    @app.get("/api/tournaments/{tid}/entries")
    def list_entries(tid: int):
        if not _tournament_row(tid):
            raise HTTPException(status_code=404, detail="Tournament not found")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tournament_entries WHERE tournament_id=? ORDER BY id",
            (tid,),
        )
        rows = [_entry_to_response(dict(r)) for r in cur.fetchall()]
        conn.close()
        return {"entries": rows}

    @app.get("/api/tournaments/{tid}/leaderboard")
    def get_leaderboard(tid: int):
        if not _tournament_row(tid):
            raise HTTPException(status_code=404, detail="Tournament not found")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM tournament_entries
               WHERE tournament_id=?
               ORDER BY rank IS NULL, rank ASC, id ASC""",
            (tid,),
        )
        rows = [_entry_to_response(dict(r), include_snapshot=False)
                for r in cur.fetchall()]
        conn.close()
        return {"tournament_id": tid, "leaderboard": rows}

    @app.post("/api/tournaments/{tid}/evaluate")
    def evaluate_tournament(tid: int, req: Request):
        _require_agent(req)
        tournament = _tournament_row(tid)
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if tournament["status"] != "open":
            raise HTTPException(
                status_code=409,
                detail=f"Tournament already in status '{tournament['status']}'",
            )
        now = utc_now_iso_z()
        if now < tournament["submission_deadline"]:
            raise HTTPException(
                status_code=409,
                detail="Submission deadline has not passed yet",
            )

        # mark evaluating
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tournaments SET status='evaluating' WHERE id=?", (tid,))
        conn.commit()
        cur.execute(
            "SELECT * FROM tournament_entries WHERE tournament_id=? ORDER BY id",
            (tid,),
        )
        entries = [dict(r) for r in cur.fetchall()]
        conn.close()

        # run each backtest, persist result on the entry
        for entry in entries:
            sharpe, return_pct, run_id = _evaluate_entry(entry, tournament)
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """UPDATE tournament_entries
                   SET backtest_run_id=?, final_sharpe=?, final_return_pct=?
                   WHERE id=?""",
                (run_id, sharpe, return_pct, entry["id"]),
            )
            conn.commit()
            conn.close()

        # rank by sharpe DESC (nulls last), tie-break by return_pct DESC
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, final_sharpe, final_return_pct
               FROM tournament_entries
               WHERE tournament_id=?""",
            (tid,),
        )
        rows = [dict(r) for r in cur.fetchall()]

        def _sort_key(r):
            s = r.get("final_sharpe")
            ret = r.get("final_return_pct")
            return (
                0 if s is not None else 1,
                -(s if s is not None else 0.0),
                -(ret if ret is not None else 0.0),
            )

        rows.sort(key=_sort_key)
        for rank_idx, r in enumerate(rows, start=1):
            cur.execute(
                "UPDATE tournament_entries SET rank=? WHERE id=?",
                (rank_idx, r["id"]),
            )

        cur.execute(
            "UPDATE tournaments SET status='closed', closed_at=? WHERE id=?",
            (utc_now_iso_z(), tid),
        )
        conn.commit()
        conn.close()

        return {
            "tournament_id": tid,
            "status":        "closed",
            "entry_count":   len(entries),
        }


def _evaluate_entry(entry: dict, tournament: dict) -> tuple[Optional[float], Optional[float], Optional[int]]:
    """Run a backtest for one entry; return (sharpe, return_pct, backtest_run_id).

    Failures are absorbed: the entry is recorded with None metrics rather
    than aborting the whole evaluation pass.
    """
    try:
        from dataclasses import asdict
        result = run_backtest(
            agent_id=entry["agent_id"],
            start_at=tournament["evaluation_start"],
            end_at=tournament["evaluation_end"],
            initial_cash=float(tournament["initial_cash"]),
            market=tournament.get("market"),
            symbol=tournament.get("symbol"),
        )
        config = {
            "start_at":     tournament["evaluation_start"],
            "end_at":       tournament["evaluation_end"],
            "initial_cash": float(tournament["initial_cash"]),
            "market":       tournament.get("market"),
            "symbol":       tournament.get("symbol"),
            "strategy_id":  entry["strategy_id"],
            "tournament_id": tournament["id"],
        }
        result_json = json.dumps({
            "summary": {
                "initial_cash":     result.initial_cash,
                "final_value":      result.final_value,
                "total_return_pct": result.total_return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "sharpe_ratio":     result.sharpe_ratio,
                "trade_count":      result.trade_count,
            },
            "closed_trades":  [asdict(t) for t in result.closed_trades],
            "open_positions": result.open_positions,
            "curve":          [asdict(p) for p in result.curve],
        })

        # Record the backtest run so it can be linked from the entry
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO backtest_runs
               (agent_id, strategy_id, status, config, result, created_at, completed_at)
               VALUES (?, ?, 'completed', ?, ?, ?, ?)""",
            (entry["agent_id"], entry["strategy_id"],
             json.dumps(config), result_json,
             utc_now_iso_z(), utc_now_iso_z()),
        )
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return result.sharpe_ratio, result.total_return_pct, run_id
    except Exception as exc:  # noqa: BLE001
        _logger.exception("[tournaments] evaluation failed for entry %s: %s",
                          entry.get("id"), exc)
        return None, None, None
