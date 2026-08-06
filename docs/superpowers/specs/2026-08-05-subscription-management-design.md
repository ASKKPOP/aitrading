# Subscription Management Page (`/account/subscription`) — Design

Date: 2026-08-05
Status: **DESIGN PRESENTED, NOT YET APPROVED** — owner rotated Claude accounts
mid-dialogue; approval is the first thing the next session must ask for.
Sub-project: B of 2 (A = `2026-08-05-welcome-onboarding-design.md`)

## Goal

A member can see their own subscription and change it — upgrade or downgrade —
from the account area, on whichever rail they actually paid with. Today the
only self-serve control is a single "Upgrade plan" link into `/subscribe`, and
there is no downgrade path at all.

## Owner decisions (from the design dialogue, 2026-08-05)

1. **Change semantics:** **upgrade = pay the difference now; downgrade = takes
   effect at renewal.** Chosen over "card users only, manual users contact
   support" and over "request → admin approves for everything".
2. **Placement:** a **new `/account/subscription` page**, linked from both
   `/settings` and `/my-trading`. Not an expansion of `/subscribe`, and not
   built inline into the already-570-line SettingsPage.

## Current state (verified against `origin/main` @ 5c31681, rebased onto
29018da — the only intervening commit was an unrelated P&L audit module)

- **`routes_subscriptions.py`** — plans list, `subscriptions/me` with lazy
  expiry, and the three legacy rails: PayPal one-time Orders, USDT, bank
  transfer. The last two go `pending` → admin approves → `active` for 30 days.
  USDT address / network and bank details are console-registered
  (`platform_settings`), not `.env`.
- **`routes_billing.py`** (#236) — Stripe hosted Checkout + Customer Portal,
  PayPal Subscriptions API, both webhook-driven. **Endpoints here never
  activate a plan**; activation, renewal, plan change and ending all arrive via
  webhook and are applied by `billing_sync`, idempotent per provider event id.
- **`SubscribePage.tsx`** already renders a "my subscription" block with the
  Stripe Portal button, PayPal `change-plan`, and cancel-auto-renew.
- **`/settings` → Membership** and **`/my-trading`** each show a plan chip plus
  one bare "Upgrade plan" link to `/subscribe`.
- **Schema:** `user_subscriptions(user_id, plan_code, status, method, reference,
  amount_usd, started_at, expires_at, decided_by, …)` plus `external_id`,
  `auto_renew`, `cancel_at_period_end` from migration `0041`. Plans seeded in
  `database.py:2566`: junior $60 (sort 1), pro $119 (2), professional $199 (3),
  enterprise contact-only (4). Tier order = `sort_order`.
  *(2026-08-06: the seed was $60/$250/$500 when this spec was written; it now
  matches the repriced prod values, so a fresh install no longer starts wrong.)*
- **Entitlements** read `expires_at` as the single gate and `plan_code` for
  limits (`entitlements.py:33–41`).

### The constraint that shapes this whole design

Stripe and PayPal auto-renew are **live but dormant on production**:
`PAYPAL_UI_ENABLED` defaults to `false`, and `stripe_available` requires
`STRIPE_SECRET_KEY`. So on day one essentially every real subscriber is on the
**manual rail**. The proration + admin-approval path is therefore the main
path, not an edge case, and is scoped as such.

## Design

### Route and links

New authenticated page `/account/subscription`.

- `/settings` → Membership and `/my-trading`'s plan chip both replace "Upgrade
  plan" with "Manage subscription" pointing here.
- `/subscribe` remains the **first-purchase** page for members whose
  subscription state is `none`.

### What the page shows

1. **My subscription** — plan, status, method, started / expires, auto-renew
   state, cancel-at-period-end, and any scheduled downgrade.
2. **Plan ladder** — junior → pro → professional → enterprise, current one
   marked; every other plan offers Upgrade or Downgrade decided by `sort_order`
   against the current plan.
3. **History** — the member's past `user_subscriptions` rows.

### Change semantics, per rail

- **Stripe** — both directions open the existing Customer Portal
  (`POST /api/subscriptions/stripe/portal`). Stripe already prorates upgrades
  and schedules downgrades for the next period. **No new backend.**
- **PayPal** — the existing `POST /api/subscriptions/paypal/change-plan`
  revision. PayPal bills the difference at the **next cycle**, not now; the copy
  must say so rather than imply immediate proration.
- **USDT / bank transfer — the real work:**
  - *Upgrade:* server computes the prorated difference
    `(new_price − old_price) × remaining_days / 30`, rounded to cents. The
    member pays that amount on the same rail and submits a tx hash or transfer
    reference. Row lands `pending` with `change_kind='upgrade'`. An admin
    approves it in the console → `plan_code` switches immediately and
    `expires_at` is left unchanged.
  - *Downgrade:* no payment. Records `pending_plan_code` on the active row and
    takes effect at expiry. Cancellable until then.

### Backend

- Migration `0044` (shared with sub-project A) adds to `user_subscriptions`:
  `pending_plan_code TEXT`, `change_kind TEXT`. Mirror both in the idempotent
  `database.py` ALTER list — prod is MySQL, local is SQLite, and only the
  ALTER list runs on a fresh local DB.
- `GET  /api/subscriptions/history`
- `POST /api/subscriptions/change/preview` → `{kind, prorated_usd, effective}`
- `POST /api/subscriptions/downgrade` `{plan_code}`
- `POST /api/subscriptions/downgrade/cancel`
- Manual upgrade reuses `_submit_manual_payment` with the prorated amount.
- Admin console gains an approve-upgrade action alongside the existing approve.

### Deliberately unchanged

- `expires_at` stays the **only** field entitlements gates on.
- A downgrade that takes effect at renewal means the member keeps the higher
  limits until expiry. That is correct — they paid for the period.
- Enterprise is `contact_only`, so upgrading into it routes to `/contract`.
  There is no self-serve enterprise purchase.

## Testing

- pytest: proration maths including the boundary cases (same-day change, one
  day remaining, downgrade priced at zero); tier comparison by `sort_order`;
  downgrade scheduling and its cancellation; admin approval flipping
  `plan_code` while leaving `expires_at` alone; history paging.
- Watch the paging trap: do **not** LEFT JOIN plans into a paginated history
  query — fan-out duplicates rows and corrupts `LIMIT`/total. Page the base
  table and fetch plan names via `IN (…)`.
- Both dialects: any generated SQL must be checked on SQLite *and* MySQL.
  MySQL enforces FKs SQLite ignores, and rowcount means *changed* not *matched*.
- `test_billing.py` already covers the Stripe/PayPal webhook paths — extend,
  don't duplicate.
- ruff + pytest + tsc green before any push.

## Out of scope

- Turning Stripe or PayPal on in production (that is a keys-and-deploy step the
  owner controls, not a code change).
- Refunds.
- Any change to the entitlements gate.
