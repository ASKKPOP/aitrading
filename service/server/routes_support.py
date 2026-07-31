"""
routes_support.py — member notification centre and member ⇄ administrator chat.

Member (user session token)
  GET  /api/notifications                    feed (limit, unread_only)
  GET  /api/notifications/summary            unread count
  POST /api/notifications/read               mark ids — or everything — read
  GET  /api/notifications/settings           category catalog + switches
  PUT  /api/notifications/settings           update switches
  GET  /api/support/thread                   my conversation + messages
  POST /api/support/messages                 send a message to the admins

Administrator (admin session token, admin_auth.require_admin)
  GET  /api/admin/support/threads            every conversation, newest first
  GET  /api/admin/support/threads/{id}       one conversation + messages
  POST /api/admin/support/threads/{id}/reply reply as the administrator
  POST /api/admin/support/threads/{id}/status  open / closed
  POST /api/admin/notifications/broadcast    announcement to one member or all

Each member has exactly one thread (support_threads.user_id is UNIQUE), so the
conversation reads like a single chat with support. Unread counters are kept
per side: the member clears theirs by opening the thread, the admin by opening
it in the console.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

import notifications
import notifications_i18n
from admin_auth import audit, require_admin
from i18n_errors import lang_from_request, translate
from database import get_db_connection
from routes_shared import RouteContext
from services import _get_user_by_token
from utils import _extract_token

logger = logging.getLogger("routes_support")

MAX_MESSAGE_CHARS = 4000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_user(authorization: Optional[str]) -> dict[str, Any]:
    user = _get_user_by_token(_extract_token(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _thread_messages(cursor, thread_id: int, limit: int = 200) -> list[dict[str, Any]]:
    cursor.execute(
        """SELECT id, sender, admin_email, body, created_at
           FROM support_messages WHERE thread_id = ?
           ORDER BY id DESC LIMIT ?""",
        (thread_id, max(1, min(limit, 500))))
    return [dict(r) for r in reversed(cursor.fetchall())]


def _get_or_create_thread(cursor, user_id: int) -> dict[str, Any]:
    cursor.execute("SELECT * FROM support_threads WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is not None:
        return dict(row)
    now = _now_iso()
    try:
        cursor.execute(
            """INSERT INTO support_threads
               (user_id, subject, status, user_unread, admin_unread, last_message_at, created_at)
               VALUES (?, NULL, 'open', 0, 0, NULL, ?)""",
            (user_id, now))
    except Exception:  # noqa: BLE001 — concurrent first-touch lost the UNIQUE race
        # On MySQL REPEATABLE READ the open transaction still sees the
        # pre-race snapshot, so end it before re-reading the winner's row.
        # Safe: both callers invoke this before any other write on the
        # connection, so the rollback discards nothing else.
        cursor.connection.rollback()
        cursor.execute("SELECT * FROM support_threads WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            raise  # genuine INSERT failure, not the duplicate-key race
        return dict(row)
    cursor.execute("SELECT * FROM support_threads WHERE user_id = ?", (user_id,))
    return dict(cursor.fetchone())


class NotificationReadBody(BaseModel):
    ids: Optional[list[int]] = None
    all: bool = False


class NotificationSettingsBody(BaseModel):
    categories: dict[str, dict[str, bool]]


class SupportMessageBody(BaseModel):
    body: str
    subject: str = ""


class ThreadStatusBody(BaseModel):
    status: str


class BroadcastBody(BaseModel):
    title: str
    body: str = ""
    user_id: int = 0
    link: Optional[str] = None


def register_support_routes(app: FastAPI, ctx: RouteContext) -> None:

    # ───────────────────────── member: notifications ─────────────────────────

    @app.get('/api/notifications')
    async def list_notifications(limit: int = 50, unread_only: bool = False,
                                 authorization: str = Header(None)):
        user = _require_user(authorization)
        return {
            'notifications': notifications.list_notifications(
                user['id'], limit=limit, unread_only=unread_only),
            'unread': notifications.unread_count(user['id']),
        }

    @app.get('/api/notifications/summary')
    async def notification_summary(authorization: str = Header(None)):
        user = _require_user(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user_unread FROM support_threads WHERE user_id = ?", (user['id'],))
            row = cursor.fetchone()
            support_unread = int(row['user_unread'] or 0) if row else 0
        finally:
            conn.close()
        return {'unread': notifications.unread_count(user['id']),
                'support_unread': support_unread}

    @app.post('/api/notifications/read')
    async def read_notifications(data: NotificationReadBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not data.all and not data.ids:
            raise HTTPException(status_code=400, detail='Pass ids or all=true')
        marked = notifications.mark_read(user['id'], None if data.all else data.ids)
        return {'success': True, 'marked': marked,
                'unread': notifications.unread_count(user['id'])}

    @app.get('/api/notifications/settings')
    async def get_notification_settings(authorization: str = Header(None)):
        user = _require_user(authorization)
        return {'categories': notifications.catalog_for_user(user['id']),
                'email': user.get('email'),
                'phone': notifications.sms_phone(user['id'])}

    @app.put('/api/notifications/settings')
    async def put_notification_settings(data: NotificationSettingsBody,
                                        authorization: str = Header(None)):
        user = _require_user(authorization)
        unknown = set(data.categories) - set(notifications.CATEGORIES)
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f'Unknown categories: {sorted(unknown)}')
        notifications.set_prefs(user['id'], data.categories)
        return {'success': True, 'categories': notifications.catalog_for_user(user['id'])}

    @app.post('/api/notifications/test')
    async def send_test_notification(request: Request,
                                     data: dict = None,  # type: ignore[assignment]
                                     authorization: str = Header(None)):
        """Prove the member's email/SMS channel works BEFORE a live trading
        run depends on it (Plan 10 D8). Throttled with its own tight per-user
        cap (journaled to alert_log kind 'custom' with a test dedupe prefix) —
        an unthrottled test endpoint would be a free SMS-send primitive.
        SMS remains tier-gated inside the send path regardless."""
        user = _require_user(authorization)
        channel = ((data or {}).get('channel') or 'email').strip().lower()
        if channel not in ('email', 'sms'):
            raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")

        from alerts import _send_email, _send_sms
        from database import begin_write_transaction, get_db_connection
        from entitlements import sms_allowed_for_user

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
            cursor.execute(
                """SELECT COUNT(*) AS n FROM alert_log
                   WHERE user_id = ? AND created_at >= ?
                     AND dedupe_key LIKE 'notify-test:%'""",
                (user['id'], hour_ago))
            if int(cursor.fetchone()["n"] or 0) >= 3:
                raise HTTPException(status_code=429,
                                    detail='Test-send limit reached (3/hour)')
            sent = False
            detail = None
            # The whole point of this endpoint is to show the member what a
            # real notification looks like — sending it in English to a
            # Korean account proves the wrong thing.
            test_title, test_body = notifications_i18n.render(
                'notification_test', notifications.user_lang(user['id']))
            if channel == 'email':
                email = user.get('email')
                if not email:
                    detail = 'no email on account'
                else:
                    try:
                        # The branded shell IS what a real notification looks
                        # like now — the test must show it. Fail-soft to plain.
                        test_html = None
                        try:
                            from alert_email import wrap_basic_email
                            test_html = wrap_basic_email(
                                test_title, test_body,
                                notifications.user_lang(user['id']))
                        except Exception:  # noqa: BLE001
                            test_html = None
                        sent = _send_email(email, f'[Sooppiy] {test_title}',
                                           test_body, html=test_html)
                        detail = None if sent else 'provider not configured or rejected'
                    except Exception as exc:  # noqa: BLE001
                        detail = str(exc)
            else:
                phone = notifications.sms_phone(user['id'])
                # own connection: the entitlement check may run a lazy-expiry
                # UPDATE and must not open a txn on this endpoint's cursor
                conn_t = get_db_connection()
                try:
                    sms_ok = sms_allowed_for_user(conn_t.cursor(), user['id'])
                    conn_t.commit()
                finally:
                    conn_t.close()
                if not phone:
                    detail = 'no phone number saved in Settings'
                elif not sms_ok:
                    detail = 'SMS is not included in your current plan'
                else:
                    try:
                        sent = _send_sms(phone, f'[Sooppiy] {test_title} — {test_body}')
                        detail = None if sent else 'provider not configured or rejected'
                    except Exception as exc:  # noqa: BLE001
                        detail = str(exc)
            cursor.execute("SELECT id FROM agents WHERE user_id = ? LIMIT 1",
                           (user['id'],))
            agent_row = cursor.fetchone()
            begin_write_transaction(cursor)
            cursor.execute(
                """INSERT INTO alert_log
                   (agent_id, user_id, kind, title, body, channels_json,
                    dedupe_key, created_at)
                   VALUES (?, ?, 'custom', ?, ?, ?, ?, ?)""",
                (agent_row['id'] if agent_row else 0, user['id'],
                 f'Notification test ({channel})',
                 'delivered' if sent else f'failed: {detail}',
                 json.dumps([channel] if sent else []),
                 f"notify-test:{user['id']}:{_now_iso()}", _now_iso()))
            conn.commit()
        finally:
            conn.close()
        # `detail` is rendered straight into the Settings page, so it needs the
        # same treatment an HTTPException detail gets from the route handler.
        # alert_log above deliberately keeps the English for operators.
        return {'success': bool(sent), 'channel': channel,
                'detail': translate(detail, lang_from_request(request.headers))
                if detail else detail}

    # ───────────────────────── member: support chat ─────────────────────────

    @app.get('/api/support/thread')
    async def get_support_thread(authorization: str = Header(None)):
        user = _require_user(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            thread = _get_or_create_thread(cursor, user['id'])
            messages = _thread_messages(cursor, thread['id'])
            # Opening the conversation clears the member's unread badge.
            if thread['user_unread']:
                cursor.execute(
                    "UPDATE support_threads SET user_unread = 0 WHERE id = ?", (thread['id'],))
                thread['user_unread'] = 0
            conn.commit()
        finally:
            conn.close()
        return {'thread': thread, 'messages': messages}

    @app.post('/api/support/messages')
    async def post_support_message(data: SupportMessageBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        body = (data.body or '').strip()
        if not body:
            raise HTTPException(status_code=400, detail='Message body is required')
        body = body[:MAX_MESSAGE_CHARS]

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            thread = _get_or_create_thread(cursor, user['id'])
            now = _now_iso()
            cursor.execute(
                """INSERT INTO support_messages (thread_id, sender, body, created_at)
                   VALUES (?, 'user', ?, ?)""",
                (thread['id'], body, now))
            # VARCHAR(255) on MySQL prod (0019) — clamp or the UPDATE 500s.
            subject = (data.subject or thread['subject'] or body[:60]).strip()[:255]
            cursor.execute(
                """UPDATE support_threads
                   SET admin_unread = admin_unread + 1, last_message_at = ?,
                       subject = ?, status = 'open'
                   WHERE id = ?""",
                (now, subject, thread['id']))
            conn.commit()
            messages = _thread_messages(cursor, thread['id'])
        finally:
            conn.close()
        return {'success': True, 'messages': messages}

    # ───────────────────────── admin: support console ─────────────────────────

    @app.get('/api/admin/support/threads')
    async def admin_list_threads(status: str = '', limit: int = 100,
                                 authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            sql = """SELECT t.*, u.email AS user_email,
                            (SELECT COUNT(*) FROM support_messages m WHERE m.thread_id = t.id) AS message_count
                     FROM support_threads t JOIN users u ON u.id = t.user_id"""
            params: list[Any] = []
            if status:
                sql += " WHERE t.status = ?"
                params.append(status)
            # Threads with no message yet sort last; newest activity first.
            sql += " ORDER BY t.last_message_at IS NULL, t.last_message_at DESC LIMIT ?"
            params.append(max(1, min(limit, 500)))
            cursor.execute(sql, params)
            threads = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                "SELECT COALESCE(SUM(admin_unread), 0) AS n FROM support_threads")
            waiting = int(cursor.fetchone()['n'] or 0)
        finally:
            conn.close()
        return {'threads': threads, 'unread_total': waiting}

    @app.get('/api/admin/support/threads/{thread_id}')
    async def admin_get_thread(thread_id: int, authorization: str = Header(None)):
        require_admin(authorization)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT t.*, u.email AS user_email FROM support_threads t
                   JOIN users u ON u.id = t.user_id WHERE t.id = ?""", (thread_id,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail='Thread not found')
            thread = dict(row)
            messages = _thread_messages(cursor, thread_id)
            if thread['admin_unread']:
                cursor.execute(
                    "UPDATE support_threads SET admin_unread = 0 WHERE id = ?", (thread_id,))
                thread['admin_unread'] = 0
            conn.commit()
        finally:
            conn.close()
        return {'thread': thread, 'messages': messages}

    @app.post('/api/admin/support/threads/{thread_id}/reply')
    async def admin_reply(thread_id: int, data: SupportMessageBody,
                          authorization: str = Header(None)):
        admin = require_admin(authorization)
        body = (data.body or '').strip()
        if not body:
            raise HTTPException(status_code=400, detail='Message body is required')
        body = body[:MAX_MESSAGE_CHARS]

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM support_threads WHERE id = ?", (thread_id,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail='Thread not found')
            thread = dict(row)
            now = _now_iso()
            cursor.execute(
                """INSERT INTO support_messages
                   (thread_id, sender, admin_id, admin_email, body, created_at)
                   VALUES (?, 'admin', ?, ?, ?, ?)""",
                (thread_id, admin['id'], admin['email'], body, now))
            cursor.execute(
                """UPDATE support_threads
                   SET user_unread = user_unread + 1, admin_unread = 0, last_message_at = ?
                   WHERE id = ?""",
                (now, thread_id))
            conn.commit()
            messages = _thread_messages(cursor, thread_id)
        finally:
            conn.close()

        # Off the event loop — notify() may do a blocking SendGrid/Twilio call.
        # The headline is localized; the admin's actual reply cannot be, so it
        # rides along as the suffix.
        await asyncio.to_thread(notifications.notify_i18n, thread['user_id'], 'support',
                                'support_replied', None, '/support', True, body[:300])
        audit(admin, 'support.reply', f'thread:{thread_id}', body[:200])
        return {'success': True, 'messages': messages}

    @app.post('/api/admin/support/threads/{thread_id}/status')
    async def admin_thread_status(thread_id: int, data: ThreadStatusBody,
                                  authorization: str = Header(None)):
        admin = require_admin(authorization)
        if data.status not in ('open', 'closed'):
            raise HTTPException(status_code=400, detail="status must be 'open' or 'closed'")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM support_threads WHERE id = ?", (thread_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail='Thread not found')
            cursor.execute(
                "UPDATE support_threads SET status = ? WHERE id = ?", (data.status, thread_id))
            conn.commit()
        finally:
            conn.close()
        audit(admin, 'support.status', f'thread:{thread_id}', data.status)
        return {'success': True, 'status': data.status}

    @app.post('/api/admin/notifications/broadcast')
    async def admin_broadcast(data: BroadcastBody, authorization: str = Header(None)):
        admin = require_admin(authorization)
        title = (data.title or '').strip()
        if not title:
            raise HTTPException(status_code=400, detail='Title is required')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if data.user_id:
                cursor.execute("SELECT id FROM users WHERE id = ?", (data.user_id,))
                if cursor.fetchone() is None:
                    raise HTTPException(status_code=404, detail='Member not found')
                user_ids = [data.user_id]
            else:
                cursor.execute("SELECT id FROM users")
                user_ids = [r['id'] for r in cursor.fetchall()]
        finally:
            conn.close()

        # Members who switched announcements off are skipped inside notify().
        # The whole fan-out runs off the event loop: notify() opens its own DB
        # connections and may make blocking SendGrid/Twilio calls per member.
        def _fan_out() -> int:
            return sum(
                1 for uid in user_ids
                if notifications.notify(uid, 'announcement', title, data.body,
                                        link=data.link).get('channels'))

        delivered = await asyncio.to_thread(_fan_out)
        audit(admin, 'notifications.broadcast',
              f'users:{len(user_ids)}', f'{title} → delivered {delivered}')
        return {'success': True, 'targeted': len(user_ids), 'delivered': delivered}
