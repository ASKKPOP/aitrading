import asyncio
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from alerts import _send_sms
from analysis_agents import LANG_NAMES
from cache import delete as _cache_delete, get_json as _cache_get, set_json as _cache_set
from email_sender import send_verification_code_email, send_welcome_email
from database import get_db_connection
from user_secrets import decrypt_secret, encrypt_secret
import sms_i18n
from routes_models import (
    PhoneForgotPasswordRequest,
    PhoneResetPasswordRequest,
    PhoneSendCodeRequest,
    PhoneVerifyRequest,
    PointsExchangeRequest,
    PointsTransferRequest,
    UserApiSettingRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResetPasswordRequest,
    UserSendCodeRequest,
)
from routes_shared import DEFAULT_AGENT_SEED_CAPITAL, RouteContext
from services import _create_user_session, _get_agent_by_token, _get_user_by_token
from utils import _extract_token, hash_password, verify_password

_PHONE_RE = re.compile(r'^\+[1-9]\d{7,14}$')

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
    'alerts': {
        'label': 'Alerts (email · SMS)',
        'description': 'Trade/risk alert delivery. In-app alerts are always on; enable email and SMS here.',
        'requires_key': False,
        'fields': ['email_enabled', 'sms_enabled', 'phone', 'sms_consent', 'sms_consent_at'],
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

# Per-day SMS caps — a cost and harassment bound independent of the
# per-send cooldown above (the cooldown limits *rate*, this limits *volume*).
PHONE_SEND_DAILY_LIMIT = 10
SMS_RESET_DAILY_LIMIT = 5

# ── Verification-code store ───────────────────────────────────────────────────
# Primary: Redis with TTL (survives restarts, works behind a load balancer).
# Fallback: ctx.verification_codes (per-process dict, preserves test isolation).
_CODE_TTL_SECONDS = 300  # 5 minutes


def _code_key(email: str) -> str:
    return f"auth:vcode:{email}"


def _store_code(email: str, payload: dict, ctx: "RouteContext",
                ttl_seconds: int = _CODE_TTL_SECONDS) -> None:
    """Write a code entry to Redis (with TTL), falling back to ctx.

    ttl_seconds only bounds the Redis key; expiry is enforced from the
    payload's own expires_at, which the ctx fallback relies on. Admin invites
    pass a longer TTL — keep the two in step or Redis evicts a live code."""
    serialisable = {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in payload.items()
    }
    if not _cache_set(_code_key(email), serialisable, ttl_seconds=ttl_seconds):
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


def _daily_quota_hit(quota_key: str, limit: int, ctx: "RouteContext",
                     now: datetime) -> bool:
    """True if `quota_key` already used up `limit` sends today (UTC).

    Otherwise bumps today's counter and returns False. Reuses the
    verification-code store (Redis/ctx) under a distinct key namespace so a
    daily SMS cap can't collide with an in-flight code."""
    today = now.strftime('%Y-%m-%d')
    quota = _load_code(quota_key, ctx)
    count = quota.get('count', 0) if quota and quota.get('day') == today else 0
    if count >= limit:
        return True
    # ttl_seconds must cover the whole day: the default 300s Redis TTL would
    # silently reset the "daily" cap every 5 minutes on a Redis deployment.
    _store_code(quota_key, {
        'day': today, 'count': count + 1,
        'expires_at': now + timedelta(hours=24), 'attempts': 0,
    }, ctx, ttl_seconds=86_400)
    return False


def _user_llm_settings(user_id: int) -> dict | None:
    """The user's own LLM provider/model/key from the Settings page, or None.

    Mirrors services.llm_context_for_agent but keyed on the user rather than an
    agent, so the usage panel can report the model that user's calls actually
    resolve to. Fail-soft: a settings problem must not break the panel."""
    try:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT api_key, config_json FROM user_api_settings "
                "WHERE user_id = ? AND target = 'llm' AND enabled = 1", (user_id,))
            row = cursor.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        try:
            config = json.loads(row['config_json'] or '{}')
        except (TypeError, ValueError):
            config = {}
        out = {'provider': (config.get('provider') or '').strip().lower() or None,
               'model': (config.get('model') or '').strip() or None,
               'api_key': (decrypt_secret(row['api_key']) or '').strip() or None}
        return out if any(out.values()) else None
    except Exception:  # noqa: BLE001
        _logger.warning('user llm settings lookup failed for user %s', user_id, exc_info=True)
        return None


def _chosen_lang(raw: str | None) -> str | None:
    """The member's explicit signup language — only trusted when it is a
    supported code. Anything else returns None and the geo guess stands."""
    if raw and raw in LANG_NAMES:
        return raw
    return None


class UserLanguageRequest(BaseModel):
    lang: str


class WelcomeDismissRequest(BaseModel):
    dismissed: bool = True


class UserLocaleRequest(BaseModel):
    region: str
    lang: str | None = None
    # Omitted ⇒ the region's default zone. Sent when the member is somewhere
    # other than their region's usual clock.
    timezone: str | None = None


def register_user_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.post('/api/users/send-code')
    async def send_verification_code(data: UserSendCodeRequest, request: Request):
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
        from signup_lang import resolve_signup_lang
        # Offload the (sync, network) geo lookup so a slow geo API can't stall
        # the shared event loop during signup — fail-soft returns 'en' anyway.
        lang = _chosen_lang(data.lang) or await asyncio.to_thread(resolve_signup_lang, request)
        if not send_verification_code_email(data.email, code, lang):
            # Fallback: log code when Resend is not configured (local dev).
            _logger.info('[Email] Verification code for %s: %s', data.email, code)
        return {'success': True, 'message': 'Code sent'}

    @app.post('/api/users/register')
    async def user_register(data: UserRegisterRequest, request: Request):
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
        chosen = _chosen_lang(data.lang)
        from signup_lang import resolve_signup_locale
        # Offload the (sync, network) geo lookup so a slow geo API can't stall
        # the shared event loop during signup — fail-soft returns 'en' anyway.
        lang, geo_country = await asyncio.to_thread(resolve_signup_locale, request)
        if chosen:
            lang = chosen
        # geo_country only. `region` stays NULL until the member answers the
        # first-run prompt: an IP guess must never grant a jurisdiction.
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, lang, geo_country)
            VALUES (?, ?, ?, ?)
            """,
            (data.email, password_hash, lang, geo_country),
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

        try:
            await asyncio.to_thread(send_welcome_email, data.email, lang)
        except Exception as exc:  # noqa: BLE001 — a mail outage must never
            # fail a signup; the account and session are already committed.
            _logger.warning('[Email] welcome email to %s failed: %s',
                            data.email, exc)

        return {'success': True, 'token': token, 'user_id': user_id}

    @app.post('/api/users/forgot-password')
    async def forgot_password(data: UserSendCodeRequest):
        # Same code store as registration, under a 'reset:' namespace so a
        # signup code can never reset a password (and vice versa).
        store_key = f'reset:{data.email}'
        now = datetime.now(timezone.utc)
        existing = _load_code(store_key, ctx)
        if existing:
            last_sent_at = existing.get('last_sent_at')
            if last_sent_at and (now - last_sent_at).total_seconds() < CODE_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429, detail='Please wait before requesting another code')

        code = f'{secrets.randbelow(1_000_000):06d}'
        # Store the entry even when no account matches so the cooldown 429
        # cannot be used to probe which emails are registered.
        _store_code(store_key, {
            'code': code,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'last_sent_at': now,
        }, ctx)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, lang FROM users WHERE email = ?', (data.email,))
        row = cursor.fetchone()
        account_exists = row is not None
        conn.close()

        if account_exists:
            lang = row['lang'] or 'en'
            if not send_verification_code_email(data.email, code, lang,
                                                purpose='reset'):
                # Fallback: log code when Resend is not configured (local dev).
                _logger.info('[Email] Password-reset code for %s: %s', data.email, code)
        return {'success': True, 'message': 'If an account exists, a code was sent'}

    @app.post('/api/users/reset-password')
    async def reset_password(data: UserResetPasswordRequest):
        store_key = f'reset:{data.email}'
        stored = _load_code(store_key, ctx)
        if stored is None:
            raise HTTPException(status_code=400, detail='No code sent')

        if stored['expires_at'] < datetime.now(timezone.utc):
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=400, detail='Code expired')

        stored['attempts'] = stored.get('attempts', 0) + 1
        _store_code(store_key, stored, ctx)  # persist the attempt count
        if stored['attempts'] > MAX_CODE_ATTEMPTS:
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=429, detail='Too many attempts. Request a new code.')

        if not hmac.compare_digest(str(stored['code']), str(data.code or '')):
            raise HTTPException(status_code=400, detail='Invalid code')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (data.email,))
        row = cursor.fetchone()
        if row is None:
            conn.close()
            _delete_code(store_key, ctx)
            # Generic detail: don't reveal whether the email is registered.
            raise HTTPException(status_code=400, detail='Invalid code')

        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                       (hash_password(data.new_password), row['id']))
        # Sign out existing sessions — a reset implies the old credential
        # may be compromised.
        cursor.execute('DELETE FROM user_tokens WHERE user_id = ?', (row['id'],))
        conn.commit()
        conn.close()
        _delete_code(store_key, ctx)
        return {'success': True, 'message': 'Password updated'}

    @app.post('/api/users/forgot-password-sms')
    async def forgot_password_sms(data: PhoneForgotPasswordRequest):
        phone = data.phone.strip()
        if not _PHONE_RE.match(phone):
            raise HTTPException(status_code=400,
                                detail='Phone must be in international format (+…)')
        # Same code store as email reset, under a 'smsreset:' namespace so a
        # phone-verification code can never reset a password (and vice versa).
        store_key = f'smsreset:{phone}'
        now = datetime.now(timezone.utc)
        existing = _load_code(store_key, ctx)
        if existing:
            last_sent_at = existing.get('last_sent_at')
            if last_sent_at and (now - last_sent_at).total_seconds() < CODE_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429, detail='Please wait before requesting another code')

        code = f'{secrets.randbelow(1_000_000):06d}'
        # Store the entry even when no account matches so the cooldown 429
        # cannot be used to probe which phones are registered/verified.
        _store_code(store_key, {
            'code': code,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'last_sent_at': now,
        }, ctx)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, lang FROM users WHERE phone = ? AND phone_verified_at IS NOT NULL',
            (phone,))
        row = cursor.fetchone()
        account_exists = row is not None
        conn.close()

        if account_exists:
            # Daily cap only counts real sends — a probe against a phone with
            # no verified account never reaches here, so it can't be used to
            # run down the real owner's quota.
            if not _daily_quota_hit(f'smsresetquota:{phone}', SMS_RESET_DAILY_LIMIT, ctx, now):
                lang = row['lang'] or 'en'
                if not _send_sms(phone, sms_i18n.reset_sms(code, lang)):
                    # Fallback: log code when Twilio is not configured (local dev).
                    _logger.info('[SMS] Password-reset code for %s: %s', phone, code)
        return {'success': True, 'message': 'If an account exists, a code was sent'}

    @app.post('/api/users/reset-password-sms')
    async def reset_password_sms(data: PhoneResetPasswordRequest):
        phone = data.phone.strip()
        if not _PHONE_RE.match(phone):
            raise HTTPException(status_code=400,
                                detail='Phone must be in international format (+…)')
        store_key = f'smsreset:{phone}'
        stored = _load_code(store_key, ctx)
        if stored is None:
            raise HTTPException(status_code=400, detail='No code sent')

        if stored['expires_at'] < datetime.now(timezone.utc):
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=400, detail='Code expired')

        stored['attempts'] = stored.get('attempts', 0) + 1
        _store_code(store_key, stored, ctx)  # persist the attempt count
        if stored['attempts'] > MAX_CODE_ATTEMPTS:
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=429, detail='Too many attempts. Request a new code.')

        if not hmac.compare_digest(str(stored['code']), str(data.code or '')):
            raise HTTPException(status_code=400, detail='Invalid code')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id FROM users WHERE phone = ? AND phone_verified_at IS NOT NULL',
            (phone,))
        row = cursor.fetchone()
        if row is None:
            conn.close()
            _delete_code(store_key, ctx)
            # Generic detail: don't reveal whether the phone is registered.
            raise HTTPException(status_code=400, detail='Invalid code')

        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                       (hash_password(data.new_password), row['id']))
        # Sign out existing sessions — a reset implies the old credential
        # may be compromised.
        cursor.execute('DELETE FROM user_tokens WHERE user_id = ?', (row['id'],))
        conn.commit()
        conn.close()
        _delete_code(store_key, ctx)
        return {'success': True, 'message': 'Password updated'}

    @app.post('/api/users/phone/send-code')
    async def phone_send_code(data: PhoneSendCodeRequest,
                              authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        phone = data.phone.strip()
        if not _PHONE_RE.match(phone):
            raise HTTPException(status_code=400,
                                detail='Phone must be in international format (+…)')
        store_key = f"phone:{user['id']}"
        now = datetime.now(timezone.utc)
        # Cooldown first: an authenticated attacker can otherwise sweep phone
        # numbers via the 409-taken check below at full speed, using the 409
        # itself as an unthrottled oracle for which phones belong to verified
        # members. Checking the cooldown before the DB lookup — and stamping
        # it even on a 409 refusal — means every probe costs the prober their
        # cooldown regardless of the outcome.
        existing = _load_code(store_key, ctx)
        if existing:
            last_sent_at = existing.get('last_sent_at')
            if last_sent_at and (now - last_sent_at).total_seconds() < CODE_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429,
                                    detail='Please wait before requesting another code')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT id FROM users WHERE phone = ? '
                'AND phone_verified_at IS NOT NULL AND id != ?',
                (phone, user['id']))
            taken = cursor.fetchone() is not None
        finally:
            conn.close()
        if taken:
            _store_code(store_key, {'code': None, 'phone': phone,
                                    'expires_at': now, 'attempts': 0,
                                    'last_sent_at': now}, ctx)
            raise HTTPException(status_code=409,
                                detail='This phone number is already verified '
                                       'on another account')
        if _daily_quota_hit(f"phonequota:{user['id']}", PHONE_SEND_DAILY_LIMIT, ctx, now):
            raise HTTPException(status_code=429,
                                detail='Daily SMS limit reached — try again tomorrow')
        code = f'{secrets.randbelow(1_000_000):06d}'
        _store_code(store_key, {
            'code': code, 'phone': phone,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0, 'last_sent_at': now,
        }, ctx)
        lang = user.get('lang') or 'en'
        if not _send_sms(phone, sms_i18n.verification_sms(code, lang)):
            # Twilio unconfigured (local dev) — same fallback as email codes.
            _logger.info('[SMS] Verification code for %s: %s', phone, code)
        return {'success': True, 'message': 'Code sent'}

    @app.post('/api/users/phone/verify')
    async def phone_verify(data: PhoneVerifyRequest,
                           authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        store_key = f"phone:{user['id']}"
        stored = _load_code(store_key, ctx)
        if stored is None:
            raise HTTPException(status_code=400, detail='No code sent')
        if stored['expires_at'] < datetime.now(timezone.utc):
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=400, detail='Code expired')
        stored['attempts'] = stored.get('attempts', 0) + 1
        _store_code(store_key, stored, ctx)
        if stored['attempts'] > MAX_CODE_ATTEMPTS:
            _delete_code(store_key, ctx)
            raise HTTPException(status_code=429,
                                detail='Too many attempts. Request a new code.')
        if not hmac.compare_digest(str(stored['code']), str(data.code or '')):
            raise HTTPException(status_code=400, detail='Invalid code')
        phone = stored.get('phone') or ''
        now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT id FROM users WHERE phone = ? '
                'AND phone_verified_at IS NOT NULL AND id != ?',
                (phone, user['id']))
            if cursor.fetchone():
                raise HTTPException(status_code=409,
                                    detail='This phone number is already '
                                           'verified on another account')
            cursor.execute(
                'UPDATE users SET phone = ?, phone_verified_at = ? WHERE id = ?',
                (phone, now_iso, user['id']))
            # Sync the alerts contact point so SMS alerts use the verified
            # number without a second entry step. Delivery still obeys the
            # member's notification switches + A2P consent — unchanged.
            cursor.execute(
                "SELECT config_json FROM user_api_settings "
                "WHERE user_id = ? AND target = 'alerts'", (user['id'],))
            row = cursor.fetchone()
            if row:
                try:
                    cfg = json.loads(dict(row)['config_json'] or '{}')
                except (TypeError, ValueError):
                    cfg = {}
                cfg['phone'] = phone
                cursor.execute(
                    "UPDATE user_api_settings SET config_json = ? "
                    "WHERE user_id = ? AND target = 'alerts'",
                    (json.dumps(cfg), user['id']))
            else:
                cursor.execute(
                    "INSERT INTO user_api_settings (user_id, target, enabled, config_json) "
                    "VALUES (?, 'alerts', 1, ?)",
                    (user['id'], json.dumps({'phone': phone})))
            conn.commit()
        finally:
            conn.close()
        _delete_code(store_key, ctx)
        return {'success': True, 'phone': phone}

    @app.post('/api/users/welcome/dismiss')
    async def welcome_dismiss(data: WelcomeDismissRequest,
                              authorization: str = Header(None)):
        """Two-way: the /welcome checkbox both sets and clears the stamp, so a
        member can re-enable the page from the profile menu later."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        stamp = (datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                 if data.dismissed else None)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET welcome_dismissed_at = ? WHERE id = ?',
                           (stamp, user['id']))
            conn.commit()
        finally:
            conn.close()
        return {'success': True, 'welcome_dismissed': data.dismissed}

    @app.post('/api/users/login')
    async def user_login(data: UserLoginRequest):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (data.email,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        # Suspended members cannot sign in (admin console member management).
        try:
            if row['status'] == 'suspended':
                raise HTTPException(status_code=403, detail='Account suspended')
        except (KeyError, IndexError):
            pass

        # Phase 5: if the user has MFA enabled, defer the session until
        # they prove the second factor. The client gets a short-lived
        # mfa_token to trade for a real session via /api/auth/mfa/verify.
        try:
            mfa_on = bool(row['mfa_enabled'])
        except (KeyError, IndexError):
            mfa_on = False

        try:
            lang = row['lang']
        except (KeyError, IndexError):
            lang = 'en'

        if mfa_on:
            from routes_auth import issue_mfa_token_for_user
            return {
                'requires_mfa': True,
                'mfa_token':    issue_mfa_token_for_user(row['id']),
                'user_id':      row['id'],
            }

        token = _create_user_session(row['id'])
        # Membership gate: the frontend routes users without an active
        # subscription to /subscribe (see routes_subscriptions.py).
        from routes_subscriptions import get_subscription_state
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            sub = get_subscription_state(cursor, row['id'])
            conn.commit()
        finally:
            conn.close()
        return {'token': token, 'user_id': row['id'], 'email': row['email'],
                'subscription_status': sub['status'], 'lang': lang}

    @app.get('/api/users/me')
    async def get_user_info(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        from routes_subscriptions import get_subscription_state
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            sub = get_subscription_state(cursor, user['id'])
            conn.commit()
        finally:
            conn.close()
        return {
            'id': user['id'],
            'email': user['email'],
            'wallet_address': user.get('wallet_address'),
            'points': user.get('points', 0),
            'status': user.get('status', 'active'),
            'lang': user.get('lang', 'en'),
            'region': user.get('region'),
            'timezone': user.get('timezone'),
            # The first-run prompt reads this. False only once the member has
            # answered — a geolocation guess never flips it.
            'locale_confirmed': bool(user.get('locale_confirmed_at')),
            'phone': user.get('phone'),
            'phone_verified': bool(user.get('phone_verified_at')),
            # The first-run /welcome gate reads this; the page's checkbox
            # writes it via /users/welcome/dismiss.
            'welcome_dismissed': bool(user.get('welcome_dismissed_at')),
            'subscription_status': sub['status'],
            'subscription': sub['subscription'],
        }

    @app.put('/api/users/language')
    async def set_user_language(data: UserLanguageRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        from analysis_agents import LANG_NAMES, normalize_lang
        # normalize_lang maps anything unknown to 'en', which is the right
        # fallback for RENDERING and the wrong one for WRITING: until
        # 2026-07-29 a client that sent a bad code got 200 and this endpoint
        # silently overwrote the member's stored language with English.
        # A write must refuse what it doesn't recognize.
        base = (data.lang or '').strip().lower().replace('_', '-').split('-')[0]
        if base not in LANG_NAMES:
            raise HTTPException(status_code=400,
                                detail=f'Unsupported language: {data.lang}')
        lang = normalize_lang(data.lang)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET lang = ? WHERE id = ?', (lang, user['id']))
            conn.commit()
        finally:
            conn.close()
        return {'lang': lang}

    @app.get('/api/users/locale/options')
    async def get_locale_options(authorization: str = Header(None)):
        """Region picker payload + what to pre-select.

        `suggested_region` is the signup-time IP guess. It is only ever a
        pre-selection; nothing is applied until the member confirms."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        import regions
        lang = user.get('lang') or 'en'
        return {
            'regions': regions.options(lang),
            'region': user.get('region'),
            'timezone': user.get('timezone'),
            'lang': lang,
            'locale_confirmed': bool(user.get('locale_confirmed_at')),
            'suggested_region': regions.normalize_region(user.get('geo_country')),
        }

    @app.put('/api/users/locale')
    async def set_user_locale(data: UserLocaleRequest, authorization: str = Header(None)):
        """The member's own answer: region + language, timezone optional.

        Setting locale_confirmed_at is what stops the first-run prompt. An
        unrecognised region is rejected rather than coerced — silently
        substituting a jurisdiction is the failure mode this whole field
        exists to avoid."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        import regions
        from analysis_agents import normalize_lang
        region = regions.normalize_region(data.region)
        if region is None:
            raise HTTPException(status_code=400, detail='unsupported region')
        lang = normalize_lang(data.lang or regions.default_lang(region))
        tz = (regions.normalize_timezone(data.timezone)
              or regions.default_timezone(region))
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'UPDATE users SET region = ?, timezone = ?, lang = ?, '
                'locale_confirmed_at = ? WHERE id = ?',
                (region, tz, lang, now, user['id']))
            conn.commit()
        finally:
            conn.close()
        return {'region': region, 'timezone': tz, 'lang': lang,
                'locale_confirmed': True}

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

    # ── Plan 06 C3: freeform trading guidelines (Personalized mode) ──
    # Injected into the trader/verifier/planner prompts; guidelines may
    # tighten behavior but never bypass the deterministic risk gates.

    @app.get('/api/users/guidelines')
    async def get_guidelines(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        conn = get_db_connection()
        row = conn.execute('SELECT trading_guidelines FROM users WHERE id = ?',
                           (user['id'],)).fetchone()
        conn.close()
        return {'guidelines': (row['trading_guidelines'] or '') if row else ''}

    @app.put('/api/users/guidelines')
    async def put_guidelines(data: dict, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        text = str(data.get('guidelines') or '').strip()
        if len(text) > 2000:
            raise HTTPException(status_code=400, detail='guidelines must be <= 2000 characters')
        conn = get_db_connection()
        conn.execute('UPDATE users SET trading_guidelines = ? WHERE id = ?',
                     (text or None, user['id']))
        conn.commit()
        conn.close()
        return {'ok': True, 'length': len(text)}

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
            # Decrypt for the mask: the last four characters shown to the
            # owner must be the KEY's, not the ciphertext's.
            api_key = decrypt_secret((row or {}).get('api_key')) or ''
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

    @app.get('/api/users/settings/llm-usage')
    async def get_llm_usage(authorization: str = Header(None)):
        """Current-month AI usage + estimated cost for the caller (Plan 11 F2).
        Owners (DOCS_OWNER_EMAILS, default info@askkpop.com) additionally get
        the system-wide aggregate."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        from llm_usage import usage_summary
        from llm_client import (LlmContext, active_provider_name, active_provider_model,
                                reset_llm_context, set_llm_context)

        out = {'user': usage_summary(user_id=user['id'])}
        # Resolve the model THIS user's analysis actually runs on. Probing the
        # bare provider reports the server default, which is wrong — and
        # confusingly so — for anyone who configured their own key on the
        # Settings page. Resolve under their context instead, and say whose key
        # is paying so "$0.71 this month" is unambiguous.
        settings = _user_llm_settings(user['id'])
        ctx_token = None
        try:
            if settings:
                ctx_token = set_llm_context(LlmContext(
                    provider=settings.get('provider'), model=settings.get('model'),
                    api_key=settings.get('api_key'), source='user', user_id=user['id']))
            out['active'] = {'provider': active_provider_name(),
                             'model': active_provider_model('decision'),
                             'key_source': 'user' if (settings or {}).get('api_key') else 'system'}
        except Exception:  # noqa: BLE001 — provider probing must not break the page
            out['active'] = None
        finally:
            if ctx_token is not None:
                reset_llm_context(ctx_token)

        from routes_guide import _owner_emails
        if (user.get('email') or '').strip().lower() in _owner_emails():
            out['system'] = usage_summary(user_id=None)
        return out

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
        # Tier gate (always-on): Junior runs on the system default AI only —
        # repointing the LLM target (own key / provider / model) is Pro+.
        if target == 'llm':
            from entitlements import check_llm_change
            deny = check_llm_change(cursor, user['id'])
            if deny:
                conn.close()
                raise HTTPException(status_code=403, detail=deny)
        cursor.execute(
            'SELECT id, api_key, config_json, enabled FROM user_api_settings WHERE user_id = ? AND target = ?',
            (user['id'], target),
        )
        row = cursor.fetchone()
        if row is not None:
            # Partial update: absent fields keep their stored values.
            # Encrypt only a NEWLY supplied key; the stored value is
            # already ciphertext and must be carried forward untouched.
            new_key = (encrypt_secret(data.api_key) if data.api_key is not None
                       else row['api_key'])
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
                (user['id'], target, encrypt_secret(data.api_key), json.dumps(config),
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
                    'INSERT INTO agents (name, password_hash, wallet_address, cash,'
                    ' starting_capital, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                    (name, hash_password(secrets.token_urlsafe(24)), '',
                     DEFAULT_AGENT_SEED_CAPITAL, DEFAULT_AGENT_SEED_CAPITAL, user['id']),
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
