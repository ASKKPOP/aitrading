"""Research export API routes."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Response

from backtest import run_backtest
from research_exports import (
    RESEARCH_EXPORTS,
    fetch_research_export_rows,
    get_research_dataset_names,
    normalize_dataset_name,
    research_schema_for_dataset,
)
from routes_shared import RouteContext


def _csv_response(filename: str, columns: list[str], rows: list[dict]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _bool_param(value: bool | str | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def register_research_routes(app: FastAPI, ctx: RouteContext) -> None:
    def _fetch(
        dataset_name: str,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool | str | None = True,
        include_content: bool | str | None = True,
        limit: int = 100000,
        offset: int = 0,
    ) -> tuple[str, list[str], list[dict]]:
        filename = normalize_dataset_name(dataset_name)
        if filename not in RESEARCH_EXPORTS:
            raise ValueError(f"Unsupported export: {dataset_name}")
        columns, rows = fetch_research_export_rows(
            filename,
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            variant_key=variant_key,
            market=market,
            agent_ids=agent_ids,
            anonymize=_bool_param(anonymize, True),
            include_content=_bool_param(include_content, True),
            limit=limit,
            offset=offset,
        )
        return filename, columns, rows

    @app.get("/api/research/datasets")
    async def api_research_datasets():
        return {"datasets": get_research_dataset_names()}

    @app.get("/api/research/events")
    async def api_research_events(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 1000,
        offset: int = 0,
    ):
        _filename, columns, rows = _fetch(
            "events",
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            variant_key=variant_key,
            market=market,
            agent_ids=agent_ids,
            anonymize=anonymize,
            include_content=include_content,
            limit=limit,
            offset=offset,
        )
        return {"columns": columns, "events": rows, "limit": max(1, min(limit, 100000)), "offset": max(0, offset)}

    @app.get("/api/research/export/{dataset_name}.csv")
    async def api_research_export_csv(
        dataset_name: str,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 100000,
        offset: int = 0,
    ):
        try:
            filename, columns, rows = _fetch(
                dataset_name,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                agent_ids=agent_ids,
                anonymize=anonymize,
                include_content=include_content,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return _csv_response(filename, columns, rows)

    @app.get("/api/research/export/{dataset_name}.json")
    async def api_research_export_json(
        dataset_name: str,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 100000,
        offset: int = 0,
    ):
        try:
            filename, columns, rows = _fetch(
                dataset_name,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                agent_ids=agent_ids,
                anonymize=anonymize,
                include_content=include_content,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return {"dataset": filename, "columns": columns, "rows": rows, "limit": max(1, min(limit, 100000)), "offset": max(0, offset)}

    @app.get("/api/research/schema/{dataset_name}")
    async def api_research_schema(dataset_name: str):
        try:
            return research_schema_for_dataset(dataset_name)
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    async def _download(
        filename: str,
        start_at: str | None,
        end_at: str | None,
        experiment_key: str | None,
        variant_key: str | None,
        market: str | None,
        limit: int,
        offset: int,
    ) -> Response:
        try:
            normalized, columns, rows = _fetch(
                filename,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return _csv_response(normalized, columns, rows)

    @app.get("/api/research/agents.csv")
    async def api_research_agents_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("agents.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/events.csv")
    async def api_research_events_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("events.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/signals.csv")
    async def api_research_signals_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("signals.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/network_edges.csv")
    async def api_research_network_edges_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("network_edges.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/backtest")
    async def api_backtest(
        agent_id: int,
        start_at: str,
        end_at: str,
        initial_cash: float = 100_000.0,
        market: Optional[str] = None,
        symbol: Optional[str] = None,
    ):
        """Replay an agent's recorded trades and return P&L metrics.

        Query parameters:
          agent_id      – required; agent whose signals to replay
          start_at      – required; ISO-8601 UTC window start (e.g. 2024-01-01T00:00:00Z)
          end_at        – required; ISO-8601 UTC window end
          initial_cash  – starting balance (default 100 000)
          market        – optional filter (e.g. us-stock)
          symbol        – optional filter (e.g. AAPL)
        """
        if initial_cash <= 0:
            raise HTTPException(status_code=400, detail="initial_cash must be positive")

        result = run_backtest(
            agent_id,
            start_at,
            end_at,
            initial_cash=initial_cash,
            market=market,
            symbol=symbol,
        )

        return {
            "agent_id": agent_id,
            "start_at": start_at,
            "end_at": end_at,
            "summary": {
                "initial_cash": result.initial_cash,
                "final_value": result.final_value,
                "total_return_pct": result.total_return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "trade_count": result.trade_count,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": result.win_rate,
                "sharpe_ratio": result.sharpe_ratio,
            },
            "closed_trades": [asdict(t) for t in result.closed_trades],
            "open_positions": result.open_positions,
            "curve": [asdict(p) for p in result.curve],
        }
