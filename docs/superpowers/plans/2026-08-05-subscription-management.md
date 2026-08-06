# Subscription Management (`/account/subscription`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A member sees their subscription and changes it from `/account/subscription` on whichever rail they paid with: Stripe → portal, PayPal → change-plan, USDT/bank → prorated upgrade with admin approval + scheduled downgrade at renewal.

**Architecture:** Two columns on `user_subscriptions` (`pending_plan_code`, `change_kind` — already in shared migration 0044 from sub-project A). Five member endpoints in `routes_subscriptions.py` (preview / upgrade / downgrade / downgrade-cancel / history), an upgrade-aware branch in the existing admin approve, one new `SubscriptionPage`, link swaps in Settings + MyTrading.

**Tech Stack:** FastAPI, SQLite+MySQL both-dialect SQL, React 18, `tr()` maps ×6.

**Spec:** `docs/superpowers/specs/2026-08-05-subscription-management-design.md` (owner decisions locked).

## Global Constraints

- Same branch/worktree/CI/i18n rules as the A plan.
- **Trial amendment** (the specs predate the trial feature — `docs/ops/HANDOFF-billing-trial.md`): a `method='trial'` subscription must NEVER be prorated — the member paid $0, so `(new − old) × remaining/30` against junior's $60 would sell them credit they never bought. Preview / upgrade / downgrade all refuse trial rows; the frontend routes trial members' Upgrade buttons to `/subscribe` (full-price first purchase — the flow already handles a trialling member, `auto_renew=0` keeps checkout from 409-ing).
- Proration uses PLAN prices (`subscription_plans.price_usd`), never `amount_usd` paid (comped members upgrade at fair price).
- `expires_at` remains the only entitlements gate; an approved upgrade must NOT move it.
- History paging: page the base table, names via `IN (…)` — the LEFT-JOIN fan-out trap (`join-fanout-breaks-paging`).
- All change endpoints refuse `method in ('stripe','paypal')` rows — those rails already have provider-native flows (portal / change-plan).

---

### Task B1: State exposure + proration + preview  (TDD file `test_subscription_change.py`)

**Files:**
- Modify: `service/server/routes_subscriptions.py` (`get_subscription_state` SELECT ~176-185; new helpers + endpoint after `subscription_me` ~254)
- Test: `service/server/tests/test_subscription_change.py` (new)

**Interfaces:**
- Produces: `get_subscription_state` rows now carry `pending_plan_code`, `change_kind`. `_tier_sort(cursor, code) -> int`; `_prorated_upgrade_usd(new_price, old_price, expires_at_iso, now) -> float` (pure, testable). `POST /api/subscriptions/change/preview` `{plan_code}` → `{kind: 'upgrade'|'downgrade', prorated_usd: float, effective: 'immediate'|'at_renewal', current_plan, target_plan, expires_at}`.
- Errors: 401 no auth; 404 no active subscription; 404 unknown plan; 400 contact_only ("Enterprise plans use the contract form" — `_load_plan` already does); 400 same plan; 400 trial (`Trial members subscribe at full price on the subscribe page`); 400 stripe/paypal (`Use the Stripe portal` / `Use PayPal change-plan`).

- [ ] **Step 1: failing tests** — proration math: pro→professional 15 of 30 days left = 125.0; 1 day = 8.33; 0 days (expired edge, clamps 0) = 0.0; full 30 = 250.0; rounding to cents. Preview API: junior→pro upgrade kind+amount; pro→junior downgrade `prorated_usd == 0.0`, `effective == 'at_renewal'`; same-plan 400; trial 400; stripe-method 400; no-sub 404. Fixtures mint user+token rows directly (pattern of `test_trial_reminder._mk_user` + a `user_tokens` insert), subscription rows inserted with explicit `expires_at`.
- [ ] **Step 2: run — fails** (endpoint 404).
- [ ] **Step 3: implement**

```python
def _prorated_upgrade_usd(new_price: float, old_price: float,
                          expires_at: str, now: datetime | None = None) -> float:
    """Pay-the-difference-now price of an immediate upgrade: the plan-price
    delta scaled by the unexpired fraction of the 30-day period. Clamped at 0
    so an expired row (or a mis-ordered pair) can never produce a credit."""
    now = now or _now()
    try:
        ends = datetime.fromisoformat((expires_at or "").replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    remaining_days = max(0.0, (ends - now).total_seconds() / 86400.0)
    return round(max(0.0, new_price - old_price) * min(remaining_days, SUBSCRIPTION_DAYS) / SUBSCRIPTION_DAYS, 2)
```

  `_change_context(cursor, user)` shared guard: loads state, 404s none/pending-only, 400s trial (`method == billing_sync.TRIAL_METHOD`), 400s stripe/paypal, loads current+target plans with `sort_order` (`SELECT code, name, price_usd, contact_only, sort_order FROM subscription_plans WHERE code = ?`), 400s same-plan. Preview returns downgrade (`target.sort < current.sort`) as `{kind:'downgrade', prorated_usd: 0.0, effective:'at_renewal'}`, upgrade as `{kind:'upgrade', prorated_usd: _prorated_upgrade_usd(...), effective:'immediate'}`.
- [ ] **Step 4: run — pass.** **Step 5: commit** `feat(subscriptions): change preview + proration (trial-aware)`

### Task B2: Manual prorated upgrade submit

**Interfaces:** `POST /api/subscriptions/change/upgrade` `{plan_code, method: 'usdt'|'bank', reference}` → `{ok, status:'pending', amount_usd}`. Row: `plan_code=target, status='pending', method, reference, amount_usd=<server-computed prorated>, change_kind='upgrade'`. Reuses `_submit_manual_payment` via two new optional params `amount_override: float | None = None, change_kind: str | None = None` (INSERT gains the `change_kind` column; `amount_usd = amount_override if amount_override is not None else plan price`). USDT availability check mirrors `/subscriptions/usdt` (503 when unconfigured); method whitelist 400 otherwise. Duplicate-pending 400 preserved. Admin alert fires with `status_note="pending upgrade — needs approval"`.

- [ ] Tests first: creates the pending row with server-computed amount (client-sent amounts impossible — there is no amount field); duplicate pending 400; trial 400; downgrade-direction target 400 (`Use the downgrade endpoint`); empty reference 400. Run red → implement → green.
- [ ] **Commit** `feat(subscriptions): manual prorated upgrade lands as pending change_kind=upgrade`

### Task B3: Downgrade schedule + cancel

**Interfaces:** `POST /api/subscriptions/downgrade` `{plan_code}` → stamps `pending_plan_code=target, change_kind='downgrade'` on the ACTIVE row → `{ok, pending_plan_code, effective_at: expires_at}`. `POST /api/subscriptions/downgrade/cancel` clears both (only when `change_kind='downgrade'`) → `{ok}`. Guards from `_change_context` (active manual-rail row, lower tier only). `subscriptions/me` now shows the schedule via B1's SELECT.

- [ ] Tests first: schedule sets both columns and `me` carries them; upgrade-direction 400; cancel clears; cancel with nothing scheduled stays 200 `{ok: true}` (idempotent); trial/stripe 400. Red → implement → green.
- [ ] **Commit** `feat(subscriptions): scheduled downgrade at renewal + cancel`

### Task B4: History endpoint

**Interfaces:** `GET /api/subscriptions/history?limit=20&offset=0` → `{items: [{id, plan_code, plan_name, status, method, amount_usd, started_at, expires_at, created_at, change_kind, pending_plan_code}], total}`. Base-table pagination (`WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?`), then one `SELECT code, name FROM subscription_plans WHERE code IN (…)` to decorate names. limit clamped 1..100.

- [ ] Tests first: N rows → correct page slices + total; names present; another member's rows never leak; 401 unauth. Red → implement → green. **Commit** `feat(subscriptions): member subscription history (fan-out-safe paging)`

### Task B5: Admin approve-upgrade + console tag

**Files:**
- Modify: `service/server/routes_admin_manage.py` (approve `:597-628`; list SELECT `:533-535`)
- Modify: `service/frontend/src/pages/AdminPage.tsx` (subscriptions table plan cell ~`:1046`)
- Test: extend `test_subscription_change.py` (admin fixture pattern from `test_admin_plan_billing_ids.py`)

**Interfaces:** existing `POST /api/admin/subscriptions/{id}/approve`: when the pending row has `change_kind='upgrade'` → find the member's current ACTIVE row; 400 `"Original subscription expired — reject this and let the member subscribe normally"` when none; else pending row becomes `status='active', started_at=now, expires_at=<old row's expires_at>, decided_by/at, note`, old row → `'superseded'`. Audit action `subscription.approve_upgrade`. Admin list SELECT adds `s.change_kind, s.pending_plan_code`; AdminPage plan cell renders `s.plan_code` plus, when `s.change_kind === 'upgrade'`, an `⬆ upgrade` chip (6-lang `tr()` map: ko 업그레이드 / en upgrade / ja アップグレード / th อัปเกรด / vi nâng cấp / id peningkatan).

- [ ] Tests first (through the API): approve-upgrade flips member to the new plan while `expires_at` of the state equals the OLD row's value to the second; old row superseded; entitlements-visible plan changes (assert via `GET /api/subscriptions/me`); approve-upgrade with the original already expired → 400 and nothing changes; a plain pending row (no change_kind) still gets the legacy `now+30d`. Red → implement → green.
- [ ] **Commit** `feat(admin): approve a prorated upgrade — plan flips, expires_at stays`

### Task B6: SubscriptionPage + links

**Files:**
- Create: `service/frontend/src/pages/SubscriptionPage.tsx`
- Modify: `service/frontend/src/App.tsx` (lazy import, route `/account/subscription` beside `/settings`, PAGE_TITLES `'Sooppiy · Subscription'`)
- Modify: `service/frontend/src/pages/SettingsPage.tsx:366-370` (Membership card link → `/account/subscription`, label "Manage subscription" ko 구독 관리 — keep `/subscribe` untouched elsewhere)
- Modify: `service/frontend/src/myTradingPage.tsx:110-113` (same swap)

**Interfaces:** consumes `/subscriptions/me`, `/subscriptions/plans`, `/subscriptions/history`, `/subscriptions/change/preview`, `/subscriptions/change/upgrade`, `/subscriptions/downgrade`, `/subscriptions/downgrade/cancel`, `/subscriptions/stripe/portal`, `/subscriptions/paypal/change-plan`, `PLAN_NAMES`/`PLAN_FEATURE_BULLETS`.

Page structure (SubscribePage's `card`/`primaryBtn`/`ghostBtn` style tokens):
1. **My subscription** — plan name+price, status chip, method, started/expires dates, auto-renew / cancels-on line (SubscribePage 336-341 pattern), trial notice when `method==='trial'`, scheduled-downgrade banner (`pending_plan_code` + effective date + cancel button).
2. **Plan ladder** — plans sorted by API order; current marked ✓; each other plan gets ONE action decided by `sort_order` vs current and by method:
   - `trial` → Upgrade = `<Link to="/subscribe">` (full price note), no Downgrade.
   - `stripe` → both directions → `POST /subscriptions/stripe/portal` redirect.
   - `paypal` → both → `POST /subscriptions/paypal/change-plan` (copy: applies next billing cycle).
   - `usdt`/`bank`/`manual` → Upgrade opens inline panel: preview amount headline, method pick (USDT shown only when `usdt_available`; bank when `bank_transfer_info`), address/QR-free compact layout (address `<code>` + copy + tx-hash input, or bank `<pre>` + reference input), submit → pending banner; Downgrade shows confirm (effective date) → schedule.
   - `enterprise` (contact_only) → `<Link to="/contract">`.
3. **History** — table (id date plan method amount status), Load-more paging via offset.
- [ ] tsc green; browser pass on the seeded local DB: manual-active member sees ladder with preview amounts; trial member's upgrade routes to /subscribe; scheduled downgrade shows + cancels; pending-upgrade banner after submit; history pages.
- [ ] **Commit** `feat(account): /account/subscription — manage, change, history`
