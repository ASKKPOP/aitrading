# Account Security Implementation Plan (Sub-project B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phone verification on the account page, SMS password reset on the sign-in page, a signup language choice that all content follows, and a localized welcome email.

**Architecture:** Everything rides existing rails: the namespaced code store in `routes_users.py` (cooldown/expiry/attempt caps, anti-enumeration), `alerts._send_sms` (Twilio), `email_i18n`/`email_sender` (6-language templates, Resend→SendGrid), and the SettingsPage alerts card that already collects the phone + A2P consent. New identity truth: `users.phone` + `users.phone_verified_at` (unique phone), synced into the alerts config on verify.

**Tech Stack:** FastAPI, SQLite dev / MySQL prod (alembic 0042), React/TS 6-language `tr()` i18n.

**Spec:** `docs/superpowers/specs/2026-08-05-account-security-design.md`

## Global Constraints

- SMS **alert** delivery behavior unchanged: verification gates password-reset-by-phone and the badge ONLY. The A2P consent disclosure text in SettingsPage is registration-bound — byte-identical, do not touch.
- Phone format: E.164, regex `^\+[1-9]\d{7,14}$`. `users.phone` is UNIQUE (nullable).
- Anti-enumeration on all unauthenticated endpoints: store the code even when no account matches; responses never reveal whether a phone/email is registered.
- All user-visible frontend strings through `tr(language, {ko,en,ja,th,vi,id})`; all emails/SMS localized to the same six languages. `analysis_agents.normalize_lang` is the single language validator.
- DB via `database.get_db_connection()` + `?` placeholders; never branch on `cursor.rowcount` after UPDATE (MySQL counts changed, not matched); no `ESCAPE '\\'`.
- Tests: `unittest.TestCase` + `TestClient` + temp SQLite (copy `test_billing.py` patterns); NO live network — conftest already blanks TWILIO_*/SENDGRID_*; patch `routes_users._send_sms` (imported name) and `email_sender` senders in tests.
- Python: `/Users/desirey/Programming/src/ai-trade/.venv/bin/python` (absolute). Work from the worktree root. Focused tests: `... -m pytest service/server/tests/test_account_security.py -q`. Before each commit: ruff CI scope (`--select F401,F811,F821,F841`) on touched files + full suite once.
- Commit after every task, exact messages given; stage only the task's files.
- Alembic head on this branch is 0041 → the new revision is **0042** (verify with `ls service/server/alembic/versions/` before creating; renumber if the branch has moved).

---

### Task 1: Schema — users.phone + phone_verified_at + unique index

**Files:**
- Modify: `service/server/database.py` (ALTER list ~line 1361 area; index near the users indexes)
- Create: `service/server/alembic/versions/0042_user_phone_verification.py`
- Test: `service/server/tests/test_account_security.py` (new)

**Interfaces:**
- Produces: `users.phone TEXT NULL`, `users.phone_verified_at TEXT NULL`, unique index `idx_users_phone ON users(phone)`. Every later task relies on these names.

- [ ] **Step 1: Write the failing test**

Create `service/server/tests/test_account_security.py`:

```python
"""Account security (sub-project B) — phone verification, SMS password reset,
signup language choice, welcome email.

Spec: docs/superpowers/specs/2026-08-05-account-security-design.md
All external delivery (Twilio SMS, Resend/SendGrid email) is mocked.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database


class PhoneSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def test_phone_columns_exist(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            cols = {r["name"] for r in cur.fetchall()}
        finally:
            conn.close()
        self.assertLessEqual({"phone", "phone_verified_at"}, cols)

    def test_phone_unique(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash, phone) "
                        "VALUES ('a@t.dev', 'x', '+12025550001')")
            with self.assertRaises(Exception):
                cur.execute("INSERT INTO users (email, password_hash, phone) "
                            "VALUES ('b@t.dev', 'x', '+12025550001')")
            conn.rollback()
            # many NULL phones are fine
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('c@t.dev', 'x')")
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('d@t.dev', 'x')")
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest service/server/tests/test_account_security.py -q` → FAIL (phone not in cols)

- [ ] **Step 3: Implement**

`database.py` — append to the ALTER-statement list (same list Task 1 of the billing plan used, near line 1361):

```python
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "ALTER TABLE users ADD COLUMN phone_verified_at TEXT",
```

Near the other `CREATE INDEX` statements for users-adjacent tables, add:

```python
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)
    """)
```

Create `service/server/alembic/versions/0042_user_phone_verification.py`:

```python
"""users.phone + phone_verified_at — verified-phone identity for SMS
password reset. UNIQUE(phone): reset-by-phone must map to one account.
NULLs are unlimited on both dialects, so members without phones are
unaffected. Verification gates reset + badge only — SMS alert delivery
still reads the alerts settings target (see spec §2)."""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "phone" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL")
    if "phone_verified_at" not in cols:
        op.execute("ALTER TABLE users ADD COLUMN phone_verified_at VARCHAR(32) NULL")
    indexes = [i["name"] for i in sa.inspect(bind).get_indexes("users")]
    if "idx_users_phone" not in indexes:
        op.execute("CREATE UNIQUE INDEX idx_users_phone ON users(phone)")


def downgrade():
    op.execute("DROP INDEX idx_users_phone ON users")
    op.execute("ALTER TABLE users DROP COLUMN phone_verified_at")
    op.execute("ALTER TABLE users DROP COLUMN phone")
```

- [ ] **Step 4: Verify** — focused file passes; `alembic history` from `service/server` shows a clean chain with 0042 as head; full suite green.

- [ ] **Step 5: Commit** — `feat(account): users.phone + phone_verified_at schema (unique phone)`

---

### Task 2: sms_i18n + phone send-code / verify endpoints + /users/me fields

**Files:**
- Create: `service/server/sms_i18n.py`
- Modify: `service/server/routes_users.py`, `service/server/routes_models.py`
- Test: `service/server/tests/test_account_security.py` (append)

**Interfaces:**
- Produces: `sms_i18n.verification_sms(code, lang) -> str`, `sms_i18n.reset_sms(code, lang) -> str`; `POST /api/users/phone/send-code {phone}` (auth) → `{success}` / 400 bad format / 409 taken / 429 cooldown; `POST /api/users/phone/verify {code}` (auth) → writes `users.phone`+`phone_verified_at`, syncs alerts config phone; `/api/users/me` gains `phone`, `phone_verified`.

- [ ] **Step 1: Failing tests** — append:

```python
import secrets as _secrets
from unittest.mock import patch

from fastapi.testclient import TestClient


def _mk_user(db, email="u@t.dev", lang="en"):
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, lang) VALUES (?, 'x', ?)",
                    (email, lang))
        user_id = cur.lastrowid
        token = _secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) "
                    "VALUES (?, ?, '2030-01-01T00:00:00Z')", (user_id, token))
        conn.commit()
        return user_id, token
    finally:
        conn.close()


class PhoneVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _mk_user(database, lang="ko")

    def tearDown(self):
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_send_code_validates_e164(self):
        r = self.client.post("/api/users/phone/send-code",
                             json={"phone": "01012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_send_and_verify_flow(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        to_number, body = sms.call_args.args
        self.assertEqual(to_number, "+821012345678")
        code = "".join(ch for ch in body if ch.isdigit())[:6]
        self.assertEqual(len(code), 6)
        self.assertIn("Sooppiy", body)  # branded, Korean template for lang=ko
        r = self.client.post("/api/users/phone/verify",
                             json={"code": code}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT phone, phone_verified_at FROM users WHERE id = ?",
                        (self.user_id,))
            row = dict(cur.fetchone())
            cur.execute("SELECT config_json FROM user_api_settings "
                        "WHERE user_id = ? AND target = 'alerts'", (self.user_id,))
            cfg = cur.fetchone()
        finally:
            conn.close()
        self.assertEqual(row["phone"], "+821012345678")
        self.assertTrue(row["phone_verified_at"])
        import json as _json
        self.assertEqual(_json.loads(dict(cfg)["config_json"]).get("phone"),
                         "+821012345678")
        me = self.client.get("/api/users/me", headers=self._h()).json()
        self.assertEqual(me["phone"], "+821012345678")
        self.assertTrue(me["phone_verified"])

    def test_send_code_409_when_taken(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash, phone, "
                        "phone_verified_at) VALUES ('o@t.dev', 'x', "
                        "'+821099998888', '2026-01-01T00:00:00Z')")
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True):
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821099998888"}, headers=self._h())
        self.assertEqual(r.status_code, 409)

    def test_send_code_cooldown(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
            r = self.client.post("/api/users/phone/send-code",
                                 json={"phone": "+821012345678"}, headers=self._h())
        self.assertEqual(r.status_code, 429)

    def test_verify_wrong_code_400(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
        r = self.client.post("/api/users/phone/verify",
                             json={"code": "000000"}, headers=self._h())
        self.assertEqual(r.status_code, 400)

    def test_verify_alerts_config_preserves_existing_keys(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO user_api_settings (user_id, target, enabled, "
                        "config_json) VALUES (?, 'alerts', 1, "
                        "'{\"sms_consent\": true, \"phone\": \"+820000000000\"}')",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True) as sms:
            self.client.post("/api/users/phone/send-code",
                             json={"phone": "+821012345678"}, headers=self._h())
        code = "".join(ch for ch in sms.call_args.args[1] if ch.isdigit())[:6]
        self.client.post("/api/users/phone/verify", json={"code": code},
                         headers=self._h())
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_json FROM user_api_settings "
                        "WHERE user_id = ? AND target = 'alerts'", (self.user_id,))
            import json as _json
            cfg = _json.loads(dict(cur.fetchone())["config_json"])
        finally:
            conn.close()
        self.assertEqual(cfg["phone"], "+821012345678")
        self.assertTrue(cfg["sms_consent"])
```

Note for the implementer: `user_api_settings` schema — check the real column set in `database.py` (`user_id/target/enabled/config_json/...`) and adjust the INSERT if it differs.

- [ ] **Step 2: verify FAIL (404)**

- [ ] **Step 3: Implement**

`service/server/sms_i18n.py`:

```python
"""SMS message bodies — 6 languages, keyed off users.lang.

Kept deliberately short: SMS segments cost money and Twilio truncates at
1600 chars. Every body carries the brand, the code, the 5-minute note and
the never-share line the email templates use."""
from __future__ import annotations

from analysis_agents import normalize_lang

_VERIFY = {
    'en': 'Sooppiy verification code: {code}. Expires in 5 minutes. Never share this code.',
    'ko': 'Sooppiy 인증 코드: {code}. 5분 후 만료됩니다. 코드를 절대 공유하지 마세요.',
    'ja': 'Sooppiy認証コード：{code}。有効期限は5分です。コードは誰にも共有しないでください。',
    'th': 'รหัสยืนยัน Sooppiy: {code} หมดอายุใน 5 นาที อย่าเปิดเผยรหัสนี้ให้ใคร',
    'vi': 'Mã xác minh Sooppiy: {code}. Hết hạn sau 5 phút. Không chia sẻ mã này.',
    'id': 'Kode verifikasi Sooppiy: {code}. Kedaluwarsa dalam 5 menit. Jangan bagikan kode ini.',
}

_RESET = {
    'en': 'Sooppiy password reset code: {code}. Expires in 5 minutes. If you did not request this, ignore it. Never share this code.',
    'ko': 'Sooppiy 비밀번호 재설정 코드: {code}. 5분 후 만료됩니다. 요청하지 않았다면 무시하세요. 코드를 절대 공유하지 마세요.',
    'ja': 'Sooppiyパスワード再設定コード：{code}。有効期限は5分です。依頼していない場合は無視してください。コードは共有しないでください。',
    'th': 'รหัสรีเซ็ตรหัสผ่าน Sooppiy: {code} หมดอายุใน 5 นาที หากไม่ได้ขอ ให้เพิกเฉย อย่าเปิดเผยรหัสนี้',
    'vi': 'Mã đặt lại mật khẩu Sooppiy: {code}. Hết hạn sau 5 phút. Nếu không phải bạn yêu cầu, hãy bỏ qua. Không chia sẻ mã này.',
    'id': 'Kode atur ulang kata sandi Sooppiy: {code}. Kedaluwarsa dalam 5 menit. Abaikan jika Anda tidak memintanya. Jangan bagikan kode ini.',
}


def verification_sms(code: str, lang: str) -> str:
    return _VERIFY[normalize_lang(lang)].format(code=code)


def reset_sms(code: str, lang: str) -> str:
    return _RESET[normalize_lang(lang)].format(code=code)
```

`routes_models.py` — add:

```python
class PhoneSendCodeRequest(BaseModel):
    phone: str


class PhoneVerifyRequest(BaseModel):
    code: str
```

`routes_users.py` — module level: `import re`, `from alerts import _send_sms`, `import sms_i18n`, and:

```python
_PHONE_RE = re.compile(r'^\+[1-9]\d{7,14}$')
```

Inside `register_user_routes`, after the reset-password endpoint:

```python
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
            raise HTTPException(status_code=409,
                                detail='This phone number is already verified '
                                       'on another account')
        store_key = f"phone:{user['id']}"
        now = datetime.now(timezone.utc)
        existing = _load_code(store_key, ctx)
        if existing:
            last_sent_at = existing.get('last_sent_at')
            if last_sent_at and (now - last_sent_at).total_seconds() < CODE_RESEND_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429,
                                    detail='Please wait before requesting another code')
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
```

(Adjust the `user_api_settings` INSERT to the real column set; check whether `routes_users.py` already imports `json` — add if missing.)

`/api/users/me` return dict — add:

```python
            'phone': user.get('phone'),
            'phone_verified': bool(user.get('phone_verified_at')),
```

- [ ] **Step 4: Verify** — focused file green; ruff CI-scope clean; full suite green.
- [ ] **Step 5: Commit** — `feat(account): phone verification — localized SMS codes, unique verified phones`

---

### Task 3: SMS password reset endpoints

**Files:**
- Modify: `service/server/routes_users.py`, `service/server/routes_models.py`
- Test: `service/server/tests/test_account_security.py` (append)

**Interfaces:**
- Produces: `POST /api/users/forgot-password-sms {phone}`; `POST /api/users/reset-password-sms {phone, code, new_password}` (new_password ≥8 via the same validator style as `UserResetPasswordRequest`).

- [ ] **Step 1: Failing tests** — append:

```python
class SmsPasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _mk_user(database, email="sms@t.dev", lang="ja")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET phone = '+818011112222', "
                        "phone_verified_at = '2026-01-01T00:00:00Z' WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_forgot_sms_generic_for_unknown_phone(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            r1 = self.client.post("/api/users/forgot-password-sms",
                                  json={"phone": "+818011112222"})
            r2 = self.client.post("/api/users/forgot-password-sms",
                                  json={"phone": "+818099990000"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json(), r2.json())     # identical bodies — no probing
        self.assertEqual(sms.call_count, 1)        # only the real, verified phone

    def test_reset_by_sms_happy_path_kills_sessions(self):
        with patch("routes_users._send_sms", return_value=True) as sms:
            self.client.post("/api/users/forgot-password-sms",
                             json={"phone": "+818011112222"})
        code = "".join(ch for ch in sms.call_args.args[1] if ch.isdigit())[:6]
        r = self.client.post("/api/users/reset-password-sms",
                             json={"phone": "+818011112222", "code": code,
                                   "new_password": "brandnewpw1"})
        self.assertEqual(r.status_code, 200, r.text)
        # old token dead
        me = self.client.get("/api/users/me",
                             headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(me.status_code, 401)
        # new password logs in
        login = self.client.post("/api/users/login",
                                 json={"email": "sms@t.dev",
                                       "password": "brandnewpw1"})
        self.assertEqual(login.status_code, 200, login.text)

    def test_reset_sms_wrong_code(self):
        with patch("routes_users._send_sms", return_value=True):
            self.client.post("/api/users/forgot-password-sms",
                             json={"phone": "+818011112222"})
        r = self.client.post("/api/users/reset-password-sms",
                             json={"phone": "+818011112222", "code": "000000",
                                   "new_password": "brandnewpw1"})
        self.assertEqual(r.status_code, 400)

    def test_unverified_phone_never_receives_reset(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET phone_verified_at = NULL WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("routes_users._send_sms", return_value=True) as sms:
            r = self.client.post("/api/users/forgot-password-sms",
                                 json={"phone": "+818011112222"})
        self.assertEqual(r.status_code, 200)
        sms.assert_not_called()
```

- [ ] **Step 2: verify FAIL (404)**

- [ ] **Step 3: Implement** — `routes_models.py`:

```python
class PhoneForgotPasswordRequest(BaseModel):
    phone: str


class PhoneResetPasswordRequest(BaseModel):
    phone: str
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw_len(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
```

`routes_users.py` — mirror the email pair exactly (namespace `smsreset:{phone}`; store the cooldown entry even for unknown/unverified phones; send `sms_i18n.reset_sms(code, lang)` only when a row matches `phone = ? AND phone_verified_at IS NOT NULL`; response always `{'success': True, 'message': 'If an account exists, a code was sent'}`). `reset-password-sms`: identical code checks; look up the user by verified phone; generic 400 `'Invalid code'` when absent; update `password_hash`; `DELETE FROM user_tokens WHERE user_id = ?`; delete the code. Follow the email endpoints' structure line-for-line — they are directly above in the same file.

- [ ] **Step 4: Verify** — focused green, ruff, full suite.
- [ ] **Step 5: Commit** — `feat(account): SMS password reset — anti-enumeration mirror of the email path`

---

### Task 4: Signup language choice + welcome email

**Files:**
- Modify: `service/server/routes_models.py` (`UserSendCodeRequest`/`UserRegisterRequest` gain `lang`), `service/server/routes_users.py` (send-code, register), `service/server/email_i18n.py`, `service/server/email_sender.py`
- Test: `service/server/tests/test_account_security.py` (append)

**Interfaces:**
- Produces: optional `lang` on `POST /api/users/send-code` + `POST /api/users/register` (validated via `normalize_lang`; invalid/absent → existing geo guess); `email_i18n.welcome_email(lang) -> tuple[str, str]` (subject, html) + `welcome_email_text(lang) -> str`; `email_sender.send_welcome_email(to_email, lang) -> bool`; register fires the welcome email fail-soft AFTER responding data is committed.

- [ ] **Step 1: Failing tests** — append:

```python
class SignupLangAndWelcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def test_chosen_lang_stored_and_welcome_sent(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            sent['lang'] = lang
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            r = self.client.post("/api/users/send-code",
                                 json={"email": "l@t.dev", "lang": "th"})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(sent['lang'], 'th')

        with patch.object(routes_users, "send_welcome_email",
                          return_value=True) as welcome:
            r = self.client.post("/api/users/register",
                                 json={"email": "l@t.dev", "code": sent['code'],
                                       "password": "longenough1", "lang": "th"})
            self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT lang FROM users WHERE email = 'l@t.dev'")
            self.assertEqual(dict(cur.fetchone())["lang"], "th")
        finally:
            conn.close()
        welcome.assert_called_once()
        self.assertEqual(welcome.call_args.args, ("l@t.dev", "th"))

    def test_invalid_lang_falls_back_to_guess(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            sent['lang'] = lang
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            self.client.post("/api/users/send-code",
                             json={"email": "g@t.dev", "lang": "xx"})
        self.assertIn(sent['lang'], {"en", "ko", "ja", "th", "vi", "id"})

    def test_welcome_failure_does_not_fail_signup(self):
        import routes_users
        sent = {}

        def fake_send_code(email, code, lang, purpose='signup'):
            sent['code'] = code
            return True

        with patch.object(routes_users, "send_verification_code_email",
                          side_effect=fake_send_code):
            self.client.post("/api/users/send-code",
                             json={"email": "w@t.dev", "lang": "en"})
        with patch.object(routes_users, "send_welcome_email",
                          side_effect=RuntimeError("mail down")):
            r = self.client.post("/api/users/register",
                                 json={"email": "w@t.dev", "code": sent['code'],
                                       "password": "longenough1", "lang": "en"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("token", r.json())

    def test_welcome_templates_all_langs(self):
        from email_i18n import welcome_email, welcome_email_text
        for lang in ("en", "ko", "ja", "th", "vi", "id"):
            subject, html = welcome_email(lang)
            self.assertTrue(subject and "<" in html)
            self.assertIn("sooppiy.com", html)
            self.assertTrue(welcome_email_text(lang))
```

- [ ] **Step 2: verify FAIL**

- [ ] **Step 3: Implement**

`routes_models.py`: add `lang: str | None = None` to `UserSendCodeRequest` and `UserRegisterRequest`.

`routes_users.py`:
- module imports: `from analysis_agents import LANG_NAMES` (for membership check), `from email_sender import send_welcome_email` (extend the existing email_sender import line).
- helper at module level:

```python
def _chosen_lang(raw: str | None) -> str | None:
    """The member's explicit signup language — only trusted when it is a
    supported code. Anything else returns None and the geo guess stands."""
    if raw and raw in LANG_NAMES:
        return raw
    return None
```

- `send_verification_code` endpoint: `lang = _chosen_lang(data.lang) or await asyncio.to_thread(resolve_signup_lang, request)` (replacing the current unconditional guess).
- `user_register`: `chosen = _chosen_lang(data.lang)`; then `lang, geo_country = ...resolve_signup_locale...` as today, followed by `if chosen: lang = chosen` before the INSERT. After `conn.commit()` / `_delete_code(...)`, before returning:

```python
        try:
            await asyncio.to_thread(send_welcome_email, data.email, lang)
        except Exception as exc:  # noqa: BLE001 — a mail outage must never
            # fail a signup; the account and session are already committed.
            _logger.warning('[Email] welcome email to %s failed: %s',
                            data.email, exc)
```

`email_i18n.py` — add a `'welcome'` entry to `_COPY`-style content but as its own dict (welcome has no code block). Implement:

```python
_WELCOME = {
    'en': {'subject': 'Welcome to Sooppiy — your account is ready',
           'heading': 'Welcome to Sooppiy',
           'body': ('Your account is ready. Sooppiy watches AI trading for '
                    'you: follow agents, mirror their signals, and let the '
                    'automation desk manage runs within the limits you set.'),
           'steps': ['Choose a membership plan to unlock the platform',
                     'Explore the market and the trading terminal',
                     'Set your notification preferences (email · SMS)'],
           'cta': 'Sign in'},
    'ko': {'subject': 'Sooppiy에 오신 것을 환영합니다 — 계정이 준비되었습니다',
           'heading': 'Sooppiy에 오신 것을 환영합니다',
           'body': ('계정이 준비되었습니다. Sooppiy는 AI 트레이딩을 대신 지켜봅니다: '
                    '에이전트를 팔로우하고, 시그널을 미러링하고, 설정한 한도 안에서 '
                    '자동 트레이딩 데스크가 운용하도록 맡겨보세요.'),
           'steps': ['멤버십 플랜을 선택해 플랫폼을 열어보세요',
                     '마켓과 트레이딩 터미널을 둘러보세요',
                     '알림 설정(이메일 · SMS)을 구성하세요'],
           'cta': '로그인'},
    'ja': {'subject': 'Sooppiyへようこそ — アカウントの準備ができました',
           'heading': 'Sooppiyへようこそ',
           'body': ('アカウントの準備ができました。SooppiyはAIトレーディングをあなたの'
                    '代わりに見守ります：エージェントをフォローし、シグナルをミラーし、'
                    '設定した上限の範囲で自動売買デスクに運用を任せられます。'),
           'steps': ['メンバーシッププランを選んでプラットフォームを開く',
                     'マーケットとトレーディングターミナルを見てみる',
                     '通知設定（メール · SMS）を構成する'],
           'cta': 'サインイン'},
    'th': {'subject': 'ยินดีต้อนรับสู่ Sooppiy — บัญชีของคุณพร้อมแล้ว',
           'heading': 'ยินดีต้อนรับสู่ Sooppiy',
           'body': ('บัญชีของคุณพร้อมแล้ว Sooppiy เฝ้าดูการเทรดด้วย AI แทนคุณ: '
                    'ติดตามเอเจนต์ คัดลอกสัญญาณ และให้เดสก์อัตโนมัติจัดการรันภายในขีดจำกัดที่คุณตั้ง'),
           'steps': ['เลือกแพ็กเกจสมาชิกเพื่อปลดล็อกแพลตฟอร์ม',
                     'สำรวจตลาดและเทอร์มินัลเทรด',
                     'ตั้งค่าการแจ้งเตือน (อีเมล · SMS)'],
           'cta': 'เข้าสู่ระบบ'},
    'vi': {'subject': 'Chào mừng đến với Sooppiy — tài khoản của bạn đã sẵn sàng',
           'heading': 'Chào mừng đến với Sooppiy',
           'body': ('Tài khoản của bạn đã sẵn sàng. Sooppiy theo dõi giao dịch AI '
                    'thay cho bạn: theo dõi các agent, sao chép tín hiệu, và để bàn '
                    'tự động quản lý các phiên trong giới hạn bạn đặt ra.'),
           'steps': ['Chọn gói thành viên để mở khóa nền tảng',
                     'Khám phá thị trường và terminal giao dịch',
                     'Thiết lập tùy chọn thông báo (email · SMS)'],
           'cta': 'Đăng nhập'},
    'id': {'subject': 'Selamat datang di Sooppiy — akun Anda siap',
           'heading': 'Selamat datang di Sooppiy',
           'body': ('Akun Anda sudah siap. Sooppiy memantau trading AI untuk '
                    'Anda: ikuti agen, tiru sinyalnya, dan biarkan meja otomasi '
                    'mengelola run dalam batas yang Anda tentukan.'),
           'steps': ['Pilih paket keanggotaan untuk membuka platform',
                     'Jelajahi pasar dan terminal trading',
                     'Atur preferensi notifikasi (email · SMS)'],
           'cta': 'Masuk'},
}


def welcome_email(lang: str) -> tuple[str, str]:
    """(subject, html) for the post-signup welcome email."""
    lang = lang if lang in _WELCOME else 'en'
    c = _WELCOME[lang]
    chrome = _CHROME[lang]
    steps = ''.join(f'<li style="margin:6px 0">{s}</li>' for s in c['steps'])
    html = f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px">
  <h2 style="margin:0 0 4px">Sooppiy</h2>
  <p style="color:#8a8073;margin:0 0 20px">{chrome['tagline']}</p>
  <h3 style="margin:0 0 12px">{c['heading']}</h3>
  <p style="line-height:1.6">{c['body']}</p>
  <ol style="line-height:1.6;padding-left:20px">{steps}</ol>
  <p style="margin:24px 0"><a href="https://sooppiy.com" style="background:#c26a45;color:#fff;padding:10px 22px;border-radius:8px;text-decoration:none">{c['cta']}</a></p>
  <p style="color:#8a8073;font-size:12px;margin-top:28px">{chrome['footer']}</p>
</div>"""
    return c['subject'], html


def welcome_email_text(lang: str) -> str:
    lang = lang if lang in _WELCOME else 'en'
    c = _WELCOME[lang]
    steps = '\n'.join(f'  {i}. {s}' for i, s in enumerate(c['steps'], 1))
    return f"{c['heading']}\n\n{c['body']}\n\n{steps}\n\nhttps://sooppiy.com\n"
```

(Match the real `_CHROME`/existing HTML style in the file — if `verification_email` uses a fuller chrome builder, reuse it instead of the inline skeleton above.)

`email_sender.py` — add, mirroring `send_verification_code_email`'s delivery chain:

```python
def send_welcome_email(to_email: str, lang: str = "en") -> bool:
    """Post-signup welcome. Same rails as the code emails: Resend when
    configured, the SendGrid alert account otherwise, no-op last."""
    from email_i18n import welcome_email, welcome_email_text
    subject, html = welcome_email(lang)
    text = welcome_email_text(lang)
    return _deliver(to_email, subject, text, html)
```

(If `email_sender` has no shared `_deliver`, extract one from `send_verification_code_email`'s existing Resend/SendGrid branches so the two senders share it — do NOT duplicate the delivery block.)

- [ ] **Step 4: Verify** — focused green, ruff, full suite.
- [ ] **Step 5: Commit** — `feat(account): signup language choice + localized welcome email`

---

### Task 5: Frontend — signup language selector + forgot-password phone toggle (authV2.tsx)

**Files:** Modify: `service/frontend/src/authV2.tsx` only.

- [ ] **Step 1: SignUpPage** (~line 342): add `const { language, setLanguage } = useLanguage()` (extend the existing destructure). On the email step, above the email input, render a language select:

```tsx
        <select value={language}
          onChange={e => setLanguage(e.target.value as any)}
          style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 14, width: '100%', marginBottom: 10 }}>
          <option value="en">English</option>
          <option value="ko">한국어</option>
          <option value="ja">日本語</option>
          <option value="th">ไทย</option>
          <option value="vi">Tiếng Việt</option>
          <option value="id">Bahasa Indonesia</option>
        </select>
```

With a label above it: `tr(language, { ko: '언어', en: 'Language', ja: '言語', th: 'ภาษา', vi: 'Ngôn ngữ', id: 'Bahasa' })`. Native names in the options are intentionally NOT translated.

Send the language with both calls: `body: JSON.stringify({ email, lang: language })` in `sendCode`, and `body: JSON.stringify({ email, code, password, lang: language })` in `completeRegister`.

- [ ] **Step 2: ForgotPasswordPage** (~line 448): add `const [method, setMethod] = useState<'email' | 'phone'>('email')` and `const [phone, setPhone] = useState('')`. Render a two-button toggle above the identifier input (email | phone, ghost/primary styles consistent with the page). When `method === 'phone'`: the identifier input becomes `type="tel"` with placeholder `+821012345678`, request goes to `/users/forgot-password-sms` with `{ phone }`, and the reset step posts to `/users/reset-password-sms` with `{ phone, code, new_password }`. Email mode unchanged. New strings (6 langs each): `email` label `{ ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email', id: 'Email' }`, `phone` label `{ ko: '휴대폰', en: 'Phone', ja: '携帯電話', th: 'โทรศัพท์', vi: 'Điện thoại', id: 'Ponsel' }`, phone-mode subtitle `{ ko: '인증된 휴대폰 번호로 코드를 보내드립니다.', en: "We'll text a code to your verified phone number.", ja: '認証済みの電話番号にコードを送信します。', th: 'เราจะส่งรหัสไปยังเบอร์โทรที่ยืนยันแล้วของคุณ', vi: 'Chúng tôi sẽ nhắn mã đến số điện thoại đã xác minh của bạn.', id: 'Kami akan mengirim kode ke nomor telepon terverifikasi Anda.' }`.

- [ ] **Step 3: Verify** — `cd service/frontend && npx tsc --noEmit && npm run build` clean.
- [ ] **Step 4: Commit** — `feat(account): signup language picker + phone option on forgot-password`

---

### Task 6: Frontend — SettingsPage verification UI + email badge

**Files:** Modify: `service/frontend/src/pages/SettingsPage.tsx` only. The A2P consent disclosure block must remain byte-identical.

- [ ] **Step 1:** Load verification state: add state `const [me, setMe] = useState<{ phone: string | null, phone_verified: boolean, email: string } | null>(null)` and fetch `/api/users/me` (auth header, same pattern as the page's other loads) on mount and after a successful verify.

- [ ] **Step 2:** Email verified badge — where the page shows account info (or, if it doesn't, at the top of the alerts card), render the account email with a badge: `✓ {tr(language, { ko: '인증됨', en: 'Verified', ja: '確認済み', th: 'ยืนยันแล้ว', vi: 'Đã xác minh', id: 'Terverifikasi' })}` in green (`#22c55e`), 12px.

- [ ] **Step 3:** Phone verification UI inside the existing phone card, below the save button/consent block. Verified iff `me?.phone_verified && me?.phone === alertPrefs.phone && !!alertPrefs.phone`. Render:
  - Verified: the green `✓ Verified` badge next to a line showing the number.
  - Not verified and a phone is entered+saved with consent: a `Send verification code` button → on 200 show a 6-digit input + `Verify` button → on 200 refetch `/users/me`, show the badge. Errors surface the response `detail` via the page's existing error style. New strings (6 langs): sendCode `{ ko: '인증 코드 보내기', en: 'Send verification code', ja: '認証コードを送信', th: 'ส่งรหัสยืนยัน', vi: 'Gửi mã xác minh', id: 'Kirim kode verifikasi' }`, verify `{ ko: '인증하기', en: 'Verify', ja: '認証する', th: 'ยืนยัน', vi: 'Xác minh', id: 'Verifikasi' }`, notVerified `{ ko: '미인증', en: 'Not verified', ja: '未認証', th: 'ยังไม่ยืนยัน', vi: 'Chưa xác minh', id: 'Belum diverifikasi' }`, codePlaceholder `{ ko: '6자리 코드', en: '6-digit code', ja: '6桁のコード', th: 'รหัส 6 หลัก', vi: 'Mã 6 chữ số', id: 'Kode 6 digit' }`, whyVerify `{ ko: '인증된 번호로 휴대폰 비밀번호 재설정을 사용할 수 있습니다.', en: 'A verified number lets you reset your password by SMS.', ja: '認証済みの番号でSMSによるパスワード再設定が使えます。', th: 'เบอร์ที่ยืนยันแล้วใช้รีเซ็ตรหัสผ่านทาง SMS ได้', vi: 'Số đã xác minh cho phép đặt lại mật khẩu qua SMS.', id: 'Nomor terverifikasi memungkinkan reset kata sandi lewat SMS.' }`.

Calls: `POST ${API_BASE}/users/phone/send-code` `{ phone: alertPrefs.phone }`, `POST ${API_BASE}/users/phone/verify` `{ code }` — both with the auth header.

- [ ] **Step 4: Verify** — tsc + build clean.
- [ ] **Step 5: Commit** — `feat(account): phone verification UI + verified badges on settings`

---

### Task 7: Full verification pass

- [ ] ruff CI scope (`--select F401,F811,F821,F841`) on `service/server` — clean.
- [ ] Full backend suite TWICE — both green.
- [ ] `cd service/frontend && npx tsc --noEmit && npm run build` — clean.
- [ ] Mutation spot-checks (apply → clear `__pycache__` → focused tests must FAIL → revert → green):
  a) In `phone_verify`, disable the uniqueness re-check (make the SELECT match nothing) → `test_send_code_409_when_taken` stays green but add-verify path: expect `test_verify_...` uniqueness coverage to fail — if nothing fails, ADD a verify-stage 409 test first, then re-run.
  b) In `reset-password-sms`, drop the `DELETE FROM user_tokens` line → `test_reset_by_sms_happy_path_kills_sessions` must fail.
  c) In `user_register`, remove the `send_welcome_email` call → `test_chosen_lang_stored_and_welcome_sent` must fail.
- [ ] Local API smoke: uvicorn from the worktree on a free port with Twilio/SendGrid env empty → signup flow works end-to-end with codes appearing in the log instead of SMS/email; `git status` clean afterwards.
- [ ] Fix anything found (smallest change, committed); no empty commits.

---

### Task 8: PR → CI → merge → prod deploy → prod verify

1. Push `feat/account-security`, open a PR describing the four features (English), wait for all CI checks, merge (merge commit, repo convention).
2. Deploy merged main to sooppiy.com per the standard runbook (dated tag `YYYYMMDD-accountsec`, compose backend+worker together, SPA publish + restorecon). Migration 0042 applies automatically at boot (advisory-locked).
3. Prod verification (≥2 passes): `/api/health` ok; alembic head `0042`; `users.phone` columns present on MySQL; signed-up test flow — mint a temp account with a chosen language, confirm `users.lang` matches, welcome email attempt logged/sent, delete the temp account (standard temp-credential practice); `/api/users/phone/send-code` returns 401 unauthenticated, 400 on a bad number with a real token; frontend serves the new authV2/SettingsPage bundle (grep a new string in the built chunk).
4. Report deferred/minor findings and any prod observations in the final summary.
