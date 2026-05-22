"""
Routes Module

所有 API 路由定义入口。
"""

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ORIGINS
from routes_agent import register_agent_routes
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
from routes_execution import register_execution_routes


def create_app() -> FastAPI:
    app = FastAPI(title='AITRAD API')

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
    register_trading_routes(app, ctx)
    register_experiment_routes(app, ctx)
    register_research_routes(app, ctx)
    register_challenge_routes(app, ctx)
    register_team_mission_routes(app, ctx)
    register_user_routes(app, ctx)
    register_execution_routes(app, ctx)
    register_misc_routes(app)   # must be last — contains /{path:path} SPA fallback
    return app
