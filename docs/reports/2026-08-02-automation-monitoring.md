# Automation monitoring — 2026-08-02 hourly loop (STOPPED by owner 18:4xZ after 8 cycles)

Owner-requested hourly loop (cron 474c5397, :21 each hour). Cycle notes newest-first.

## NIGHT LOOP (restarted 23:50Z, cron 7a915d6a :11 hourly, until 2026-08-03 17:00Z / 10:00 PDT)

### LOOP ENDED — cron 7a915d6a deleted 2026-08-05 20:02Z

**Only 2 cycles actually ran** (2026-08-02 23:50Z and 2026-08-03 00:25Z). The
session then went idle and the remaining fires never executed; the next wake
landed 2026-08-05 20:02Z, past the 08-03 10:00 PDT stop time, so the job was
deleted without running a cycle. **The 08-03 00:30Z → 08-05 20:00Z window was
NOT monitored by this loop** — anything the fleet did in those ~2.8 days is
unreviewed here. The one change shipped from this loop stands:
horizon-discipline (PR #199, image `20260803-horizonskill`), whose first
post-deploy decisions (01:01Z 08-03) were never observed — its effect on the
churn pattern is still UNVERIFIED and is the first thing to check if
monitoring resumes.

### Night cycle 2 — 2026-08-03 00:25Z (light)

**933 BTC retired itself, slot refilled in 43s — E3 machinery textbook:** cyc-6
00:02:20Z desk emitted `retire` (6 consecutive holds, conf .42–.48 never near
gate) → desk_retired stop → fleet 26 built **937 ZECUSDT spot** at 00:03:11Z;
its cyc-1 is a disciplined hold (conf .48). Note: the 00:01–00:03Z decisions
PREDATE the horizon-skill deploy (worker recreated 00:17Z) — first decisions
riding the new light block land 01:01Z (932/934) / 01:03Z (937).

Health: worker/backend Up 8m post-swap, 0 tracebacks both, book flat (0 open
positions), no trades this hour, docs page 200. Running: 932 (−1.27), 934,
935 (weekend-gated), 937. Nothing to act on.

### Night cycle 1 — 2026-08-02 23:50Z–00:20Z

**Book was RESET by the owner at 18:55–18:57Z:** fleet 25 stop_all (908 final
+4.42, 931 final −3.26 — stopped 25 min after entry) plus user_stop on all solo
runs (915, 920 +0.29, 925 −0.52, 928, 930 −0.52). New book: **fleet 26** =
932 SOL / 933 BTC / 934 ETH futures (created 18:59Z) + **935 SPCX** us-stock solo
(19:40Z). Zero open positions as of 23:50Z.

**Churn instance #9 — run 932, on the fresh fleet:** short 6.108 SOL @73.535
19:01Z (conf .58) → intent=close cover @73.677 20:01Z, exactly ONE cycle later,
−1.27 (price −0.87 + fees 0.40). Close rationale again capital-protection
boilerplate ("small loss, R:R unfavorable"). Adapt losing_close engaged
correctly (size_mult 0.75, conf_bump 0.05, loss cooldown cyc-3). Intent path
still executing exits correctly post-reset (compiled cover 1.0, real trade).

**ACTION SHIPPED TO PROD: Horizon Discipline skill** (PR #199 squash `1975f36`,
image `20260803-horizonskill`, surgical 2 files, no migration, no SPA):
23rd BASE_SKILLS entry, prompts light+trader, priority 42 — sub-horizon exits
need one named trigger from a closed set; "protect capital"/"R:R now
unfavorable"/restated-entry-in-reverse are NOT triggers; sub-hour round trips
are negative-expectancy. MAX_BLOCK_LEN 14000→16000 (trader/us-stock set now
needs 14530; budget-invariant test guards). Local: 26/26 skills tests +
3038-test full suite green; CI green. Deploy: clean path (both files
byte-identical prod==5ad700a), guard held pre-build AND at swap
(tiergates/23:24:34). Verified 3×: (1) site+api 200, 0 tb both containers,
23 skills, HD in light (4582) + trader (13891) + trader/us-stock (14530≤16000)
blocks, absent verifier/planner; (2) DB 23/23 enabled, row stamped
updated_by=seed prio 42, earnings-preview us-stock scoping intact, 37 worker
tasks; (3) strict catalog_hash == _content_hash(catalogue) in-container.
NEXT-CYCLE CHECK: first fleet-26 decision after 01:01Z rides the new light
block — watch whether churn closes now carry a named trigger or hold.
Backups /tmp/horizonskill-bak-20260803, .env.bak-20260803-horizonskill;
rollback image 20260802-tiergates.

**Other findings:**
- Float-precision gate artifact: 932 cyc-5 sell blocked "confidence 0.58 below
  threshold 0.5800000000000001" (0.53 base + 0.05 conf_bump in float). Direction
  was pro-caution here (post-loss re-short) but an exactly-at-gate decision
  should pass; epsilon fix candidate, low priority.
- 933 BTC 5/5 disciplined holds (conf .42–.48 < gate). 934 ETH 5/5 holds.
  935 SPCX weekend `market closed` gate_skips — all correct.
- Prod deploys by parallel sessions today: watchdogseed 19:33Z, fleetmail
  20:29Z, guidetheme 23:01Z, tiergates 23:25Z (current). Worker healthy after
  recreate: liquidation_watch + hot_issue_daemon running, 0 tracebacks,
  market-news errors=3 (known).
- Docs: /docs/how-it-works 200; guide API how-it-works-en 200 35KB /
  ko 200 38.5KB; liq-defense-en/ko 200; local plan-16 HTML intact. (Note:
  guide doc keys are `<group>-<lang>`, not `?lang=` — first probe 404'd on a
  malformed key, NOT a regression.)

## FINAL WRAP-UP (12:15Z–18:30Z, 8 cycles)

Shipped to prod: **RUN_ORDER_INTENT=apply** (Plan 17 phase-1, exits-only) — verified
live 5×: close-full ×3 (920 +0.29, 921, 925), reduce-half ×3 (916's scale-outs),
intent correctly overrides weaker legacy verbs and bypasses entry gates. The
close→short-add inversion class (killed 919's +6.79 peak) is dead.

Day realized net ≈ **+2.0** (916 +3.08 best, 908 +4.42, 920 +0.29, 930 +0.15leg;
churn −4.9 across 8 intra-horizon round-trips; 919 −0.83, 921 −3.25 pre-flip).

Prioritized fix backlog (evidence counts in cycle notes below):
1. Horizon enforcement promotion — 8 churn round-trips, desks rarely survive 2
   cycles with a position; every one had a days-out stated horizon. TOP LEVER.
2. Stale run-peak trail re-anchor when book goes flat — killed 921 in 28s.
3. Cap desk trail_arm_pct ≤ target_pct — 3 unreachable-trail instances.
4. Parser: strip markdown ** before JSON parse — 2 lost decisions (conf 0.0).
5. Investigate phantom 15%/8% house bracket (rr_floor refuses at 1.875) — 2 blocks.
6. Cosmetic: post-stop race cycle (2×), UI surfacing 409 exclusivity reason,
   5 orphan draft runs (922/924/926/927/929) to delete, 928 spot-short dead weight.

## Cycle 8 — 2026-08-02 18:30Z

**916 ZEC finished the day's best run:** stop_event:at_time flattened the last
quarter @471.62 → final **+3.08 realized**, lifecycle textbook (3 halvings +
timed flatten, 3/3 winning closes). Fleet 25 refilled the slot in 30 seconds
with 931 BTCUSDT — short 0.0226@63296, but note scores risk_context 1.0 /
entry_quality 0.9 (suspiciously maxed) drove size_scale 1.0 → full notional.

**Churn resumed as ETH bounced 1855→1868 (tally now 8 round-trips, ≈−4.9):**
- 925 XRP: short 16:59 → close 17:30 (31 min) @1.0815, −0.37; close rationale
  INCOHERENT: "eliminate exposure while the downtrend persists" (if downtrend
  persists, you keep the short). Conf 0.72 on a self-contradictory exit.
- 930 SOL: short 17:10 → close 17:40 (30 min) @73.30, −0.58; margin-health
  rationale defensible (tape moved against), but again 30 min vs 36h horizon.
The pattern is exact: desks rarely survive 2 cycles with a position on.

**Recurring issues:** (a) 15%/8% phantom bracket blocked 923's short via
rr_floor (instance #2 today; where does this bracket come from? — investigate,
it may be refusing good entries at R:R 1.875); (b) post-stop race cycle #2
(923 events after idle_retired, cosmetic); (c) 923 idle_retired 12 cycles.

Day realized net ≈ **+2.0** (dip: churn + 931 entry fee). Open: 931 BTC short
+0.25u. 908 loss-cooldown (adapt), 920/928 holds, 915 weekend.

**No churn this hour** — first hour since the flip with zero intra-horizon
round-trips. 925 re-shorted XRP (185@1.0805) with SANE self-authored params
(stop 4%/target 9%, trail_arm 5% — the desk fixed its own 40% trail!). 930
re-shorted SOL (2.735@73.12, conf .78/conv .765 strong) BUT trail_arm 40%
AGAIN → activate $80 vs max-possible ~$14: unreachable-trail instance #3
(rail candidate hardening: cap trail_arm ≤ target_pct).

**New machinery observed working:**
- `thesis_review` loop live: 916 "intact — 3/3 short closes won ~3.53%";
  908 "weakened — 1/3 wins" → adapt size_mult 0.75/0.5 + conf_bump 0.1 +
  loss cooldown. Textbook self-correction.
- First `arm` intent journaled (916: if price_above 478 → reduce 0.5) —
  conditional orders in the vocabulary; arm execution not built (by design).

**Issue tally:** 923 cyc-9 parse failure conf 0.0 — the gpt-oss model wrapped
JSON keys in markdown bold (`**"confidence": 0.66,**`), 2nd identical instance
today (928 cyc-2). Parser-hardening candidate: strip ** before JSON parse.

Book: 3 shorts (ZEC +0.81u, XRP −0.2u, SOL −0.3u). Day realized ≈ **+3.0**
(dip from 3.2 = new entry fees). Health clean; 915 weekend; 920 defensive holds.

**NEW DEFECT SHAPE — stale run-peak instantly killed a fresh probe (run 921):**
15:37:33 desk opened a 0.05-budget short probe (1.368 SOL @73.08) with desk trail
activate_usd 0.8 / giveback 0.15. **28 seconds later** trailing_lock fired at the
SAME price (zero move, −0.09 fees) and stopped the whole run (realized −3.25;
auto-restart → 930). Why: the run's peak_pnl_usd (+2.74) survives from the
POSITION CLOSED HOURS EARLIER; the fresh trail (activate 0.8 ≤ stale peak 2.74,
current total −3.2 « peak×0.85) armed-and-fired against history. Fix candidate:
reset/re-anchor peak when the book goes flat (positions→0), or track trail
against per-position peak. 1 instance, cheap this time — could kill a winner.

**916 third halving:** covered 0.343 @469.83 (+1.14) → realized **+2.56**, last
quarter riding +0.93u. The intent path does all the work (legacy verdicts were
sub-gate buys; reduce executes on the exit asymmetry). Model run of the day.

**Churn continues but turned profitable once:** 930 (921's replacement) shorted
2.737@73.06 (conf .71/conv .73) → closed 30 min later @72.94 "+$0.42 확보" →
+0.15 net. 908 round-tripped its ETH long (buy 1858.1 15:17 → reduce-1.0 sell
1856.9 16:18): −0.58 leg. Churn tally today: 6 intra-horizon round-trips
(921×3, 925×1, 930×1, 908×1), net ≈ −3.9 across them. Horizon enforcement
evidence keeps building — every one had a stated hold-until days out.

Book: only ZEC quarter-short open. Day realized net ≈ **+3.2** (rising: 2.2 →
2.6 → 3.2). Health clean; 928 conviction present again; 915 weekend-idle;
920 low-conviction holds post-cooldown.

**916 ZEC is the model citizen:** scaled out of its winner in halves twice
(reduce 0.5 → +0.46 more banked; realized **+1.42**, quarter position riding
+0.86u). Adapt journaled winning_close +1.55. This is exactly the shape we want.

**Churn pattern now 2 runs / 4 instances:** 925 XRP repeated 921's whipsaw —
short @1.0814 (14:28) → intent=close @1.0807 (14:59, 31 min later): price +0.39,
fees 0.54, net −0.15. Close rationale "protects margin health" at conviction
0.295 while margin was fine — weak. BOTH runs' own order_plan horizons (hold to
Aug-4) would have prevented these exits; horizon is still shadow-only. Today's
churn cost ≈ −3.3 total. RECOMMENDATION FORMING: promote horizon enforcement
(needs code, not just env — evidence file building here).

**908 re-entered long** 0.285 ETH @1858.1 (conf .68/conv .585, stop 1.11%/target
2.6%, RR 2.34 passed floor; adapt size_mult 0.75 shrank the order correctly).
920/921/925 in re-entry cooldowns (leverage-scaled, working). 923 patient holds
w/ coherent breakout thesis. 928 stopped attempting spot-shorts (holds now).

Day realized ≈ **+2.6 net** (908 +5.00, 916 +1.42, 920 +0.29, 919 −0.83,
921 −3.16, 925 −0.15). Health: clean logs, feeds green, daemon idle-armed.

**Third intent verb live — REDUCE works:** 14:16:50 run 916 intent=reduce 0.5
(legacy said short-ADD!) → real cover 1.3727 ZEC @472.02, banked +1.84−0.29 fee;
realized −0.58 → **+0.96**, half short still on (~+1.7u). Every exit verb
(close-full ×2, reduce-half ×1) has now executed correctly on prod.

**Churn watch — run 921 whipsawed:** cyc 7 (13:36) desk OPENED short 2.746@72.82
(small 0.1-budget probe) → cyc 8 (14:06, 30 min later) intent=close covered @72.95:
−0.36 price −0.18 fees. Run realized now −3.16 over 3 losing round trips today.
NOTE: the desk's own horizon (order_plan hold-until 2026-08-04) would have
prevented cyc-8's exit — horizon is shadow-only (`horizon_shadow.would_hold`).
Churn is now driven by the desk flip-flopping between cycles, not by inversion.

**Other:** 918 BTC idle_retired 13:45 after 12/12 holds (slot freed, correct;
one post-stop cycle raced in at 13:46, cosmetic). 925 XRP opened short 554.8
@1.0814 (conf .62/conv .66, stop .61%/target 1.22%, R:R 2.0) — but trail_arm_pct
40 → activate_usd 240 on a ~$600 position: trail will NEVER arm (919-class
unreachable-trail shape, this time desk-authored). 908 buy blocked by rr_floor
(reward 278.31 < 2× risk 148.43 — 15%/8% bracket, refusal correct + merciful in
this tape). 928 cycle-2 conviction_missing with malformed report JSON (gpt-oss
parse hiccup, 1 instance). 920 in 120m re-entry cooldown. 915 weekend-idle.

Health: 0 tracebacks, 0 "no LLM verdict", feeds green. Day realized ≈ **+2.2 net**
(908 +5.24, 916 +0.96, 920 +0.29, 919 −0.83, 921 −3.16, 925 −0.27).

**Second live apply-mode win:** 12:35:57Z run 921 desk `intent: close` ("전량 청산")
→ REAL cover 44.43 SOL @73.08 (full position; intent 1.0 correctly overrode the
order_params 0.05 trim). Run net −2.63, of which 2.92 is FEES (price side +0.30).
Without apply this was 919's add-churn shape all over again — leak plugged.

**Owner activity 12:54–12:55Z** (their Mac Chrome on /automation, 136.52.175.68):
8 runs created, 3 started — 923 ETH fut, 925 XRP fut, 928 ETH spot. Five 409'd on
start (exclusivity refusing dup symbol runs: 927 SOL vs running 921 etc.) leaving
orphan DRAFTS 922/924/926/927/929. UI point: each 409 pushed the owner to re-create
instead of surfacing why. (923 ETH fut started fine beside running 920 ETH fut —
exclusivity behavior inconsistent between the two? worth a look later.)

**Book:** 916 ZEC short 2.745@473.36 opened 13:16Z (conf 0.68/conv 0.72, stop 1.3%
/target 3.4%) — ~+2.5 unrealized. 920 flat +0.294 realized, cycles hourly. 921 flat
−2.63, re-entry cooldown then flat cycles. 918 BTC 11/11 disciplined holds. 915
TSLA weekend-idle. 908 +5.24 holds. 923/925 cycle-1&2 holds (sane reasons).
**928 ETH SPOT is dead weight: desk wants short (conf 0.66), spot can't — "spot
sell with no inventory" skip; will burn LLM cycles until tape turns bullish.**

Health: worker/backend clean, docs 200, liq daemon idle-armed (only ZEC 1x-ish
short open), skills 22/22. New-run params: 923/925 max_bet ~$1000 futures 2x.

No change vs cycle 1 wrap-up. Worker/backend Up 14m post-recreate, event stream
current, LLM 200s. 920 cover visible in worker logs ("[Position] ETH: closed short
position", "run 920 executed signal 295"). 921 short 44.4 SOL, desk horizon holds
until 13:05:46Z (horizon_shadow) — next decision then. 908/916 next cycles ~12:45.
915 weekend-idle, 918 disciplined holds. No failures, no action.

## Cycle 1 — 2026-08-02 ~12:15Z

**Book state** (6 running runs, agent 6):

| run | symbol | mkt | fleet | realized | peak | note |
|-----|--------|-----|-------|----------|------|------|
| 908 | ETHUSDT | spot | 25 | +5.24 | 16.26 | stop-loss exit 11:56Z sold 0.3346@1851.7 (leg −8.38, adapt cooldown armed) |
| 916 | ZECUSDT | fut | 25 | 0.00 | — | 5 decisions all hold, no trades |
| 915 | TSLA | us-stock | — | 0.00 | — | weekend: `market closed` gate_skips, correct |
| 918 | BTC | fut | — | 0.00 | — | 8 holds, conf 0.34–0.58 < 0.65 gate, no trades |
| 920 | ETH | fut | — | −0.02 | 0.49 | short 0.0267@1870.69, ~+0.45 unrealized |
| 921 | SOL | fut | — | −1.46 (fees) | 2.74 | short 44.43@73.087 avg, ~+0.48 unrealized |

Stopped since 06:00Z: 907 SOLUSDT idle_retired flat; **919 SOL short peaked +6.79 → realized −0.83** via trailing_lock (auto-restarted as 921).

**KEY FINDING + PROD CHANGE — Plan 17 phase-1 flipped to apply.**
Run 919's desk emitted `intent: close` ("lock in profit / 청산") on cycles 2,3,4,5
(08:45–10:16Z) while the legacy futures mapping (`sell`→short) instead ADDED to the
short 3×, quadrupling the position (2.7→84.6 SOL), paying $5.57 total fees, and the
trailing lock finally flattened at −0.83 after a +6.79 peak. Run 921 repeated the
identical inversion at 12:05Z (intent=close, compiled=[cover 1.0] → executed short
ADD 27.39). 7-day shadow tally: 54 close intents = 18 agree-cover + 19 agree-sell +
**7 inverted to short-adds** + 10 riding on `hold`; 65 reduce intents; 1 flip.
Mechanism understood (desk says "sell" meaning "close" while short; futures remap
turns it into an add), reproduced across ≥3 runs and 2 days, measurable P&L damage,
and the fix is the DESIGNED phase-1 rollout gated on exactly this shadow evidence.

Action taken 12:20Z: `RUN_ORDER_INTENT=apply` added to prod .env (backup
`.env.bak-20260802-intent`), worker+backend recreated (compose env propagation),
flag verified `apply` in both containers, site 200, worker loops healthy.
Apply mode executes ONLY reduce/close (exits) — risk-shedding by construction;
opens/adds/flips still shadow. Rollback: remove line, `docker compose --profile
prod up -d worker`.

**Feature checks:**
- Liquidation defense (plan 16): `liquidation_watch` task running, `LIQ_REFLEX=true`,
  zero escalation events — correctly idle (2x shorts far from liq).
- Trading skills (plan 20): registry 22/22 enabled on prod (tmport image
  20260802-tmport deployed ~11:15Z with PR #193/194); injection is prompt-level
  (not journaled) — no error evidence.
- /docs/how-it-works: en 200 (35KB) / ko 200 (38.5KB) via `/api/guide/doc/…` with
  member auth. July-31 snapshot gap "slug not registered" is RESOLVED.
- Worker/backend healthy, 0 tracebacks in 4h; market-news feed `errors=3`
  (recurring, low-sev, watch).

**VERIFIED 12:33:23Z (two passes — event + state):** run 920 cycle-4 emitted
`order_intent mode:"apply", intent:close, compiled:[cover]` and the engine executed
a REAL `cover` 0.02672811 ETH @ 1858.0 (full position). Run 920 realized flipped
−0.02 → **+0.294**; position row gone. Before the flip this exact shape was a
short-ADD inversion. Plan 17 phase-1 works on prod.

**Issues / watch list:**
1. ~~Verify first apply-mode exit executes as cover~~ DONE (above). Keep watching 921's next close intent.
2. 908 (fleet 25 spot long ETH) vs 920 (solo futures short ETH) held opposite
   directions simultaneously — book-level netting/coherence question for the desk.
3. 918 BTC: 8/8 holds — data-starved or genuinely quiet; watch for stall.
4. Add-churn: 919 paid $5.57 fees on $6.2k notional churn; apply-mode exits should
   reduce this, verify.
5. Market-news `errors=3` each refresh.
