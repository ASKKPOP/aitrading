# Welcome Page + Signup Verification QA — Design

Date: 2026-08-05
Status: **DESIGN PRESENTED, NOT YET APPROVED** — owner rotated Claude accounts
mid-dialogue; approval is the first thing the next session must ask for.
Sub-project: A of 2 (B = `2026-08-05-subscription-management-design.md`)

## Goal

A new members land on a first-run `/welcome` page that explains the product in
four visual sections, prompts phone verification, and stops appearing once the
member ticks "don't show this again". Separately, verify on production that the
welcome email and the phone-verification API — both already shipped in #242 —
actually work, and fix only what is measurably broken.

## Owner decisions (from the design dialogue, 2026-08-05)

Each of these was chosen by the owner from options presented. They are not
assumptions — do not re-litigate them without asking.

1. **Scope of "checking welcome email":** verify the existing flow AND put the
   phone-verify prompt on the new welcome page. Signup itself stays untouched —
   nobody is blocked from entering the product by an unverified phone.
2. **Dismissal:** a real **checkbox** — "do not show next time welcome page".
   (An earlier reading of the request as "no checkbox" was wrong and the owner
   corrected it. The checkbox is explicitly wanted.)
3. **Relationship to `/getting-started`:** build a NEW `/welcome` page.
   `/getting-started` survives unchanged as the deep reference and is linked
   from welcome section 4.
4. **Visual treatment:** **icon + numbered step cards** — a large glyph, a
   headline, 2–3 lines of copy, and that section's links. Not SVG diagrams, not
   screenshots. Matches the existing card style in GettingStartedPage/Settings.

## Current state (verified against `origin/main` @ 5c31681, rebased onto
29018da — the only intervening commit was an unrelated P&L audit module)

The repo checkout at `~/Programming/src/ai-trade` was on `feat/i18n-followups`,
**155 commits behind main**, with unrelated uncommitted changes from parallel
sessions. All findings below come from a clean worktree off `origin/main`.

- **Welcome email exists.** `email_i18n.welcome_email(lang)` /
  `welcome_email_text(lang)` (6 languages); sent from `routes_users.py:318` on
  email signup and from `routes_oauth.py` on OAuth first-signup (off the event
  loop via `asyncio.to_thread`).
- **Phone verification exists as API only.** `POST /api/users/phone/send-code`,
  `POST /api/users/phone/verify` in `routes_users.py` (~495–616), with
  anti-enumeration 409s, per-user cooldown, and daily caps. Columns
  `users.phone` / `users.phone_verified_at` (migration `0042`).
- **Phone-verify UI is buried.** It lives inside `SettingsPage.tsx`
  (~lines 74, 123, 170, 187, 488) as part of the SMS *notification* preferences.
  It is not part of signup and a new member will never find it.
- **Signup already redirects to `/getting-started`** — `authV2.tsx:391`
  (email signup) and `authV2.tsx:756` (OAuth, `created` branch).
- **`/getting-started`** (`pages/GettingStartedPage.tsx`, 187 lines) is a
  permanent nav page: it builds its content from `buildNavSections` plus each
  page's own localized guide summary. No first-run behaviour, no dismissal.

## Design

### Route and gate

New authenticated route `/welcome`.

- Signup redirects here instead of `/getting-started` — both `authV2.tsx:391`
  and `authV2.tsx:756`.
- On every sign-in, if `users.welcome_dismissed_at IS NULL`, the app redirects
  to `/welcome` **once per session**. Once-per-session matters: a redirect on
  every navigation would trap the member on the page.
- The checkbox posts to `POST /api/users/welcome/dismiss`, which stamps
  `welcome_dismissed_at`. After that the page never auto-appears.
- It stays reachable from the profile menu forever.

### The four cards

Each card: number + glyph + headline + 2–3 lines + its own links.

| # | Section | Links out to |
|---|---------|--------------|
| 1 | Service introduction — agents publish signals, followers mirror them, the simulated ledger is the default | `/about`, `/signals-board`, `/leaderboard` |
| 2 | How to use — the signal → automation → position loop | `/automation`, `/market`, `/positions` |
| 3 | Subscription information — the four tiers with price and the real limits (concurrent runs, max bet) from `entitlements.py` | `/account/subscription` (sub-project B), `/subscribe` |
| 4 | Step-by-step guide — verify phone → set region + language → choose a plan → start the first run | `/getting-started`, `/docs` |

### Phone verification on the page

Card 4 step 1 is a **live** control, not a link. Extract the existing
send-code/verify control out of `SettingsPage.tsx` into a shared
`components/PhoneVerifyCard.tsx` and consume it from both places, so there is
one implementation rather than two drifting copies. This refactor is in scope
precisely because the alternative is duplicating ~60 lines of request state.

The card reads `phone_verified` from `GET /api/users/me` (already returned,
`routes_users.py:699`).

### Localization

All copy in the six supported languages via `tr()`, exactly like every other
page. English is the runtime fallback; it is never a translation *target*.

### Backend

- Migration `0044` (shared with sub-project B) + the `database.py` idempotent
  ALTER list: `users.welcome_dismissed_at TEXT`.
- `GET /api/users/me` gains `welcome_dismissed: bool`.
- `POST /api/users/welcome/dismiss` — auth required, idempotent.

## The verification pass ("checking welcome email")

Run against **production**, with a throwaway account created and then deleted
(the established pattern; `info@askkpop.com` is the standing prod test account).
Report findings plainly whether or not anything is broken; fix only what is
actually broken.

1. Email signup → welcome email arrives, in the **signup language** (spot-check
   at minimum `en` and `ko`; the signup language is supposed to govern all
   content per #242).
2. OAuth signup → welcome email fires too, and does not block the callback.
3. `phone/send-code` → SMS arrives; `phone/verify` accepts the code and stamps
   `phone_verified_at`.
4. The anti-enumeration path: a phone already verified by another account
   returns the throttled 409 and does **not** leak registration state.
5. The daily send cap trips at the configured limit and the quota key expires
   (the 86400 TTL trap from #242).

## Testing

- pytest: dismiss endpoint (auth required, idempotent, sets the column);
  `/users/me` reports `welcome_dismissed`; signup still sends the welcome email.
- Mutation check: break the dismissal write and confirm a test fails. A brief
  or flag that no test actually exercises is a silent no-op — this repo has been
  bitten by exactly that.
- tsc + ruff green before any push (CI runs both).

## Out of scope

- Changing the signup form itself.
- Retiring or restyling `/getting-started`.
- Any change to `entitlements.py`.
