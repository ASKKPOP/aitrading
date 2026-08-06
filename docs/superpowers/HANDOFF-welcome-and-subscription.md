# HANDOFF — welcome page + subscription management

Written 2026-08-05, at the end of a design session, because the owner rotates
Claude accounts and the assistant's own memory does not survive that. **This
file and the two specs are the authority. Nothing about this work lives
anywhere else.**

## What the owner asked for

Verbatim, in two numbered items:

> 1. Checking welcome email ( include email phone verification ), and after
>    sign up must be go to welcome page that
>    1. Service introduce
>    2. How to use
>    3. infomation for subscription
>    4. Step by step guide
>    Each contents must be visualization with each part links
>    until do not show anymore ( do not show checkbox )
>
> 2. we need subscrion page from account page ( upgrade & downgrade ,
>    my subscription )

## Where this got to

A design dialogue ran to completion. Both designs are written and committed:

- `docs/superpowers/specs/2026-08-05-welcome-onboarding-design.md` (sub-project A)
- `docs/superpowers/specs/2026-08-05-subscription-management-design.md` (sub-project B)

**No code was written.** **The designs are not yet approved** — the session
ended before the owner said yes or no.

## Exact next step

Ask the owner to review the two spec files and approve or amend them. On
approval, write implementation plans into `docs/superpowers/plans/` (one per
sub-project) and execute A first — B's `/account/subscription` route is linked
from A's welcome card 3, so building A first leaves one dangling link for a
short window, whereas building B first leaves none.

## Decisions already locked (do not silently re-open)

Each was chosen by the owner from options presented:

| Question | Owner's answer |
|---|---|
| What "checking welcome email" means | Verify the existing flow **and** put the phone-verify prompt on the new welcome page. Signup itself is untouched. |
| How the welcome page stops appearing | A real **"do not show next time" checkbox**. The request line "( do not show checkbox )" was first misread as "use no checkbox"; the owner corrected it. |
| Upgrade / downgrade semantics | **Upgrade = pay the difference now. Downgrade = takes effect at renewal.** |
| Where the subscription page lives | New `/account/subscription`, linked from both `/settings` and `/my-trading`. |
| Relationship to `/getting-started` | Build a **new** `/welcome`; `/getting-started` survives unchanged as the deep reference. |
| Visual treatment of the 4 sections | **Icon + numbered step cards** — not SVG diagrams, not screenshots. |

## Two things the next session must not trip over

1. **The repo checkout is stale and dirty.**
   `~/Programming/src/ai-trade` was on `feat/i18n-followups`, **155 commits
   behind `origin/main`**, carrying uncommitted changes from other parallel
   sessions. All of this work was done in a clean worktree off `origin/main`
   and committed on the branch **`feat/welcome-and-subscription`**, based on
   `29018da`. Start from that branch, not from the main checkout. It is a local
   branch — it has not been pushed to `origin`.

2. **The constraint that shapes sub-project B.** Stripe and PayPal auto-renew
   are live in code but **dormant on production** — `PAYPAL_UI_ENABLED`
   defaults to `false` and Stripe needs `STRIPE_SECRET_KEY`. So essentially
   every real subscriber today is on the manual USDT / bank rail, which makes
   the proration + admin-approval path the *main* path, not an edge case. This
   was flagged to the owner and the scope reflects it.

## What already exists (so nothing gets rebuilt)

Verified by reading the code, not assumed:

- Welcome email — **exists**, six languages, fired on email signup
  (`routes_users.py:318`) and OAuth first-signup.
- Phone verification — **exists as API** (`/api/users/phone/send-code`,
  `/api/users/phone/verify`), but the UI is buried inside SettingsPage's SMS
  notification preferences and is not part of signup.
- Post-signup redirect — already goes to `/getting-started`
  (`authV2.tsx:391`, `authV2.tsx:756`).
- `/subscribe` — already has "my subscription", the Stripe Customer Portal
  button, PayPal `change-plan`, and cancel-auto-renew.
- Missing entirely: any downgrade path, and any first-run welcome experience.
