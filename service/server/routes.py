"""
Routes Module

所有 API 路由定义入口。
"""

import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ORIGINS
from i18n_errors import lang_from_request, translate
from routes_admin import register_admin_routes
from routes_admin_auth import register_admin_auth_routes
from routes_admin_manage import register_admin_manage_routes
from routes_admin_skills import register_admin_skill_routes
from routes_subscriptions import register_subscription_routes
from routes_agent import register_agent_routes
from routes_analysis import register_analysis_routes
from routes_automation import register_automation_routes
from routes_runs import register_runs_routes
from routes_fleets import register_fleet_routes
from routes_run_stream import register_run_stream_routes
from routes_challenges import register_challenge_routes
from routes_experiments import register_experiment_routes
from routes_market import register_market_routes
from routes_misc import register_misc_routes
from routes_research import register_research_routes
from routes_shared import RouteContext
from routes_signals import register_signal_routes
from routes_team_missions import register_team_mission_routes
from routes_trading import register_trading_routes
from routes_users import register_user_routes
from routes_backtest import register_backtest_routes
from routes_execution import register_execution_routes
from routes_auth import register_auth_routes
from routes_guide import register_guide_routes
from routes_watches import register_watch_routes
from routes_memory import register_memory_routes
from routes_oauth import register_oauth_routes
from routes_reputation import register_reputation_routes
from routes_risk import register_risk_routes
from routes_strategies import register_strategy_routes
from routes_support import register_support_routes
from routes_tournaments import register_tournament_routes


def create_app() -> FastAPI:
    app = FastAPI(title='Sooppiy API')

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.middleware('http')
    async def add_request_metadata(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Process-Time'] = str(time.time() - start_time)
        return response

    @app.exception_handler(HTTPException)
    async def localized_http_exception_handler(request: Request, exc: HTTPException):
        """Render `detail` in the caller's language before FastAPI serializes it.

        Routes raise English; this is the one place that knows the request's
        language, so it is the only place that translates.

        `detail` is usually a string, but a few endpoints return a structured
        payload the client acts on — the run-start conflict ships
        {"message": ..., "conflicts": {...}} so the UI can offer to resolve
        them. Those get their "message" translated and the rest left alone;
        translating the machine-readable half would break the client.
        """
        detail = exc.detail
        lang = lang_from_request(request.headers)
        if lang != 'en':
            if isinstance(detail, str):
                detail = translate(detail, lang)
            elif isinstance(detail, dict) and isinstance(detail.get('message'), str):
                detail = {**detail, 'message': translate(detail['message'], lang)}
            if detail is not exc.detail:
                exc = HTTPException(status_code=exc.status_code, detail=detail,
                                    headers=exc.headers)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, 'request_id', None)
        return JSONResponse(
            status_code=500,
            content={'error': {'code': 'internal_error', 'message': 'An unexpected error occurred.', 'request_id': request_id}},
        )

    ctx = RouteContext()
    register_market_routes(app, ctx)
    register_agent_routes(app, ctx)
    register_signal_routes(app, ctx)
    register_analysis_routes(app, ctx)
    register_automation_routes(app, ctx)
    register_risk_routes(app, ctx)
    register_admin_routes(app, ctx)
    register_admin_auth_routes(app, ctx)
    register_admin_manage_routes(app, ctx)
    register_admin_skill_routes(app, ctx)
    register_subscription_routes(app, ctx)
    register_support_routes(app, ctx)
    register_trading_routes(app, ctx)
    register_experiment_routes(app, ctx)
    register_research_routes(app, ctx)
    register_challenge_routes(app, ctx)
    register_team_mission_routes(app, ctx)
    register_user_routes(app, ctx)
    register_execution_routes(app, ctx)
    register_strategy_routes(app, ctx)
    register_backtest_routes(app, ctx)
    register_tournament_routes(app, ctx)
    register_memory_routes(app, ctx)
    register_reputation_routes(app, ctx)
    register_auth_routes(app, ctx)
    register_guide_routes(app, ctx)
    register_watch_routes(app, ctx)
    register_runs_routes(app, ctx)
    register_fleet_routes(app, ctx)
    register_run_stream_routes(app, ctx)
    register_oauth_routes(app, ctx)
    register_misc_routes(app)   # must be last — contains /{path:path} SPA fallback
    return app
