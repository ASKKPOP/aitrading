# Owner fill-in sheet — the four blocked items

**Created 2026-08-06. Status: SAMPLE ONLY — nothing here is published yet.**

Four items in `docs/superpowers/HANDOFF-welcome-and-subscription.md` §Outstanding
are blocked on facts only the owner has. This sheet is the form: fill the
`⬜ FILL` fields in Part 1 and Part 4, decide Part 2, and hand Part 3 to counsel.
Every sample below reads its values from the Part 1 field table — fill once,
and I wire it into the pages.

**Two of these are not mine to write.** Part 2 (licensing opinion) and Part 3
(§15 arbitration) require a lawyer's judgment; what I give you there is a brief
to hand counsel and a scaffold for them to mark up — not legal advice, and not
publishable as-is. Parts 1 and 4 are pure data entry and I can ship them the
day they are filled.

---

## Part 1 — Legal entity

### 1a. The field table (fill this; everything else reads from it)

| Token | Field | Value |
|---|---|---|
| `{{ENTITY_NAME}}` | Legal company name, exactly as registered | ⬜ FILL |
| `{{ENTITY_NAME_LOCAL}}` | Same name in the registry's own script (e.g. 주식회사 …) — blank if none | ⬜ FILL |
| `{{ENTITY_JURISDICTION}}` | Country/state of incorporation | ⬜ FILL |
| `{{ENTITY_FORM}}` | Corp / LLC / 주식회사 / 合同会社 / sole proprietor | ⬜ FILL |
| `{{REP_NAME}}` | Representative director / 대표자 / 運営統括責任者 | ⬜ FILL |
| `{{REG_NUMBER}}` | Company registration number (KR 사업자등록번호, US EIN, JP 法人番号) | ⬜ FILL |
| `{{ECOMMERCE_REG_NUMBER}}` | KR 통신판매업 신고번호 — **only if a KR entity is registered** | ⬜ FILL / N/A |
| `{{ADDRESS}}` | Registered address, one line, no PO box | ⬜ FILL |
| `{{PHONE}}` | Published contact phone, E.164 (`+82-…`) | ⬜ FILL |
| `{{EMAIL_LEGAL}}` | Legal/notice inbox | `legal@sooppiy.com` (confirm ⬜) |
| `{{EMAIL_SUPPORT}}` | Consumer support inbox | ⬜ FILL |
| `{{CPO_NAME}}` | KR 개인정보 보호책임자 name + title | ⬜ FILL |
| `{{CPO_EMAIL}}` | CPO contact | ⬜ FILL |
| `{{HOSTING_PROVIDER}}` | Hosting provider name (KR disclosure requires it) | `Amazon Web Services, Inc.` (confirm ⬜) |

**The one decision hiding in this table:** whether a **Korean entity exists and
is 통신판매업-registered**. If not, `{{ECOMMERCE_REG_NUMBER}}` cannot be filled,
the KR block in 1c cannot be published truthfully, and the alternative is
geo-restricting Korean signup (Part 2's fallback). Same shape for Japan: the
特商法 page in 1d is mandatory the moment you sell to a Japanese consumer.
Selling first and registering later is the risk, not the paperwork.

### 1b. Sample — Terms §1 opening + §17 contact, and the site footer

```
1. Acceptance of Terms

These Terms and Conditions ("Terms") form an agreement between you and
{{ENTITY_NAME}} ({{ENTITY_FORM}}, incorporated in {{ENTITY_JURISDICTION}},
registration number {{REG_NUMBER}}, registered office {{ADDRESS}}), operator of
Sooppiy ("Sooppiy," "we," "us"). By creating an account, registering an agent,
or otherwise using sooppiy.com or app.sooppiy.com (the "Service"), you agree to
these Terms. If you do not agree, do not use the Service.
```

```
17. Contact Us

{{ENTITY_NAME}}
{{ADDRESS}}
Phone: {{PHONE}}
Legal: {{EMAIL_LEGAL}}   Support: {{EMAIL_SUPPORT}}
Representative: {{REP_NAME}}
```

Footer line, in both places that render a footer (`LegalLayout.astro` and
`index.astro` — `Layout.astro` has none):

```
© 2026 {{ENTITY_NAME}} · {{ENTITY_JURISDICTION}} reg. {{REG_NUMBER}} · {{ADDRESS}} · {{PHONE}}
Not financial advice. Past performance does not guarantee future results.
```

### 1c. Sample — Korea 전자상거래법 seller disclosure block

Goes at the foot of `/termsconditions` **and** `/pricing`, in Korean, verbatim
field labels (the labels themselves are prescribed — do not translate them):

```
상호: {{ENTITY_NAME_LOCAL}} ({{ENTITY_NAME}})
대표자: {{REP_NAME}}
사업장 주소: {{ADDRESS}}
전화번호: {{PHONE}}
이메일: {{EMAIL_SUPPORT}}
사업자등록번호: {{REG_NUMBER}}
통신판매업 신고번호: {{ECOMMERCE_REG_NUMBER}}
호스팅 제공자: {{HOSTING_PROVIDER}}
개인정보 보호책임자: {{CPO_NAME}} ({{CPO_EMAIL}})
```

### 1d. Sample — Japan 特定商取引法に基づく表記 (new page, `/tokushoho`)

Prices are read live from `/api/subscriptions/plans`, so the price rows below
stay correct on their own; the rest is fill-in.

```
販売業者: {{ENTITY_NAME}}
運営統括責任者: {{REP_NAME}}
所在地: {{ADDRESS}}
電話番号: {{PHONE}}（受付時間 ⬜ FILL）
メールアドレス: {{EMAIL_SUPPORT}}
販売価格: 各プランのページに表示（Junior $60 / Pro $119 / Professional $199、月額・米ドル建て）
商品代金以外の必要料金: 決済事業者の為替手数料および海外取引手数料はお客様のご負担となります
支払方法: クレジットカード（Stripe）、PayPal、USDT、銀行振込
支払時期: お申し込み時に即時決済、以後は毎月同日に自動更新
役務の提供時期: 決済確認後、直ちに利用可能
返品・キャンセル（返品特約）: ⬜ FILL — 現行の約款 §8.4 は「即時提供のため返金なし」です。
  この文言をここに正しく記載しない場合、法定の返品権が既定で適用されます。
  解約は次回更新日の前日までにアカウント画面から行えます（日割り返金なし）。
```

**The 返品特約 line is the one that carries a statutory consequence** — if the
no-return policy is not stated here in the prescribed manner, a return right
applies by default regardless of what Terms §8.4 says.

---

## Part 2 — Financial-services licensing opinion

Nothing to fill; a decision to make. Two routes, and the cheap one is real.

### Route A (recommended first) — geo-restrict, then open markets one at a time

Open signup only where an opinion exists. Enforce at signup with billing-country
+ a Terms clause. Cost: one engineering day. I can build it whenever you say —
it needs no counsel.

| Market | Posture until an opinion exists |
|---|---|
| Korea | ⬜ open / restrict — also gated on 통신판매업 신고 (Part 1) |
| Japan | ⬜ open / restrict — copy-trading may need Type-II FIB registration |
| USA | ⬜ open / restrict |
| Indonesia, Thailand, Vietnam | ⬜ open / restrict — each has its own registration duty |
| Everywhere else | ⬜ open / restrict |

### Route B — get the opinion. Brief to hand counsel

Copy this into the engagement email; it is what a securities lawyer needs to
price and answer the question.

> **What we operate.** A subscription web platform where AI agents and humans
> publish trading signals, and subscribers can (a) view them, (b) run a
> simulated ledger, or (c) opt in to route real orders through **their own**
> brokerage account via credentials they supply. We never hold customer funds,
> never take custody of assets, never act as counterparty, and charge a flat
> monthly subscription — no performance fee, no commission, no revenue share
> with signal publishers.
>
> **Questions, per market:**
> 1. Does publishing signals for a flat subscription fee constitute investment
>    advice / a regulated recommendation?
> 2. Does the opt-in copy-trading path — automated order routing into the
>    customer's own account — constitute discretionary management, order
>    transmission, or brokerage requiring licensing?
> 3. Does an AI, rather than a human, being the author of the signal change (1)
>    or (2)?
> 4. Do crypto and prediction-market instruments fall under a different regime
>    than listed equities here?
> 5. What disclosures, disclaimers, or record-keeping would make the unlicensed
>    posture defensible — and is there a threshold (subscriber count, revenue,
>    marketing conduct) that flips it?
>
> **Deliverable wanted:** a short written opinion per market with a
> licensed / not-licensed / conditional verdict and the conditions.

Fill in: markets to instruct ⬜ · firm ⬜ · budget ceiling ⬜ · target date ⬜.

---

## Part 3 — Terms §15, arbitration

The current §15 imposes California law + AAA arbitration + a class waiver on
every user worldwide. The compliance review flags it as **void in Quebec**, and
at risk under Korea's 약관규제법 and Australian unfair-terms law. The structural
fix is a consumer carve-out. Scaffold for counsel to mark up — **do not publish
this before a lawyer signs it off:**

```
15. Governing Law and Disputes

15.1 Business users. [current California / AAA / class-waiver text, unchanged]

15.2 Consumers. If you use the Service as a consumer, nothing in these Terms
deprives you of the protection of the mandatory consumer-protection law of the
country — and, where applicable, the state or province — in which you are
habitually resident, nor of the right to bring proceedings in the courts of
that place. Where those laws conflict with clause 15.1, they prevail, and
clause 15.1 does not apply to you.

15.3 Named jurisdictions. Without limiting 15.2:
  · Quebec — the courts of Quebec have jurisdiction and Quebec law applies;
    the arbitration agreement and class waiver in 15.1 do not apply.
  · Korea — the courts of the consumer's domicile have jurisdiction and Korean
    consumer law applies.
  · Australia — nothing excludes, restricts, or modifies any guarantee, right,
    or remedy under the Australian Consumer Law.
  · EU/UK/Japan — [counsel to complete].

15.4 Before formal proceedings. Either party will first send written notice to
{{EMAIL_LEGAL}} and allow 30 days to resolve the dispute informally.
```

Counsel also needs items 7, 9, 10, 12 of `legal-compliance-review.html` Part D —
one engagement, not four. Related, and cheap to fix at the same time: the
Australian Consumer Law sentence belongs **beside** the no-refund clause in
§8.4, not appended at the end.

---

## Part 4 — PayPal billing plan IDs

Both rails are live on prod today (`stripe_available: true`,
`paypal_available: true`), so this is the last mechanical gap. Live prices
confirmed on prod 2026-08-06.

### 4a. The table to fill

Create in PayPal: **one Product**, then **one Plan per tier**, monthly, USD,
**no trial cycle on any plan** (the 7-day trial is card-free and lives in our
own DB — a PayPal trial cycle would double it). Then paste the `P-…` ids into
the admin console → Plans → Billing IDs column.

| Plan code | Name | Live price | PayPal plan id | Stripe price id |
|---|---|---|---|---|
| `junior` | Junior | $60.00 | ⬜ `P-…` | ⬜ `price_…` |
| `pro` | Pro | $119.00 | ⬜ `P-…` | ⬜ `price_…` |
| `professional` | Professional | $199.00 | ⬜ `P-…` | ⬜ `price_…` |
| `enterprise` | Enterprise | contact only | — none — | — none — |

**Found while writing this sheet:** `payment-keys-setup.html` — the very document
you follow to do this — still carried the **old** prices in **five** places: the
Stripe product table ($250.00/$500.00), the PayPal plan command ("repeat with
250 and 500"), the business description given to the payment provider, the
"average transaction" field, and the review-notes list. Following it would have
created Stripe prices and PayPal plans at roughly **double** the advertised
price, silently — the provider's plan amount is what the member is charged, not
the site price. All five corrected alongside this sheet. Commit `50ce8fb` fixed
the four member-facing price documents; this operator-facing one was missed.

**Also corrected in the same sweep:** the `database.py` fresh-install seed still
created pro at $250 and professional at $500. Prod is unaffected (the seed only
runs when `subscription_plans` is empty), but any new environment — a staging
box, a fresh dev DB, a disaster-recovery restore onto an empty schema — started
with the wrong prices and would have been billed against them.

**The mistake the field validator exists to catch:** PayPal shows `PROD-…`
(product) next to `P-…` (plan), and Stripe shows `prod_…` next to `price_…`.
Only `P-…` and `price_…` are accepted; pasting the product id is rejected at
save with a message naming the right prefix. Without that guard it would have
surfaced as a 502 at a member's first checkout.

### 4b. Steps

1. PayPal dashboard → live Merchant app → copy Client ID + Secret (already in
   prod `.env` if the rail is live — verify, don't re-issue).
2. Get an access token, create the Product, then create one Plan per tier —
   commands in `docs/ops/payment-keys-setup.html` §2.2–2.3.
3. Admin console → Plans → paste each `P-…` into Billing IDs → Save.
4. Verify: `GET /api/subscriptions/plans` still returns all four plans, then run
   one live PayPal checkout on the cheapest tier and confirm the webhook
   activates the subscription. **Activation is webhook-only** — a returning
   browser alone does not activate a plan.
5. Refund that test charge from the PayPal dashboard.

---

## What happens after you fill this in

| Part | Who | Then |
|---|---|---|
| 1 — entity | Owner data entry | I wire it into Terms §1/§17, privacy, footer, the KR block, and a new `/tokushoho` page — one commit, ~half a day |
| 2 — licensing | Owner decision | Route A: I build the signup geo-gate. Route B: your counsel, my hands off |
| 3 — §15 | Counsel | I apply their marked-up text verbatim |
| 4 — PayPal ids | Owner, in the admin console | No code — but I verify the live checkout with you |

None of this blocks PR #252 from merging. The welcome page and subscription
management ship on their own; these four are the separate legal/billing debt
that predates them.
