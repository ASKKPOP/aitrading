# Account Security: Phone Verification, SMS Password Reset, Welcome Email — Design

Date: 2026-08-05
Status: approved by owner (design dialogue, 2026-08-05)
Sub-project: B of 2 (A = Stripe/PayPal auto-renew billing — shipped 2026-08-05, PR #236)

## Goal

1. Members can verify a phone number from the account (Settings) page.
2. Password reset works by SMS as well as email, from the sign-in page.
3. Every new signup receives a localized welcome email.
4. The account page shows verification state: email (always verified at
   signup — surface it) and phone (verify / re-verify flow).
5. (Owner addition, 2026-08-05 mid-design) Signup carries an explicit
   language choice, and ALL content follows it — the signup UI itself, the
   verification email, the stored `users.lang` (which already drives every
   email/SMS/notification/AI-content language), and the welcome email.

Decisions made with the owner:

- SMS **alert** delivery behavior is unchanged — verification is NOT a new
  gate on alerts (existing members' SMS must not silently stop). Verification
  gates password-reset-by-phone and the verified badge only.
- Twilio prod credentials already exist (the alert rail is live; A2P approved).
- Same flow as sub-project A: worktree → TDD tasks → per-task review → final
  review → PR → CI → merge → prod deploy → prod verification.

## Current state (what exists)

- `alerts._send_sms(to_number, body) -> bool` — Twilio REST, env-gated
  (TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER), returns False unconfigured.
- Phone number today: `user_api_settings` target='alerts' `config_json.phone`
  (+ `sms_consent`, `sms_consent_at`) — entered on SettingsPage, UNVERIFIED.
  `alerts._alert_prefs` reads it for SMS alert delivery.
- Code store (routes_users.py `_store_code`/`_load_code`/`_delete_code` +
  RouteContext): namespaced keys, 60s resend cooldown
  (CODE_RESEND_COOLDOWN_SECONDS), 5-min expiry, MAX_CODE_ATTEMPTS,
  anti-enumeration pattern proven on `forgot-password` (store even when no
  account matches; generic response).
- Email: `email_i18n.py` (_CHROME + _COPY, 6 langs en/ko/ja/th/vi/id;
  purposes 'signup'/'reset'/'invite'), `email_sender.py` (Resend primary,
  SendGrid fallback — prod uses SendGrid).
- Frontend: `authV2.tsx` ForgotPasswordPage (email 2-step flow, ~line 450);
  SettingsPage alerts card with phone input + A2P consent checkbox
  (~line 340; consent disclosure text is registration-bound — DO NOT ALTER).
- `users` has no phone column. `/api/users/me` returns id/email/wallet/points/
  status/lang/region/timezone/locale_confirmed/subscription*.

## 1. Schema (alembic 0042 + SQLite DDL in database.py)

- `users.phone TEXT NULL` (E.164), `users.phone_verified_at TEXT NULL`.
- UNIQUE index `idx_users_phone` on `users(phone)` — reset-by-phone must map
  to exactly one account. (SQLite and MySQL both permit multiple NULLs in a
  unique index; members without phones are unaffected.)

## 2. Phone verification (authenticated)

New module `sms_i18n.py`: `verification_sms(code, lang)` and
`reset_sms(code, lang)` — short localized bodies, 6 langs, code + 5-minute
note, "never share" line.

- `POST /api/users/phone/send-code {phone}` (auth):
  - validate E.164 (`^\+[1-9]\d{7,14}$`) → 400 otherwise;
  - 409 if the phone is already verified by a DIFFERENT user
    (`SELECT id FROM users WHERE phone = ? AND phone_verified_at IS NOT NULL
    AND id != ?`);
  - code store namespace `phone:{user_id}` (cooldown/expiry/attempts identical
    to email codes); the pending phone is stored inside the code payload;
  - send via `alerts._send_sms(phone, sms_i18n.verification_sms(code, lang))`;
    unconfigured Twilio → log the code (local dev), still return success.
- `POST /api/users/phone/verify {code}` (auth):
  - standard code checks (expiry, attempts, hmac compare);
  - re-check uniqueness (409 if another user verified it meanwhile);
  - `UPDATE users SET phone = ?, phone_verified_at = <now> WHERE id = ?`;
  - sync the alerts settings target: update `config_json.phone` (preserving
    other keys) if the row exists, else insert an enabled row with
    `{"phone": ...}` — SMS alerts still fire only per the member's
    notification switches + consent, unchanged;
  - delete the code.
- Changing the number: send-code with a new phone then verify replaces
  `users.phone` and stamps a fresh `phone_verified_at`. The frontend treats
  "settings phone ≠ verified users.phone" as unverified.
- `/api/users/me` gains `'phone': user.get('phone')`,
  `'phone_verified': bool(user.get('phone_verified_at'))`.

## 2b. Signup language choice

- `UserSendCodeRequest` and `UserRegisterRequest` gain optional
  `lang: str | None`. Validation: accepted only when in the supported set
  (`analysis_agents.normalize_lang` — LANG_NAMES is the single language
  list); anything else falls back to today's geo/Accept-Language guess
  (`resolve_signup_lang` / `resolve_signup_locale`), which stays the
  behavior for API clients that don't send `lang`.
- `send-code` uses the chosen lang for the verification email;
  `register` stores it in `users.lang` (geo_country still recorded
  separately as the guess it is). The welcome email (section 4) then uses
  `users.lang` naturally, as does every existing localized surface.
- Frontend SignUpPage: a language `<select>` on the first step, defaulting
  to the current UI language; changing it calls `setLanguage()` immediately
  so the signup flow itself flips language on the spot; the chosen value is
  sent with both `send-code` and `register`.

## 3. SMS password reset (unauthenticated, sign-in page)

Mirrors of the email pair, same anti-enumeration discipline:

- `POST /api/users/forgot-password-sms {phone}`:
  - store code under `smsreset:{phone}` even when no verified account
    matches (cooldown probing reveals nothing); generic success response;
  - only send the SMS when a user exists with
    `phone = ? AND phone_verified_at IS NOT NULL` (lang from that user).
- `POST /api/users/reset-password-sms {phone, code, new_password}`:
  - code checks identical to email reset; on success update `password_hash`
    and `DELETE FROM user_tokens` (sign out everywhere); generic 400 when the
    phone matches no verified account.

## 4. Welcome email

- `email_i18n.welcome_email(lang) -> (subject, html)` +
  `welcome_email_text(lang)` — 6 langs, existing chrome; content: welcome
  heading, one-paragraph what-Sooppiy-is, three first steps (choose a plan,
  explore the market/terminal, set notification preferences), sign-in link
  to https://sooppiy.com, standard footer. NO placeholder variables beyond
  what f-strings safely provide (static text + link).
- `email_sender.send_welcome_email(to_email, lang) -> bool` — same
  Resend→SendGrid→no-op chain as the verification sender.
- Hook: in `user_register`, AFTER the signup transaction commits and the
  token is created, `asyncio.create_task`-free fire-and-forget via
  `asyncio.to_thread(...)` wrapped in try/except — a mail failure must never
  block or fail the signup response. Send failure logs a warning only.

## 5. Account page UI (SettingsPage) + sign-in page

- SettingsPage account/alerts area:
  - Email row: address + `✓ Verified` badge (static — email is always
    code-verified at signup).
  - Phone block (existing input + consent stays byte-identical on the
    consent disclosure): after Save, if the saved phone is not the verified
    one, show `Not verified` + "Send verification code" button → 6-digit
    input + Verify button → on success `✓ Verified` badge. Status read from
    `/api/users/me` (`phone`, `phone_verified`): verified iff
    `phone_verified && me.phone === alertPrefs.phone`.
- ForgotPasswordPage (authV2.tsx): method toggle Email | Phone (default
  Email). Phone mode posts to the `-sms` endpoints with the E.164 input;
  step flow identical to email. All new strings in 6 languages via `tr()`.

## 6. Config & dependencies

None new. Twilio + SendGrid env already on prod. Tests rely on conftest
blanking TWILIO_*/SENDGRID_* (already done).

## 7. Testing

- New `tests/test_account_security.py` (unittest + TestClient + temp SQLite,
  external HTTP mocked — patch `routes_users._send_sms` where imported /
  `alerts._send_sms`, and `email_sender` internals):
  - phone send-code: E.164 validation, cooldown 429, 409 taken-by-other,
    SMS body contains code + correct language, dev fallback when
    unconfigured;
  - verify: success writes users.phone + verified_at + alerts config sync
    (existing row preserved keys; missing row created), wrong code 400,
    attempt cap 429, uniqueness re-check 409;
  - /users/me carries phone + phone_verified;
  - forgot-password-sms: cooldown probing safe (same generic response with
    and without account), SMS sent only for verified phone;
  - reset-password-sms: full happy path (old sessions die, new password
    logs in), wrong code, unverified phone → generic 400;
  - welcome email: register triggers exactly one send with the signup lang;
    sender failure does not fail registration (response still 200 + token).
- ruff (CI scope) + full pytest ×2 + tsc + vite build; mutation spot-checks
  (disable uniqueness check → test fails; disable session-kill on SMS reset
  → test fails).

## Out of scope

- Making phone verification a requirement for SMS alerts or any entitlement.
- 2FA / TOTP login.
- Email change flow (email remains immutable post-signup).
- Subscription/billing changes (sub-project A shipped separately).
