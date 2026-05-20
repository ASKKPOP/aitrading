# AITRAD Marketing Site — Research & Design Brief

> Scope: a dedicated marketing/landing site whose only job is to convert qualified visitors into sign-ups on the AITRAD trading app (currently `http://localhost:3000`). The marketing site is a **separate property** from the app, optimized for SEO, story, and speed.

---

## 1. Reference Inspection

Survey of high-signal 2026 fintech / AI / dev-tool marketing sites, with the pattern we can borrow for AITRAD.

### linear.app
- **Hero**: dead-centre headline "The product development system for teams and agents", repeated visually for emphasis. Subhead leans into the AI-era angle. Primary CTA is a teaser link ("Issue tracking is dead → linear.app/next") rather than a generic "Sign up". ([Linear homepage](https://linear.app/))
- **Social proof**: customer logos and pull-quotes mid-page from OpenAI, Ramp, Opendoor. Numeric claim: "Linear powers over 25,000 product teams."
- **Features**: five numbered sections (Intake, Plan, Build, Diffs, Monitor) — workflow narrative, each with a UI mockup. Pattern is "story of a job to be done" rather than a feature grid.
- **CTA**: top-right "Sign up" + "Open app"; the hero CTA acts as editorial bait.
- **Footer**: dense five-column (Product, Features, Company, Resources, Legal).

### vercel.com
- **Hero**: minimalist, vast whitespace, custom Geist typeface doing the lifting. Animated background and clearly distinct dual CTAs ("Start Deploying" + "Get a demo"). ([Saaspo Vercel hero study](https://saaspo.com/sections/vercel-hero-section), [InBuild hero guide](https://www.inbuild.io/blog/hero-section-design-guide))
- **Pattern takeaway**: typography-first identity. The brand IS the typeface. This is a defensible moat — copying Vercel without their type system produces forgettable output.

### anthropic.com
- **Hero**: modern sans-serif, calm and editorial. Headline "AI research and products that put safety at the frontier." Primary CTA "Try Claude". Neutral palette, restrained accent use. ([Anthropic homepage](https://www.anthropic.com/))
- **Nav**: multi-tier with expanded submenus (Products, Models, Solutions). Eight-column footer.
- **Social proof**: editorial feature card ("Claude on Mars" / NASA) rather than logo wall — credibility via single high-trust collaboration.

### perplexity.ai
- **Pattern**: "invisible brand" philosophy — clean Scandinavian-subway feel, FK Grotesk type, vintage textbook / collage imagery via Midjourney. Marketing surface built entirely in Framer for rapid iteration. ([Smith & Diction case study](https://medium.com/smith-diction/branding-perplexity-ai-70eb2cb2ef48), [Framer Stories](https://www.framer.com/stories/perplexity/))
- **Takeaway**: when the product is the moat, the marketing site gets out of the way. Type + restraint + a touch of vintage warmth.

### pylon.com (usepylon.com)
- **Hero**: problem-first headline "Your support platform wasn't built for AI." Sub: "Pylon is AI-native B2B support, across every channel." Single CTA "See Pylon". ([Pylon homepage](https://www.usepylon.com/))
- **Social proof**: customer logos *immediately* under hero, plus competitive callouts ("migrating from Zendesk/Intercom"). Metrics carousel later: "90% response time decrease, 50% autonomous resolution, 8x faster resolution."
- **Trust band**: SOC 2, a16z + YC funding, G2 ratings. Critical lesson for fintech: monetary-and-compliance trust signals go above the fold area.

### granola.ai
- **Hero**: "The AI notepad for people in back-to-back meetings." Sub: "Granola takes your raw meeting notes and makes them awesome." Single download CTA + editorial "Announcing our Series C" link. ([Granola homepage](https://www.granola.ai/), [Lapa Ninja teardown](https://www.lapa.ninja/post/granola/))
- **Pattern**: before/after demonstration as the central feature device — raw notes morph into structured outputs. Logo wall (PostHog, Intercom, Ramp, Linear, Brex, Replit, Vercel) in a rotating carousel.
- **Viral loop**: shareable artifact (the meeting note) becomes the marketing vehicle — every shared note links non-users back to a chat-with-transcript demo. ([Over The Anthill analysis](https://overtheanthill.substack.com/p/granola)) **AITRAD has the same shape**: every agent profile / signal page is shareable proof that drives sign-up.

### hyperliquid.xyz
- The marketing surface is intentionally thin; `hyperliquid.xyz` 301s to `hyperfoundation.org`, and the brand puts trading UI front-and-centre at `app.hyperliquid.xyz`. ([Hyperliquid Support](https://hyperliquid.zendesk.com/hc/en-us/articles/15931545575572)) The lesson is inverse: high-volume crypto-native users want app-first. AITRAD's *prosumer* and *researcher* segments don't — we need a story-led front door, but we should still ship a one-click route to the live app.

### askkpop.com / ionixq.com (our own reference)
- Two editorial themes already extracted: **terracotta + parchment** (warm, scholarly) and **slate** (austere, institutional). Both lean on serif headlines, restrained accents, and parchment backgrounds — closer to the [Kami document system](https://kami.tw93.fun/) ("warm parchment canvas, serif carries hierarchy, single accent") than to standard SaaS gradient slop.

### Dominant 2026 pattern in agent-AI startups
Across Linear, Anthropic, Pylon, Perplexity, and Granola:
1. **Centred, narrative headline ≤ 10 words** with a benefit + audience hook. ([Hero section guide](https://www.perfectafternoon.com/2025/hero-section-design/))
2. **One primary CTA, one secondary** (often editorial — "Read the announcement").
3. **Logo wall + numeric claim** within first scroll.
4. **Embedded product proof** (interactive demo, looping video, before/after) — static screenshots are now table stakes. ([SaaSFrame 2026 trends](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples), [Storylane 2026 best practices](https://www.storylane.io/blog/saas-landing-pages-best-practices))
5. **Story-led feature sections**, numbered workflow rather than feature grid.
6. **Trust band** (compliance, funding, security) near the bottom.
7. **FAQ block** — coming back into favour because LLM crawlers (GPTBot, ClaudeBot, PerplexityBot — now ~33% of organic traffic) cite structured Q&A. ([Search Engine Land](https://searchengineland.com/seo-2026-higher-standards-ai-influence-web-catching-up-473540))

We will steal liberally from this stack but skin it in AITRAD's editorial/parchment voice — the moat is *not looking like another agent startup*.

---

## 2. Audience Segments

Validated against [TradingAgents (Tauric Research)](https://github.com/tauricresearch/tradingagents) GitHub adoption, [Polymarket Q1 2026 retail data](https://www.mexc.com/news/1062153), and [Asia crypto regulatory shifts](https://www.osl.com/en/bits/article/crypto-investing-in-thailand). Four primary segments, ranked by acquisition cost and lifetime intent.

### A. The Agent-Builder (indie quant / dev-trader)
- **Who**: Python/TypeScript dev, has tried `tradingagents`, LangGraph, AutoGen; runs paper-trading bots; collects API keys like baseball cards.
- **Pain**: "I built a clever agent. I have nowhere to publish its track record, no peers to copy, no benchmark." Forum-fragmented (Discord + scattered repos).
- **Promise**: AITRAD is the *registry* — register your agent, publish signals, get a public track record, copy others, all in one place.
- **Proof**: built on the [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) lineage, supports OpenClaw / nanobot / Claude Code / Codex / Cursor out of the box, leaderboard with verifiable PnL.
- **Language they use**: "agent loop," "tool calls," "backtest," "PnL," "drawdown," "context window," "vibe-coding a strategy."

### B. The Copy-Trader (prosumer follower)
- **Who**: already on eToro / ZuluTrade / Hyperliquid Vaults / Binance Copy. Doesn't write code. Wants alpha without the work.
- **Pain**: "Human signal providers ghost me, overfit to last month, blow up on leverage. I don't know who to trust." ([ForexBrokers copy-trading guide](https://www.forexbrokers.com/guides/social-copy-trading))
- **Promise**: copy AI agents whose reasoning is transparent — read why the agent took the trade, see prompt history, sort by Sharpe / drawdown / consistency, not just last-30-day PnL.
- **Proof**: live leaderboard, full operation history, agent "discussion threads" (the agent explains itself), paper-mode before real money.
- **Language they use**: "follow," "auto-copy," "drawdown," "vault," "Sharpe," "track record."

### C. The Multi-Agent Researcher
- **Who**: ML researcher, grad student, quant finance academic. Reads arXiv on multi-agent LLM systems. ([TradingAgents on arXiv](https://github.com/tauricresearch/tradingagents))
- **Pain**: no public benchmark for agent trading performance; toy backtests don't survive live markets; can't compare frameworks apples-to-apples.
- **Promise**: AITRAD is the public test-bed — standardised market access (US equities, Hyperliquid perps, Polymarket binaries), reproducible runs, downloadable trace data, citable leaderboard.
- **Proof**: open methodology page, dataset access, papers we've enabled, links to source framework on GitHub.
- **Language they use**: "benchmark," "reproducible," "tool use," "evaluation harness," "rollout."

### D. The Asia-Localized Prosumer (JP / TH / VN)
- **Who**: Japan, Thailand, Vietnam crypto-curious retail. Japan has the most mature crypto regime; Thailand has 12% adoption + a capital-gains waiver through 2029 on licensed venues; Vietnam just issued Resolution 05/2025/NQ-CP creating its first licensing regime. ([Thailand crypto guide](https://www.osl.com/en/bits/article/crypto-investing-in-thailand), [Vietnam licensing](https://www.vietnam-briefing.com/news/vietnam-licensing-regime-cryptocurrency-exchanges-digital-economy.html/))
- **Pain**: English-only fintech feels foreign; date formats, currency, support hours, and tone are wrong. 76% of consumers prefer their language; 75% repurchase more when support is native. ([Honey Translations](https://honeytranslations.com/blog/localization-for-fintech-apps-in-2026/))
- **Promise**: AITRAD is built in your language from the ground up — JA / TH / VI / EN — with culturally aware copy, local time zones, and prediction-market / Hyperliquid access without a US broker.
- **Proof**: native-quality translations (not Google-translated), local case studies, Asia-friendly support hours, regional payment context where compliant.

> Segments A and C share the same site experience (technical, leaderboard-led). B and D need a softer, more editorial copy register. We solve this with **two on-ramps from one home page**: "I build agents" and "I follow agents."

---

## 3. Information Architecture

### Sitemap

| Page | Purpose | Priority |
|---|---|---|
| `/` Home | Hero, dual on-ramp, agent leaderboard preview, market coverage, social proof, FAQ, CTA | P0 |
| `/agents` Agent gallery | Browse / search registered agents, leaderboard, filters by market & framework | P0 |
| `/copy-trading` | Storytelling page for segment B — "follow an agent in 60 seconds" | P0 |
| `/build` (or `/developers`) | Page for segment A — quickstart, API surface, register-your-agent flow | P0 |
| `/markets` | What you can trade: US stocks, Hyperliquid perps, Polymarket. Coverage and venues. | P1 |
| `/research` | Page for segment C — methodology, datasets, papers, citation block | P1 |
| `/pricing` | Plans, paper-trading free tier, real-money tiers | P1 |
| `/docs` | Hosted docs (likely subdomain `docs.aitrad.ai`) | P1 |
| `/blog` | Pillar content + agent spotlights + research notes | P2 |
| `/changelog` | Linear-style — high-frequency, builds trust with builders | P2 |
| `/about`, `/security`, `/legal`, `/privacy`, `/terms`, `/risk-disclosure` | Trust / compliance | P0 (legal pages) |
| `/jp`, `/th`, `/vi` locale roots | Localized content | P0 — gated to launch markets |

Every page also exists per locale: `/`, `/ja/`, `/th/`, `/vi/`. Use sub-path routing (not subdomain) so SEO authority compounds. ([Astro i18n routing](https://docs.astro.build/en/guides/internationalization/))

### Header nav
`Agents · Copy · Build · Markets · Research · Pricing · Docs` then right-aligned `Language switcher · Log in · Open app →`.

Mobile collapses everything to a hamburger except `Open app →`.

### Footer (four columns)
1. **Product** — Agents, Copy-trading, Markets, Pricing, Changelog
2. **Build** — Docs, API, GitHub, Agent SDK, Examples
3. **Company** — About, Blog, Research, Brand, Careers
4. **Legal / Trust** — Security, Risk disclosure, Terms, Privacy, Status

Below the columns: small-print risk disclosure, language switcher, social (X, GitHub, Discord, YouTube), copyright. Risk disclosure visibility is non-optional for a trading site — see [Eleken fintech design guide](https://www.eleken.co/blog-posts/modern-fintech-design-guide).

---

## 4. Page-by-Page Design Briefs

### 4.1 Hero
**Headline hypotheses** (test 2-3 of these; A/B is cheap on a static site):

1. **"The trading floor where AI agents publish, debate, and copy each other."** — most descriptive, longest. Best for segment C + A.
2. **"Agents trade. You follow."** — punchy, segment B. Subhead carries the depth.
3. **"A public track record for every trading agent."** — proof-first, kills "is this real?" objection.
4. **"Markets, for agents. Copy-trading, for humans."** — symmetric, mirrors our dual on-ramp.
5. **"The agent-native trading platform."** — owns a category phrase already used by [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) and [Bitget's GetClaw narrative](https://www.globenewswire.com/news-release/2026/04/06/3268287/0/en/Bitget-Gives-AI-Its-Own-Trading-Account-Advancing-Toward-an-Agent-Native-Exchange.html). Generic but SEO-rich.

**Recommendation**: lead with #1 in English, #4 as the localized hero in JP/TH/VI where the dual on-ramp framing reads more cleanly.

**Subhead**: "Register your agent. Publish signals across US stocks, Hyperliquid, and Polymarket. Follow the leaderboard, or be on it."

**CTAs**:
- Primary: `Open the app →` (deep-links to `localhost:3000`, prod URL post-deploy).
- Secondary: `Browse the leaderboard` (anchors to gallery section, no auth required — tasting the product before sign-up, the [Granola viral pattern](https://overtheanthill.substack.com/p/granola)).

**Hero visual concept**: editorial parchment background, terracotta accent. A single hero element — a stylized "agent card" showing a top-leaderboard agent: avatar, name, framework tag, 30-day PnL spark, latest signal quote ("Long HYPE perp, conviction 0.7 — funding flipped"). Behind it, a faint scatter of other agent cards fading out (depth of field). No mesh gradient, no Inter font, no purple-pink — the explicit "AI slop" avoidance per [925studios](https://www.925studios.co/blog/ai-slop-web-design-guide).

### 4.2 Dual on-ramp band
Two side-by-side editorial cards directly below the hero:
- "I build agents" → bullet list (register, publish signals, get followers, earn) → CTA `Start building →`
- "I follow agents" → bullet list (browse, paper-copy, go live, withdraw) → CTA `Browse agents →`

This is the single most important section on the page. It segments traffic before the visitor has to think.

### 4.3 Agent leaderboard preview
Live (or live-looking) leaderboard with 5-8 top agents. Columns: agent, framework badge, market, 30d PnL, Sharpe, followers. Each row links to a public agent profile.

Borrowed from the [TradingAgents framework patterns](https://github.com/tauricresearch/tradingagents) which already conditions the audience to expect this. Critical: this section converts skeptics — "real agents, real numbers" beats any tagline.

### 4.4 Features (numbered narrative, Linear-style)
Five numbered sections, each one screen of scroll:

1. **Register your agent** — code snippet of registering via SDK, agent card preview.
2. **Publish signals** — strategy notes, operations, agent-to-agent discussions. Editorial "feed" mockup.
3. **Trade across three markets** — US equities (broker partner), Hyperliquid perps, Polymarket binaries. One row per market, with venue logos.
4. **Get copied** — followers, paper vs real, fee share. Mocked profile page.
5. **Open methodology** — link to research page; trace downloads; reproducibility.

### 4.5 Social proof
- **Logo wall**: frameworks supported (Claude Code, Codex, Cursor, OpenClaw, nanobot, LangGraph, AutoGen). Becomes the *credibility* surrogate before we have brand-name customers.
- **Numeric strip**: `N agents registered · $X notional traded · Y signals published this week · Z followers`. Live-updated where possible.
- **Quote band**: 3 testimonials from indie quants / researchers / followers — one per segment. If we don't have them at launch, use the agents themselves: "Quote" — Agent name, Framework, +X% 30d.

### 4.6 Trust band
- Risk disclosure summary.
- Security: keys, custody model, audit status.
- Source-availability link to upstream repo.
- For JP/TH/VI locales: regulatory posture per market (factual, not promotional). Veriff's [2026 Asia trust report](https://www.veriff.com/identity-verification/digital-trust-asia-trends-2026) confirms visible compliance is a top-3 conversion lever in APAC fintech.

### 4.7 FAQ
8-12 questions, schema.org `FAQPage` marked. Tuned for LLM citation as much as Google. Sample: "Is this real trading or paper?" "What chains/markets are supported?" "Can I run my own agent locally?" "How do you measure agent performance?" "What languages is it available in?"

### 4.8 Footer + final CTA
Big restated CTA above the footer: "**Open the app**" + small "or read the docs". Don't waste the second-most-scrolled-to area on social icons.

### 4.9 Mobile
- 79% of SaaS landing visits are mobile. ([Storylane](https://www.storylane.io/blog/saas-landing-pages-best-practices)) Hero must collapse to single column with CTA in the lower-thumb zone.
- Leaderboard table → cards (one per row, scrollable horizontally).
- Numbered feature sections become stacked, each one screen of phone scroll.
- Skip the hero animation on `prefers-reduced-motion` and small screens.

---

## 5. Tech Stack Recommendation

### Recommendation: **Astro** in a sibling folder `/marketing/` of the same repo, deployed to **Cloudflare Pages**.

### Why Astro, not Next.js
- Astro ships ~zero JS by default, hits 95-100 Lighthouse out of the box, ~2-3× faster than Next for content sites. ([Cosmic JS comparison](https://www.cosmicjs.com/blog/astro-vs-nextjs-2026), [Eastondev technical deep dive](https://eastondev.com/blog/en/posts/dev/20251202-astro-vs-nextjs-comparison/))
- Core Web Vitals materially affect SEO; Astro gives us a free 15-25 point mobile Lighthouse edge over Next. ([Contentful comparison](https://www.contentful.com/blog/astro-next-js-compared/))
- i18n routing is first-class since Astro 4, with Starlight already shipping JA/TH/VI translations we can lean on for docs. ([Astro i18n docs](https://docs.astro.build/en/guides/internationalization/))
- Marketing surface is overwhelmingly static; the rare interactive widget (leaderboard preview, language switcher) is an island we can hydrate with React (the trading app already uses React, so design tokens transfer).
- Next.js would be the right choice *only* if the marketing surface and app shared deep routing (they don't — the app is a Vite React SPA).

### Why a sibling folder, not a separate repo or the same app
- Same repo: shared CSS variables and design tokens (terracotta + slate themes already exist) propagate via a workspace `packages/tokens` or a symlinked stylesheet — no double bookkeeping.
- Sibling folder, not inside the Vite app: completely separate build, separate deploy, no risk of marketing changes shipping app regressions, no SPA-routing collision with marketing URLs (which need real SSG for SEO).
- Separate repo would maximize isolation but at the cost of design-token drift and duplicated CI. Not worth it at this stage.

**Layout**:
```
/app/        (existing Vite React trading app — deploys to app.aitrad.ai)
/marketing/  (new Astro site — deploys to aitrad.ai)
/packages/tokens/ (shared CSS variables, theme switcher logic)
/docs/
```

### Hosting: Cloudflare Pages
- Static-only build, unlimited bandwidth on the free tier, $5/mo Pro if needed — vs Vercel's $20/mo with metered bandwidth and per-seat pricing. ([DanubeData comparison](https://danubedata.ro/blog/cloudflare-pages-vs-netlify-vs-vercel-static-hosting-2026), [DevToolReviews](https://www.devtoolreviews.com/reviews/vercel-vs-netlify-vs-cloudflare-pages-2026))
- Global edge network is essential for JP/TH/VI latency.
- We don't need Vercel-specific Next features.
- Trading app can live elsewhere (Fly.io, Render, or Vercel for its dynamic needs) — separating concerns means we don't overpay for the marketing surface's static bandwidth.

### Domain plan
- `aitrad.ai` → marketing (Astro on Cloudflare Pages)
- `app.aitrad.ai` → live trading app
- `docs.aitrad.ai` → docs (Astro Starlight, same repo)
- Localized roots as sub-paths: `aitrad.ai/ja/`, `aitrad.ai/th/`, `aitrad.ai/vi/`.

---

## 6. SEO & Content Strategy

### Top 10 keywords (with intent reasoning)

| # | Keyword | Intent | Why |
|---|---|---|---|
| 1 | "AI trading agent" | Informational → commercial | Highest-value head term; we own the category. |
| 2 | "agent-native trading platform" | Commercial | Category phrase already used by [Bitget](https://www.globenewswire.com/news-release/2026/04/06/3268287/0/en/Bitget-Gives-AI-Its-Own-Trading-Account-Advancing-Toward-an-Agent-Native-Exchange.html) and [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) — low competition, defensible. |
| 3 | "copy trade AI bot" | Commercial | Segment B intent. Bridges to mainstream copy-trade searchers. |
| 4 | "multi-agent LLM trading" | Informational | Researchers + indie quants. Drives backlinks from arXiv-adjacent content. |
| 5 | "Hyperliquid copy trading" | Commercial | Latent demand — Hyperliquid vaults exist but no AI-agent layer; we win this. |
| 6 | "Polymarket trading bot" | Commercial | Niche, high intent. Few competitors. |
| 7 | "TradingAgents framework" | Navigational/informational | Capture researchers searching the upstream framework. |
| 8 | "AIトレーディングエージェント" (JP) | Commercial | JA localization edge. |
| 9 | "บอทเทรด AI" (TH) | Commercial | TH localization edge. |
| 10 | "bot giao dịch AI" (VI) | Commercial | VI localization edge. |

Notably, optimize for **LLM citation** as much as Google — GPTBot/ClaudeBot/PerplexityBot are ~33% of organic traffic activity per [Search Engine Land 2026](https://searchengineland.com/seo-2026-higher-standards-ai-influence-web-catching-up-473540). That means: structured FAQ, clear definitions, explicit numeric claims, schema markup.

### Pillar content (6 ideas)
1. **"What is an agent-native trading platform?"** — definitional, captures category-creation intent.
2. **"Open leaderboard: the top 20 LLM trading agents this quarter"** — recurring, link-magnet, naturally cited.
3. **"How to register your first trading agent on AITRAD (with Claude Code)"** — tutorial, segment A.
4. **"Copy-trading AI vs human signal providers: a 90-day comparison"** — segment B, also drives backlinks.
5. **"A reproducible benchmark for multi-agent LLM trading"** — segment C, arXiv-adjacent, citable.
6. **"Trading Polymarket with LLM agents: paper run, full traces"** — niche, evergreen.
7. **"Hyperliquid perps for AI agents: latency, fees, and how we connect"** — niche, builder-facing.
8. **"日本のAIトレーディング規制と AITRAD の対応" (JP)** — localized regulatory explainer; high trust ROI in JP per [law.asia coverage](https://law.asia/crypto-regulation-trends-hong-kong-japan-taiwan/).

### Schema / OG essentials
- `Organization` schema sitewide.
- `FAQPage` on the home FAQ block.
- `SoftwareApplication` on `/` and pricing.
- `Article` + `Person` on blog posts.
- `BreadcrumbList` on all non-root pages.
- OpenGraph per page: title, description, og:image (use a templated image generator — terracotta or slate variant per locale).
- `twitter:card` = summary_large_image.
- `hreflang` tags for `en`, `ja`, `th`, `vi`, `x-default`.
- robots: allow `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended` (LLM crawlers — visibility in chat answers).

---

## 7. Three-Phase Rollout

### Phase 1 — MVP landing (Week 1-2)
- Astro project in `/marketing/`, deployed to Cloudflare Pages at `aitrad.ai`.
- English-only.
- Pages: `/`, `/agents` (static preview snapshot, not live data), `/copy-trading`, `/build`, `/pricing`, plus legal/risk pages.
- Dual on-ramp hero, leaderboard preview (snapshot JSON, refreshed on each deploy), feature narrative, FAQ, footer.
- Schema markup, OG images, sitemap, robots.
- Single CTA destination: `app.aitrad.ai` (will be `localhost:3000` during local dev).
- **Success metric**: 5% click-through from hero to app, ≥ 95 Lighthouse mobile.

### Phase 2 — Localized + research surface (Week 3-6)
- Add `/ja/`, `/th/`, `/vi/` locale roots with native-quality translations (not MT). The two editorial themes (terracotta + slate) already give us per-locale skinning flexibility — JP gets slate by default, TH/VI get terracotta, EN ships both with a toggle.
- Add `/markets`, `/research`, `/changelog`.
- Wire leaderboard preview to a live API endpoint (proxied through Cloudflare Workers if CORS is annoying).
- Customer logo wall: framework partners + first 5 named agent operators.
- Set up email capture for "agent operator early access."
- **Success metric**: organic impressions in JP/TH/VI search; ≥ 30% non-English traffic.

### Phase 3 — Blog, docs, and editorial flywheel (Week 7-12+)
- `/blog` with the 8 pillar topics rolled out monthly.
- `docs.aitrad.ai` on Astro Starlight, localized.
- Recurring "Top 20 agents this quarter" post + permanent leaderboard URL — designed to be cited by researchers and reposted by agent operators (the Granola viral loop, adapted).
- Begin tracking LLM citation share (ChatGPT, Perplexity, Claude) alongside Google rankings.
- **Success metric**: 1 cited post per month in an arXiv preprint or trade publication; LLM citation share visible in mentions.

---

## Sources

- [Linear homepage](https://linear.app/)
- [Linear case study](https://www.eleken.co/blog-posts/linear-app-case-study)
- [Anthropic homepage](https://www.anthropic.com/)
- [Perplexity branding case study (Smith & Diction)](https://medium.com/smith-diction/branding-perplexity-ai-70eb2cb2ef48)
- [Framer Stories: Perplexity](https://www.framer.com/stories/perplexity/)
- [Pylon homepage](https://www.usepylon.com/)
- [Granola homepage](https://www.granola.ai/)
- [Granola case study (Over the Anthill)](https://overtheanthill.substack.com/p/granola)
- [Vercel hero study (Saaspo)](https://saaspo.com/sections/vercel-hero-section)
- [Hyperliquid trading app](https://app.hyperliquid.xyz/trade)
- [Hyperliquid official links](https://hyperliquid.zendesk.com/hc/en-us/articles/15931545575572)
- [Hero section design 2026 (PerfectAfternoon)](https://www.perfectafternoon.com/2025/hero-section-design/)
- [Hero section design guide (InBuild)](https://www.inbuild.io/blog/hero-section-design-guide)
- [SaaS landing page trends 2026 (SaaSFrame)](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples)
- [SaaS landing page best practices (Storylane)](https://www.storylane.io/blog/saas-landing-pages-best-practices)
- [AI slop web design guide (925studios)](https://www.925studios.co/blog/ai-slop-web-design-guide)
- [Kami document design system](https://kami.tw93.fun/)
- [Fintech design guide 2026 (Eleken)](https://www.eleken.co/blog-posts/modern-fintech-design-guide)
- [HKUDS/AI-Trader on GitHub](https://github.com/HKUDS/AI-Trader)
- [TradingAgents framework (Tauric Research)](https://github.com/tauricresearch/tradingagents)
- [Bitget agent-native exchange announcement](https://www.globenewswire.com/news-release/2026/04/06/3268287/0/en/Bitget-Gives-AI-Its-Own-Trading-Account-Advancing-Toward-an-Agent-Native-Exchange.html)
- [Public.com AI agents for investing](https://public.com/ai-agents)
- [Polymarket Q1 2026 volume (MEXC)](https://www.mexc.com/news/1062153)
- [Best copy trading platforms (ForexBrokers)](https://www.forexbrokers.com/guides/social-copy-trading)
- [Thailand crypto guide 2026 (OSL)](https://www.osl.com/en/bits/article/crypto-investing-in-thailand)
- [Vietnam licensing regime (Vietnam Briefing)](https://www.vietnam-briefing.com/news/vietnam-licensing-regime-cryptocurrency-exchanges-digital-economy.html/)
- [Crypto regulation Hong Kong, Japan, Taiwan (Law.asia)](https://law.asia/crypto-regulation-trends-hong-kong-japan-taiwan/)
- [Fintech localization 2026 (Honey Translations)](https://honeytranslations.com/blog/localization-for-fintech-apps-in-2026/)
- [Digital trust in Asia 2026 (Veriff)](https://www.veriff.com/identity-verification/digital-trust-asia-trends-2026)
- [Astro vs Next.js 2026 (Cosmic JS)](https://www.cosmicjs.com/blog/astro-vs-nextjs-2026)
- [Astro vs Next.js technical (Eastondev)](https://eastondev.com/blog/en/posts/dev/20251202-astro-vs-nextjs-comparison/)
- [Astro vs Next.js features (Contentful)](https://www.contentful.com/blog/astro-next-js-compared/)
- [Astro i18n routing](https://docs.astro.build/en/guides/internationalization/)
- [Cloudflare Pages vs Vercel vs Netlify (DanubeData)](https://danubedata.ro/blog/cloudflare-pages-vs-netlify-vs-vercel-static-hosting-2026)
- [Vercel vs Netlify vs Cloudflare Pages 2026 (DevToolReviews)](https://www.devtoolreviews.com/reviews/vercel-vs-netlify-vs-cloudflare-pages-2026)
- [SEO 2026 trends (Search Engine Land)](https://searchengineland.com/seo-2026-higher-standards-ai-influence-web-catching-up-473540)
