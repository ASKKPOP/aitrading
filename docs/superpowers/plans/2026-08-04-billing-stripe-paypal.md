# Stripe + PayPal Auto-Renew Billing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Members pay for plans with cards / Apple Pay / Google Pay (Stripe hosted Checkout) or PayPal (Subscriptions API), auto-renewing monthly, with upgrade / downgrade / cancel — webhooks are the only activation path.

**Architecture:** New `billing_sync.py` owns all subscription-state writes (idempotent, provider-agnostic). New `routes_billing.py` exposes Stripe checkout/portal, PayPal subscribe/change-plan/cancel, and both webhook endpoints. `user_subscriptions.expires_at` stays the single field entitlements reads; renewals push it to `period_end + 3 days grace`. Existing USDT/bank/enterprise rails untouched.

**Tech Stack:** FastAPI, `stripe` Python SDK (new dep), raw `requests` for PayPal (matches existing code), React/TS frontend, SQLite dev / MySQL prod via Alembic.

**Spec:** `docs/superpowers/specs/2026-08-04-billing-stripe-paypal-design.md`

## Global Constraints

- Python 3.10+ syntax (`X | None`), FastAPI route style: `register_*_routes(app, ctx)` closures, module-level helpers prefixed `_`.
- DB access ONLY via `database.get_db_connection()`, `?` placeholders (adapted for MySQL by database.py). No `ESCAPE '\\'` in LIKE. MySQL `rowcount` counts CHANGED rows, not matched — never branch on `rowcount > 0` after an UPDATE that may be a no-op.
- Tests: `unittest.TestCase` + FastAPI `TestClient`, temp SQLite DB per test (copy `test_entitlements.py` setUp pattern). NO live network calls — every `requests.*` and `stripe.*` call mocked; conftest must blank all payment env keys.
- Frontend strings: every user-visible string through `tr(language, {ko, en, ja, th, vi, id})` — all six languages, no English-only strings.
- Run everything from repo root. Backend tests: `.venv/bin/python -m pytest service/server/tests/... -q`. Lint: `.venv/bin/python -m ruff check service/server`. Frontend: `cd service/frontend && npx tsc --noEmit`.
- Commit after every task. Only stage files THIS plan touches — parallel sessions edit the same worktree.
- `SUBSCRIPTION_DAYS = 30` (existing), `GRACE_DAYS = 3` (new, in billing_sync.py).
- Activation/renewal/cancel state changes happen ONLY in webhook handlers (via billing_sync), never in checkout/subscribe endpoints (those may create `pending` rows only).

---

### Task 1: Schema — new columns, billing_events table, conftest env blanking

**Files:**
- Modify: `service/server/database.py` (CREATE TABLE section ~line 2462, ALTER list ~line 1361)
- Create: `service/server/alembic/versions/0036_billing_autorenew.py`
- Modify: `service/server/tests/conftest.py`
- Test: `service/server/tests/test_billing.py` (new file, first test class)

**Interfaces:**
- Produces: columns `users.stripe_customer_id`, `subscription_plans.stripe_price_id`, `subscription_plans.paypal_plan_id`, `user_subscriptions.external_id`, `user_subscriptions.auto_renew` (default 0), `user_subscriptions.cancel_at_period_end` (default 0); table `billing_events(id, provider, event_id, type, payload, processed_at)` with UNIQUE(provider, event_id). All later tasks rely on these exact names.

- [ ] **Step 1: Write the failing test**

Create `service/server/tests/test_billing.py`:

```python
"""Billing (Stripe + PayPal auto-renew) — schema, state sync, routes, webhooks.

Spec: docs/superpowers/specs/2026-08-04-billing-stripe-paypal-design.md
All external HTTP (Stripe SDK, PayPal requests) is mocked — no live calls.
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


class BillingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _cols(self, table: str) -> set[str]:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            return {r["name"] for r in cur.fetchall()}
        finally:
            conn.close()

    def test_new_columns_exist(self):
        self.assertIn("stripe_customer_id", self._cols("users"))
        self.assertLessEqual({"stripe_price_id", "paypal_plan_id"},
                             self._cols("subscription_plans"))
        self.assertLessEqual({"external_id", "auto_renew", "cancel_at_period_end"},
                             self._cols("user_subscriptions"))

    def test_billing_events_unique(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                "VALUES ('stripe', 'evt_1', 'invoice.paid', '{}', '2026-01-01T00:00:00Z')")
            with self.assertRaises(Exception):
                cur.execute(
                    "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                    "VALUES ('stripe', 'evt_1', 'invoice.paid', '{}', '2026-01-01T00:00:00Z')")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: FAIL (`stripe_customer_id` not in columns / `billing_events` no such table)

- [ ] **Step 3: Implement schema changes**

In `service/server/database.py`, find the ALTER-statement list around line 1361 (`"ALTER TABLE positions ADD COLUMN first_opened_at TEXT",` etc.) and append to that same list:

```python
        "ALTER TABLE users ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE subscription_plans ADD COLUMN stripe_price_id TEXT",
        "ALTER TABLE subscription_plans ADD COLUMN paypal_plan_id TEXT",
        "ALTER TABLE user_subscriptions ADD COLUMN external_id TEXT",
        "ALTER TABLE user_subscriptions ADD COLUMN auto_renew INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE user_subscriptions ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0",
```

Then, directly after the `contract_requests` CREATE TABLE (~line 2500), add:

```python
    # Webhook idempotency + audit for auto-renew billing (Stripe / PayPal).
    # UNIQUE(provider, event_id) is the dedup gate: a redelivered webhook hits
    # the constraint and is answered 200 without re-applying state.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS billing_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            provider     TEXT NOT NULL,
            event_id     TEXT NOT NULL,
            type         TEXT,
            payload      TEXT,
            processed_at TEXT,
            UNIQUE(provider, event_id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_subscriptions_external
        ON user_subscriptions(method, external_id)
    """)
```

Create `service/server/alembic/versions/0036_billing_autorenew.py`:

```python
"""Auto-renew billing: Stripe/PayPal ids on users + plans + subscriptions,
billing_events webhook-idempotency table.

expires_at remains the ONLY field entitlements reads; auto_renew rows just
keep pushing it forward (period_end + 3-day grace) on each paid invoice.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def cols(table):
        return [c["name"] for c in insp.get_columns(table)]

    if "stripe_customer_id" not in cols("users"):
        op.execute("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(64) NULL")
    if "stripe_price_id" not in cols("subscription_plans"):
        op.execute("ALTER TABLE subscription_plans ADD COLUMN stripe_price_id VARCHAR(64) NULL")
    if "paypal_plan_id" not in cols("subscription_plans"):
        op.execute("ALTER TABLE subscription_plans ADD COLUMN paypal_plan_id VARCHAR(64) NULL")
    if "external_id" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN external_id VARCHAR(128) NULL")
    if "auto_renew" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN auto_renew TINYINT NOT NULL DEFAULT 0")
    if "cancel_at_period_end" not in cols("user_subscriptions"):
        op.execute("ALTER TABLE user_subscriptions ADD COLUMN cancel_at_period_end TINYINT NOT NULL DEFAULT 0")

    if "billing_events" not in insp.get_table_names():
        op.execute("""
            CREATE TABLE billing_events (
                id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                provider     VARCHAR(16) NOT NULL,
                event_id     VARCHAR(128) NOT NULL,
                type         VARCHAR(80),
                payload      MEDIUMTEXT,
                processed_at VARCHAR(32),
                UNIQUE KEY uq_billing_events (provider, event_id)
            )
        """)
        op.execute("CREATE INDEX idx_user_subscriptions_external "
                   "ON user_subscriptions(method(16), external_id(64))")


def downgrade():
    op.execute("DROP TABLE IF EXISTS billing_events")
    for col in ("cancel_at_period_end", "auto_renew", "external_id"):
        op.execute(f"ALTER TABLE user_subscriptions DROP COLUMN {col}")
    op.execute("ALTER TABLE subscription_plans DROP COLUMN paypal_plan_id")
    op.execute("ALTER TABLE subscription_plans DROP COLUMN stripe_price_id")
    op.execute("ALTER TABLE users DROP COLUMN stripe_customer_id")
```

In `service/server/tests/conftest.py`, extend the credential-blanking loop to cover payment providers:

```python
for _key in ("SENDGRID_API_KEY", "ALERT_FROM_EMAIL",
             "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
             "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
             "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"):
    os.environ[_key] = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: 2 passed

Also run the full suite to confirm the conftest change breaks nothing:
`.venv/bin/python -m pytest service/server/tests -q` — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add service/server/database.py service/server/alembic/versions/0036_billing_autorenew.py service/server/tests/conftest.py service/server/tests/test_billing.py
git commit -m "feat(billing): schema for auto-renew subscriptions + billing_events idempotency table"
```

---

### Task 2: billing_sync.py — idempotency + subscription state transitions

**Files:**
- Create: `service/server/billing_sync.py`
- Test: `service/server/tests/test_billing.py` (append `BillingSyncTests`)

**Interfaces:**
- Consumes: Task 1 schema.
- Produces (exact signatures — webhook handlers in Tasks 4/6 call these):
  - `GRACE_DAYS = 3`
  - `stripe_configured() -> bool` (reads `STRIPE_SECRET_KEY`)
  - `record_billing_event(provider: str, event_id: str, event_type: str, payload: str) -> bool` — True = first delivery; False = duplicate
  - `delete_billing_event(provider: str, event_id: str) -> None` — undo on handler failure so the provider's retry is not treated as a duplicate
  - `upsert_autorenew_subscription(*, provider: str, user_id: int, plan_code: str, external_id: str, period_end: datetime | None = None) -> None`
  - `extend_subscription(provider: str, external_id: str, period_end: datetime | None = None) -> None`
  - `apply_subscription_update(provider: str, external_id: str, *, plan_code: str | None = None, cancel_at_period_end: bool | None = None, period_end: datetime | None = None) -> None`
  - `mark_cancelled(provider: str, external_id: str) -> None` — no-renew flag; access continues to expires_at
  - `end_subscription(provider: str, external_id: str) -> None` — status='expired' now
  - `active_autorenew(user_id: int) -> dict | None`
  - `plan_for_stripe_price(price_id: str) -> str | None`
  - `plan_for_paypal_plan(paypal_plan_id: str) -> str | None`
  - `billing_ids_for_plan(plan_code: str) -> dict` — `{"stripe_price_id": ..., "paypal_plan_id": ...}`

- [ ] **Step 1: Write the failing tests**

Append to `service/server/tests/test_billing.py`:

```python
from datetime import datetime, timedelta, timezone


class BillingSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (email, password_hash) VALUES ('b@t.dev', 'x')")
            self.user_id = cur.lastrowid
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr', "
                        "paypal_plan_id = 'P-JR' WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_pro', "
                        "paypal_plan_id = 'P-PRO' WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _sub_row(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_subscriptions WHERE user_id = ? "
                        "ORDER BY id DESC LIMIT 1", (self.user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def test_record_event_dedupes(self):
        import billing_sync
        self.assertTrue(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))
        self.assertFalse(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))
        billing_sync.delete_billing_event("stripe", "evt_a")
        self.assertTrue(billing_sync.record_billing_event("stripe", "evt_a", "t", "{}"))

    def test_activate_extend_cancel_lifecycle(self):
        import billing_sync
        from routes_subscriptions import get_subscription_state
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_1")
        row = self._sub_row()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["method"], "stripe")
        self.assertEqual(int(row["auto_renew"]), 1)

        # renewal pushes expires_at to period_end + grace
        pe = datetime.now(timezone.utc) + timedelta(days=30)
        billing_sync.extend_subscription("stripe", "sub_1", pe)
        expires = self._sub_row()["expires_at"]
        want = (pe + timedelta(days=billing_sync.GRACE_DAYS)).strftime("%Y-%m-%d")
        self.assertTrue(expires.startswith(want))

        # plan switch via subscription.updated
        billing_sync.apply_subscription_update("stripe", "sub_1", plan_code="pro")
        self.assertEqual(self._sub_row()["plan_code"], "pro")

        # cancel-at-period-end keeps access
        billing_sync.mark_cancelled("stripe", "sub_1")
        row = self._sub_row()
        self.assertEqual(row["status"], "active")
        self.assertEqual(int(row["cancel_at_period_end"]), 1)
        self.assertEqual(int(row["auto_renew"]), 0)

        # hard end closes access now
        billing_sync.end_subscription("stripe", "sub_1")
        self.assertEqual(self._sub_row()["status"], "expired")
        conn = database.get_db_connection()
        try:
            state = get_subscription_state(conn.cursor(), self.user_id)
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(state["status"], "none")

    def test_upsert_supersedes_previous_rows(self):
        import billing_sync
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "started_at, expires_at) VALUES (?, 'junior', 'active', 'usdt', "
                "'2026-08-01T00:00:00Z', '2026-08-30T00:00:00Z')", (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="pro",
            external_id="I-XYZ")
        row = self._sub_row()
        self.assertEqual((row["method"], row["status"]), ("paypal", "active"))
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE user_id = ? AND status = 'active'", (self.user_id,))
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_activate_is_idempotent_per_external_id(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_dup")
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_dup")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE external_id = 'sub_dup'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_plan_lookups(self):
        import billing_sync
        self.assertEqual(billing_sync.plan_for_stripe_price("price_pro"), "pro")
        self.assertIsNone(billing_sync.plan_for_stripe_price("price_nope"))
        self.assertEqual(billing_sync.plan_for_paypal_plan("P-JR"), "junior")
        ids = billing_sync.billing_ids_for_plan("junior")
        self.assertEqual(ids["stripe_price_id"], "price_jr")
        self.assertEqual(ids["paypal_plan_id"], "P-JR")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'billing_sync'`

- [ ] **Step 3: Implement `service/server/billing_sync.py`**

```python
"""billing_sync.py — auto-renew subscription state, written ONLY by webhooks.

Single owner of user_subscriptions writes for the two auto-renew rails
(method = 'stripe' | 'paypal'). Checkout endpoints never activate anything;
providers' webhooks land here. `expires_at` stays the one field entitlements
reads — each paid period pushes it to period_end + GRACE_DAYS so a slow
webhook or payment retry cannot flicker a member's access off.

Idempotency: record_billing_event() inserts into billing_events first; a
redelivered event returns False and the caller answers 200 without touching
state. On handler failure the caller delete_billing_event()s the row so the
provider's retry is processed, not swallowed as a duplicate.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from database import get_db_connection

logger = logging.getLogger("billing_sync")

GRACE_DAYS = 3
DEFAULT_PERIOD_DAYS = 30


def stripe_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _expires(period_end: datetime | None) -> str:
    end = period_end or (_now() + timedelta(days=DEFAULT_PERIOD_DAYS))
    return _iso(end + timedelta(days=GRACE_DAYS))


def record_billing_event(provider: str, event_id: str, event_type: str,
                         payload: str) -> bool:
    """True = first delivery, proceed. False = duplicate, answer 200 and stop."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO billing_events (provider, event_id, type, payload, processed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, event_id, (event_type or "")[:80], (payload or "")[:20000],
                 _iso(_now())))
            conn.commit()
            return True
        except Exception:  # noqa: BLE001 — UNIQUE(provider, event_id) hit = duplicate
            conn.rollback()
            return False
    finally:
        conn.close()


def delete_billing_event(provider: str, event_id: str) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM billing_events WHERE provider = ? AND event_id = ?",
                    (provider, event_id))
        conn.commit()
    finally:
        conn.close()


def upsert_autorenew_subscription(*, provider: str, user_id: int, plan_code: str,
                                  external_id: str,
                                  period_end: datetime | None = None) -> None:
    """Activate the member's auto-renew subscription (idempotent per external_id).

    One live subscription per member: any other active/pending rows are marked
    'superseded' (get_subscription_state only reads active|pending, so they
    simply drop out)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM user_subscriptions WHERE method = ? AND external_id = ?",
            (provider, external_id))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE user_subscriptions SET status = 'active', plan_code = ?, "
                "expires_at = ?, auto_renew = 1, cancel_at_period_end = 0 WHERE id = ?",
                (plan_code, _expires(period_end), dict(row)["id"]))
        else:
            cur.execute(
                "UPDATE user_subscriptions SET status = 'superseded' "
                "WHERE user_id = ? AND status IN ('active', 'pending')",
                (user_id,))
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "reference, external_id, auto_renew, started_at, expires_at) "
                "VALUES (?, ?, 'active', ?, ?, ?, 1, ?, ?)",
                (user_id, plan_code, provider, external_id, external_id,
                 _iso(_now()), _expires(period_end)))
        conn.commit()
    finally:
        conn.close()
    logger.info("billing: activated %s sub %s user=%s plan=%s",
                provider, external_id, user_id, plan_code)


def extend_subscription(provider: str, external_id: str,
                        period_end: datetime | None = None) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET status = 'active', expires_at = ? "
            "WHERE method = ? AND external_id = ?",
            (_expires(period_end), provider, external_id))
        conn.commit()
    finally:
        conn.close()


def apply_subscription_update(provider: str, external_id: str, *,
                              plan_code: str | None = None,
                              cancel_at_period_end: bool | None = None,
                              period_end: datetime | None = None) -> None:
    sets, args = [], []
    if plan_code is not None:
        sets.append("plan_code = ?"); args.append(plan_code)
    if cancel_at_period_end is not None:
        sets.append("cancel_at_period_end = ?")
        args.append(1 if cancel_at_period_end else 0)
    if period_end is not None:
        sets.append("expires_at = ?"); args.append(_expires(period_end))
    if not sets:
        return
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE user_subscriptions SET {', '.join(sets)} "
            "WHERE method = ? AND external_id = ?",
            (*args, provider, external_id))
        conn.commit()
    finally:
        conn.close()


def mark_cancelled(provider: str, external_id: str) -> None:
    """Member cancelled: stop renewing, keep access until expires_at."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET auto_renew = 0, cancel_at_period_end = 1 "
            "WHERE method = ? AND external_id = ?",
            (provider, external_id))
        conn.commit()
    finally:
        conn.close()


def end_subscription(provider: str, external_id: str) -> None:
    """The subscription actually ended (deleted/expired event): close access."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_subscriptions SET status = 'expired', auto_renew = 0 "
            "WHERE method = ? AND external_id = ?",
            (provider, external_id))
        conn.commit()
    finally:
        conn.close()


def active_autorenew(user_id: int) -> dict | None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, plan_code, method, external_id, expires_at "
            "FROM user_subscriptions WHERE user_id = ? AND status = 'active' "
            "AND auto_renew = 1 ORDER BY id DESC LIMIT 1",
            (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _plan_lookup(column: str, value: str) -> str | None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT code FROM subscription_plans WHERE {column} = ? AND active = 1",
            (value,))
        row = cur.fetchone()
        return dict(row)["code"] if row else None
    finally:
        conn.close()


def plan_for_stripe_price(price_id: str) -> str | None:
    return _plan_lookup("stripe_price_id", price_id)


def plan_for_paypal_plan(paypal_plan_id: str) -> str | None:
    return _plan_lookup("paypal_plan_id", paypal_plan_id)


def billing_ids_for_plan(plan_code: str) -> dict:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT stripe_price_id, paypal_plan_id FROM subscription_plans "
            "WHERE code = ?", (plan_code,))
        row = cur.fetchone()
        return dict(row) if row else {"stripe_price_id": None, "paypal_plan_id": None}
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: all pass (schema + sync classes)

- [ ] **Step 5: Commit**

```bash
git add service/server/billing_sync.py service/server/tests/test_billing.py
git commit -m "feat(billing): billing_sync — idempotent webhook-driven subscription state"
```

---

### Task 3: Stripe checkout + portal endpoints (routes_billing.py) and route registration

**Files:**
- Create: `service/server/routes_billing.py`
- Modify: `service/server/routes.py` (import + register, next to `register_subscription_routes`)
- Modify: `service/requirements.txt` (add `stripe>=7.0.0`)
- Modify: `.env.example` (document new keys)
- Test: `service/server/tests/test_billing.py` (append `StripeCheckoutTests`)

**Interfaces:**
- Consumes: `billing_sync.active_autorenew`, `billing_sync.billing_ids_for_plan`, `billing_sync.stripe_configured`; `_require_user`, `_load_plan`, `_frontend_url`, `PlanOrderBody` from `routes_subscriptions`.
- Produces: `POST /api/subscriptions/stripe/checkout {plan_code} → {"url": str}`; `POST /api/subscriptions/stripe/portal → {"url": str}`; `register_billing_routes(app, ctx)`.

- [ ] **Step 1: Install the SDK and document env**

Add to `service/requirements.txt` (alphabetical position near other API SDKs):

```
stripe>=7.0.0
```

Run: `.venv/bin/pip install "stripe>=7.0.0"`
Expected: installs cleanly.

Add to `.env.example` under the PayPal block:

```
# Stripe (auto-renew card subscriptions — cards / Apple Pay / Google Pay)
# STRIPE_SECRET_KEY=sk_test_...
# STRIPE_WEBHOOK_SECRET=whsec_...
# PayPal webhooks (auto-renew subscriptions)
# PAYPAL_WEBHOOK_ID=...
```

- [ ] **Step 2: Write the failing tests**

Append to `service/server/tests/test_billing.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient


def _register_user(client: TestClient, db) -> tuple[int, str]:
    """Insert a user + session token directly (register route needs email codes)."""
    import secrets
    conn = db.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('pay@t.dev', 'x')")
        user_id = cur.lastrowid
        token = secrets.token_urlsafe(24)
        cur.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES (?, ?, "
                    "'2030-01-01T00:00:00Z')", (user_id, token))
        conn.commit()
        return user_id, token
    finally:
        conn.close()


class StripeCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr' "
                        "WHERE code = 'junior'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_checkout_returns_hosted_url_and_saves_customer(self):
        with patch("stripe.Customer.create", return_value={"id": "cus_1"}) as cc, \
             patch("stripe.checkout.Session.create",
                   return_value={"url": "https://checkout.stripe.com/x"}) as sc:
            r = self.client.post("/api/subscriptions/stripe/checkout",
                                 json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["url"], "https://checkout.stripe.com/x")
        cc.assert_called_once()
        kwargs = sc.call_args.kwargs
        self.assertEqual(kwargs["mode"], "subscription")
        self.assertEqual(kwargs["client_reference_id"], str(self.user_id))
        self.assertEqual(kwargs["line_items"], [{"price": "price_jr", "quantity": 1}])
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT stripe_customer_id FROM users WHERE id = ?",
                        (self.user_id,))
            self.assertEqual(dict(cur.fetchone())["stripe_customer_id"], "cus_1")
        finally:
            conn.close()

    def test_checkout_409_when_autorenew_active(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="junior",
            external_id="I-1")
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 409)

    def test_checkout_503_when_unconfigured(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 503)

    def test_checkout_503_when_plan_has_no_price(self):
        r = self.client.post("/api/subscriptions/stripe/checkout",
                             json={"plan_code": "pro"}, headers=self._h())
        self.assertEqual(r.status_code, 503)

    def test_portal_returns_url(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET stripe_customer_id = 'cus_9' WHERE id = ?",
                        (self.user_id,))
            conn.commit()
        finally:
            conn.close()
        with patch("stripe.billing_portal.Session.create",
                   return_value={"url": "https://billing.stripe.com/p"}):
            r = self.client.post("/api/subscriptions/stripe/portal", headers=self._h())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["url"], "https://billing.stripe.com/p")

    def test_portal_404_without_customer(self):
        r = self.client.post("/api/subscriptions/stripe/portal", headers=self._h())
        self.assertEqual(r.status_code, 404)
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: FAIL — 404s (routes don't exist yet)

- [ ] **Step 4: Implement `service/server/routes_billing.py` (Stripe half)**

```python
"""routes_billing.py — auto-renew billing rails (Stripe + PayPal subscriptions).

Stripe:   hosted Checkout (cards / Apple Pay / Google Pay) + Customer Portal
          for plan switches, card updates and cancellation. Needs
          STRIPE_SECRET_KEY (+ STRIPE_WEBHOOK_SECRET for the webhook).
PayPal:   Subscriptions API (v1/billing) — replaces the one-time Orders flow
          for NEW purchases; the legacy capture route in routes_subscriptions
          stays for in-flight orders. Needs PAYPAL_WEBHOOK_ID too.

State rule: endpoints here never activate a plan. Activation, renewal, plan
changes and endings arrive via the two webhook endpoints and are applied by
billing_sync (idempotent per provider event id).

  POST /api/subscriptions/stripe/checkout    start Stripe Checkout  → {url}
  POST /api/subscriptions/stripe/portal      manage (portal)        → {url}
  POST /api/subscriptions/paypal/subscribe   start PayPal approval  → {approve_url}
  POST /api/subscriptions/paypal/change-plan revise (next cycle)
  POST /api/subscriptions/paypal/cancel      stop renewing
  POST /api/webhooks/stripe                  Stripe events (signed)
  POST /api/webhooks/paypal                  PayPal events (verified)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Header, HTTPException, Request

import billing_sync
from database import get_db_connection
from routes_shared import RouteContext
from routes_subscriptions import (PlanOrderBody, _alert_new_subscription,
                                  _frontend_url, _load_plan, _paypal_base,
                                  _paypal_configured, _paypal_token,
                                  _require_user)

logger = logging.getLogger("routes_billing")

ALREADY_AUTORENEW = ("An auto-renewing subscription is already active — "
                     "manage or cancel it first")


def _alert_webhook_failure(provider: str, event_id: str, exc: Exception) -> None:
    """Spec §4: processing failure → 500 (provider retries) + owner alert.
    Fail-soft — alerting must never mask the original failure."""
    try:
        from admin_alerts import notify_admins
        notify_admins("Billing webhook processing failed",
                      f"provider: {provider}\nevent: {event_id}\nerror: {exc}")
    except Exception:  # noqa: BLE001
        logger.warning("billing webhook failure alert failed", exc_info=True)


def _stripe():
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    return stripe


def _stripe_customer_id(user: dict) -> str:
    """Reuse the saved Stripe customer or create one (saved for next time)."""
    existing = (user.get("stripe_customer_id") or "").strip()
    if existing:
        return existing
    customer = _stripe().Customer.create(
        email=user.get("email"), metadata={"user_id": str(user["id"])})
    customer_id = customer["id"]
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET stripe_customer_id = ? WHERE id = ?",
                    (customer_id, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return customer_id


def register_billing_routes(app: FastAPI, ctx: RouteContext) -> None:

    @app.post('/api/subscriptions/stripe/checkout')
    async def stripe_checkout(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not billing_sync.stripe_configured():
            raise HTTPException(status_code=503, detail="Card payments are not configured")
        if billing_sync.active_autorenew(user["id"]):
            raise HTTPException(status_code=409, detail=ALREADY_AUTORENEW)
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        price_id = (billing_sync.billing_ids_for_plan(plan["code"])
                    .get("stripe_price_id") or "")
        if not price_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for card payments")
        customer_id = _stripe_customer_id(user)
        session = _stripe().checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user["id"]),
            line_items=[{"price": price_id, "quantity": 1}],
            metadata={"user_id": str(user["id"]), "plan_code": plan["code"]},
            subscription_data={"metadata": {"user_id": str(user["id"]),
                                            "plan_code": plan["code"]}},
            success_url=f"{_frontend_url()}/subscribe?stripe=success",
            cancel_url=f"{_frontend_url()}/subscribe?stripe=cancel",
        )
        return {"url": session["url"]}

    @app.post('/api/subscriptions/stripe/portal')
    async def stripe_portal(authorization: str = Header(None)):
        user = _require_user(authorization)
        if not billing_sync.stripe_configured():
            raise HTTPException(status_code=503, detail="Card payments are not configured")
        customer_id = (user.get("stripe_customer_id") or "").strip()
        if not customer_id:
            raise HTTPException(status_code=404, detail="No card subscription on file")
        session = _stripe().billing_portal.Session.create(
            customer=customer_id, return_url=f"{_frontend_url()}/subscribe")
        return {"url": session["url"]}
```

In `service/server/routes.py`: add `from routes_billing import register_billing_routes` next to the `routes_subscriptions` import (line ~20), and call `register_billing_routes(app, ctx)` immediately after `register_subscription_routes(app, ctx)` in the registration sequence (search for that call).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add service/server/routes_billing.py service/server/routes.py service/requirements.txt .env.example service/server/tests/test_billing.py
git commit -m "feat(billing): Stripe hosted Checkout + Customer Portal endpoints"
```

---

### Task 4: Stripe webhook endpoint

**Files:**
- Modify: `service/server/routes_billing.py`
- Test: `service/server/tests/test_billing.py` (append `StripeWebhookTests`)

**Interfaces:**
- Consumes: `billing_sync.record_billing_event/delete_billing_event/upsert_autorenew_subscription/extend_subscription/apply_subscription_update/end_subscription/plan_for_stripe_price`.
- Produces: `POST /api/webhooks/stripe` (signature-checked; 200 duplicate no-op; 500 → provider retry).

- [ ] **Step 1: Write the failing tests**

Append to `service/server/tests/test_billing.py`:

```python
import hashlib
import hmac as hmac_mod
import json
import time


def _stripe_sig(payload: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac_mod.new(secret.encode(),
                       f"{ts}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class StripeWebhookTests(unittest.TestCase):
    SECRET = "whsec_test"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["STRIPE_WEBHOOK_SECRET"] = self.SECRET
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_jr' "
                        "WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET stripe_price_id = 'price_pro' "
                        "WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ["STRIPE_WEBHOOK_SECRET"] = ""
        self.tmp.cleanup()

    def _post(self, event: dict, sig: str | None = None):
        payload = json.dumps(event).encode()
        return self.client.post(
            "/api/webhooks/stripe", content=payload,
            headers={"Stripe-Signature": sig or _stripe_sig(payload, self.SECRET),
                     "Content-Type": "application/json"})

    def _checkout_completed(self, event_id="evt_cs1", sub_id="sub_A"):
        return {"id": event_id, "type": "checkout.session.completed",
                "data": {"object": {"client_reference_id": str(self.user_id),
                                    "subscription": sub_id,
                                    "metadata": {"user_id": str(self.user_id),
                                                 "plan_code": "junior"}}}}

    def test_bad_signature_rejected(self):
        r = self._post(self._checkout_completed(), sig="t=1,v1=deadbeef")
        self.assertEqual(r.status_code, 400)

    def test_checkout_completed_activates(self):
        r = self._post(self._checkout_completed())
        self.assertEqual(r.status_code, 200, r.text)
        import billing_sync
        sub = billing_sync.active_autorenew(self.user_id)
        self.assertIsNotNone(sub)
        self.assertEqual((sub["method"], sub["plan_code"], sub["external_id"]),
                         ("stripe", "junior", "sub_A"))

    def test_duplicate_event_is_noop(self):
        self._post(self._checkout_completed())
        r = self._post(self._checkout_completed())
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE external_id = 'sub_A'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()

    def test_invoice_paid_extends(self):
        self._post(self._checkout_completed())
        period_end = int(time.time()) + 30 * 86400
        r = self._post({"id": "evt_inv1", "type": "invoice.paid",
                        "data": {"object": {"subscription": "sub_A",
                                            "lines": {"data": [{"period": {"end": period_end}}]}}}})
        self.assertEqual(r.status_code, 200)
        import billing_sync
        expires = billing_sync.active_autorenew(self.user_id)["expires_at"]
        from datetime import datetime, timedelta, timezone
        want = (datetime.fromtimestamp(period_end, tz=timezone.utc)
                + timedelta(days=billing_sync.GRACE_DAYS)).strftime("%Y-%m-%d")
        self.assertTrue(expires.startswith(want))

    def test_subscription_updated_switches_plan_and_flags_cancel(self):
        self._post(self._checkout_completed())
        r = self._post({"id": "evt_up1", "type": "customer.subscription.updated",
                        "data": {"object": {"id": "sub_A", "cancel_at_period_end": True,
                                            "items": {"data": [{"price": {"id": "price_pro"}}]}}}})
        self.assertEqual(r.status_code, 200)
        row = None
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT plan_code, cancel_at_period_end FROM user_subscriptions "
                        "WHERE external_id = 'sub_A'")
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["plan_code"], "pro")
        self.assertEqual(int(row["cancel_at_period_end"]), 1)

    def test_subscription_deleted_ends_access(self):
        self._post(self._checkout_completed())
        r = self._post({"id": "evt_del1", "type": "customer.subscription.deleted",
                        "data": {"object": {"id": "sub_A"}}})
        self.assertEqual(r.status_code, 200)
        import billing_sync
        self.assertIsNone(billing_sync.active_autorenew(self.user_id))

    def test_unknown_event_stored_and_ignored(self):
        r = self._post({"id": "evt_odd", "type": "charge.refunded",
                        "data": {"object": {}}})
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py::StripeWebhookTests -q`
Expected: FAIL (404 — endpoint missing)

- [ ] **Step 3: Implement the webhook in `routes_billing.py`**

Add module-level handler above `register_billing_routes`:

```python
def _handle_stripe_event(event: dict) -> None:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        user_id = int(obj.get("client_reference_id") or meta.get("user_id") or 0)
        sub_id = obj.get("subscription") or ""
        plan_code = meta.get("plan_code") or ""
        if not (user_id and sub_id and plan_code):
            logger.warning("stripe checkout.session.completed missing fields: %s", obj)
            return
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=user_id, plan_code=plan_code,
            external_id=sub_id)
        _alert_new_subscription(email=None, plan_code=plan_code, amount=None,
                                method="stripe", status_note="auto-activated",
                                reference=sub_id)
    elif etype == "invoice.paid":
        sub_id = obj.get("subscription") or ""
        period_end = None
        lines = ((obj.get("lines") or {}).get("data") or [])
        end_ts = (lines[0].get("period") or {}).get("end") if lines else None
        if end_ts:
            period_end = datetime.fromtimestamp(int(end_ts), tz=timezone.utc)
        if sub_id:
            billing_sync.extend_subscription("stripe", sub_id, period_end)
    elif etype == "customer.subscription.updated":
        sub_id = obj.get("id") or ""
        items = ((obj.get("items") or {}).get("data") or [])
        price_id = ((items[0].get("price") or {}).get("id") or "") if items else ""
        plan_code = billing_sync.plan_for_stripe_price(price_id) if price_id else None
        period_end = None
        if obj.get("current_period_end"):
            period_end = datetime.fromtimestamp(int(obj["current_period_end"]),
                                                tz=timezone.utc)
        billing_sync.apply_subscription_update(
            "stripe", sub_id, plan_code=plan_code,
            cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
            period_end=period_end)
    elif etype == "customer.subscription.deleted":
        if obj.get("id"):
            billing_sync.end_subscription("stripe", obj["id"])
    # anything else: recorded in billing_events, deliberately ignored
```

Inside `register_billing_routes`, add:

```python
    @app.post('/api/webhooks/stripe')
    async def stripe_webhook(request: Request,
                             stripe_signature: str = Header(None)):
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise HTTPException(status_code=503, detail="Stripe webhook not configured")
        payload = await request.body()
        import stripe
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature or "",
                                                   secret)
        except Exception:  # noqa: BLE001 — bad signature or malformed payload
            raise HTTPException(status_code=400, detail="Invalid signature")
        event = dict(event)
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Event has no id")
        if not billing_sync.record_billing_event(
                "stripe", event_id, str(event.get("type") or ""),
                payload.decode("utf-8", "replace")):
            return {"ok": True, "duplicate": True}
        try:
            _handle_stripe_event(event)
        except Exception as exc:  # noqa: BLE001
            # Un-record so Stripe's retry is processed, then let it retry.
            billing_sync.delete_billing_event("stripe", event_id)
            logger.exception("stripe webhook processing failed: %s", exc)
            _alert_webhook_failure("stripe", event_id, exc)
            raise HTTPException(status_code=500, detail="Processing failed")
        return {"ok": True}
```

Note: `stripe.Webhook.construct_event` returns a `StripeObject`; `dict(event)` +
nested `.get` works because StripeObject subclasses dict recursively.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_billing.py service/server/tests/test_billing.py
git commit -m "feat(billing): Stripe webhook — signature-checked, idempotent activation/renewal/cancel"
```

---

### Task 5: PayPal subscribe / change-plan / cancel endpoints

**Files:**
- Modify: `service/server/routes_billing.py`
- Test: `service/server/tests/test_billing.py` (append `PaypalSubscribeTests`)

**Interfaces:**
- Consumes: `_paypal_base/_paypal_configured/_paypal_token` from routes_subscriptions; `billing_sync.active_autorenew/billing_ids_for_plan/mark_cancelled`.
- Produces: `POST /api/subscriptions/paypal/subscribe {plan_code} → {"subscription_id", "approve_url"}`; `POST /api/subscriptions/paypal/change-plan {plan_code} → {"ok": True, "approve_url": str|None}`; `POST /api/subscriptions/paypal/cancel → {"ok": True}`.

- [ ] **Step 1: Write the failing tests**

Append to `service/server/tests/test_billing.py`:

```python
class _Resp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class PaypalSubscribeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["PAYPAL_CLIENT_ID"] = "cid"
        os.environ["PAYPAL_CLIENT_SECRET"] = "sec"
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET paypal_plan_id = 'P-JR' "
                        "WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET paypal_plan_id = 'P-PRO' "
                        "WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ["PAYPAL_CLIENT_ID"] = ""
        os.environ["PAYPAL_CLIENT_SECRET"] = ""
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_subscribe_returns_approve_url_and_pending_row(self):
        def fake_post(url, **kw):
            if url.endswith("/v1/oauth2/token"):
                return _Resp(200, {"access_token": "tok"})
            if url.endswith("/v1/billing/subscriptions"):
                self.assertEqual(kw["json"]["plan_id"], "P-JR")
                self.assertEqual(kw["json"]["custom_id"], str(self.user_id))
                return _Resp(201, {"id": "I-NEW", "links": [
                    {"rel": "approve", "href": "https://paypal.com/approve/x"}]})
            raise AssertionError(f"unexpected POST {url}")

        with patch("routes_subscriptions.requests.post", side_effect=fake_post), \
             patch("routes_billing.requests.post", side_effect=fake_post):
            r = self.client.post("/api/subscriptions/paypal/subscribe",
                                 json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["approve_url"], "https://paypal.com/approve/x")
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, method, external_id, auto_renew "
                        "FROM user_subscriptions WHERE user_id = ?", (self.user_id,))
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual((row["status"], row["method"], row["external_id"]),
                         ("pending", "paypal", "I-NEW"))

    def test_subscribe_409_when_autorenew_active(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_1")
        r = self.client.post("/api/subscriptions/paypal/subscribe",
                             json={"plan_code": "junior"}, headers=self._h())
        self.assertEqual(r.status_code, 409)

    def test_change_plan_revises(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="junior",
            external_id="I-CUR")

        def fake_post(url, **kw):
            if url.endswith("/v1/oauth2/token"):
                return _Resp(200, {"access_token": "tok"})
            if url.endswith("/v1/billing/subscriptions/I-CUR/revise"):
                self.assertEqual(kw["json"]["plan_id"], "P-PRO")
                return _Resp(200, {"links": []})
            raise AssertionError(f"unexpected POST {url}")

        with patch("routes_subscriptions.requests.post", side_effect=fake_post), \
             patch("routes_billing.requests.post", side_effect=fake_post):
            r = self.client.post("/api/subscriptions/paypal/change-plan",
                                 json={"plan_code": "pro"}, headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)

    def test_cancel_stops_renewal_keeps_access(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=self.user_id, plan_code="junior",
            external_id="I-CAN")

        def fake_post(url, **kw):
            if url.endswith("/v1/oauth2/token"):
                return _Resp(200, {"access_token": "tok"})
            if url.endswith("/v1/billing/subscriptions/I-CAN/cancel"):
                return _Resp(204, {})
            raise AssertionError(f"unexpected POST {url}")

        with patch("routes_subscriptions.requests.post", side_effect=fake_post), \
             patch("routes_billing.requests.post", side_effect=fake_post):
            r = self.client.post("/api/subscriptions/paypal/cancel", headers=self._h())
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, auto_renew, cancel_at_period_end "
                        "FROM user_subscriptions WHERE external_id = 'I-CAN'")
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual(row["status"], "active")
        self.assertEqual(int(row["auto_renew"]), 0)
        self.assertEqual(int(row["cancel_at_period_end"]), 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py::PaypalSubscribeTests -q`
Expected: FAIL (404)

- [ ] **Step 3: Implement the PayPal endpoints in `routes_billing.py`**

Add inside `register_billing_routes`:

```python
    @app.post('/api/subscriptions/paypal/subscribe')
    async def paypal_subscribe(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        if not _paypal_configured():
            raise HTTPException(status_code=503, detail="PayPal is not configured")
        if billing_sync.active_autorenew(user["id"]):
            raise HTTPException(status_code=409, detail=ALREADY_AUTORENEW)
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        paypal_plan_id = (billing_sync.billing_ids_for_plan(plan["code"])
                          .get("paypal_plan_id") or "")
        if not paypal_plan_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for PayPal")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "plan_id": paypal_plan_id,
                "custom_id": str(user["id"]),
                "application_context": {
                    "return_url": f"{_frontend_url()}/subscribe?paypal=sub-return",
                    "cancel_url": f"{_frontend_url()}/subscribe?paypal=cancel",
                    "user_action": "SUBSCRIBE_NOW",
                },
            },
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            logger.error("PayPal subscribe failed: %s %s", resp.status_code,
                         resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal subscription failed")
        sub = resp.json()
        approve_url = next((link["href"] for link in sub.get("links", [])
                            if link.get("rel") == "approve"), None)
        if not approve_url:
            raise HTTPException(status_code=502, detail="PayPal returned no approval link")
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO user_subscriptions (user_id, plan_code, status, method, "
                "reference, external_id, auto_renew, amount_usd) "
                "VALUES (?, ?, 'pending', 'paypal', ?, ?, 1, ?)",
                (user["id"], plan["code"], sub["id"], sub["id"], plan["price_usd"]))
            conn.commit()
        finally:
            conn.close()
        return {"subscription_id": sub["id"], "approve_url": approve_url}

    @app.post('/api/subscriptions/paypal/change-plan')
    async def paypal_change_plan(body: PlanOrderBody, authorization: str = Header(None)):
        user = _require_user(authorization)
        current = billing_sync.active_autorenew(user["id"])
        if not current or current["method"] != "paypal":
            raise HTTPException(status_code=404, detail="No active PayPal subscription")
        conn = get_db_connection()
        try:
            plan = _load_plan(conn.cursor(), body.plan_code)
        finally:
            conn.close()
        paypal_plan_id = (billing_sync.billing_ids_for_plan(plan["code"])
                          .get("paypal_plan_id") or "")
        if not paypal_plan_id:
            raise HTTPException(status_code=503,
                                detail="This plan is not configured for PayPal")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions/{current['external_id']}/revise",
            headers={"Authorization": f"Bearer {access}"},
            json={"plan_id": paypal_plan_id},
            timeout=20,
        )
        if resp.status_code not in (200, 204):
            logger.error("PayPal revise failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal plan change failed")
        # Plan actually flips on the BILLING.SUBSCRIPTION.UPDATED webhook.
        links = (resp.json().get("links", []) if resp.status_code == 200 else [])
        approve_url = next((link["href"] for link in links
                            if link.get("rel") == "approve"), None)
        return {"ok": True, "approve_url": approve_url}

    @app.post('/api/subscriptions/paypal/cancel')
    async def paypal_cancel(authorization: str = Header(None)):
        user = _require_user(authorization)
        current = billing_sync.active_autorenew(user["id"])
        if not current or current["method"] != "paypal":
            raise HTTPException(status_code=404, detail="No active PayPal subscription")
        access = _paypal_token()
        resp = requests.post(
            f"{_paypal_base()}/v1/billing/subscriptions/{current['external_id']}/cancel",
            headers={"Authorization": f"Bearer {access}"},
            json={"reason": "Member cancelled from the subscribe page"},
            timeout=20,
        )
        if resp.status_code not in (200, 204):
            logger.error("PayPal cancel failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(status_code=502, detail="PayPal cancel failed")
        billing_sync.mark_cancelled("paypal", current["external_id"])
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_billing.py service/server/tests/test_billing.py
git commit -m "feat(billing): PayPal Subscriptions — subscribe, change-plan (revise), cancel"
```

---

### Task 6: PayPal webhook endpoint

**Files:**
- Modify: `service/server/routes_billing.py`
- Test: `service/server/tests/test_billing.py` (append `PaypalWebhookTests`)

**Interfaces:**
- Consumes: billing_sync state functions; PayPal verify-webhook-signature API (mocked in tests).
- Produces: `POST /api/webhooks/paypal`.

- [ ] **Step 1: Write the failing tests**

Append to `service/server/tests/test_billing.py`:

```python
class PaypalWebhookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["PAYPAL_CLIENT_ID"] = "cid"
        os.environ["PAYPAL_CLIENT_SECRET"] = "sec"
        os.environ["PAYPAL_WEBHOOK_ID"] = "WH-1"
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE subscription_plans SET paypal_plan_id = 'P-JR' "
                        "WHERE code = 'junior'")
            cur.execute("UPDATE subscription_plans SET paypal_plan_id = 'P-PRO' "
                        "WHERE code = 'pro'")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        for key in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"):
            os.environ[key] = ""
        self.tmp.cleanup()

    def _post(self, event: dict, verified: bool = True):
        def fake_post(url, **kw):
            if url.endswith("/v1/oauth2/token"):
                return _Resp(200, {"access_token": "tok"})
            if url.endswith("/v1/notifications/verify-webhook-signature"):
                self.assertEqual(kw["json"]["webhook_id"], "WH-1")
                return _Resp(200, {"verification_status":
                                   "SUCCESS" if verified else "FAILURE"})
            raise AssertionError(f"unexpected POST {url}")

        with patch("routes_subscriptions.requests.post", side_effect=fake_post), \
             patch("routes_billing.requests.post", side_effect=fake_post):
            return self.client.post("/api/webhooks/paypal", json=event)

    def test_unverified_rejected(self):
        r = self._post({"id": "WHE-0", "event_type": "PAYMENT.SALE.COMPLETED",
                        "resource": {}}, verified=False)
        self.assertEqual(r.status_code, 400)

    def test_activated_creates_active_sub(self):
        r = self._post({"id": "WHE-1",
                        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                        "resource": {"id": "I-77", "plan_id": "P-JR",
                                     "custom_id": str(self.user_id),
                                     "billing_info": {"next_billing_time":
                                                      "2026-09-03T10:00:00Z"}}})
        self.assertEqual(r.status_code, 200, r.text)
        import billing_sync
        sub = billing_sync.active_autorenew(self.user_id)
        self.assertEqual((sub["method"], sub["plan_code"], sub["external_id"]),
                         ("paypal", "junior", "I-77"))
        self.assertTrue(sub["expires_at"].startswith("2026-09-06"))

    def test_sale_completed_extends(self):
        self._post({"id": "WHE-1", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                    "resource": {"id": "I-77", "plan_id": "P-JR",
                                 "custom_id": str(self.user_id)}})
        r = self._post({"id": "WHE-2", "event_type": "PAYMENT.SALE.COMPLETED",
                        "resource": {"billing_agreement_id": "I-77"}})
        self.assertEqual(r.status_code, 200)

    def test_updated_switches_plan(self):
        self._post({"id": "WHE-1", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                    "resource": {"id": "I-77", "plan_id": "P-JR",
                                 "custom_id": str(self.user_id)}})
        r = self._post({"id": "WHE-3", "event_type": "BILLING.SUBSCRIPTION.UPDATED",
                        "resource": {"id": "I-77", "plan_id": "P-PRO"}})
        self.assertEqual(r.status_code, 200)
        import billing_sync
        self.assertEqual(billing_sync.active_autorenew(self.user_id)["plan_code"],
                         "pro")

    def test_cancelled_keeps_access_expired_ends_it(self):
        self._post({"id": "WHE-1", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
                    "resource": {"id": "I-77", "plan_id": "P-JR",
                                 "custom_id": str(self.user_id)}})
        r = self._post({"id": "WHE-4", "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
                        "resource": {"id": "I-77"}})
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, auto_renew FROM user_subscriptions "
                        "WHERE external_id = 'I-77'")
            row = dict(cur.fetchone())
        finally:
            conn.close()
        self.assertEqual((row["status"], int(row["auto_renew"])), ("active", 0))
        r = self._post({"id": "WHE-5", "event_type": "BILLING.SUBSCRIPTION.EXPIRED",
                        "resource": {"id": "I-77"}})
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status FROM user_subscriptions "
                        "WHERE external_id = 'I-77'")
            self.assertEqual(dict(cur.fetchone())["status"], "expired")
        finally:
            conn.close()

    def test_duplicate_event_noop(self):
        evt = {"id": "WHE-D", "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
               "resource": {"id": "I-88", "plan_id": "P-JR",
                            "custom_id": str(self.user_id)}}
        self._post(evt)
        r = self._post(evt)
        self.assertEqual(r.status_code, 200)
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM user_subscriptions "
                        "WHERE external_id = 'I-88'")
            self.assertEqual(int(dict(cur.fetchone())["c"]), 1)
        finally:
            conn.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py::PaypalWebhookTests -q`
Expected: FAIL (404)

- [ ] **Step 3: Implement the PayPal webhook in `routes_billing.py`**

Module-level handler:

```python
def _parse_paypal_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _handle_paypal_event(event: dict) -> None:
    etype = event.get("event_type", "")
    res = event.get("resource") or {}
    if etype == "BILLING.SUBSCRIPTION.ACTIVATED":
        sub_id = res.get("id") or ""
        user_id = int(res.get("custom_id") or 0)
        plan_code = billing_sync.plan_for_paypal_plan(res.get("plan_id") or "")
        period_end = _parse_paypal_time(
            ((res.get("billing_info") or {}).get("next_billing_time")) or "")
        if not (sub_id and user_id and plan_code):
            logger.warning("paypal ACTIVATED missing fields: %s", res)
            return
        billing_sync.upsert_autorenew_subscription(
            provider="paypal", user_id=user_id, plan_code=plan_code,
            external_id=sub_id, period_end=period_end)
        _alert_new_subscription(email=None, plan_code=plan_code, amount=None,
                                method="paypal", status_note="auto-activated",
                                reference=sub_id)
    elif etype == "PAYMENT.SALE.COMPLETED":
        sub_id = res.get("billing_agreement_id") or ""
        if sub_id:
            billing_sync.extend_subscription("paypal", sub_id)
    elif etype == "BILLING.SUBSCRIPTION.UPDATED":
        sub_id = res.get("id") or ""
        plan_code = billing_sync.plan_for_paypal_plan(res.get("plan_id") or "")
        if sub_id and plan_code:
            billing_sync.apply_subscription_update("paypal", sub_id,
                                                   plan_code=plan_code)
    elif etype in ("BILLING.SUBSCRIPTION.CANCELLED", "BILLING.SUBSCRIPTION.SUSPENDED"):
        if res.get("id"):
            billing_sync.mark_cancelled("paypal", res["id"])
    elif etype == "BILLING.SUBSCRIPTION.EXPIRED":
        if res.get("id"):
            billing_sync.end_subscription("paypal", res["id"])
    # anything else: recorded, ignored
```

Route:

```python
    @app.post('/api/webhooks/paypal')
    async def paypal_webhook(request: Request):
        webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
        if not (_paypal_configured() and webhook_id):
            raise HTTPException(status_code=503, detail="PayPal webhook not configured")
        event = await request.json()
        headers = request.headers
        access = _paypal_token()
        verify = requests.post(
            f"{_paypal_base()}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {access}"},
            json={
                "auth_algo": headers.get("paypal-auth-algo", ""),
                "cert_url": headers.get("paypal-cert-url", ""),
                "transmission_id": headers.get("paypal-transmission-id", ""),
                "transmission_sig": headers.get("paypal-transmission-sig", ""),
                "transmission_time": headers.get("paypal-transmission-time", ""),
                "webhook_id": webhook_id,
                "webhook_event": event,
            },
            timeout=20,
        )
        if (verify.status_code != 200
                or verify.json().get("verification_status") != "SUCCESS"):
            raise HTTPException(status_code=400, detail="Invalid signature")
        event_id = str(event.get("id") or "")
        if not event_id:
            raise HTTPException(status_code=400, detail="Event has no id")
        import json as _json
        if not billing_sync.record_billing_event(
                "paypal", event_id, str(event.get("event_type") or ""),
                _json.dumps(event)):
            return {"ok": True, "duplicate": True}
        try:
            _handle_paypal_event(event)
        except Exception as exc:  # noqa: BLE001
            billing_sync.delete_billing_event("paypal", event_id)
            logger.exception("paypal webhook processing failed: %s", exc)
            _alert_webhook_failure("paypal", event_id, exc)
            raise HTTPException(status_code=500, detail="Processing failed")
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_billing.py service/server/tests/test_billing.py
git commit -m "feat(billing): PayPal webhook — verified, idempotent lifecycle sync"
```

---

### Task 7: plans + me endpoints expose billing capability and auto-renew state

**Files:**
- Modify: `service/server/routes_subscriptions.py` (plans response, `get_subscription_state` SELECT)
- Test: `service/server/tests/test_billing.py` (append `PlansEndpointTests`)

**Interfaces:**
- Produces: `GET /api/subscriptions/plans` gains `"stripe_available": bool`; `GET /api/subscriptions/me` subscription dict gains `external_id`, `auto_renew`, `cancel_at_period_end`. Frontend (Task 8) reads exactly these keys.

- [ ] **Step 1: Write the failing tests**

```python
class PlansEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.user_id, self.token = _register_user(self.client, database)

    def tearDown(self):
        os.environ["STRIPE_SECRET_KEY"] = ""
        self.tmp.cleanup()

    def test_stripe_available_flag(self):
        r = self.client.get("/api/subscriptions/plans")
        self.assertFalse(r.json()["stripe_available"])
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_x"
        r = self.client.get("/api/subscriptions/plans")
        self.assertTrue(r.json()["stripe_available"])

    def test_me_includes_autorenew_fields(self):
        import billing_sync
        billing_sync.upsert_autorenew_subscription(
            provider="stripe", user_id=self.user_id, plan_code="junior",
            external_id="sub_me")
        r = self.client.get("/api/subscriptions/me",
                            headers={"Authorization": f"Bearer {self.token}"})
        sub = r.json()["subscription"]
        self.assertEqual(sub["external_id"], "sub_me")
        self.assertEqual(int(sub["auto_renew"]), 1)
        self.assertEqual(int(sub["cancel_at_period_end"]), 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest service/server/tests/test_billing.py::PlansEndpointTests -q`
Expected: FAIL (KeyError `stripe_available` / `external_id`)

- [ ] **Step 3: Implement**

In `routes_subscriptions.py`: add `import billing_sync` to the module-level imports (safe — billing_sync imports nothing from routes_subscriptions, no cycle), then in the `subscription_plans()` response dict add after `"paypal_available"`:

```python
            "stripe_available": billing_sync.stripe_configured(),
```

In `get_subscription_state()`, widen the SELECT:

```python
        SELECT id, plan_code, status, method, started_at, expires_at, created_at,
               external_id, auto_renew, cancel_at_period_end
        FROM user_subscriptions
```

- [ ] **Step 4: Run the whole backend suite**

Run: `.venv/bin/python -m pytest service/server/tests -q`
Expected: all pass (entitlements tests exercise get_subscription_state — confirm no break)

- [ ] **Step 5: Commit**

```bash
git add service/server/routes_subscriptions.py service/server/tests/test_billing.py
git commit -m "feat(billing): expose stripe_available + auto-renew fields on plans/me"
```

---

### Task 8: Frontend — SubscribePage Stripe/PayPal buttons, return states, manage card

**Files:**
- Modify: `service/frontend/src/pages/SubscribePage.tsx`

**Interfaces:**
- Consumes: `stripe_available` from plans, `auto_renew`/`cancel_at_period_end`/`method`/`external_id` from me, `POST /api/subscriptions/stripe/checkout|portal`, `POST /api/subscriptions/paypal/subscribe|change-plan|cancel`.

- [ ] **Step 1: State + loader changes**

Add state next to `paypalAvailable`:

```tsx
  const [stripeAvailable, setStripeAvailable] = useState(false)
```

In `loadState()` after `setPaypalAvailable(...)`:

```tsx
      setStripeAvailable(!!p.stripe_available)
```

- [ ] **Step 2: Add the new i18n strings to `T`**

```tsx
    payCard: tr(language, { ko: '카드로 구독 — 카드 · Apple Pay · Google Pay', en: 'Subscribe with card — card · Apple Pay · Google Pay',
      ja: 'カードで購読 — カード · Apple Pay · Google Pay', th: 'สมัครด้วยบัตร — บัตร · Apple Pay · Google Pay',
      vi: 'Đăng ký bằng thẻ — thẻ · Apple Pay · Google Pay', id: 'Berlangganan dengan kartu — kartu · Apple Pay · Google Pay' }),
    autoRenewNote: tr(language, { ko: '매월 자동 갱신 · 언제든 해지 가능', en: 'Renews monthly · cancel anytime',
      ja: '毎月自動更新 · いつでも解約可能', th: 'ต่ออายุรายเดือน · ยกเลิกได้ทุกเมื่อ',
      vi: 'Gia hạn hằng tháng · hủy bất cứ lúc nào', id: 'Diperpanjang bulanan · batalkan kapan saja' }),
    activating: tr(language, { ko: '결제 확인 중 — 곧 활성화됩니다…', en: 'Payment received — activating…',
      ja: '支払いを確認中 — まもなく有効になります…', th: 'ได้รับการชำระเงินแล้ว — กำลังเปิดใช้งาน…',
      vi: 'Đã nhận thanh toán — đang kích hoạt…', id: 'Pembayaran diterima — mengaktifkan…' }),
    stripeCancelled: tr(language, { ko: '카드 결제가 취소되었습니다.', en: 'Card checkout was cancelled.',
      ja: 'カード決済がキャンセルされました。', th: 'การชำระด้วยบัตรถูกยกเลิก',
      vi: 'Thanh toán thẻ đã bị hủy.', id: 'Pembayaran kartu dibatalkan.' }),
    renewsAuto: tr(language, { ko: '자동 갱신', en: 'Renews automatically', ja: '自動更新',
      th: 'ต่ออายุอัตโนมัติ', vi: 'Tự động gia hạn', id: 'Diperpanjang otomatis' }),
    cancelsOn: tr(language, { ko: '해지 예정일', en: 'Cancels on', ja: '解約予定日',
      th: 'จะยกเลิกในวันที่', vi: 'Sẽ hủy vào', id: 'Berakhir pada' }),
    manageSub: tr(language, { ko: '구독 관리', en: 'Manage subscription', ja: '購読を管理',
      th: 'จัดการการสมัคร', vi: 'Quản lý gói đăng ký', id: 'Kelola langganan' }),
    changePlan: tr(language, { ko: '플랜 변경 (다음 결제 주기부터 적용)', en: 'Change plan (applies next billing cycle)',
      ja: 'プラン変更 (次の請求サイクルから適用)', th: 'เปลี่ยนแพ็กเกจ (มีผลรอบบิลถัดไป)',
      vi: 'Đổi gói (áp dụng từ chu kỳ sau)', id: 'Ganti paket (berlaku siklus berikutnya)' }),
    cancelAutoRenew: tr(language, { ko: '자동 갱신 해지', en: 'Cancel auto-renewal', ja: '自動更新を解約',
      th: 'ยกเลิกการต่ออายุอัตโนมัติ', vi: 'Hủy tự động gia hạn', id: 'Batalkan perpanjangan otomatis' }),
    cancelKeepsAccess: tr(language, { ko: '해지해도 현재 결제 기간이 끝날 때까지는 이용할 수 있습니다.', en: 'You keep access until the end of the current billing period.',
      ja: '解約後も現在の請求期間の終了までご利用いただけます。', th: 'คุณยังใช้งานได้จนสิ้นสุดรอบบิลปัจจุบัน',
      vi: 'Bạn vẫn dùng được đến hết chu kỳ thanh toán hiện tại.', id: 'Anda tetap punya akses hingga akhir periode tagihan saat ini.' }),
```

- [ ] **Step 3: Purchase actions + return handling**

Add the two starters next to `startPaypal` (and change `startPaypal` to call the new subscribe endpoint):

```tsx
  async function startStripe(planCode: string) {
    setBusy(true); setError('')
    try {
      const r = await fetch(`${API_BASE}/subscriptions/stripe/checkout`, {
        method: 'POST',
        headers: { ...authHdr, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_code: planCode }),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      window.location.href = (await r.json()).url
    } catch (e: any) { setError(String(e?.message || e)); setBusy(false) }
  }
```

Replace the body of `startPaypal` to call `/subscriptions/paypal/subscribe` (same shape — response key changes from `approve_url` stays `approve_url`, so only the URL path changes):

```tsx
      const r = await fetch(`${API_BASE}/subscriptions/paypal/subscribe`, {
```

Add a webhook-wait poller + return-parameter effect (activation arrives via webhook, so poll `subscriptions/me` up to ~30 s):

```tsx
  // Stripe/PayPal auto-renew returns: activation lands via webhook, so poll.
  useEffect(() => {
    const stripeMode = params.get('stripe')
    const paypalMode = params.get('paypal')
    if (stripeMode === 'cancel') { setError(T.stripeCancelled); return }
    if (paypalMode === 'cancel') { setError(T.paypalCancel); return }
    if ((stripeMode !== 'success' && paypalMode !== 'sub-return') || !userToken) return
    setBusy(true); setNotice(T.activating)
    let tries = 0
    const timer = setInterval(async () => {
      tries += 1
      try {
        const m = await fetch(`${API_BASE}/subscriptions/me`, { headers: authHdr })
          .then(r => r.ok ? r.json() : null)
        if (m?.status === 'active' && Number(m?.subscription?.auto_renew)) {
          clearInterval(timer)
          setNotice(T.paypalDone)
          setTimeout(() => { window.location.href = '/' }, 1200)
          return
        }
      } catch { /* keep polling */ }
      if (tries >= 15) { clearInterval(timer); setBusy(false); setNotice('') }
    }, 2000)
    return () => clearInterval(timer)
  }, [params, userToken])
```

Keep the existing legacy `paypal=return` capture effect untouched (in-flight one-time orders).

- [ ] **Step 4: Payment method UI**

In the payment card (`status !== 'active' && … && selected` block), insert ABOVE the USDT section — card is now the primary rail when configured:

```tsx
          {stripeAvailable && (
            <div style={{ marginBottom: 18 }}>
              <button style={primaryBtn} disabled={busy} onClick={() => startStripe(selected)}>
                💳 {T.payCard}
              </button>
              <div style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)', marginTop: 6, textAlign: 'center' }}>
                {T.autoRenewNote}
              </div>
            </div>
          )}
```

(The existing `paypalAvailable` button block stays where it is; it now starts an auto-renewing subscription and its caption `T.payPaypal` is unchanged.)

- [ ] **Step 5: Manage card for active auto-renew subscribers**

Inside the `status === 'active'` card, after the expires line, add:

```tsx
          {Number(mine?.subscription?.auto_renew) === 1 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, color: 'var(--text-muted,#8a8073)' }}>
                {Number(mine?.subscription?.cancel_at_period_end) === 1
                  ? `${T.cancelsOn}: ${String(mine?.subscription?.expires_at || '').slice(0, 10)}`
                  : `↻ ${T.renewsAuto}`}
              </div>
              {mine?.subscription?.method === 'stripe' && (
                <button style={{ ...ghostBtn, width: 'auto', marginTop: 10 }} disabled={busy}
                  onClick={async () => {
                    setBusy(true); setError('')
                    try {
                      const r = await fetch(`${API_BASE}/subscriptions/stripe/portal`, {
                        method: 'POST', headers: authHdr })
                      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
                      window.location.href = (await r.json()).url
                    } catch (e: any) { setError(String(e?.message || e)); setBusy(false) }
                  }}>{T.manageSub}</button>
              )}
              {mine?.subscription?.method === 'paypal' && (
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                    {plans.filter(p => !p.contact_only && p.code !== mine?.subscription?.plan_code).map(p => (
                      <button key={p.code} style={{ ...ghostBtn, width: 'auto' }} disabled={busy}
                        onClick={async () => {
                          setBusy(true); setError('')
                          try {
                            const r = await fetch(`${API_BASE}/subscriptions/paypal/change-plan`, {
                              method: 'POST',
                              headers: { ...authHdr, 'Content-Type': 'application/json' },
                              body: JSON.stringify({ plan_code: p.code }),
                            })
                            if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
                            const b = await r.json()
                            if (b.approve_url) { window.location.href = b.approve_url; return }
                            await loadState()
                          } catch (e: any) { setError(String(e?.message || e)) }
                          setBusy(false)
                        }}>{p.name} — {T.changePlan}</button>
                    ))}
                  </div>
                  {Number(mine?.subscription?.cancel_at_period_end) !== 1 && (
                    <button style={{ background: 'none', border: 'none', color: 'var(--text-muted,#8a8073)', cursor: 'pointer', fontSize: 12.5, textDecoration: 'underline' }}
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true); setError('')
                        try {
                          const r = await fetch(`${API_BASE}/subscriptions/paypal/cancel`, {
                            method: 'POST', headers: authHdr })
                          if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
                          await loadState()
                        } catch (e: any) { setError(String(e?.message || e)) }
                        setBusy(false)
                      }}>{T.cancelAutoRenew}</button>
                  )}
                  <div style={{ fontSize: 11.5, color: 'var(--text-muted,#8a8073)' }}>{T.cancelKeepsAccess}</div>
                </div>
              )}
            </div>
          )}
```

Also update the header comment of the file (lines 7–10) to mention the two auto-renew rails.

- [ ] **Step 6: Type-check**

Run: `cd service/frontend && npx tsc --noEmit`
Expected: no errors. Then `cd ../..`.

- [ ] **Step 7: Commit**

```bash
git add service/frontend/src/pages/SubscribePage.tsx
git commit -m "feat(billing): SubscribePage — card/Apple/Google Pay + PayPal auto-renew, manage card"
```

---

### Task 9: Full verification pass

**Files:** none new — verification only.

- [ ] **Step 1: Lint + full backend suite (twice)**

```bash
.venv/bin/python -m ruff check service/server
.venv/bin/python -m pytest service/server/tests -q
.venv/bin/python -m pytest service/server/tests -q
```
Expected: ruff clean; suite passes both runs (owner rule: minimum 2 verification passes).

- [ ] **Step 2: Frontend build check**

```bash
cd service/frontend && npx tsc --noEmit && npm run build && cd ../..
```
Expected: clean.

- [ ] **Step 3: Mutation spot-check (proves the new tests bite)**

Temporarily break `billing_sync.record_billing_event` to always return True (comment out the try/except duplicate path), run
`.venv/bin/python -m pytest service/server/tests/test_billing.py -q` — expect FAILURES (duplicate tests). Revert. Clear `__pycache__` before re-running (`find service/server -name __pycache__ -prune -exec rm -rf {} +`) so the mutant isn't cached. Repeat once with `_handle_stripe_event`'s `invoice.paid` branch disabled — expect the extend test to fail. Revert both, re-run suite green.

- [ ] **Step 4: Manual local smoke (no live money)**

Start backend from repo root (`.venv/bin/python -m uvicorn --app-dir service/server main:app --port 8001`) and frontend dev server; with `STRIPE_SECRET_KEY` unset confirm the Subscribe page hides the card button and still shows USDT/bank. This proves prod can deploy safely before the owner's keys exist.

- [ ] **Step 5: Commit any fixes; final commit**

```bash
git add -A -- service/server/billing_sync.py service/server/routes_billing.py service/server/tests/test_billing.py
git commit -m "test(billing): verification pass fixes" --allow-empty
```

---

### Task 10: Deploy to production (code live, rails dormant until keys)

Follow the standard Sooppiy deploy procedure (memory: `sooppiy-deploy-procedure`): build, tarball + docker to EC2, run `alembic upgrade head` (applies 0036 on MySQL), restart, verify `/api/subscriptions/plans` returns `stripe_available: false` on prod (keys not yet set — card/PayPal-subscription buttons stay hidden; existing USDT/bank rails unaffected).

Then hand the owner the deploy checklist from the spec (§ Owner deploy checklist): Stripe account + Prices + Portal config + webhook endpoint; PayPal live billing plans + webhook; seed `subscription_plans.stripe_price_id` / `paypal_plan_id`; set env keys; flip `PAYPAL_API_BASE`/`PAYPAL_UI_ENABLED`. After keys land: one real-money smoke test per provider (owner authorizes), watched via webhook logs + `billing_events` rows.
