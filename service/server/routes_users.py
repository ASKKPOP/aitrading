import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException

from cache import delete as _cache_delete, get_json as _cache_get, set_json as _cache_set
from email_sender import send_verification_code_email
from database import get_db_connection
from routes_models import (
    PointsExchangeRequest,
    PointsTransferRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserSendCodeRequest,
)
from routes_shared import RouteContext
from services import _create_user_session, _get_agent_by_token, _get_user_by_token
from utils import _extract_token, hash_password, verify_password

_logger = logging.getLogger(__name__)

EXCHANGE_RATE = 1000

# Bounds the brute-force budget for the 6-digit (1M-space) verification code:
# attackers who blow past MAX_CODE_ATTEMPTS must request a fresh code, and the
# CODE_RESEND_COOLDOWN_SECONDS throttle stops them from cycling codes faster
# than humans actually need.
MAX_CODE_ATTEMPTS = 5
CODE_RESEND_COOLDOWN_SECONDS = 30

# ── Verification-code store ───────────────────────────────────────────────────
# Primary: Redis with TTL (survives restarts, works behind a load balancer).
# Fallback: ctx.verification_codes (per-process dict, preserves test isolation).
_CODE_TTL_SECONDS = 300  # 5 minutes


def _code_key(email: str) -> str:
    return f"auth:vcode:{email}"


def _store_code(email: str, payload: dict, ctx: "RouteContext") -> None:
    """Write a code entry to Redis (with TTL), falling back to ctx."""
    serialisable = {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in payload.items()
    }
    if not _cache_set(_code_key(email), serialisable, ttl_seconds=_CODE_TTL_SECONDS):
        ctx.verification_codes[email] = payload  # fallback keeps native datetime objects


def _load_code(email: str, ctx: "RouteContext") -> dict | None:
    """Read a code entry from Redis, falling back to ctx."""
    cached = _cache_get(_code_key(email))
    if cached is not None:
        # Re-hydrate ISO strings back to datetime objects.
        for key in ("expires_at", "last_sent_at"):
            if isinstance(cached.get(key), str):
                try:
                    cached[key] = datetime.fromisoformat(cached[key])
                except ValueError:
                    pass
        return cached
    return ctx.verification_codes.get(email)


def _delete_code(email: str, ctx: "RouteContext") -> None:
    """Remove a code entry from Redis and ctx."""
    _cache_delete(_code_key(email))
    ctx.verification_codes.pop(email, None)


def register_user_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.post('/api/users/send-code')
    async def send_verification_code(data: UserSendCodeRequest):
        now = datetime.now(timezone.utc)
        existing = _load_code(data.email, ctx)
        if existing:
            last_sent_at = existing.get('last_sent_at')
            if last_sent_at and (now - last_sent_at).total_seconds() < CODE_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429, detail='Please wait before requesting another code')

        code = f'{secrets.randbelow(1_000_000):06d}'
        _store_code(data.email, {
            'code': code,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'last_sent_at': now,
        }, ctx)
        if not send_verification_code_email(data.email, code):
            # Fallback: log code when Resend is not configured (local dev).
            _logger.info('[Email] Verification code for %s: %s', data.email, code)
        return {'success': True, 'message': 'Code sent'}

    @app.post('/api/users/register')
    async def user_register(data: UserRegisterRequest):
        stored = _load_code(data.email, ctx)
        if stored is None:
            raise HTTPException(status_code=400, detail='No code sent')

        if stored['expires_at'] < datetime.now(timezone.utc):
            _delete_code(data.email, ctx)
            raise HTTPException(status_code=400, detail='Code expired')

        stored['attempts'] = stored.get('attempts', 0) + 1
        if stored['attempts'] > MAX_CODE_ATTEMPTS:
            _delete_code(data.email, ctx)
            raise HTTPException(status_code=429, detail='Too many attempts. Request a new code.')

        if not hmac.compare_digest(str(stored['code']), str(data.code or '')):
            raise HTTPException(status_code=400, detail='Invalid code')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (data.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail='User already exists')

        password_hash = hash_password(data.password)
        cursor.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (data.email, password_hash),
        )
        user_id = cursor.lastrowid

        # Create the session token within the same connection to avoid a nested
        # SQLite write lock (_create_user_session would open a second connection
        # while this one already holds a write transaction).
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat().replace('+00:00', 'Z')
        cursor.execute(
            """
            INSERT INTO user_tokens (user_id, token, expires_at)
            VALUES (?, ?, ?)
            """,
            (user_id, token, expires_at),
        )

        conn.commit()
        conn.close()
        _delete_code(data.email, ctx)

        return {'success': True, 'token': token, 'user_id': user_id}

    @app.post('/api/users/login')
    async def user_login(data: UserLoginRequest):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (data.email,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        token = _create_user_session(row['id'])
        return {'token': token, 'user_id': row['id'], 'email': row['email']}

    @app.get('/api/users/me')
    async def get_user_info(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        return {
            'id': user['id'],
            'email': user['email'],
            'wallet_address': user.get('wallet_address'),
            'points': user.get('points', 0),
        }

    @app.get('/api/users/points')
    async def get_points_balance(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        return {'points': user.get('points', 0)}

    @app.post('/api/agents/points/exchange')
    async def exchange_points_for_cash(data: PointsExchangeRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail='Amount must be positive')

        current_points = agent.get('points', 0)
        if current_points < data.amount:
            raise HTTPException(
                status_code=400,
                detail=f'Insufficient points. Current: {current_points}, Requested: {data.amount}',
            )

        cash_to_add = data.amount * EXCHANGE_RATE
        current_cash = agent.get('cash', 0)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE agents
            SET points = points - ?, cash = cash + ?, deposited = deposited + ?
            WHERE id = ?
            """,
            (data.amount, cash_to_add, cash_to_add, agent['id']),
        )
        conn.commit()
        conn.close()

        return {
            'success': True,
            'points_exchanged': data.amount,
            'cash_added': cash_to_add,
            'remaining_points': current_points - data.amount,
            'total_cash': current_cash + cash_to_add,
        }

    @app.get('/api/users/points/history')
    async def get_points_history(authorization: str = Header(None), limit: int = 50):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM points_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user['id'], limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return {'transactions': [dict(row) for row in rows]}

    @app.post('/api/users/points/transfer')
    async def transfer_points(data: PointsTransferRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail='Invalid amount')
        if user['points'] < data.amount:
            raise HTTPException(status_code=400, detail='Insufficient points')

        from_user_id = user['id']
        to_user_id = data.to_user_id
        if from_user_id == to_user_id:
            raise HTTPException(status_code=400, detail='Cannot transfer to yourself')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points - ? WHERE id = ?', (data.amount, from_user_id))
        cursor.execute('UPDATE users SET points = points + ? WHERE id = ?', (data.amount, to_user_id))
        cursor.execute(
            """
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
            """,
            (from_user_id, -data.amount, f'Transfer to user {to_user_id}'),
        )
        cursor.execute(
            """
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
            """,
            (to_user_id, data.amount, f'Transfer from user {from_user_id}'),
        )
        conn.commit()
        conn.close()

        return {'success': True, 'amount': data.amount}
