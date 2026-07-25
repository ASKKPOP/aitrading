# Localized Notifications (email + SMS in the user's selected language) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send every member-facing email and SMS (signup/reset codes, all trade/risk/watch/run/fleet alerts, notification-center messages) in the language the member selected, persisted server-side, defaulting at signup from IP country → browser language → English.

**Architecture:** Add a persisted `users.lang` column (the one durable source both request-time and background senders can read). Derive the signup default from a new `signup_lang.py` resolver (IP-country lookup, falling back to the `Accept-Language` header, falling back to `en`). Externalize all system-generated notification copy into two catalogues (`email_i18n.py` for transactional emails, `notifications_i18n.py` for alerts), mirroring the existing `i18n_errors_data.py` pattern, and thread the recipient's stored language into `send_verification_code_email`, `alerts.send_alert`, and `notifications.notify`.

**Tech Stack:** FastAPI + Python 3.12, SQLite (dev) / MySQL 8 (prod), Alembic migrations, React 18 + Vite + TypeScript (hand-rolled i18n in `i18n.ts`). No new Python dependency — IP geolocation uses the already-present `httpx` against a free no-key HTTP API with a short timeout and graceful fallback.

## Global Constraints

- Supported languages are exactly `ko`, `en`, `ja`, `th`, `vi`; unknown → `en`. Reuse `analysis_agents.normalize_lang` — do NOT introduce a second language list.
- Every notification path is **fail-soft**: a localization, GeoIP, or DB error must never break trading, signup, or alerting. On any doubt, fall back to English and continue.
- Migrations must work on BOTH SQLite (dev, idempotent ALTER mirrored in `database.init_database()`) and MySQL 8 (prod, Alembic). Follow the `0029_position_leverage.py` pattern exactly.
- `users.lang` is `VARCHAR(8) NOT NULL DEFAULT 'en'`. Store only normalized codes (`normalize_lang` output) — never a raw locale like `ko-KR`.
- Prod runs MySQL; test the worker/background paths, not just the API. Run `ruff check` and `pytest` before every push (repo CI runs ruff F-checks + pytest + tsc).
- **Out of scope (staff-authored free text):** admin announcements and support replies (`routes_support.py`) are typed by a human in one language and cannot be machine-localized here. Admin *operator* alerts (`admin_alerts.py`) stay English (they go to the operator, not members). Do not touch these.
- **Translation honesty:** provide verified `en` + `ko` for every catalogue entry (ko is the frontend `DEFAULT_LANGUAGE`). `ja`/`th`/`vi` entries fall through to English via the catalogue's safe fallback until a native speaker fills them — do NOT fabricate unverified translations. Enabling ja/th/vi copy is a follow-up task gated on verified translations.

---

## File Structure

**New files**
- `service/server/signup_lang.py` — resolve a default language from a request (IP country → Accept-Language → en).
- `service/server/email_i18n.py` — subject + HTML catalogue for transactional emails (verification, reset), keyed by message id and language.
- `service/server/notifications_i18n.py` — title/body template catalogue for system alerts, keyed by message id and language, with a `render(msg_id, lang, **params)` function.
- `service/server/alembic/versions/0031_user_lang.py` — add `users.lang`.
- `service/server/tests/test_signup_lang.py`, `test_email_i18n.py`, `test_notifications_i18n.py`, `test_user_language_endpoint.py` — unit tests.

**Modified files**
- `service/server/database.py` — SQLite mirror ALTER for `users.lang` (~line 2966 block).
- `service/server/routes_users.py` — `request: Request` on `send-code`/`register`; set `lang` at register; `GET`/`PUT /api/users/language`; return `lang` in `login` and `/me`.
- `service/server/email_sender.py` — `send_verification_code_email(to_email, code, lang="en")`.
- `service/server/alerts.py` — look up recipient `users.lang`; render catalogue title/body before sending; accept structured `(msg_id, params)`.
- `service/server/notifications.py` — thread recipient `lang` into `_send_external`; `notify_i18n` helper for templated callers.
- 8 producer files (`fleet_supervisor.py`, `automation.py`, `run_engine.py`, `risk_engine.py`, `watch_engine.py`, `run_reports.py`, `execution/gateway.py`) — pass `(msg_id, params)` instead of English strings.
- `service/frontend/src/App.tsx`, `appChrome.tsx`, `apiLanguage.ts` — persist switcher to server when logged in; seed language from server on login/`/me`.

Three independently shippable phases: **A** (persisted language + signup default), **B** (transactional emails), **C** (alert/notification catalogue). A and B deliver value alone; C is the largest.

---

# Phase A — Persisted user language + signup default

### Task A1: Add `users.lang` column (migration + SQLite mirror)

**Files:**
- Create: `service/server/alembic/versions/0031_user_lang.py`
- Modify: `service/server/database.py` (the idempotent ALTER block near line 2966, `ALTER TABLE users ADD COLUMN ai_automation_state ...`)
- Test: `service/server/tests/test_user_lang_migration.py`

**Interfaces:**
- Produces: `users.lang VARCHAR(8) NOT NULL DEFAULT 'en'` present on both engines.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_user_lang_migration.py
import sqlite3
from database import init_database, get_db_connection

def test_users_has_lang_column(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    init_database()
    conn = get_db_connection()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    conn.close()
    assert "lang" in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_user_lang_migration.py -v`
Expected: FAIL — `lang` not in cols.

- [ ] **Step 3: Add the Alembic migration**

```python
# service/server/alembic/versions/0031_user_lang.py
"""Per-user notification language.

Adds users.lang (default 'en'). This is the durable source both request-time
and background senders read to localize email/SMS. SQLite mirror is the
idempotent ALTER in database.init_database().

Revision ID: 0031
Revises: 0030
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN lang VARCHAR(8) NOT NULL DEFAULT 'en'")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN lang")
```

- [ ] **Step 4: Add the SQLite mirror**

In `service/server/database.py`, find the existing idempotent user-column ALTER block (the one adding `ai_automation_state`/`ai_automation_held_at` around line 2966). Add a mirror ALTER in the SAME idempotent style used there (each ALTER wrapped so a re-run that hits "duplicate column" is swallowed):

```python
        "ALTER TABLE users ADD COLUMN lang VARCHAR(8) NOT NULL DEFAULT 'en'",
```

Match the surrounding `try/except`-per-statement (or `_safe_alter`) idiom exactly — do not invent a new helper.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_user_lang_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add service/server/alembic/versions/0031_user_lang.py service/server/database.py service/server/tests/test_user_lang_migration.py
git commit -m "feat(i18n): add users.lang column (migration + sqlite mirror)"
```

---

### Task A2: Signup language resolver (`signup_lang.py`)

**Files:**
- Create: `service/server/signup_lang.py`
- Test: `service/server/tests/test_signup_lang.py`

**Interfaces:**
- Consumes: `analysis_agents.normalize_lang`, `i18n_errors._parse_accept_language`.
- Produces: `resolve_signup_lang(request) -> str` (a normalized code) and `_country_to_lang(country_code: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
# service/server/tests/test_signup_lang.py
from signup_lang import _country_to_lang, resolve_signup_lang

class FakeReq:
    def __init__(self, headers=None, host="1.2.3.4"):
        self.headers = headers or {}
        class C: pass
        self.client = C(); self.client.host = host

def test_country_maps_to_lang():
    assert _country_to_lang("KR") == "ko"
    assert _country_to_lang("JP") == "ja"
    assert _country_to_lang("TH") == "th"
    assert _country_to_lang("VN") == "vi"
    assert _country_to_lang("US") == "en"
    assert _country_to_lang(None) is None

def test_falls_back_to_accept_language_when_geo_unknown(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: None)
    req = FakeReq(headers={"accept-language": "ja,en;q=0.8"})
    assert resolve_signup_lang(req) == "ja"

def test_falls_back_to_english_when_nothing_known(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: None)
    req = FakeReq(headers={})
    assert resolve_signup_lang(req) == "en"

def test_geo_country_wins_over_header(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: "KR")
    req = FakeReq(headers={"accept-language": "ja"})
    assert resolve_signup_lang(req) == "ko"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest service/server/tests/test_signup_lang.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `signup_lang.py`**

```python
# service/server/signup_lang.py
"""Resolve a member's default notification language at signup.

Order (Henry's directive — IP country first, browser language fallback):
  1. IP-geolocated country → language (KR→ko, JP→ja, TH→th, VN→vi, else en)
  2. Accept-Language header → language
  3. 'en'

Fail-soft: any geo lookup error or timeout is swallowed and we drop to the
header. No new dependency — httpx is already in requirements. The lookup uses
a free no-key endpoint with a short timeout; if it is unreachable the header
still gives a good default.
"""
from __future__ import annotations

import logging
import os

import httpx

from analysis_agents import normalize_lang
from i18n_errors import _parse_accept_language

logger = logging.getLogger(__name__)

# Only the countries whose primary language is one we support need an entry;
# everything else (incl. unknown) resolves to English.
_COUNTRY_LANG = {"KR": "ko", "JP": "ja", "TH": "th", "VN": "vi"}

_GEO_TIMEOUT = float(os.getenv("SIGNUP_GEO_TIMEOUT", "1.5") or 1.5)
# ip-api.com: free, no key, returns {"countryCode": "KR", ...}. Overridable so
# tests never hit the network and prod can point at a paid endpoint later.
_GEO_URL = os.getenv("SIGNUP_GEO_URL", "http://ip-api.com/json/{ip}?fields=countryCode")


def _country_to_lang(country_code: str | None) -> str | None:
    if not country_code:
        return None
    cc = country_code.strip().upper()
    if not cc:
        return None
    return _COUNTRY_LANG.get(cc, "en")


def _client_ip(request) -> str | None:
    # Behind nginx the real client is the first X-Forwarded-For hop.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _geo_country(ip: str | None) -> str | None:
    """Country code for an IP, or None on any failure. Never raises."""
    if not ip or ip.startswith(("127.", "10.", "192.168.")) or ip == "::1":
        return None
    try:
        resp = httpx.get(_GEO_URL.format(ip=ip), timeout=_GEO_TIMEOUT)
        if resp.status_code != 200:
            return None
        return (resp.json() or {}).get("countryCode") or None
    except Exception as exc:  # noqa: BLE001 — geo must never break signup
        logger.info("signup geo lookup failed for %s: %s", ip, exc)
        return None


def resolve_signup_lang(request) -> str:
    """Best default language for a signing-up user: IP country, else header, else en."""
    try:
        by_country = _country_to_lang(_geo_country(_client_ip(request)))
        if by_country:
            return normalize_lang(by_country)
        return normalize_lang(_parse_accept_language(request.headers.get("accept-language")))
    except Exception as exc:  # noqa: BLE001
        logger.info("resolve_signup_lang failed: %s", exc)
        return "en"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_signup_lang.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add service/server/signup_lang.py service/server/tests/test_signup_lang.py
git commit -m "feat(i18n): signup language resolver (IP country -> header -> en)"
```

---

### Task A3: Set `users.lang` at registration

**Files:**
- Modify: `service/server/routes_users.py` (`send_verification_code` ~168, `user_register` ~189–241)
- Test: `service/server/tests/test_register_sets_lang.py`

**Interfaces:**
- Consumes: `signup_lang.resolve_signup_lang`.
- Produces: a new user row has `lang` set from the request; `send-code` and `register` accept `request: Request`.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_register_sets_lang.py
# Full-app test via the FastAPI TestClient, mirroring existing route tests.
# Mock the geo lookup and email send so no network is touched.
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: "KR")
    monkeypatch.setattr("email_sender.send_verification_code_email", lambda *a, **k: True)
    import importlib, main
    importlib.reload(main)
    return TestClient(main.app)

def test_register_persists_language(client):
    email = "lang@example.com"
    client.post("/api/users/send-code", json={"email": email})
    # Read the code from the store the test DB exposes (same pattern as
    # test_users.py — reuse its helper to fetch the stored code).
    from routes_users import _load_code
    code = _load_code(email, _ctx())["code"]  # _ctx(): the app's RouteContext
    r = client.post("/api/users/register",
                    json={"email": email, "password": "pw12345678", "code": code})
    assert r.status_code == 200
    from database import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT lang FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    assert row["lang"] == "ko"
```

> Note: adapt `_ctx()`/code retrieval to match the existing `test_users.py` helpers in this repo (they already exercise send-code/register). The assertion that matters is `users.lang == 'ko'`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_register_sets_lang.py -v`
Expected: FAIL — column stores default `'en'`, not `'ko'`.

- [ ] **Step 3: Thread request + set lang**

In `service/server/routes_users.py`, ensure `Request` is imported (`from fastapi import Request`). Change the two handlers to receive it and persist lang at insert:

```python
    @app.post('/api/users/send-code')
    async def send_verification_code(data: UserSendCodeRequest, request: Request):
        # ... unchanged body, but pass request-derived lang to the email in Phase B (Task B2)
```

```python
    @app.post('/api/users/register')
    async def user_register(data: UserRegisterRequest, request: Request):
        # ... unchanged validation ...
        from signup_lang import resolve_signup_lang
        lang = resolve_signup_lang(request)
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, lang)
            VALUES (?, ?, ?)
            """,
            (data.email, password_hash, lang),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_register_sets_lang.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_users.py service/server/tests/test_register_sets_lang.py
git commit -m "feat(i18n): persist users.lang at registration from signup location"
```

---

### Task A4: Read/update language endpoint + expose in login/`/me`

**Files:**
- Modify: `service/server/routes_users.py` (`user_login` ~317–362, `get_user_info` ~364, add `PUT /api/users/language`)
- Test: `service/server/tests/test_user_language_endpoint.py`

**Interfaces:**
- Consumes: existing `_extract_token`, `_get_user_by_token`, `analysis_agents.normalize_lang`.
- Produces: `GET/PUT /api/users/language`; `lang` field in `login` and `/me` responses.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_user_language_endpoint.py
# Register (lang defaults from geo), then PUT a new language and confirm login
# echoes it back and the column changed.
def test_put_language_updates_and_login_echoes(client, register_user):
    token = register_user("l2@example.com")          # helper: returns session token
    r = client.put("/api/users/language",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"lang": "ja"})
    assert r.status_code == 200 and r.json()["lang"] == "ja"
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["lang"] == "ja"

def test_put_language_rejects_unknown(client, register_user):
    token = register_user("l3@example.com")
    r = client.put("/api/users/language",
                   headers={"Authorization": f"Bearer {token}"}, json={"lang": "xx"})
    # Unknown normalizes to 'en' — never a 500.
    assert r.status_code == 200 and r.json()["lang"] == "en"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_user_language_endpoint.py -v`
Expected: FAIL — endpoint 404, `/me` has no `lang`.

- [ ] **Step 3: Add the endpoint and echo lang**

In `service/server/routes_users.py`, add near the other `/api/users/*` routes:

```python
    class UserLanguageRequest(BaseModel):
        lang: str

    @app.put('/api/users/language')
    async def set_user_language(data: UserLanguageRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        from analysis_agents import normalize_lang
        lang = normalize_lang(data.lang)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET lang = ? WHERE id = ?', (lang, user['id']))
            conn.commit()
        finally:
            conn.close()
        return {'lang': lang}
```

In `user_login`, add `lang` to the returned dict (read `row['lang']` with the same `try/except KeyError` guard used for `status`/`mfa_enabled`, defaulting `'en'`). In `get_user_info` (`/me`), include `'lang'` from the loaded user row the same way.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_user_language_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_users.py service/server/tests/test_user_language_endpoint.py
git commit -m "feat(i18n): PUT /api/users/language + expose lang in login and /me"
```

---

### Task A5: Frontend — persist switcher to server, seed from server

**Files:**
- Modify: `service/frontend/src/App.tsx` (~98–104 language state), `service/frontend/src/appChrome.tsx` (`LanguageSwitcher` ~30–40), `service/frontend/src/apiLanguage.ts`
- Test: manual + `tsc` (this repo's frontend has no unit-test runner wired; verify by build + browser).

**Interfaces:**
- Consumes: `PUT /api/users/language`; `lang` from login/`/me` responses.
- Produces: switching the top-bar language writes to the server when a session token exists; on login/refresh the server value seeds `localStorage` + state.

- [ ] **Step 1: Seed language from server on auth**

In `App.tsx`, where the login/`/me` response is handled, if `resp.lang` is present and differs from the stored language, set the language state and `localStorage.setItem('sooppiy_language', resp.lang)`. Keep `localStorage` as the pre-auth default (anonymous visitors).

- [ ] **Step 2: Persist on change when logged in**

In the language `setLanguage` handler (App.tsx) or `LanguageSwitcher` (appChrome.tsx), after updating state + `localStorage`, if a session token exists, fire-and-forget:

```ts
fetch('/api/users/language', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  body: JSON.stringify({ lang }),
}).catch(() => {});  // fail-soft: UI language already changed locally
```

- [ ] **Step 3: Verify with the dev server**

Run the app (`preview_start {name}`), log in as the prod/local test account, switch language, reload, confirm the choice persists across reload (served from server, not just localStorage). Check `read_network_requests` shows the `PUT /api/users/language` firing and returning 200.

- [ ] **Step 4: Typecheck + commit**

```bash
cd service/frontend && npx tsc --noEmit && cd ../..
git add service/frontend/src/App.tsx service/frontend/src/appChrome.tsx service/frontend/src/apiLanguage.ts
git commit -m "feat(i18n): persist language selection to server and seed from it on login"
```

**Phase A ship gate:** language is stored per user and round-trips through the API + UI. Ship A before starting B/C.

---

# Phase B — Transactional emails localized

### Task B1: Transactional email catalogue (`email_i18n.py`)

**Files:**
- Create: `service/server/email_i18n.py`
- Test: `service/server/tests/test_email_i18n.py`

**Interfaces:**
- Consumes: `analysis_agents.normalize_lang`.
- Produces: `verification_email(code: str, lang: str) -> tuple[str, str]` returning `(subject, html)`.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_email_i18n.py
from email_i18n import verification_email

def test_english_default():
    subj, html = verification_email("123456", "en")
    assert "123456" in html and "verification code" in subj.lower()

def test_korean_localized():
    subj, html = verification_email("123456", "ko")
    assert "123456" in html
    assert subj != verification_email("123456", "en")[0]   # actually translated

def test_unknown_falls_back_to_english():
    assert verification_email("123456", "xx") == verification_email("123456", "en")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_email_i18n.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the catalogue**

```python
# service/server/email_i18n.py
"""Localized transactional email copy (verification / password-reset code).

en + ko are verified. ja/th/vi intentionally fall through to en until a native
speaker fills them — a wrong-language email is worse than an English one.
"""
from __future__ import annotations

from analysis_agents import normalize_lang

# {lang: (subject, html_template)}; html_template has a single {code} slot.
_VERIFICATION = {
    "en": ("Your Sooppiy verification code",
           "<p>Your verification code is: <strong>{code}</strong></p>"
           "<p>It expires in 5 minutes. Do not share it.</p>"),
    "ko": ("Sooppiy 인증 코드",
           "<p>인증 코드: <strong>{code}</strong></p>"
           "<p>5분 후 만료됩니다. 코드를 공유하지 마세요.</p>"),
    # ja/th/vi: add verified translations here; absent -> English via .get below.
}


def verification_email(code: str, lang: str) -> tuple[str, str]:
    subject, template = _VERIFICATION.get(normalize_lang(lang), _VERIFICATION["en"])
    return subject, template.format(code=code)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_email_i18n.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add service/server/email_i18n.py service/server/tests/test_email_i18n.py
git commit -m "feat(i18n): transactional email catalogue (en+ko, safe en fallback)"
```

---

### Task B2: Wire language into `send_verification_code_email` and its callers

**Files:**
- Modify: `service/server/email_sender.py` (`send_verification_code_email` ~30)
- Modify: `service/server/routes_users.py` (`send_verification_code` ~184, `forgot_password` ~272)
- Test: `service/server/tests/test_email_sender_lang.py`

**Interfaces:**
- Consumes: `email_i18n.verification_email`, `signup_lang.resolve_signup_lang` (send-code path, pre-user), `users.lang` (reset path, existing user).
- Produces: `send_verification_code_email(to_email, code, lang="en")`.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_email_sender_lang.py
import email_sender

def test_send_uses_localized_subject(monkeypatch):
    captured = {}
    class FakeEmails:
        @staticmethod
        def send(payload): captured.update(payload); return {"id": "x"}
    monkeypatch.setattr(email_sender, "_RESEND_AVAILABLE", True)
    monkeypatch.setattr(email_sender, "_resend_lib", type("L", (), {"Emails": FakeEmails}))
    email_sender.send_verification_code_email("a@b.com", "654321", "ko")
    assert captured["subject"] == "Sooppiy 인증 코드"
    assert "654321" in captured["html"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_email_sender_lang.py -v`
Expected: FAIL — `send_verification_code_email` takes no `lang`.

- [ ] **Step 3: Add the `lang` param**

In `email_sender.py`:

```python
def send_verification_code_email(to_email: str, code: str, lang: str = "en") -> bool:
    if not _RESEND_AVAILABLE or _resend_lib is None:
        return False
    from email_i18n import verification_email
    subject, html = verification_email(code, lang)
    try:
        _resend_lib.Emails.send({
            "from": EMAIL_FROM,
            "to": to_email,
            "subject": subject,
            "html": html,
        })
        _logger.info("[Email] Verification code sent to %s (%s)", to_email, lang)
        return True
    except Exception as exc:
        _logger.warning("[Email] Failed to send to %s: %s", to_email, exc)
        return False
```

- [ ] **Step 4: Pass the right language at each caller**

In `routes_users.py`:
- `send_verification_code` (signup, no user yet): `lang = resolve_signup_lang(request)`, then `send_verification_code_email(data.email, code, lang)`.
- `forgot_password` (existing user): after confirming `account_exists`, read that user's stored `lang` (the `SELECT id FROM users` already runs — extend it to `SELECT id, lang`), then `send_verification_code_email(data.email, code, row['lang'] or 'en')`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_email_sender_lang.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add service/server/email_sender.py service/server/routes_users.py service/server/tests/test_email_sender_lang.py
git commit -m "feat(i18n): send verification/reset emails in the user's language"
```

**Phase B ship gate:** signup and reset emails arrive in the member's language. Ship B independently.

---

# Phase C — System alert / notification catalogue + threading (largest phase)

> Producers currently pass rendered English `title`/`body` into `send_alert`. To localize, each system alert becomes a **message id + params**; `send_alert`/`notify` look up the recipient's `users.lang` and render title/body from the catalogue at send time. Staff free-text (announcements, support replies) and operator alerts are untouched (see Global Constraints).

### Task C1: Alert message catalogue (`notifications_i18n.py`)

**Files:**
- Create: `service/server/notifications_i18n.py`
- Test: `service/server/tests/test_notifications_i18n.py`

**Interfaces:**
- Consumes: `analysis_agents.normalize_lang`.
- Produces: `render(msg_id: str, lang: str, **params) -> tuple[str, str]` returning `(title, body)`; `MESSAGES` dict keyed `msg_id -> {lang -> (title_template, body_template)}`.

The full message-id inventory (one per producer call site found in the audit), with the English source each replaces:

| msg_id | producer (file:line) | English title / body |
|---|---|---|
| `trade_executed` | automation.py:760, run_engine.py:1626 | `Trade executed` / `{side} {qty} {symbol} @ {price}` |
| `position_closed` | risk_engine.py:695 | `Position closed` / `{symbol} P&L {pnl}` |
| `breaker` | risk_engine.py:191 | `Circuit breaker HALT ({scope})` / `{reason}` |
| `verify_rejected` | (verify path) | `Pre-trade check rejected` / `{reason}` |
| `run_report` | run_reports.py:157 | `Run #{run_id} P&L digest` / `{summary}` |
| `run_threshold` | run_reports.py:301,308 | `Run #{run_id} threshold hit` / `{detail}` |
| `run_stopped` | run_engine.py:563 (kind) | `Run #{run_id} stopped` / `{reason}` |
| `gateway_down` | automation.py:320, gateway.py:406 | `Broker gateway down` / `{detail}` |
| `order_drift` | gateway.py:388 | `Order drift detected` / `{detail}` |
| `fleet_drawdown_warning` | fleet_supervisor.py:70 (kind) | `Fleet drawdown warning` / `{detail}` |
| `fleet_breaker` | fleet_supervisor.py:70 (kind) | `Fleet circuit breaker` / `{detail}` |
| `fleet_churn` | fleet_supervisor.py:70 | `Fleet churn notice` / `{detail}` |
| `fleet_watchdog` | fleet_supervisor.py:70 | `Fleet watchdog` / `{detail}` |
| `fleet_slot_dormant` | fleet_supervisor.py:70 | `Fleet slot dormant` / `{detail}` |
| `watch` | watch_engine.py:141 | `Watch: {name}` / `{detail}` |

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_notifications_i18n.py
from notifications_i18n import render, MESSAGES

def test_english_render():
    title, body = render("breaker", "en", scope="account", reason="daily loss cap")
    assert title == "Circuit breaker HALT (account)"
    assert "daily loss cap" in body

def test_korean_title_differs_when_translated():
    en = render("run_stopped", "en", run_id=7, reason="loss")
    ko = render("run_stopped", "ko", run_id=7, reason="loss")
    assert ko[0] != en[0]         # ko title is localized
    assert "7" in ko[1] or "7" in ko[0]

def test_unknown_lang_falls_back_to_english():
    assert render("trade_executed", "xx", side="BUY", qty=1, symbol="BTC", price=100) == \
           render("trade_executed", "en", side="BUY", qty=1, symbol="BTC", price=100)

def test_every_msg_id_has_english():
    for mid, variants in MESSAGES.items():
        assert "en" in variants, f"{mid} missing en"

def test_missing_param_falls_back_not_raises():
    # A template referencing an unpassed param must return English, never raise.
    title, body = render("breaker", "ko")   # no scope/reason
    assert isinstance(title, str) and isinstance(body, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_notifications_i18n.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the catalogue + safe render**

```python
# service/server/notifications_i18n.py
"""Localized system-alert copy. Producers pass a msg_id + params; send_alert /
notify render (title, body) in the recipient's language at send time.

en is authoritative and complete. ko is verified. ja/th/vi are added
incrementally; any missing (lang, msg_id) or any param mismatch renders in
English — a monolingual-but-correct alert beats a broken localized one.

Only SYSTEM-templated alerts live here. Staff free text (announcements, support
replies) and operator alerts are never routed through this module.
"""
from __future__ import annotations

import logging

from analysis_agents import normalize_lang

logger = logging.getLogger(__name__)

# msg_id -> {lang -> (title_template, body_template)}
MESSAGES: dict[str, dict[str, tuple[str, str]]] = {
    "trade_executed": {
        "en": ("Trade executed", "{side} {qty} {symbol} @ {price}"),
        "ko": ("체결 완료", "{symbol} {side} {qty} @ {price}"),
    },
    "position_closed": {
        "en": ("Position closed", "{symbol} P&L {pnl}"),
        "ko": ("포지션 종료", "{symbol} 손익 {pnl}"),
    },
    "breaker": {
        "en": ("Circuit breaker HALT ({scope})", "{reason}"),
        "ko": ("서킷 브레이커 정지 ({scope})", "{reason}"),
    },
    "verify_rejected": {
        "en": ("Pre-trade check rejected", "{reason}"),
        "ko": ("사전 점검 거부됨", "{reason}"),
    },
    "run_report": {
        "en": ("Run #{run_id} P&L digest", "{summary}"),
        "ko": ("런 #{run_id} 손익 요약", "{summary}"),
    },
    "run_threshold": {
        "en": ("Run #{run_id} threshold hit", "{detail}"),
        "ko": ("런 #{run_id} 임계값 도달", "{detail}"),
    },
    "run_stopped": {
        "en": ("Run #{run_id} stopped", "{reason}"),
        "ko": ("런 #{run_id} 중지됨", "{reason}"),
    },
    "gateway_down": {
        "en": ("Broker gateway down", "{detail}"),
        "ko": ("브로커 게이트웨이 중단", "{detail}"),
    },
    "order_drift": {
        "en": ("Order drift detected", "{detail}"),
        "ko": ("주문 불일치 감지", "{detail}"),
    },
    "fleet_drawdown_warning": {
        "en": ("Fleet drawdown warning", "{detail}"),
        "ko": ("플릿 손실 경고", "{detail}"),
    },
    "fleet_breaker": {
        "en": ("Fleet circuit breaker", "{detail}"),
        "ko": ("플릿 서킷 브레이커", "{detail}"),
    },
    "fleet_churn": {
        "en": ("Fleet churn notice", "{detail}"),
        "ko": ("플릿 회전 알림", "{detail}"),
    },
    "fleet_watchdog": {
        "en": ("Fleet watchdog", "{detail}"),
        "ko": ("플릿 워치독", "{detail}"),
    },
    "fleet_slot_dormant": {
        "en": ("Fleet slot dormant", "{detail}"),
        "ko": ("플릿 슬롯 휴면", "{detail}"),
    },
    "watch": {
        "en": ("Watch: {name}", "{detail}"),
        "ko": ("감시: {name}", "{detail}"),
    },
}


def _fmt(template: str, params: dict) -> str:
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        raise  # caller decides fallback


def render(msg_id: str, lang: str, **params) -> tuple[str, str]:
    """(title, body) for msg_id in lang. Falls back to English on any miss."""
    variants = MESSAGES.get(msg_id)
    if not variants:
        # Unknown id: no catalogue entry. Return the id + a compact param dump so
        # nothing is silently dropped, but this should never happen in prod.
        logger.warning("notifications_i18n: unknown msg_id %r", msg_id)
        return msg_id, ", ".join(f"{k}={v}" for k, v in params.items())
    en_title, en_body = variants["en"]
    code = normalize_lang(lang)
    title_t, body_t = variants.get(code, variants["en"])
    try:
        return _fmt(title_t, params), _fmt(body_t, params)
    except (KeyError, IndexError, ValueError):
        try:
            return _fmt(en_title, params), _fmt(en_body, params)
        except (KeyError, IndexError, ValueError):
            logger.warning("notifications_i18n: param mismatch for %s", msg_id)
            return en_title, en_body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_notifications_i18n.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Mutation check (per project rule #4)**

Temporarily break one template (e.g. change `run_stopped` ko title to match en) and confirm `test_korean_title_differs_when_translated` fails; revert.

- [ ] **Step 6: Commit**

```bash
git add service/server/notifications_i18n.py service/server/tests/test_notifications_i18n.py
git commit -m "feat(i18n): system-alert message catalogue with safe English fallback"
```

---

### Task C2: Render in the recipient's language inside `send_alert`

**Files:**
- Modify: `service/server/alerts.py` (`_alert_prefs` ~112 to also select `u.lang`; `send_alert` ~186 to accept `msg_id`/`params` and render)
- Test: `service/server/tests/test_alerts_lang.py`

**Interfaces:**
- Consumes: `notifications_i18n.render`.
- Produces: `send_alert(agent_id, kind, msg_id, params, dedupe_key=None)` renders `(title, body)` from the recipient's `users.lang`. Backward-compat shim: if called with the legacy `(title, body)` strings (str, str) it still works by treating them as pre-rendered English.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_alerts_lang.py
# A user with lang='ko' triggering a 'breaker' alert gets a Korean title
# stored in alert_log. Mock the senders; assert on the journaled title.
def test_alert_stored_in_user_language(seed_user_agent, capture_senders):
    agent_id = seed_user_agent(lang="ko")                # helper sets users.lang
    from alerts import send_alert
    send_alert(agent_id, "breaker", "breaker",
               {"scope": "account", "reason": "loss cap"})
    from database import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT title FROM alert_log WHERE agent_id=? ORDER BY id DESC LIMIT 1",
                       (agent_id,)).fetchone()
    conn.close()
    assert row["title"].startswith("서킷 브레이커 정지")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_alerts_lang.py -v`
Expected: FAIL — signature mismatch / English stored.

- [ ] **Step 3: Add lang to prefs and render in send_alert**

In `_alert_prefs`, add `u.lang` to the SELECT and return `"lang": row["lang"] or "en"` (and `"en"` in the no-row branch).

Change `send_alert` to render:

```python
def send_alert(agent_id: int, kind: str, msg_id: str, params: dict | None = None,
               dedupe_key: Optional[str] = None) -> dict[str, Any]:
    if kind not in ALERT_KINDS:
        kind = "custom"
    params = params or {}
    channels: list[str] = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if dedupe_key and _is_duplicate(dedupe_key, cursor):
            conn.close()
            return {"skipped": "duplicate", "channels": []}
        category = ALERT_KIND_CATEGORY.get(kind, "watch")
        prefs = _alert_prefs(agent_id, cursor, category)
        from notifications_i18n import render
        title, body = render(msg_id, prefs.get("lang", "en"), **params)
        channels.append("inapp")
        # ... rest unchanged: uses `title`/`body` exactly as before ...
```

The `_send_email`/`_send_sms`/`alert_log INSERT`/`notify(...)` lines stay byte-for-byte — they already consume local `title`/`body`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_alerts_lang.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/server/alerts.py service/server/tests/test_alerts_lang.py
git commit -m "feat(i18n): render alerts in the recipient's stored language"
```

---

### Task C3: Convert producers to pass `(msg_id, params)`

**Files:** (one commit per file; each is independently testable by its existing suite)
- Modify: `service/server/risk_engine.py` (191, 695), `run_reports.py` (157, 301, 308), `run_engine.py` (563, 1626), `automation.py` (320, 760), `watch_engine.py` (141), `fleet_supervisor.py` (70), `execution/gateway.py` (388, 406)

**Interfaces:**
- Consumes: `alerts.send_alert(agent_id, kind, msg_id, params, dedupe_key=...)`.
- Produces: no behavior change in English; alerts now localizable.

For EACH call site, replace the English `title`/`body` args with the matching `msg_id` (from the C1 table) and a `params` dict carrying the interpolation values. Example — `risk_engine.py:191`:

```python
# before
send_alert(agent_id, "breaker", f"Circuit breaker HALT ({scope})", reason)
# after
send_alert(agent_id, "breaker", "breaker", {"scope": scope, "reason": reason})
```

Example — `run_reports.py:157`:

```python
# before
out = send_alert(run["agent_id"], "run_report", f"Run #{run['id']} P&L digest", summary)
# after
out = send_alert(run["agent_id"], "run_report", "run_report",
                 {"run_id": run["id"], "summary": summary})
```

`fleet_supervisor.py:70` and `run_engine.py:563` pass a computed `kind` + `title`/`body`; map `kind` → `msg_id` (they share names) and move the interpolated pieces into `params`. Where a producer builds a rich multi-line body, keep that string as a single `{detail}`/`{summary}` param (do not shatter it into many keys — the surrounding data is language-neutral numbers/tickers).

- [ ] **Step 1: For each file, run its existing tests first (baseline green)**

Run: `.venv/bin/python -m pytest service/server/tests/ -k "risk or run or fleet or watch or automation or gateway" -q`
Expected: PASS (record the count).

- [ ] **Step 2: Convert one file, run that file's tests**

After editing e.g. `risk_engine.py`, run its suite; fix any test that asserted on the old positional `title`/`body` args (update the assertion to the new `(msg_id, params)` shape — the rendered output is unchanged in English).

- [ ] **Step 3: Repeat per file, committing each**

```bash
git add service/server/risk_engine.py service/server/tests/test_risk_engine*.py
git commit -m "refactor(i18n): risk_engine alerts pass msg_id+params"
```
…one commit per producer file.

- [ ] **Step 4: Full suite green**

Run: `.venv/bin/python -m pytest service/server -q`
Expected: PASS. Then `ruff check service/server`.

---

### Task C4: Localize `notify()` external delivery for templated callers

**Files:**
- Modify: `service/server/notifications.py` (`_send_external` ~262, add `notify_i18n`)
- Test: `service/server/tests/test_notify_lang.py`

**Interfaces:**
- Consumes: `notifications_i18n.render`, `users.lang`.
- Produces: `notify_i18n(user_id, category, msg_id, params, link=None)` — renders in the user's language then calls the existing `notify`. `send_alert`'s internal `notify(..., external=False)` already passes rendered (localized) title/body from C2, so the feed mirror is localized without change.

- [ ] **Step 1: Write the failing test**

```python
# service/server/tests/test_notify_lang.py
def test_notify_i18n_renders_user_language(seed_user, capture_senders):
    uid = seed_user(lang="ko")
    import notifications
    notifications.notify_i18n(uid, "auto_trading_safety", "run_stopped",
                              {"run_id": 3, "reason": "loss"})
    from database import get_db_connection
    conn = get_db_connection()
    row = conn.execute("SELECT title FROM user_notifications WHERE user_id=? ORDER BY id DESC LIMIT 1",
                       (uid,)).fetchone()
    conn.close()
    assert row["title"].startswith("런 #3")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_notify_lang.py -v`
Expected: FAIL — `notify_i18n` undefined.

- [ ] **Step 3: Implement `notify_i18n` + a lang lookup**

```python
def _user_lang(user_id: int) -> str:
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT lang FROM users WHERE id = ?", (user_id,)).fetchone()
        return (row["lang"] if row else None) or "en"
    finally:
        conn.close()


def notify_i18n(user_id: Optional[int], category: str, msg_id: str,
                params: dict | None = None, link: Optional[str] = None) -> dict[str, Any]:
    """notify() for system-templated messages: render (title, body) in the
    member's language, then delegate to notify()."""
    if user_id is None:
        return {"skipped": "no_user", "channels": []}
    from notifications_i18n import render
    title, body = render(msg_id, _user_lang(user_id), **(params or {}))
    return notify(user_id, category, title, body, link=link, external=True)
```

Leave `notify()` itself unchanged (it still serves the staff free-text announcement/support paths in whatever language the author typed).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest service/server/tests/test_notify_lang.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/server/notifications.py service/server/tests/test_notify_lang.py
git commit -m "feat(i18n): notify_i18n renders member notifications in stored language"
```

**Phase C ship gate:** full suite green + ruff clean; a `lang='ko'` member receives Korean alert emails/SMS and feed entries end-to-end. English behavior byte-identical for `lang='en'`.

---

## Deployment

Follow the standing prod rule (deploy to sooppiy.com). After merge to `main` and CI green:
1. Prod is MySQL — the Alembic `0031` runs in the deploy migration step; verify `SHOW COLUMNS FROM users LIKE 'lang'` on prod.
2. Rebuild + publish the frontend `dist` to the host nginx SPA root (`/usr/share/nginx/sooppiy`) per the deploy memory.
3. Smoke test on prod with the debug account: switch language, confirm it persists across reload, trigger a futures QA run to fire a localized alert, confirm the alert email/feed entry render in the selected language (and English for an English account).

## Self-Review notes

- **Spec coverage:** persisted language (A1–A5) ✓; signup default IP→header→en (A2–A3) ✓; all member-facing emails (B, C2) ✓; all member-facing SMS (C2 — same `_send_sms` path, same rendered body) ✓; alert feed mirror (C2/C4) ✓. Admin operator alerts excluded per scope ✓. Free-text announcements/support explicitly excluded ✓.
- **Type consistency:** `render(msg_id, lang, **params) -> (title, body)` used identically in C2/C4; `verification_email(code, lang) -> (subject, html)` in B1/B2; `resolve_signup_lang(request) -> str` in A2/A3/B2.
- **Open follow-ups (flag to Henry, not fabricate):** ja/th/vi catalogue entries need verified native translations before they stop falling back to English; ip-api.com free tier is HTTP + 45 req/min (fine at signup volume, revisit if signups spike or an HTTPS/keyed geo provider is preferred).
