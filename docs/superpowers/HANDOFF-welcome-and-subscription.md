# HANDOFF — welcome page + subscription management

**Status 2026-08-05 (continuation session): IMPLEMENTED, VERIFIED LOCALLY, NOT DEPLOYED.**
The design session's original handoff said "no code was written" — that is no longer true.
Everything below supersedes it. The two specs and two plans in this directory are the
design record; this file is the state.

## What the owner asked for (verbatim)

> 1. Checking welcome email ( include email phone verification ), and after
>    sign up must be go to welcome page that
>    1. Service introduce  2. How to use  3. infomation for subscription
>    4. Step by step guide — each contents must be visualization with each
>    part links — until do not show anymore ( do not show checkbox )
>
> 2. we need subscrion page from account page ( upgrade & downgrade ,
>    my subscription )

## Where everything lives

One stacked branch: **`feat/welcome-and-subscription`** =
`origin/main` + trial commit + specs + plans + 9 implementation commits.
Worktree: `~/Programming/src/ai-trade-trial` (frontend `node_modules` and
`marketing/node_modules` are real copies, kept so tsc/astro run — do not symlink).
The old `feat/trial-reminder` branch points at the trial commit inside this stack.
The main checkout (`feat/i18n-followups`) still carries the billing session's
uncommitted marketing edits — they were PORTED onto this branch and then fixed,
so the main-checkout copies are superseded and can be discarded after merge.

## What was built (all TDD, committed in order)

1. `feat(billing)` — the billing session's card-free trial + admin billing IDs,
   committed from its handoff (`docs/ops/HANDOFF-billing-trial.md`), rebased onto main.
2. `feat(welcome)` — `users.welcome_dismissed_at` (alembic **0044** + ALTER list + DDL),
   two-way `POST /api/users/welcome/dismiss`, `welcome_dismissed` on `/users/me`.
3. `refactor(settings)` — `PhoneVerifyCard` extracted from SettingsPage (one
   send-code/verify state machine; optional own phone input).
4. `feat(welcome)` — `/welcome` page (4 icon+numbered cards ×6 langs, live phone
   verify in card 4, dismissal checkbox), signup redirects (`authV2.tsx` :391/:756),
   once-per-session gate in App.tsx, profile-menu link.
5–8. `feat(subscriptions)` — `/change/preview` (+`_prorated_upgrade_usd`, clamped 0..full),
   `/change/upgrade` (server-priced pending row, `change_kind='upgrade'`),
   `/downgrade` + `/downgrade/cancel` (scheduled on the active row),
   `/history` (fan-out-safe paging). `get_subscription_state` now returns
   `pending_plan_code`/`change_kind`.
9. `feat(admin)` — approve on a `change_kind='upgrade'` row flips the plan and
   **keeps the original expires_at** (old row → superseded); console upgrade tag.
10. `feat(account)` — `/account/subscription` page (my subscription / ladder /
    history); Settings + /my-trading link "Manage subscription" there.
11. `docs(billing)` — the four stale trial docs rewritten card-free
    (terms §8, pricing.astro, service-rules §1/§5, payment-keys 2.3) + prod prices.

## Decisions locked by the owner (specs) + two amendments made here

Owner decisions unchanged: real dismissal checkbox; upgrade = pay difference now,
downgrade = at renewal; new `/account/subscription`; new `/welcome`, `/getting-started`
untouched; icon+numbered cards. Amendments this session (documented, not silently):

- **Trial rows are never prorated** — `method='trial'` refuses preview/upgrade/downgrade
  (the member paid $0; proration against list price would sell unbought credit).
  Trial members' Upgrade buttons route to `/subscribe` at full price.
- **Stripe/PayPal rows refuse the manual-change endpoints** — portal / change-plan
  are their flows; the page routes per method.

## Verification done (2026-08-05)

- pytest **3449 passed + 1360 subtests — twice**; ruff CI subset clean; tsc clean;
  astro build clean (5 pages).
- **44 new tests** (5 welcome + 39 subscription-change). **3 mutants injected, 3 caught**
  (dismissal write dropped; proration clamp dropped; approve-upgrade resetting expiry).
- Browser QA on the branch servers (worktree uvicorn :8002 + vite :3002, since stopped):
  fresh trial member auto-redirects to /welcome once per session; dismissal round-trips
  and survives fresh sessions; trial subscription page shows trial chip and full-price
  upgrade links; manual (usdt) member: Pro→Professional panel showed **$124.99**
  ((500−250)×15/30 at local seed prices), pending banner, admin approve flipped the plan
  with **expires_at unchanged**, history correct, downgrade scheduled and cancelled.
- Prod QA (spec A pass): plans API healthy; test account login + `/users/me` fine;
  `[Email] Sent … via SendGrid` confirmed live for the signup-code path (same sender
  the welcome email uses); **prod has ZERO verified phones** (the welcome page exists
  to fix exactly that). Unverifiable headless: inbox rendering per language, OAuth
  signup email, SMS handset arrival — nothing measured broken.

## Prod facts discovered (matter for deploy)

- **Owner repriced plans on prod: Pro $250→$119, Professional $500→$199.** The
  app pages read prices from the API (already correct); pricing.astro and
  service-rules.html were hardcoded and are now updated to $119/$199.
- **Stripe AND PayPal are live on prod** (`stripe_available: true`,
  `paypal_available: true`) — the "dormant rails" constraint in the B spec has aged;
  the manual rails remain first-class as designed.

## Outstanding — owner-gated (from `docs/ops/HANDOFF-billing-trial.md` §6, still true)

1. **Legal entity** (company name, registration number, address, phone) absent from
   the legal docs — mandatory for consumer sales in KR (전자상거래법) / JP (特定商取引法).
2. Financial-services licensing opinion, or geo-restrict signup.
3. Terms §15 (California law + AAA arbitration) needs counsel for Quebec/AU/KR.
4. Not built: checkout consent checkbox (recorded), "Export my data",
   the remaining "free" site strings (service-rules §4 items 2–6).
5. PayPal billing-plan IDs: seed via the admin console Billing IDs column
   (NO trial cycle on any plan — see payment-keys 2.3 as revised).

## Deploy note

Nothing here is deployed. Deploying this branch ships: the card-free trial,
the welcome page, subscription management, and the corrected legal/marketing
pages together — that is the intended unit. The marketing pages must be
rebuilt (`cd marketing && npm run build`) and published to the marketing
root(s); the SPA + backend follow the standard tarball deploy
(memory `sooppiy-deploy-procedure`, THREE static roots + restorecon).
