import hmac
import json
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
    UserApiSettingRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserSendCodeRequest,
)
from routes_shared import RouteContext
from services import _create_user_session, _get_agent_by_token, _get_user_by_token
from utils import _extract_token, hash_password, verify_password

_logger = logging.getLogger(__name__)

EXCHANGE_RATE = 1000

# External API targets a user can configure on the settings page. Keyless
# targets appear read-only so the UI shows the full data-source picture.
API_TARGET_CATALOG: dict = {
    'llm': {
        'label': 'LLM (AI analysis)',
        'description': 'Provider for the 4-analyst analysis engine. Without a key the deterministic rule-based engine runs.',
        'requires_key': True,
        'fields': ['provider', 'model'],
    },
    'alpha_vantage': {
        'label': 'Alpha Vantage',
        'description': 'US stock prices, news + sentiment, ETF flows.',
        'requires_key': True,
        'fields': [],
    },
    'finnhub': {
        'label': 'FinnHub',
        'description': 'Company news merged into the news analyst when a key is present.',
        'requires_key': True,
        'fields': [],
    },
    'fred': {
        'label': 'FRED',
        'description': 'Macro-economic series merged into the fundamentals analyst.',
        'requires_key': True,
        'fields': [],
    },
    'okx': {
        'label': 'OKX',
        'description': 'Crypto candles, funding rate, basis, volume. Public API — no key needed.',
        'requires_key': False,
        'fields': [],
    },
    'stocktwits': {
        'label': 'StockTwits',
        'description': 'Crowd sentiment and mention rates. Public API — no key needed.',
        'requires_key': False,
        'fields': [],
    },
    'polymarket': {
        'label': 'Polymarket',
        'description': 'Prediction-market odds (anticipation signal). Public API — no key needed.',
        'requires_key': False,
        'fields': [],
    },
    'alternative_me': {
        'label': 'alternative.me',
        'description': 'Fear & Greed index. Public API — no key needed.',
        'requires_key': False,
        'fields': [],
    },
}

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

        # Phase 5: if the user has MFA enabled, defer the session until
        # they prove the second factor. The client gets a short-lived
        # mfa_token to trade for a real session via /api/auth/mfa/verify.
        try:
            mfa_on = bool(row['mfa_enabled'])
        except (KeyError, IndexError):
            mfa_on = False
        if mfa_on:
            from routes_auth import issue_mfa_token_for_user
            return {
                'requires_mfa': True,
                'mfa_token':    issue_mfa_token_for_user(row['id']),
                'user_id':      row['id'],
            }

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

    # ─────────────────── per-target API configuration (settings page) ───────────────────
    # Catalog of external API targets a user can configure. Keyless targets are
    # listed so the settings UI can show the full data-source picture; only
    # requires_key targets accept an api_key.

    @app.get('/api/users/settings')
    async def get_user_settings(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT target, api_key, config_json, enabled, updated_at FROM user_api_settings WHERE user_id = ?',
            (user['id'],),
        )
        rows = {r['target']: dict(r) for r in cursor.fetchall()}
        conn.close()

        targets = []
        for target, spec in API_TARGET_CATALOG.items():
            row = rows.get(target)
            api_key = (row or {}).get('api_key') or ''
            try:
                config = json.loads((row or {}).get('config_json') or '{}')
            except (TypeError, ValueError):
                config = {}
            targets.append({
                'target': target,
                'label': spec['label'],
                'description': spec['description'],
                'requires_key': spec['requires_key'],
                'fields': spec.get('fields', []),
                'configured': bool(api_key) or bool(config),
                'enabled': bool(row['enabled']) if row is not None else True,
                'masked_key': f'····{api_key[-4:]}' if api_key else None,
                'config': {k: v for k, v in config.items() if k in spec.get('fields', [])},
                'updated_at': (row or {}).get('updated_at'),
            })
        return {'user_id': user['id'], 'targets': targets}

    @app.put('/api/users/settings/api/{target}')
    async def put_user_api_setting(target: str, data: UserApiSettingRequest,
                                   authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        spec = API_TARGET_CATALOG.get(target)
        if spec is None:
            raise HTTPException(status_code=404, detail=f'Unknown API target: {target}')
        if data.api_key and not spec['requires_key']:
            raise HTTPException(status_code=400, detail=f'{target} does not take an API key')

        config = {k: v for k, v in (data.config or {}).items() if k in spec.get('fields', [])}
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, api_key, config_json, enabled FROM user_api_settings WHERE user_id = ? AND target = ?',
            (user['id'], target),
        )
        row = cursor.fetchone()
        if row is not None:
            # Partial update: absent fields keep their stored values.
            new_key = data.api_key if data.api_key is not None else row['api_key']
            if data.config is not None:
                new_config = json.dumps(config)
            else:
                new_config = row['config_json']
            new_enabled = int(data.enabled) if data.enabled is not None else row['enabled']
            cursor.execute(
                'UPDATE user_api_settings SET api_key = ?, config_json = ?, enabled = ?, updated_at = ? WHERE id = ?',
                (new_key, new_config, new_enabled, now, row['id']),
            )
        else:
            cursor.execute(
                'INSERT INTO user_api_settings (user_id, target, api_key, config_json, enabled, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                (user['id'], target, data.api_key, json.dumps(config),
                 int(data.enabled) if data.enabled is not None else 1, now),
            )
        conn.commit()
        conn.close()
        return {'success': True, 'target': target}

    @app.delete('/api/users/settings/api/{target}')
    async def delete_user_api_setting(target: str, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        if target not in API_TARGET_CATALOG:
            raise HTTPException(status_code=404, detail=f'Unknown API target: {target}')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_api_settings WHERE user_id = ? AND target = ?', (user['id'], target))
        conn.commit()
        conn.close()
        return {'success': True, 'target': target}

    # ─────────────────── linked agent (one per human user) ───────────────────
    # Most of the app runs on agent (claw) auth. A human account gets its own
    # auto-provisioned simulator agent so logging in unlocks the whole app.

    @app.post('/api/users/agent')
    async def ensure_user_agent(authorization: str = Header(None)):
        from services import _issue_agent_token

        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, name FROM agents WHERE user_id = ?', (user['id'],))
            row = cursor.fetchone()
            created = False
            if row is None:
                # Derive a readable unique agent name from the email local part.
                base = ''.join(ch for ch in user['email'].split('@')[0].lower()
                               if ch.isalnum() or ch in '-_') or 'trader'
                name = base
                suffix = 1
                while True:
                    cursor.execute('SELECT 1 FROM agents WHERE TRIM(name) = ?', (name,))
                    if cursor.fetchone() is None:
                        break
                    suffix += 1
                    name = f'{base}-{suffix}'
                # Password is random and unused — this agent authenticates only
                # through the linked user account (token issued below).
                cursor.execute(
                    'INSERT INTO agents (name, password_hash, wallet_address, cash, user_id) VALUES (?, ?, ?, ?, ?)',
                    (name, hash_password(secrets.token_urlsafe(24)), '', 100000.0, user['id']),
                )
                agent_id = cursor.lastrowid
                conn.commit()
                created = True
            else:
                agent_id, name = row['id'], row['name']
        finally:
            conn.close()

        agent_token = _issue_agent_token(agent_id)
        return {'token': agent_token, 'agent_id': agent_id, 'name': name, 'created': created}
