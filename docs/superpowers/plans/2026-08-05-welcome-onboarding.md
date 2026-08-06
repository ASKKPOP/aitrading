# Welcome Page + Signup Verification QA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New members land on a first-run `/welcome` page (4 icon+number cards, live phone-verify control, "do not show next time" checkbox) and the existing welcome email / phone-verify shipping in #242 gets verified on production.

**Architecture:** One new users column (`welcome_dismissed_at`), one endpoint (`POST /api/users/welcome/dismiss`), one new field on `/users/me`, one shared `PhoneVerifyCard` extracted from SettingsPage, one new `WelcomePage`, two redirect edits in authV2, one once-per-session gate effect in App.tsx.

**Tech Stack:** FastAPI + SQLite/MySQL (idempotent ALTER list + alembic 0044), React 18 + inline `tr()` i18n maps (6 langs).

**Spec:** `docs/superpowers/specs/2026-08-05-welcome-onboarding-design.md`. All owner decisions there are locked.

## Global Constraints

- Repo base: branch `feat/welcome-and-subscription`, worktree `~/Programming/src/ai-trade-trial` (`origin/main` + trial commit + specs commit). Never edit the stale main checkout.
- Every user-facing string: full 6-language `tr()` map (ko, en, ja, th, vi, id). English is the runtime fallback, never a translation target.
- Migration 0044 is **shared with sub-project B** — it carries `users.welcome_dismissed_at` AND `user_subscriptions.pending_plan_code` / `change_kind`. Mirror all three in the `database.py` idempotent ALTER list (prod=MySQL runs alembic; fresh local SQLite only runs the ALTER list).
- CI = `ruff check --select F401,F811,F821,F841` + full pytest + `tsc --noEmit`. All three green before any push.
- Trial interplay (from `docs/ops/HANDOFF-billing-trial.md`): a fresh signup now holds an ACTIVE trial subscription, so new members pass the membership gate and actually see `/welcome`. If the trial grant failed (fail-soft), the gate bounces them to `/subscribe` — acceptable, do not special-case.
- New-coverage rule: mutation-check the dismissal write (break it, watch a test fail) before reporting coverage.

---

### Task A1: Migration 0044 + dismiss endpoint + `/users/me` field

**Files:**
- Create: `service/server/alembic/versions/0044_welcome_and_plan_change.py`
- Modify: `service/server/database.py:1401-1403` (ALTER list tail)
- Modify: `service/server/routes_users.py` (`/users/me` ~697-713; new endpoint after `phone_verify` ~627)
- Test: `service/server/tests/test_welcome_page.py` (new)

**Interfaces:**
- Produces: `POST /api/users/welcome/dismiss` body `{"dismissed": bool=true}` → `{"success": true, "welcome_dismissed": bool}`; `/users/me` gains `'welcome_dismissed': bool`.
- Consumes: `_get_user_by_token`, `_extract_token` (already imported in routes_users.py).

- [ ] **Step 1: failing tests** — `test_welcome_page.py` with the repo's `_DbCase`-style setUp (tempdir SQLite + `database.init_database()` + `TestClient(create_app())`, user via `POST /api/users/register-request`? No — mint the user row + token directly like `test_admin_plan_billing_ids.py` mints admins). Tests: (1) unauth dismiss → 401; (2) dismiss stamps `welcome_dismissed_at` and `/users/me` flips `welcome_dismissed` false→true; (3) double-dismiss stays 200/true (idempotent); (4) `{"dismissed": false}` clears it; (5) `/users/me` reports false for a fresh user.
- [ ] **Step 2: run — must fail** (`welcome/dismiss` 404, `welcome_dismissed` KeyError).
- [ ] **Step 3: implement** — alembic 0044 (pattern-copy 0042: inspect columns, `ADD COLUMN welcome_dismissed_at VARCHAR(32) NULL` on users; `pending_plan_code VARCHAR(32) NULL` + `change_kind VARCHAR(16) NULL` on user_subscriptions; `down_revision="0043"`). database.py ALTER list: three `"ALTER TABLE … ADD COLUMN …"` strings. routes_users.py:

```python
    class WelcomeDismissRequest(BaseModel):
        dismissed: bool = True

    @app.post('/api/users/welcome/dismiss')
    async def welcome_dismiss(data: WelcomeDismissRequest,
                              authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')
        stamp = (datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                 if data.dismissed else None)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET welcome_dismissed_at = ? WHERE id = ?',
                           (stamp, user['id']))
            conn.commit()
        finally:
            conn.close()
        return {'success': True, 'welcome_dismissed': data.dismissed}
```

  `/users/me` response dict: add `'welcome_dismissed': bool(user.get('welcome_dismissed_at')),` after the `phone_verified` line.
- [ ] **Step 4: run — pass.** Then mutation check: comment out the UPDATE, confirm tests (2) and (4) fail, restore.
- [ ] **Step 5: commit** `feat(welcome): dismissal column, endpoint, /users/me flag`

### Task A2: Extract `PhoneVerifyCard` from SettingsPage

**Files:**
- Create: `service/frontend/src/components/PhoneVerifyCard.tsx`
- Modify: `service/frontend/src/pages/SettingsPage.tsx:73-78` (state), `:166-200` (handlers), `:487-531` (JSX block)

**Interfaces:**
- Produces: `<PhoneVerifyCard userToken={string} phone={string|undefined} onVerified={() => void} />` — when `phone` prop is given, the card verifies THAT number (no input of its own; Settings passes `alertPrefs.phone`); without it the card renders its own phone input (Welcome page use). Internally fetches `/users/me` for `phone`/`phone_verified`, drives `phone/send-code` + `phone/verify`, shows the verified badge, localized ×6 with the exact strings currently in SettingsPage 493-528.
- Consumes: `API_BASE`, `tr` — same imports SettingsPage uses; `errMessage` copied into the component (module-local, it is 9 lines).

- [ ] **Step 1:** build the component by MOVING the logic: state (`me/codeSent/verifyCode/phoneError/phoneBusy`), `fetchMe`, `sendVerificationCode` (posts the prop phone or its own input), `verifyPhoneCode` (calls `onVerified` after `fetchMe`), and the JSX from SettingsPage 487-531 verbatim plus an optional `<input type="tel">` when no `phone` prop.
- [ ] **Step 2:** SettingsPage: delete the moved state/handlers/JSX, render `<PhoneVerifyCard userToken={userToken} phone={alertPrefs.phone} onVerified={fetchMe} />` in their place (keep `me`/`fetchMe` in Settings — the email row at :123 still uses it).
- [ ] **Step 3:** `npx tsc --noEmit` green; no backend change so pytest untouched.
- [ ] **Step 4: commit** `refactor(settings): extract PhoneVerifyCard for reuse on /welcome`

### Task A3: WelcomePage + route + redirects + once-per-session gate

**Files:**
- Create: `service/frontend/src/pages/WelcomePage.tsx`
- Modify: `service/frontend/src/App.tsx` (lazy import ~54; route in authed shell ~591; PAGE_TITLES ~460; gate effect in AppRouter before the early returns ~439)
- Modify: `service/frontend/src/authV2.tsx:391` and `:756`
- Modify: `service/frontend/src/appChrome.tsx` (~200 label map, ~322 profile dropdown)

**Interfaces:**
- Consumes: `PhoneVerifyCard` (A2), `POST /api/users/welcome/dismiss` (A1), `GET /users/me.welcome_dismissed` (A1).

- [ ] **Step 1: WelcomePage.tsx** — layout copies GettingStartedPage's tokens (`V`, `wrap`, `cardS`, `kicker`, `h2S`). Four cards, each: number circle (GettingStarted :119 pattern) + glyph + headline + 2-3 lines + link row. Content per spec §The four cards: 1 service intro (`/about`, `/signals-board`, `/leaderboard`), 2 how to use (`/automation`, `/market`, `/positions`), 3 subscription info — the four tiers with `PLAN_NAMES` + price from `GET /api/subscriptions/plans` + `PLAN_FEATURE_BULLETS` first bullet, links `/account/subscription`, `/subscribe`, 4 step-by-step — live `<PhoneVerifyCard userToken …/>` as step 1, then region/language (`/settings`), plan (`/subscribe`), first run (`/automation`), links `/getting-started`, `/docs`. Footer: checkbox `welcome_dismissed` ← `/users/me` on mount; onChange POSTs `{dismissed: checked}`.
- [ ] **Step 2: App.tsx** — `const WelcomePage = lazy(() => import('./pages/WelcomePage'))`; route `<Route path="/welcome" element={userToken ? <WelcomePage userToken={userToken} /> : <Navigate to="/sign-in" replace />} />` next to `/settings`; PAGE_TITLES `'/welcome': 'Sooppiy · Welcome'`. Gate effect at the top of AppRouter (hooks before ALL early returns):

```tsx
  const navigate = useNavigate()
  useEffect(() => {
    if (!userToken || !userInfo) return
    if (userInfo.subscription_status !== 'active') return
    if (userInfo.welcome_dismissed) return
    if (sessionStorage.getItem('sooppiy_welcome_seen')) return
    sessionStorage.setItem('sooppiy_welcome_seen', '1')
    navigate('/welcome')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userToken, userInfo])
```

- [ ] **Step 3: authV2.tsx** — `:391` `navigate('/getting-started')` → `navigate('/welcome')`; `:756` `navigate(d.created ? '/getting-started' : '/my-trading')` → `navigate(d.created ? '/welcome' : '/my-trading')`. Comments updated to say welcome page.
- [ ] **Step 4: appChrome.tsx** — profile dropdown gains `<Link to="/welcome">` with 6-lang label (ko 웰컴 가이드 / en Welcome guide / ja ウェルカムガイド / th ไกด์ต้อนรับ / vi Hướng dẫn chào mừng / id Panduan selamat datang) above the settings item.
- [ ] **Step 5:** tsc green. Browser pass: sign in fresh (local seeded user, `welcome_dismissed` false) → redirected once to `/welcome`; navigate away and back (no re-redirect same session); tick checkbox → reload → no redirect; untick from profile menu → next session redirects again.
- [ ] **Step 6: commit** `feat(welcome): first-run /welcome page, redirects, once-per-session gate`

### Task A4: Production QA pass (spec §verification)

Not a code task — run against prod after deploy (or before, for the parts that exist in #242 already, which is all of the email/phone surface). Throwaway account per `verify-on-target-with-temp-credentials`; delete after. Checklist: welcome email arrives in signup language (en + ko spot checks), OAuth signup fires it, `phone/send-code` 200 + Twilio log line, anti-enum 409 for a foreign verified phone, daily cap + TTL behavior (do NOT burn the cap on prod — assert the counter rows only). SMS physical arrival is unverifiable without a handset — report as gap. Findings → report; fix only what is measurably broken.
