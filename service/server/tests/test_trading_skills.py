"""Plan 20 — trading skills registry, prompt injection, and admin CRUD."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import trading_skills

BASE_SLUGS = {s["slug"] for s in trading_skills.BASE_SKILLS}


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        trading_skills.invalidate_trading_skills_cache()

    def tearDown(self):
        trading_skills.invalidate_trading_skills_cache()
        self.tmp.cleanup()


class RegistryTests(_Db):
    def test_base_skills_seed_on_first_read(self):
        skills = trading_skills.all_skills(fresh=True)
        by_slug = {s["slug"]: s for s in skills}
        self.assertTrue(BASE_SLUGS.issubset(by_slug.keys()))
        for slug in BASE_SLUGS:
            self.assertTrue(by_slug[slug]["is_base"])
            self.assertTrue(by_slug[slug]["enabled"])
            self.assertTrue(by_slug[slug]["body"])

    def _patched_catalogue(self, slug: str, **changes):
        patched = [dict(s) for s in trading_skills.BASE_SKILLS]
        for i, s in enumerate(patched):
            if s["slug"] == slug:
                patched[i] = dict(s, **changes)
        by_slug = {s["slug"]: s for s in patched}
        return patch.multiple(trading_skills, BASE_SKILLS=patched,
                              _BASE_BY_SLUG=by_slug)

    def test_catalogue_upgrade_flows_to_untouched_rows(self):
        trading_skills.all_skills(fresh=True)  # seed at v1
        with self._patched_catalogue("data-honesty", body="v2 catalogue body",
                                     priority=61):
            trading_skills.invalidate_trading_skills_cache()
            skill = trading_skills.get_skill("data-honesty")
        self.assertEqual(skill["body"], "v2 catalogue body")
        self.assertEqual(skill["priority"], 61)
        self.assertEqual(skill["updated_by"], "seed-upgrade")

    def test_upgrade_preserves_disabled_state(self):
        trading_skills.all_skills(fresh=True)
        trading_skills.update_skill("exit-discipline", {"enabled": 0})
        # disabling is operator state, not a content edit — the body still
        # follows the catalogue, the switch stays off
        with self._patched_catalogue("exit-discipline", body="v2 exit body"):
            trading_skills.invalidate_trading_skills_cache()
            skill = trading_skills.get_skill("exit-discipline")
        self.assertEqual(skill["body"], "v2 exit body")
        self.assertFalse(skill["enabled"])

    def test_admin_edit_blocks_upgrade_until_reset(self):
        trading_skills.all_skills(fresh=True)
        trading_skills.update_skill("data-honesty", {"body": "my edit"},
                                    updated_by="t@t")
        with self._patched_catalogue("data-honesty", body="v2 body"):
            trading_skills.invalidate_trading_skills_cache()
            self.assertEqual(trading_skills.get_skill("data-honesty")["body"],
                             "my edit")
            # reset jumps to the CURRENT catalogue and re-arms auto-upgrade
            trading_skills.reset_skill("data-honesty")
            self.assertEqual(trading_skills.get_skill("data-honesty")["body"],
                             "v2 body")
        # catalogue back at v1: the reset row (stamped v2) is untouched-at-v2,
        # so it downgrades back with the catalogue — proving the hash re-arm
        trading_skills.invalidate_trading_skills_cache()
        base = next(s for s in trading_skills.BASE_SKILLS
                    if s["slug"] == "data-honesty")
        self.assertEqual(trading_skills.get_skill("data-honesty")["body"],
                         base["body"])

    def test_null_hash_backfills_only_on_exact_match(self):
        trading_skills.all_skills(fresh=True)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_skills SET catalog_hash = NULL "
                    "WHERE slug IN ('data-honesty', 'exit-discipline')")
        # pre-hash edit: content no longer matches the catalogue
        cur.execute("UPDATE trading_skills SET body = 'legacy edit' "
                    "WHERE slug = 'exit-discipline'")
        conn.commit()
        conn.close()
        trading_skills.all_skills(fresh=True)  # backfill pass
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT slug, catalog_hash FROM trading_skills "
                    "WHERE slug IN ('data-honesty', 'exit-discipline')")
        hashes = {r["slug"]: r["catalog_hash"] for r in cur.fetchall()}
        conn.close()
        self.assertIsNotNone(hashes["data-honesty"])   # matched -> stamped
        self.assertIsNone(hashes["exit-discipline"])   # edited -> protected
        self.assertEqual(trading_skills.get_skill("exit-discipline")["body"],
                         "legacy edit")

    def test_seed_never_overwrites_an_edit(self):
        trading_skills.all_skills(fresh=True)  # seed
        trading_skills.update_skill("data-honesty", {"body": "edited body"},
                                    updated_by="t@t")
        # A later read must keep the edit, not restore the catalogue text.
        skill = trading_skills.get_skill("data-honesty")
        self.assertEqual(skill["body"], "edited body")
        self.assertTrue(skill["is_base"])

    def test_selection_by_site(self):
        trader = {s["slug"] for s in trading_skills.skills_for_prompt("trader")}
        light = {s["slug"] for s in trading_skills.skills_for_prompt("light")}
        self.assertIn("market-regime-lens", trader)
        self.assertIn("thesis-validation", trader)
        self.assertNotIn("market-regime-lens", light)
        self.assertIn("risk-reward-structure", light)
        self.assertIn("position-management", light)
        self.assertIn("data-honesty", light)
        planner = {s["slug"] for s in trading_skills.skills_for_prompt("planner")}
        self.assertEqual(planner, {"position-sizing-discipline", "data-honesty",
                                   "catalyst-map", "watchlist-review",
                                   "portfolio-concentration"})
        self.assertEqual(trading_skills.skills_for_prompt("nonsense"), [])

    def test_horizon_discipline_rides_exit_sites(self):
        # Anti-churn skill (2026-08-03): must ride BOTH sites that produce
        # exit decisions — every observed intra-horizon churn close came
        # through the light route, opens come through trader.
        for site in ("light", "trader"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertIn("horizon-discipline", slugs)
            self.assertIn("### Horizon Discipline\n",
                          trading_skills.skills_block(site))
        for site in ("verifier", "planner"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertNotIn("horizon-discipline", slugs)

    def test_earnings_preview_rides_the_light_site_for_us_stock(self):
        # 2026-08-04: the print-gap discipline was trader-only while the light
        # route carried nearly every us-stock cycle — and until the earnings
        # date brief, no path knew a print was coming at all.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site, "us-stock")
            self.assertIn("### Earnings Preview\n", block,
                          f"earnings-preview missing from {site}/us-stock")
            self.assertIn("opening fresh exposure within days", block)
        self.assertNotIn("### Earnings Preview\n",
                         trading_skills.skills_block("light", "crypto"))

    def test_risk_reward_structure_warns_that_silence_forfeits_the_bracket(self):
        # 2026-08-04: 956 MSFT burned 3 consecutive cycles at conviction up to
        # 0.765 — the light route authored NO parseable bracket, the flat
        # default (8% stop / 15% target) stood in, and 15 < 2x8 fails the R:R
        # floor deterministically. The desk never knew its silence was the
        # cause. The skill must say so on every site that can author entries.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("silence forfeits the bracket", block,
                          f"authorship clause missing from {site}")
            self.assertIn("REFUSED at the gate", block)

    def test_risk_reward_structure_names_the_noise_floor(self):
        # Watch (a) fired 2026-08-05: SECOND sub-1% authored stop-out. 955
        # authored stop_pct 0.65 on leveraged SOL (rails had already rescued
        # a NEGATIVE authored target); price wandered +0.74% and donated
        # -17.6 within the hour. 941 paid -8.045 to the same class. The
        # bracket skill must name the too-NEAR failure mode as it names the
        # too-FAR one (reachable-exits).
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("noise-trigger, not protection", block,
                          f"noise-floor clause missing from {site}")
            self.assertIn("shrinking the stop to fit", block)

    def test_reentry_discipline_rides_both_sites(self):
        # 2026-08-05, the -57 day: 955/957 re-entered SHORT into a rising
        # tape repeatedly (short, cut, short, cut). The desk must know that
        # two same-direction losing closes flip the burden of proof.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("### Re-entry Discipline\n", block,
                          f"reentry-discipline missing from {site}")
            self.assertIn("burden of proof flips", block)
            self.assertIn("not new evidence", block)

    def test_exit_discipline_names_the_ledger_shape(self):
        # Same day: five banked wins (+0.5..+4.7) surrendered to two
        # oversized losses (-17.6, -31). The asymmetry is the bleed.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("SHAPE of your ledger", block,
                          f"ledger-shape clause missing from {site}")
            self.assertIn("cut losers early and small", block)

    def test_loss_aging_rides_both_sites(self):
        # HYPE case: 949 held a deteriorating short -4.6 -> -8.9 -> -14.5
        # across ~12h of consecutive holds, then capitulated at the worst
        # price. The sequence, not any single hold, was the failure.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("### Loss Aging\n", block,
                          f"loss-aging missing from {site}")
            self.assertIn("decision by default", block)
            self.assertIn("would I open this position now", block)

    def test_reachable_exits_covers_entry_churn(self):
        # 956 case: four identical refused entries at conviction up to 0.81.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("third identical attempt is", block,
                          f"entry-churn clause missing from {site}")
            self.assertIn("never resubmit the same refused numbers", block)

    def test_earnings_preview_covers_post_print(self):
        # SPCX case: +9.4% post-print gap; pre-print levels are stale.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site, "us-stock")
            self.assertIn("RESETS your map", block,
                          f"post-print clause missing from {site}")
            self.assertIn("both are trades on the old map", block)

    def test_reentry_discipline_teaches_flat_retirement(self):
        # 949 case (2026-08-05): flat for 7+ consecutive cycles at
        # conviction 0.24-0.29 after its -14.5 loss, burning an LLM read
        # per cycle. The never-traded idle rail cannot collect it and the
        # retire verb went unused — the desk needs to know that a flat
        # book with no arriving read IS the retire case.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("not waiting, it is occupying capital", block,
                          f"flat-retirement clause missing from {site}")
            self.assertIn("retire verb exists for exactly this", block)

    def test_flat_retirement_is_gated_on_the_streak_line(self):
        # Regression 2026-08-05: within hours of #238, FIVE newborn ZEC desks
        # retired on cycle 1 — one at conviction 0.70 on a thesis it agreed
        # with. The clause made retire salient with no precondition a fresh
        # desk could check. It must bind to the Streak brief line, which
        # renders only after 4+ consecutive flat holds.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("only when the Streak line", block,
                          f"newborn guard missing from {site}")
            self.assertIn("retiring at birth wastes the build", block)

    def test_risk_rail_reconciliation_rides_both_entry_sites(self):
        # 2026-08-05: run 971 authored a 3.5% stop while its equity brake sat
        # 0.72% away and was retired on a -0.62% move it had budgeted for.
        # An audit of 21 runs found the brake INSIDE the desk's own stop in
        # seven. The desk must reconcile its authored stop against the rail,
        # and must know an add divides the distance to it.
        for site in ("light", "trader"):
            block = trading_skills.skills_block(site)
            self.assertIn("Risk rail", block,
                          f"rail reconciliation missing from {site}")
            self.assertIn("doubling the position HALVES", block)

    def test_defaults_never_hit_the_budget(self):
        # The catalogue ships with EVERY skill enabled; the budget exists for
        # admin-authored additions, not to silently prune the defaults. Every
        # enabled matching skill must appear in the block for every site and
        # market combination.
        for site in trading_skills.PROMPT_SITES:
            for market in (None, "us-stock", "crypto"):
                block = trading_skills.skills_block(site, market)
                for skill in trading_skills.skills_for_prompt(site, market):
                    self.assertIn(f"### {skill['name']}\n", block,
                                  f"{skill['slug']} dropped from {site}/{market}")

    def test_seeded_market_scoping_survives_db_roundtrip(self):
        # Regression (prod 2026-08-02): the original seed path hard-coded
        # markets_json=None on insert, so earnings-preview lost its us-stock
        # scoping ON PROD and rode every market's trader prompt. The scoping
        # must hold through seed -> DB -> selection, not just in BASE_SKILLS.
        trading_skills.all_skills(fresh=True)
        crypto = {s["slug"] for s in trading_skills.skills_for_prompt("trader", "crypto")}
        us = {s["slug"] for s in trading_skills.skills_for_prompt("trader", "us-stock")}
        self.assertNotIn("earnings-preview", crypto)
        self.assertIn("earnings-preview", us)
        # Plan 21 port: each new skill rides exactly its own market.
        self.assertIn("crypto-regime-lens", crypto)
        self.assertNotIn("crypto-regime-lens", us)
        self.assertIn("bottom-confirmation", us)
        self.assertNotIn("bottom-confirmation", crypto)

    def test_plan21_skills_ride_their_trader_blocks(self):
        # The two hermes-work-package ports must actually render (not be
        # budget-skipped) in their market's trader block, and stay off the
        # exit-path light site — they are entry/posture methods.
        self.assertIn("### Crypto Regime Lens\n",
                      trading_skills.skills_block("trader", "crypto"))
        self.assertIn("### Bottom Confirmation\n",
                      trading_skills.skills_block("trader", "us-stock"))
        for site in ("light", "verifier", "planner"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertNotIn("crypto-regime-lens", slugs)
            self.assertNotIn("bottom-confirmation", slugs)

    def test_mined_statistical_skills_ride_every_trader_block(self):
        # The two agiprolabs-mining ports are market-agnostic entry/sizing
        # methods: they must render (not be budget-skipped) in EVERY market's
        # trader block, and stay off the exit-path light site.
        for market in (None, "us-stock", "crypto", "futures", "forex"):
            block = trading_skills.skills_block("trader", market)
            self.assertIn("### Volatility Context\n", block, market)
            self.assertIn("### Reversion Requires a Range\n", block, market)
        for site in ("light", "verifier", "planner"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertNotIn("volatility-context", slugs)
            self.assertNotIn("mean-reversion-guard", slugs)

    def test_stage_discipline_rides_us_stock_trader_only(self):
        # finance-skills mining (2026-08-04): an entry/posture method like
        # bottom-confirmation — it must render (not be budget-skipped) in the
        # us-stock trader block, stay off every other market's trader block,
        # and stay off the exit-path light site entirely.
        block = trading_skills.skills_block("trader", "us-stock")
        self.assertIn("### Stage Discipline\n", block)
        self.assertIn("never assume Stage 2", block)
        for market in (None, "crypto", "futures", "forex"):
            self.assertNotIn(
                "### Stage Discipline\n",
                trading_skills.skills_block("trader", market))
        for site in ("light", "verifier", "planner"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertNotIn("stage-discipline", slugs)

    def test_breadth_context_rides_us_stock_trader_only(self):
        # tradermonty mining (2026-08-04): teaches the desk to read the
        # breadth line the run_engine now injects — us-stock only, like the
        # feed itself. It must render (not be budget-skipped) in the
        # us-stock trader block and stay off everything else.
        block = trading_skills.skills_block("trader", "us-stock")
        self.assertIn("### Breadth Context\n", block)
        self.assertIn("never evidence of health", block)
        for market in (None, "crypto", "futures", "forex"):
            self.assertNotIn(
                "### Breadth Context\n",
                trading_skills.skills_block("trader", market))
        for site in ("light", "verifier", "planner"):
            slugs = {s["slug"] for s in trading_skills.skills_for_prompt(site)}
            self.assertNotIn("breadth-context", slugs)

    def test_selection_by_market(self):
        trading_skills.create_skill(
            "crypto-only", "Crypto Only", "crypto body", prompts=["trader"],
            markets=["crypto"], priority=1)
        crypto = {s["slug"] for s in trading_skills.skills_for_prompt("trader", "crypto")}
        stocks = {s["slug"] for s in trading_skills.skills_for_prompt("trader", "us-stock")}
        none_given = {s["slug"] for s in trading_skills.skills_for_prompt("trader")}
        self.assertIn("crypto-only", crypto)
        self.assertNotIn("crypto-only", stocks)
        self.assertNotIn("crypto-only", none_given)

    def test_disabled_skill_excluded(self):
        trading_skills.all_skills(fresh=True)
        trading_skills.update_skill("exit-discipline", {"enabled": 0})
        light = {s["slug"] for s in trading_skills.skills_for_prompt("light")}
        self.assertNotIn("exit-discipline", light)

    def test_block_framing(self):
        block = trading_skills.skills_block("trader", "crypto")
        self.assertIn("never override risk limits or execution gates", block)
        self.assertIn("Market Regime Lens", block)
        self.assertIn("Data Honesty", block)
        # No enabled skill for the site -> no header either.
        for slug in BASE_SLUGS:
            trading_skills.update_skill(slug, {"enabled": 0})
        self.assertEqual(trading_skills.skills_block("trader"), "")

    def test_block_budget_skips_whole_skills(self):
        # Three admin-authored max-size skills blow the trader budget; the
        # overflow must skip whole skills (the lowest-priority ones), never
        # truncate mid-body.
        trading_skills.create_skill(
            "huge", "Huge Skill", "x" * trading_skills.MAX_BODY_LEN,
            prompts=["trader"], priority=1)
        trading_skills.create_skill(
            "huge2", "Huge Skill Two", "y" * trading_skills.MAX_BODY_LEN,
            prompts=["trader"], priority=2)
        trading_skills.create_skill(
            "huge3", "Huge Skill Three", "z" * trading_skills.MAX_BODY_LEN,
            prompts=["trader"], priority=3)
        block = trading_skills.skills_block("trader")
        self.assertIn("Huge Skill", block)
        # Budget: header + sections never exceed MAX_BLOCK_LEN (+ final \n).
        self.assertLessEqual(len(block), trading_skills.MAX_BLOCK_LEN + 1)
        last = trading_skills.skills_for_prompt("trader")[-1]
        self.assertNotIn(f"### {last['name']}\n", block)
        self.assertIn("x" * trading_skills.MAX_BODY_LEN, block)

    def test_fail_soft_when_table_broken(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DROP TABLE trading_skills")
        conn.commit()
        conn.close()
        trading_skills.invalidate_trading_skills_cache()
        self.assertEqual(trading_skills.skills_block("trader"), "")
        self.assertEqual(trading_skills.all_skills(fresh=True), [])


class PromptInjectionTests(_Db):
    def test_trader_prompt_carries_skills(self):
        import analysis_agents
        captured = []

        def fake_generate(prompt, **kwargs):
            captured.append(prompt)
            return '{"action":"hold","confidence":0.5,"rationale":"r","report":"rep"}'

        skills = analysis_agents._skills_block("trader", "crypto")
        self.assertIn("Market Regime Lens", skills)
        with patch.object(analysis_agents, "llm_configured", return_value=True), \
             patch.object(analysis_agents, "generate_text", side_effect=fake_generate):
            analysis_agents._trader_risk_decision(
                "BTC", "crypto", {"news": "n", "sentiment": "s",
                                  "fundamentals_macro": "f", "technical": "t"},
                {"current_price": 100.0}, {}, "en", skills=skills)
        self.assertTrue(any("Market Regime Lens" in p for p in captured))
        self.assertTrue(any("Position Sizing Discipline" in p for p in captured))

    def test_verifier_prompt_carries_skills(self):
        import analysis_agents
        captured = []

        def fake_generate(prompt, **kwargs):
            captured.append(prompt)
            return '{"verdict":"upheld","adjusted_confidence":0.5,"reason":"ok"}'

        skills = analysis_agents._skills_block("verifier", "crypto")
        self.assertIn("Conviction Calibration", skills)
        self.assertNotIn("Market Regime Lens", skills)
        with patch.object(analysis_agents, "llm_configured", return_value=True), \
             patch.object(analysis_agents, "generate_text", side_effect=fake_generate):
            analysis_agents._verify_decision(
                "BTC", "crypto", {"news": "n", "sentiment": "s",
                                  "fundamentals_macro": "f", "technical": "t"},
                {"current_price": 100.0},
                {"action": "buy", "confidence": 0.7, "rationale": "r"},
                "en", skills=skills)
        self.assertTrue(any("Conviction Calibration" in p for p in captured))

    def test_light_prompt_carries_light_skills_only(self):
        import run_engine
        captured = []

        def fake_generate(prompt, **kwargs):
            captured.append(prompt)
            return ('{"action":"hold","confidence":0.5,'
                    '"report":"rep"}')

        run = {"id": 1, "agent_id": 1, "symbol": "BTC", "market": "crypto",
               "market_type": "spot", "stop_conditions_json": "{}"}
        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]), \
             patch("llm_client.generate_text", side_effect=fake_generate):
            run_engine._light_analysis(run, {})
        self.assertEqual(len(captured), 1)
        prompt = captured[0]
        self.assertIn("Risk/Reward Structure", prompt)
        self.assertIn("Exit Discipline", prompt)
        self.assertIn("Position Management", prompt)
        self.assertIn("Data Honesty", prompt)
        # trader-only skills must not ride on the cheap path
        self.assertNotIn("Market Regime Lens", prompt)
        self.assertNotIn("Conviction Calibration", prompt)

    def test_light_path_survives_broken_registry(self):
        import run_engine
        captured = []

        def fake_generate(prompt, **kwargs):
            captured.append(prompt)
            return '{"action":"hold","confidence":0.5,"report":"rep"}'

        run = {"id": 1, "agent_id": 1, "symbol": "BTC", "market": "crypto",
               "market_type": "spot", "stop_conditions_json": "{}"}
        with patch("price_fetcher.get_price_from_market", return_value=100.0), \
             patch("price_fetcher.get_daily_candles", return_value=[]), \
             patch("llm_client.generate_text", side_effect=fake_generate), \
             patch("trading_skills.skills_block", side_effect=RuntimeError("boom")):
            out = run_engine._light_analysis(run, {})
        self.assertEqual(out["decision"].get("action"), "hold")
        self.assertNotIn("TRADING SKILLS", captured[0])


class AdminRoutesTests(_Db):
    def setUp(self):
        super().setUp()
        from routes import create_app
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login",
                             json={"email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}

    def test_auth_required(self):
        self.assertIn(self.client.get("/api/admin/skills").status_code, (401, 403))

    def test_list_includes_base(self):
        r = self.client.get("/api/admin/skills", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        slugs = {s["slug"] for s in r.json()["skills"]}
        self.assertTrue(BASE_SLUGS.issubset(slugs))

    def test_create_validate_and_duplicate(self):
        good = {"slug": "my-skill", "name": "My Skill", "body": "Do the thing.",
                "prompts": ["light"]}
        r = self.client.post("/api/admin/skills", json=good, headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["skill"]["is_base"])
        # duplicate slug
        self.assertEqual(self.client.post("/api/admin/skills", json=good,
                                          headers=self.admin).status_code, 409)
        # bad slug
        bad = dict(good, slug="Bad Slug!")
        self.assertEqual(self.client.post("/api/admin/skills", json=bad,
                                          headers=self.admin).status_code, 400)
        # unknown prompt site
        bad = dict(good, slug="ok-slug", prompts=["router"])
        self.assertEqual(self.client.post("/api/admin/skills", json=bad,
                                          headers=self.admin).status_code, 400)
        # oversize body
        bad = dict(good, slug="ok-slug2",
                   body="x" * (trading_skills.MAX_BODY_LEN + 1))
        self.assertEqual(self.client.post("/api/admin/skills", json=bad,
                                          headers=self.admin).status_code, 400)
        # empty prompts
        bad = dict(good, slug="ok-slug3", prompts=[])
        self.assertEqual(self.client.post("/api/admin/skills", json=bad,
                                          headers=self.admin).status_code, 400)
        # the created skill is live for selection immediately
        light = {s["slug"] for s in trading_skills.skills_for_prompt("light")}
        self.assertIn("my-skill", light)

    def test_patch_base_and_custom(self):
        r = self.client.patch("/api/admin/skills/data-honesty",
                              json={"body": "tightened body", "enabled": False},
                              headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        skill = r.json()["skill"]
        self.assertEqual(skill["body"], "tightened body")
        self.assertFalse(skill["enabled"])
        self.assertTrue(skill["is_base"])
        self.assertEqual(self.client.patch("/api/admin/skills/nope",
                                           json={"body": "x"},
                                           headers=self.admin).status_code, 404)
        self.assertEqual(self.client.patch("/api/admin/skills/data-honesty",
                                           json={}, headers=self.admin).status_code, 400)

    def test_reset_restores_base_defaults(self):
        self.client.patch("/api/admin/skills/data-honesty",
                          json={"body": "scribble", "enabled": False},
                          headers=self.admin)
        r = self.client.post("/api/admin/skills/data-honesty/reset",
                             headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        skill = r.json()["skill"]
        base = next(s for s in trading_skills.BASE_SKILLS
                    if s["slug"] == "data-honesty")
        self.assertEqual(skill["body"], base["body"])
        self.assertTrue(skill["enabled"])
        # custom skills cannot be reset
        self.client.post("/api/admin/skills",
                         json={"slug": "cust", "name": "C", "body": "b",
                               "prompts": ["light"]}, headers=self.admin)
        self.assertEqual(self.client.post("/api/admin/skills/cust/reset",
                                          headers=self.admin).status_code, 400)

    def test_delete_refuses_base_allows_custom(self):
        r = self.client.delete("/api/admin/skills/data-honesty", headers=self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("disable or reset", r.json()["detail"])
        self.client.post("/api/admin/skills",
                         json={"slug": "byebye", "name": "B", "body": "b",
                               "prompts": ["light"]}, headers=self.admin)
        self.assertEqual(self.client.delete("/api/admin/skills/byebye",
                                            headers=self.admin).status_code, 200)
        self.assertIsNone(trading_skills.get_skill("byebye"))

    def test_writes_are_audited(self):
        self.client.post("/api/admin/skills",
                         json={"slug": "aud", "name": "A", "body": "b",
                               "prompts": ["light"]}, headers=self.admin)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT action, target FROM admin_audit_log "
                    "WHERE action = 'skill.create'")
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "skill:aud")


if __name__ == "__main__":
    unittest.main()
