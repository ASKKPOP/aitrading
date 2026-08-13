# Handoff — Billing, trial, legal docs (session of 2026-08-05)

> **Status update 2026-08-12.** This file was written while the work was still
> uncommitted. Since then a **parallel session committed and pushed most of it to
> `origin/main`** — the backend trial code, the admin billing-ID fields, the tests, the
> rewritten Terms §8, the privacy-policy corrections and `docs/ops/` are all upstream.
> Verify against `origin/main` before trusting any "uncommitted" statement below.
> Prod deployment was not verified from this session.

Everything below describes work across two locations. Read this first, then check each
against `origin/main`.

---

## 1. Where the work lives

| Location | Branch | Contains |
|---|---|---|
| `~/Programming/src/ai-trade` (main checkout) | `feat/i18n-followups` | Marketing site + legal docs + all `docs/ops/*.html` |
| `~/Programming/src/ai-trade-trial` (git worktree) | `feat/trial-reminder` (off `origin/main`) | All backend + admin-console code |

**Why two.** `feat/i18n-followups` is ~153 commits behind `main` and has no
`routes_billing.py` / `billing_sync.py` at all — the billing feature does not exist on
that branch. Backend work therefore had to happen in a worktree off `origin/main`.
The marketing/legal edits were made in the main checkout because `marketing/` there was
already identical to `main`, so those changes apply cleanly either way.

**Neither branch is deployed.** Per the project rule, shipped work must reach prod
sooppiy.com — that has NOT happened for any of this.

```bash
# worktree, if it needs recreating
git worktree add -b feat/trial-reminder ~/Programming/src/ai-trade-trial origin/main
```

Note: `~/Programming/src/ai-trade-trial/service/frontend/node_modules` was copied in
(not symlinked) so `tsc` could run. It is gitignored. Do not symlink it —
see memory `deploy-gitignore-symlink-trap`.

---

## 2. What changed — main checkout (`feat/i18n-followups`)

```
M marketing/src/layouts/LegalLayout.astro     + /pricing nav & footer links, h3 style
M marketing/src/pages/index.astro             + /pricing nav & footer links
M marketing/src/pages/privacypolicy.astro     factual corrections (see below)
M marketing/src/pages/termsconditions.astro   §8 rewritten into 8.1–8.7
?? marketing/src/pages/pricing.astro          NEW public pricing + refund policy page
?? docs/ops/                                  NEW — 4 documents
```

### Privacy policy corrections
Removed a **false statement** that was live: *"the Service has no paid features at this
time."* Replaced with what is actually held (payment-provider customer/subscription ids,
plan, status, renewal date, card brand / last-4 / billing country) plus an explicit
"we do not receive or store your full card number". Also added the previously
**undisclosed broker/exchange API credentials** to collected data, and added payment
providers + connected brokers as recipients.

### Terms §8
Was three lines saying the service is free. Now 8.1 paid plans / 8.2 free trial /
8.3 automatic renewal / 8.4 immediate access + no refunds + exceptions / 8.5
cancellation / 8.6 data after access ends / 8.7 price changes. §9–17 renumbering
untouched.

> ⚠️ §8.2–8.4 still describe the **card-up-front** trial design, which the owner
> later reversed (see §4). **This text is now wrong and must be updated.**

### docs/ops/ (4 new documents)
- `payment-keys-setup.html` — step-by-step Stripe + PayPal key issuance, env vars,
  webhook events, DB seeding, verification, rotation. Includes the "what does your
  business do?" copy for Stripe onboarding.
- `service-rules.html` — the owner's three service rules. **Sections 1 and 3 describe
  the card-up-front trial and are now stale** (see §4).
- `legal-compliance-review.html` — 6-jurisdiction gap audit (US, CA, AU, VN, ID, TH). **Korea and Japan were
  removed on owner instruction 2026-08-05** — not target markets. See the "Markets excluded" section for the
  condition that exclusion depends on.
- `HANDOFF-billing-trial.md` — this file.

---

## 3. What changed — worktree (`feat/trial-reminder`)

```
M service/server/billing_sync.py              + grant_trial, trial_notice_tick, helpers
M service/server/email_i18n.py                + _TRIAL copy (2 kinds × 6 langs), trial_email*
M service/server/email_sender.py              + send_trial_notice_email
M service/server/routes_users.py              grant trial on email signup
M service/server/routes_oauth.py              grant trial on Google signup
M service/server/tasks.py                     trial_notice_tick on subscription_enforcer_loop
M service/server/routes_admin_manage.py       plan billing-id read/write + validation
M service/frontend/src/pages/AdminPage.tsx    billing-id column + edit buttons (6 langs)
M service/server/tests/test_user_api_settings.py  fixture moved to Pro (see below)
?? service/server/tests/test_trial_reminder.py         NEW 28 tests
?? service/server/tests/test_admin_plan_billing_ids.py NEW 17 tests
```

`routes_billing.py` is **byte-identical to `main`** — an earlier Stripe-native trial was
fully reverted when the requirement changed.

### 3a. Card-free 7-day trial

The trial is modelled as an **ordinary active subscription row**, not a new status:
`plan_code='junior'`, `method='trial'`, `auto_renew=0`, `expires_at=+7d`.

That single choice is why almost no new code was needed:

| Requirement | Satisfied by |
|---|---|
| 7 days free, no payment method | `billing_sync.grant_trial()` at both signup paths |
| Stop all daemons at day 7 | lazy expiry → `PLAN_LIMITS[None]` zeroes limits → existing `subscription_enforcer_tick` pauses every run |
| Always open the subscribe page | `App.tsx:521` already forces `/subscribe` when `subscription_status !== 'active'` |
| Email the user | new `billing_sync.trial_notice_tick()` |

`auto_renew=0` is load-bearing twice: nothing implies a recurring charge, and
`active_autorenew()` stays empty so a trialling member can subscribe early without a 409.

**Notices** ride `subscription_enforcer_loop` deliberately — the same sweep that pauses a
lapsed member's runs sends "your automation has stopped", so the two cannot drift apart.
Dedupe reuses `billing_events` (already `UNIQUE(provider,event_id)`) → exactly-once with
no migration; a failed send deletes its own marker so the next tick retries. A
`STALE_AFTER = 30 days` guard stops ancient rows generating mail on first run.

**Copy:** two kinds (`reminder` day-4, `ended` at expiry) × 6 languages. Neither may imply
a charge — there is no payment method. A test fails if affirmative charge language returns.

### 3b. Admin console: plan billing IDs

The gap that blocked go-live: `subscription_plans.stripe_price_id` / `paypal_plan_id`
could **only** be set by raw SQL on prod. The admin API neither returned nor accepted them
(classic "silent no-op until whitelisted" — see memory `stop-conditions-validator-strips-keys`).

Now: `GET /api/admin/plans` returns both; `PATCH /api/admin/plans/{code}` accepts both,
trims, allows `""` to clear, and **validates format** — `price_…` and `P-…`, rejecting
`prod_…` / `PROD-…` with a message naming the right prefix. That mistake would otherwise
only surface as a 502 at a member's first checkout. Admin UI has a Billing IDs column and
two edit buttons, localized to 6 languages.

---

## 4. ⚠️ Requirement reversal — read before touching the docs

The owner initially chose **card up front, auto-converts** (via AskUserQuestion), then
later reversed it: *"TRIAL is first 7 days don't need subscription payment (Stripe, PayPal)"*
and added *"after 7 days, stop all user daemon and services, email to user and always open
Subscription page."*

The **code** implements the final (card-free) design. The **documents do not**:

- `docs/ops/service-rules.html` §1 and §3 — describes card-up-front, Stripe
  `trial_period_days`, PayPal `TRIAL` billing cycle, once-per-person via card fingerprint.
- `docs/ops/payment-keys-setup.html` — the PayPal step 2.3 warning about creating the
  Junior plan with a trial cycle is now **obsolete**; the trial no longer involves any
  provider.
- `marketing/src/pages/termsconditions.astro` §8.2–8.4 — says a payment method is required
  and the subscription renews automatically after the trial. **Now false.**
- `marketing/src/pages/pricing.astro` — same problem in the "Free trial" section.

**These are user-facing false statements about billing. Fix before any deploy.**

---

## 5. Verification already done

- `test_trial_reminder.py` — 28 tests, TDD (red first). **10 mutants, all caught.**
- `test_admin_plan_billing_ids.py` — 17 tests, all asserted *through the API*.
- Full backend suite: **3368 passed**, 1360 subtests.
- `ruff check server/ --select F401,F811,F821,F841` → clean (CI's actual rule set; a bare
  `ruff check` shows ~571 pre-existing default-ruleset findings that CI does not run).
- `tsc --noEmit` → clean.
- Astro build → clean, 5 pages, `/pricing` generated, all routes 200.
- Emails rendered and read visually (en/ko), both kinds.
- Layout measured at 1280 and 375 — no page overflow; wide tables scroll inside their own containers.

### One real regression found and resolved
`test_user_api_settings.py` began 403-ing. **Correct new behavior, not a bug:** trial
members are Junior members, and Junior is pinned to the system-default AI
(`entitlements.py:227`). Previously a fresh account had *no* plan and slipped past that
junior-specific gate — unsubscribed users had more freedom than paying Junior users on
that setting. Fixture moved to Pro. If trial users should get more than Junior, it is a
one-line change to `billing_sync.TRIAL_PLAN_CODE`.

---

## 6. Outstanding — in priority order

1. **Fix the stale trial docs** (§4). User-facing false billing statements.
2. **Publish the legal entity** — company name, registration number, registered address,
   phone. Absent from both legal documents. Stripe onboarding will ask, and no data-protection
   regime in scope accepts an unnamed controller. *Only the owner has this.*
3. **Seed the billing IDs** — now doable in the admin console (§3b) instead of SQL. Stripe
   key is set; PayPal was in progress at session end.
4. **Financial-services licensing opinion**, or geo-restrict signup to markets with an
   opinion. The largest risk in the compliance review — regulated activity in all 6 target
   markets. Not a documentation problem.

5. **Geo-restriction is now load-bearing twice.** Korea and Japan are declared out of scope,
   but the platform ships ko/ja as first-class languages, guesses country at signup
   (`users.geo_country`), and has **no country blocking anywhere in the codebase**. These
   regimes attach obligations by conduct, not intent, so the exclusion is only real once
   signup/payment from those countries is actually refused. Same mechanism would serve
   item 4.
6. Refund/cancellation policy is published on `/pricing`, but Terms §15 (California law +
   AAA arbitration + class waiver) is **void against consumers in Quebec** and an
   unfair-terms risk in Australia. Needs counsel.
7. Not built, from the service-rules doc: checkout consent checkbox (immediate
   commencement + no-refund acknowledgment, recorded with timestamp), **"Export my data"**
   (rule 3.3 is unfair to publish without it), and the 6 site strings still saying "free".
8. PayPal has **no trial** — irrelevant now, since the trial no longer touches a provider.

---

## 7. Things that will bite you

- **Two worktrees, two branches.** Do not try to merge the backend work into
  `feat/i18n-followups` — that branch predates the billing feature entirely.
- The trial grant is **fail-soft** in both signup paths: a grant failure logs a warning and
  the member lands on `/subscribe`. Signup must never 500 after the account is committed.
- `grant_trial` opens its own connection, so it must stay **after** the signup commit+close,
  never inside that write transaction.
- Trial rows count in `has_prior_subscription`, so an expired trial does not earn a second
  one. That is deliberate.
- Preview/browser pane frequently reports `clientWidth: 0` when hidden — layout
  measurements are meaningless then. Resize to an explicit width first. See memory
  `browser-pane-hidden-tab-quirks`.
