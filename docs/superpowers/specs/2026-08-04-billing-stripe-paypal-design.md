# Billing: Stripe + PayPal Auto-Renew Subscriptions — Design

Date: 2026-08-04
Status: approved by owner (design dialogue, 2026-08-04)
Sub-project: A of 2 (B = account security: phone verification, SMS password reset,
welcome email — separate spec, designed after A ships)

## Goal

Let members pay for subscription plans with cards / Apple Pay / Google Pay (via
Stripe) and PayPal, on a monthly auto-renew basis, with upgrade / downgrade /
cancel — while keeping the existing entitlements gate (`user_subscriptions.expires_at`)
untouched as the single source of truth for AI-trading access.

Decisions made with the owner:

- Billing ships first; account-security items are sub-project B.
- Owner will create the Stripe account (US business — full Stripe support).
  Implementation targets Stripe **test mode**; live keys are a deploy step.
- Renewal model: **auto-renew monthly** for Stripe AND PayPal.
- Stripe integration style: **hosted Checkout + Customer Portal** (approach 1),
  not embedded Payment Element, not a merchant-of-record vendor.
- USDT and bank-transfer remain as today: one-time 30-day, admin-approved.
- US sales tax: NOT built now. Future item: enable Stripe Tax when revenue
  approaches state economic-nexus thresholds (see stripe.com/docs/tax).

## Current state (what exists)

- `routes_subscriptions.py`: plans list, `subscription/me`, PayPal one-time
  Orders flow (hidden behind `PAYPAL_UI_ENABLED=false`, sandbox base), USDT +
  bank-transfer manual submission, enterprise contract form.
- `subscription_plans` table (code, name, price_usd, contact_only, active),
  `user_subscriptions` (plan_code, status active|pending|expired, method,
  started_at, expires_at). Lazy expiry in `get_subscription_state()`.
- `entitlements.py` gates AI trading off the active subscription row.
- No Stripe anywhere. No webhooks. No upgrade/downgrade.

## 1. Data model

- `users`: add `stripe_customer_id TEXT NULL`.
- `subscription_plans`: add `stripe_price_id TEXT NULL`, `paypal_plan_id TEXT NULL`.
  Seeded once from the Stripe / PayPal dashboards (deploy checklist below).
- `user_subscriptions`: add `external_id TEXT NULL` (Stripe subscription id or
  PayPal subscription id), `auto_renew INTEGER DEFAULT 0`,
  `cancel_at_period_end INTEGER DEFAULT 0`. Existing `method` column values
  gain `stripe`; `paypal` now means the subscription flow.
- New table `billing_events`:
  `(id PK, provider TEXT, event_id TEXT, type TEXT, payload TEXT,
  processed_at TEXT, UNIQUE(provider, event_id))` — webhook idempotency + audit.
- `expires_at` remains the ONLY field entitlements reads. Every successful
  renewal payment pushes it to `current_period_end + 3 days grace`. Gating code
  is not modified.
- Migrations: one Alembic revision (MySQL prod) + matching SQLite DDL in
  `database.py`. Mind the SQLite↔MySQL dialect traps (no `ESCAPE '\\'`, FK
  enforcement differences).

## 2. Purchase flow

Stripe:

- `POST /api/subscriptions/stripe/checkout {plan_code}` (auth required):
  create-or-reuse Stripe Customer (store `stripe_customer_id`), create Checkout
  Session `mode=subscription` with the plan's `stripe_price_id`,
  `client_reference_id=user_id`, success/cancel URLs
  `/subscribe?stripe=success|cancel`. Returns `{url}`; frontend redirects.
  Cards, Apple Pay, Google Pay, debit all appear automatically on the hosted page.
- Rejected with 409 if the user already has an active auto-renew subscription
  on PayPal ("cancel your current subscription first"). An active one-time
  period (USDT/bank) does NOT block — the new sub supersedes it.

PayPal:

- `POST /api/subscriptions/paypal/subscribe {plan_code}`: create a Subscription
  (v1/billing/subscriptions) from the plan's `paypal_plan_id`,
  `custom_id=user_id`, return approve URL. Mirror-image 409 rule vs Stripe.
- The old one-time `create-order`/`capture` endpoints remain only for in-flight
  legacy orders; the UI stops offering them.

Activation happens ONLY via webhook — a closed browser tab cannot lose a payment.
The success-return page polls `subscription/me` briefly and shows "payment
received, activating…" until the webhook lands.

## 3. Upgrade / downgrade / cancel

- Stripe: `POST /api/subscriptions/stripe/portal` returns a Customer Portal
  session URL. Portal product config allows: switch between paid plans
  (upgrade = immediate + prorated invoice; downgrade = at period end), update
  card, cancel at period end. No custom proration code on our side; webhooks
  reflect the changes.
- PayPal: `POST /api/subscriptions/paypal/change-plan {plan_code}` → the
  subscription *revise* API (takes effect next cycle — no proration; UI states
  this). `POST /api/subscriptions/paypal/cancel` → cancel API
  (`cancel_at_period_end` semantics: access continues to `expires_at`).
- Rule: at most one auto-renew subscription per user across providers.

## 4. Webhooks — source of truth

- `POST /api/webhooks/stripe`: signature check with `STRIPE_WEBHOOK_SECRET`.
  Handled events:
  - `checkout.session.completed` — link subscription → user
    (client_reference_id), upsert active row.
  - `invoice.paid` — extend `expires_at = current_period_end + 3d`.
  - `customer.subscription.updated` — plan switches, `cancel_at_period_end`.
  - `customer.subscription.deleted` — mark cancelled; access lapses at `expires_at`.
- `POST /api/webhooks/paypal`: verified via PayPal
  verify-webhook-signature API using `PAYPAL_WEBHOOK_ID`. Handled events:
  `BILLING.SUBSCRIPTION.ACTIVATED`, `PAYMENT.SALE.COMPLETED` (extend),
  `BILLING.SUBSCRIPTION.CANCELLED` / `SUSPENDED` / `EXPIRED`.
- Idempotency: insert into `billing_events` first; duplicate `(provider,
  event_id)` → 200 no-op. Unknown event types: store, 200, ignore.
- Processing failure → 500 (provider retries) + owner alert via the existing
  `admin_alerts` path (same channel as `_alert_new_subscription`).
- Failed renewals: Stripe smart-retries automatically; we build nothing. If
  retries never succeed, `expires_at` lapses and entitlements close access.

## 5. Frontend (SubscribePage + account area)

- Plan cards: primary "Subscribe — card / Apple Pay / Google Pay" button
  (→ Stripe Checkout URL) + PayPal button (→ approve URL). USDT / bank flows
  unchanged. Legacy PayPal one-time button removed.
- Active subscribers: "Manage subscription" card — current plan, renewal date,
  state line (`Renews automatically` / `Cancels on <date>` / plan-change
  pending), manage button (Stripe → Portal URL; PayPal → in-app
  change-plan/cancel controls).
- Success/cancel return states on `/subscribe` (incl. the webhook-pending
  polling state).
- All new strings go through the existing 6-language i18n pipeline
  (en/ko/ja/th/vi/id).

## 6. Config & dependencies

- New env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PAYPAL_WEBHOOK_ID`.
- Existing env repurposed at deploy: `PAYPAL_API_BASE` → live host,
  `PAYPAL_UI_ENABLED=true`.
- Add official `stripe` Python SDK to `service/requirements.txt`. PayPal stays
  raw `requests` (matches existing code).
- `.env.example` updated with all of the above.

### Owner deploy checklist (live keys — owner-only steps)

1. Create Stripe account (US). In Stripe dashboard: create one monthly
   recurring Price per paid plan; enable Apple Pay / Google Pay (domain
   verification for sooppiy.com); configure Customer Portal (allowed plan
   switches, cancel at period end); create webhook endpoint
   `https://sooppiy.com/api/webhooks/stripe` with the four events above; copy
   `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, price ids.
2. PayPal developer dashboard (live): create a Product + monthly billing Plan
   per paid tier; create webhook for the five subscription events; copy
   `PAYPAL_WEBHOOK_ID`, live client id/secret.
3. Seed `subscription_plans.stripe_price_id` / `paypal_plan_id` on prod.
4. Set env on prod, flip `PAYPAL_API_BASE` + `PAYPAL_UI_ENABLED`, deploy,
   then run one real-money smoke test on each provider (owner authorizes).

## 7. Testing

- pytest (all external HTTP mocked; no live calls from tests):
  - webhook signature acceptance/rejection for both providers,
  - idempotent replay (same event twice → one state change),
  - state transitions: checkout-completed → invoice.paid renew → plan switch →
    cancel-at-period-end → lapse,
  - entitlements open/close at each transition,
  - 409 cross-provider block; USDT-period superseded correctly,
  - PayPal revise/cancel endpoints.
- SQLite + MySQL-dialect review of every new SQL statement.
- ruff + pytest + tsc green before deploy (CI mirrors this).
- Manual E2E: Stripe test mode via Stripe CLI webhook forwarding; PayPal
  sandbox. Then prod deploy per standard procedure; live smoke test is
  owner-authorized.

## Out of scope (this spec)

- Sub-project B: phone verification, SMS password reset, welcome email,
  account-page verification UI.
- Sales tax automation (Stripe Tax) — future toggle.
- Refunds/dunning UI beyond provider defaults; admin billing dashboard.
