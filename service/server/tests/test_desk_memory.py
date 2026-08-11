"""The desk corpus — storage, retrieval and ingest.

Owner, 2026-08-06: "RAG keep all analysis and monitoring for this session and
sooppiy AI".
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import database
import desk_memory
import desk_memory_ingest


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()


class StorageTests(_Db):
    def test_remember_then_find(self):
        desk_memory.remember(
            "monitoring", "notes.md#arms",
            "Arms are set too far",
            "Of 60+ armed levels only two ever fired. The desk sizes the arm "
            "to a whole ordinary day when its next look is 30 minutes away.")
        hits = desk_memory.search("armed level never fired")
        self.assertEqual(len(hits), 1)
        self.assertIn("only two ever fired", hits[0]["body"])
        self.assertGreater(hits[0]["score"], 0)

    def test_reingest_is_idempotent(self):
        for _ in range(3):
            desk_memory.remember("monitoring", "a.md#x", "T", "body text here")
        self.assertEqual(desk_memory.stats()["total"], 1)

    def test_edited_chunk_is_stored_not_silently_kept_stale(self):
        """Monitoring notes are corrected in place; an edit must land."""
        desk_memory.remember("monitoring", "a.md#x", "T", "the old finding")
        desk_memory.remember("monitoring", "a.md#x", "T", "the corrected finding")
        self.assertEqual(desk_memory.stats()["total"], 2)

    def test_preloaded_shas_replace_the_per_chunk_lookup(self):
        """Measured on prod: a no-op ingest took 26-33s because it issued one
        SELECT per chunk. The pre-loaded set must dedupe identically."""
        desk_memory.remember("monitoring", "a.md#x", "T", "the first finding")
        seen = desk_memory.known_shas()
        self.assertEqual(len(seen), 1)
        # already stored -> skipped without touching the database
        self.assertIsNone(desk_memory.remember("monitoring", "a.md#x", "T",
                                               "the first finding", known=seen))
        # new -> stored, and the set is updated in place so a duplicate later
        # in the SAME batch is caught too
        self.assertIsNotNone(desk_memory.remember("monitoring", "b.md#x", "T",
                                                  "a second finding", known=seen))
        self.assertEqual(len(seen), 2)
        self.assertIsNone(desk_memory.remember("monitoring", "b.md#x", "T",
                                               "a second finding", known=seen))
        self.assertEqual(desk_memory.stats()["total"], 2)

    def test_empty_body_is_not_stored(self):
        self.assertIsNone(desk_memory.remember("monitoring", "a.md", "T", "   "))
        self.assertEqual(desk_memory.stats()["total"], 0)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            desk_memory.remember("gossip", "a.md", "T", "body")


class RankingTests(_Db):
    def test_a_corpus_wide_term_does_not_decide_the_ranking(self):
        """Every monitoring note says "run". If a term that appears in the
        whole corpus scored like a rare one, retrieval would return whatever
        was longest rather than whatever was relevant."""
        for i in range(12):
            desk_memory.remember("monitoring", f"n{i}.md#x", f"note {i}",
                                 f"the run cycled and the run reported {i} " * 6)
        desk_memory.remember("monitoring", "hit.md#x", "liquidation",
                             "the run was liquidated when margin fell short")
        hits = desk_memory.search("run liquidated margin", limit=3)
        self.assertEqual(hits[0]["source"], "hit.md#x")

    def test_a_term_in_every_document_carries_almost_no_signal(self):
        """Isolates the IDF term. The ranking test above does NOT: its target
        also wins on term coverage, so it passed with IDF disabled. Here every
        document contains "run", so "run" alone must rank nothing."""
        for i in range(12):
            desk_memory.remember("monitoring", f"c{i}.md#x", f"note {i}",
                                 "the run cycled and the run reported and the "
                                 "run closed")
        desk_memory.remember("monitoring", "rare.md#x", "liquidation",
                             "the run was liquidated when margin fell short")
        common = desk_memory.search("run", limit=20)
        rare = desk_memory.search("liquidated", limit=20)
        self.assertTrue(common, "the common term should still match something")
        self.assertLess(max(h["score"] for h in common), 0.2,
                        "a term present in every document is being scored as "
                        "if it were rare")
        self.assertGreater(rare[0]["score"], 1.0,
                           "a term unique to one document should score high")

    def test_market_scoping_keeps_general_knowledge(self):
        desk_memory.remember("monitoring", "gen.md#x", "general",
                             "fees must be cleared before a trade can pay")
        desk_memory.remember("monitoring", "c.md#x", "crypto only",
                             "fees on perpetual funding accrue hourly",
                             market="crypto")
        desk_memory.remember("monitoring", "s.md#x", "stock only",
                             "fees on stock commissions are fixed",
                             market="us-stock")
        got = {h["source"] for h in desk_memory.search("fees", market="crypto",
                                                       limit=10)}
        self.assertIn("gen.md#x", got, "general knowledge was scoped away")
        self.assertIn("c.md#x", got)
        self.assertNotIn("s.md#x", got, "another market's note leaked in")

    def test_tags_boost_but_do_not_outrank_text(self):
        desk_memory.remember("monitoring", "weak.md#x", "weak",
                             "an unrelated note about weather", tags=["losing"])
        desk_memory.remember("monitoring", "strong.md#x", "strong",
                             "the stop was placed inside ordinary noise so it "
                             "was tripped by noise, not by the thesis failing")
        hits = desk_memory.search("stop tripped by noise", tags=["losing"],
                                  limit=2)
        self.assertEqual(hits[0]["source"], "strong.md#x")

    def test_no_match_returns_nothing_rather_than_filler(self):
        desk_memory.remember("monitoring", "a.md#x", "T",
                             "the stop was placed inside ordinary noise")
        self.assertEqual(desk_memory.search("kubernetes ingress certificate"), [])


class IngestTests(_Db):
    def _agent_and_run(self, **cols):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (name, cash) VALUES (?, ?)",
                        ("a", 1000.0))
            cur.execute(
                "INSERT INTO trading_runs (agent_id, symbol, market, status, "
                "status_reason, realized_pnl_usd, cycle_seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, cols.get("symbol", "BTCUSDT"), cols.get("market", "crypto"),
                 cols.get("status", "running"), cols.get("status_reason"),
                 cols.get("realized_pnl_usd", 0.0), 3, "2026-08-06T00:00:00Z"))
            conn.commit()
            cur.execute("SELECT id FROM trading_runs ORDER BY id DESC")
            return dict(cur.fetchone())["id"]
        finally:
            conn.close()

    def _decision(self, run_id, seq, payload):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, "decision", "2026-08-06T23:28:54Z",
                 json.dumps(payload)))
            conn.commit()
        finally:
            conn.close()

    def test_the_desks_own_reasoning_is_kept_and_retrievable(self):
        run_id = self._agent_and_run(symbol="SI", market="futures")
        self._decision(run_id, 35, {
            "cycle": 2, "action": "buy", "confidence": 0.68, "conviction": 0.69,
            "scores": {"entry_quality": 0.85, "risk_context": 0.55},
            "gate_source": "confidence", "size_scale": 0.7155,
            "route": {"route": "light"},
            "report": "Long entry justified by recent up-trend, good entry "
                      "price and a stop ~2% below current level giving a >2:1 "
                      "risk-reward.",
        })
        self.assertEqual(desk_memory_ingest.ingest_decisions(), 1)
        hits = desk_memory.search("stop below current level risk reward",
                                  kind="decision")
        self.assertEqual(len(hits), 1)
        self.assertIn("risk-reward", hits[0]["body"])
        self.assertIn("confidence=0.68", hits[0]["body"])
        self.assertEqual(hits[0]["symbol"], "SI")
        self.assertIn("action:buy", json.loads(hits[0]["tags_json"]))

    def test_a_decision_with_no_stated_case_is_skipped(self):
        run_id = self._agent_and_run()
        self._decision(run_id, 1, {"action": "hold", "confidence": 0.5})
        self.assertEqual(desk_memory_ingest.ingest_decisions(), 0)

    def test_ingest_decisions_is_safe_to_rerun_every_cycle(self):
        run_id = self._agent_and_run()
        self._decision(run_id, 1, {"cycle": 1, "action": "buy",
                                   "report": "a clear stated case for buying"})
        desk_memory_ingest.ingest_decisions()
        self.assertEqual(desk_memory_ingest.ingest_decisions(), 0)
        self.assertEqual(desk_memory.stats()["total"], 1)

    def test_finished_run_outcome_is_kept_with_the_loss_floor_tag(self):
        self._agent_and_run(symbol="ZC", status="stopped",
                            status_reason="loss_floor", realized_pnl_usd=-1.42)
        self.assertEqual(desk_memory_ingest.ingest_run_outcomes(), 1)
        hits = desk_memory.search("realized", kind="outcome")
        self.assertEqual(len(hits), 1)
        self.assertIn("below-loss-floor", json.loads(hits[0]["tags_json"]))
        self.assertIn("-1.42", hits[0]["body"])

    def test_running_runs_have_no_outcome_yet(self):
        self._agent_and_run(status="running", realized_pnl_usd=-5.0)
        self.assertEqual(desk_memory_ingest.ingest_run_outcomes(), 0)

    def test_monitoring_markdown_is_chunked_by_heading(self):
        root = os.path.join(self.tmp.name, "reports")
        os.makedirs(root)
        with open(os.path.join(root, "2026-08-06-automation-monitoring.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(
                "# Day note\n\nIntro paragraph that is long enough to be kept "
                "as its own chunk because the framing is usually the finding "
                "itself in these notes.\n\n"
                "## Losses\n\nSix of eighty-four closes accounted for seventy "
                "four percent of all loss, and every one of them dumped the "
                "whole book on a sub-two-percent move.\n\n"
                "## Tiny\n\nshort\n")
        stored = desk_memory_ingest.ingest_reports(root)
        self.assertEqual(stored, 2, "intro and Losses expected; Tiny too short")
        hits = desk_memory.search("dumped the whole book", kind="monitoring")
        self.assertEqual(len(hits), 1)
        self.assertIn("Losses", hits[0]["source"])
        self.assertTrue(hits[0]["ts"].startswith("2026-08-06"))

    def test_ingest_all_reports_counts_per_source(self):
        self._agent_and_run(status="stopped", realized_pnl_usd=2.0)
        out = desk_memory_ingest.ingest_all()
        self.assertEqual(out["outcomes"], 1)
        self.assertEqual(out["decisions"], 0)


class SkillLessonTests(_Db):
    """Plan 22 §7 increment (a3)(i) — the skills catalogue as `lesson` chunks.

    Recall reads a monitoring pool that has been frozen at ~560 chunks since
    08-08, and several situation classes cannot offer the >=3 above-floor
    candidates the attribution model needs. This is pool work only: nothing
    retrieves `lesson` yet, and that no-op is pinned below."""

    _BODY = (
        "Size from risk, not from conviction alone. Per-unit risk is the "
        "entry-to-stop distance plus expected friction, and the position must "
        "keep total risk inside the run's budget even if the stop fills with "
        "slippage. Round size DOWN, and when several constraints apply the "
        "strictest constraint wins every time it is consulted. Never size "
        "with full-Kelly aggression: half measures capture most of the growth "
        "with far less ruin risk in a book this small. If a key input is "
        "unknown, that is a reason to defer or shrink, never to guess bigger."
    )

    def _catalogue(self, *skills):
        import trading_skills
        return patch.object(trading_skills, "all_skills",
                            return_value=list(skills))

    def _skill(self, **cols):
        return {"slug": cols.get("slug", "position-sizing-discipline"),
                "name": cols.get("name", "Position Sizing Discipline"),
                "body": cols.get("body", self._BODY),
                "prompts": cols.get("prompts", ["trader", "planner"]),
                "markets": cols.get("markets"),
                "enabled": cols.get("enabled", True)}

    def test_a_skill_becomes_several_atomic_lessons(self):
        with self._catalogue(self._skill()):
            self.assertGreater(desk_memory_ingest.ingest_skill_lessons(), 1)
        self.assertGreater(desk_memory.stats()["by_kind"]["lesson"], 1)

    def test_an_atom_keeps_whole_sentences_and_loses_no_text(self):
        """A half claim is not doctrine — and a splitter that drops a clause
        would teach the desk something its author never wrote."""
        atoms = desk_memory_ingest._atomise(self._BODY)
        self.assertGreater(len(atoms), 1)
        self.assertEqual(" ".join(atoms), self._BODY)
        for atom in atoms:
            self.assertTrue(atom.endswith((".", "!", "?")), atom)

    def test_a_short_tail_is_folded_back_rather_than_stored_as_noise(self):
        """A body whose LAST sentence lands just after a chunk boundary — the
        only case where the fold-back does anything."""
        body = (self._BODY + " An aggressive stop or an oversized conviction "
                "cannot be repaired afterwards by sizing at all. Round down.")
        atoms = desk_memory_ingest._atomise(body)
        self.assertTrue(all(len(a) >= desk_memory_ingest._LESSON_MIN
                            for a in atoms), [len(a) for a in atoms])
        self.assertTrue(atoms[-1].endswith("Round down."))

    def test_a_body_shorter_than_the_floor_is_still_kept(self):
        """Unlike a markdown heading, a short skill body IS the doctrine."""
        self.assertEqual(desk_memory_ingest._atomise("Cut a loser small."),
                         ["Cut a loser small."])

    def test_a_multi_market_skill_is_reachable_from_each_of_its_markets(self):
        with self._catalogue(self._skill(markets=["crypto", "futures"])):
            desk_memory_ingest.ingest_skill_lessons()
        for market in ("crypto", "futures"):
            hits = desk_memory.search("size from risk not conviction",
                                      kind="lesson", market=market)
            self.assertTrue(hits, f"unreachable from {market}")

    def test_a_market_scoped_lesson_does_not_leak_into_another_market(self):
        with self._catalogue(self._skill(markets=["crypto"])):
            desk_memory_ingest.ingest_skill_lessons()
        self.assertFalse(desk_memory.search("size from risk not conviction",
                                            kind="lesson", market="forex"))

    def test_a_disabled_skill_teaches_nothing(self):
        with self._catalogue(self._skill(enabled=False)):
            self.assertEqual(desk_memory_ingest.ingest_skill_lessons(), 0)

    def test_reingest_is_idempotent(self):
        with self._catalogue(self._skill()):
            first = desk_memory_ingest.ingest_skill_lessons()
            self.assertGreater(first, 0)
            self.assertEqual(desk_memory_ingest.ingest_skill_lessons(), 0)
        self.assertEqual(desk_memory.stats()["by_kind"]["lesson"], first)

    def test_lessons_stay_out_of_the_pool_recall_actually_reads(self):
        """No behavior change today: `_recall_line` searches kind=monitoring,
        so a lesson must not be able to reach a live position brief."""
        desk_memory.remember("monitoring", "n.md#x", "T",
                             "Size from risk and not from conviction alone, "
                             "because conviction is not a risk measure.")
        with self._catalogue(self._skill()):
            desk_memory_ingest.ingest_skill_lessons()
        hits = desk_memory.search("size from risk not conviction",
                                  kind="monitoring")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["kind"], "monitoring")

    def test_the_real_catalogue_fills_the_pool(self):
        """The whole point of (a3): a pool big enough that a class can offer
        alternates. Measured on the shipped catalogue, not a fixture."""
        import trading_skills
        trading_skills.invalidate_trading_skills_cache()
        try:
            stored = desk_memory_ingest.ingest_skill_lessons()
        finally:
            trading_skills.invalidate_trading_skills_cache()
        self.assertGreater(stored, 100, "expected ~120-180 lessons")

    def test_a_broken_catalogue_never_costs_the_tick_its_other_ingests(self):
        import trading_skills
        with patch.object(trading_skills, "all_skills",
                          side_effect=RuntimeError("skills are on fire")):
            out = desk_memory_ingest.ingest_all()
        self.assertEqual(out["lessons"], 0)
        self.assertIn("decisions", out)


class DaemonTests(_Db):
    """The ingest rides the ~30s scheduler tick. Two properties matter: it
    throttles itself, and it can never fail a trading tick."""

    def setUp(self):
        super().setUp()
        desk_memory_ingest._last_ingest_epoch = 0.0

    def tearDown(self):
        desk_memory_ingest._last_ingest_epoch = 0.0
        os.environ.pop("DESK_MEMORY_INGEST_MIN", None)
        super().tearDown()

    def test_it_throttles_between_intervals(self):
        self.assertIsNotNone(desk_memory_ingest.maybe_ingest(now_epoch=10_000.0))
        self.assertIsNone(desk_memory_ingest.maybe_ingest(now_epoch=10_060.0),
                          "ingested twice inside one interval")
        self.assertIsNotNone(
            desk_memory_ingest.maybe_ingest(now_epoch=10_000.0 + 30 * 60),
            "did not ingest after a full interval")

    def test_interval_is_env_overridable(self):
        os.environ["DESK_MEMORY_INGEST_MIN"] = "5"
        self.assertEqual(desk_memory_ingest._ingest_every_min(), 5)
        # Epochs must start beyond the interval: _last_ingest_epoch is 0.0 on
        # a fresh process, which is why the first tick after boot ingests.
        self.assertIsNotNone(desk_memory_ingest.maybe_ingest(now_epoch=10_000.0))
        self.assertIsNone(desk_memory_ingest.maybe_ingest(now_epoch=10_200.0))
        self.assertIsNotNone(desk_memory_ingest.maybe_ingest(now_epoch=10_302.0))

    def test_reports_are_ingested_without_a_prod_env_edit(self):
        """The container and a local checkout both run from the project root,
        so the default path must work in both. Prod shipped with the corpus
        keeping only decisions because the reports dir was never set."""
        self.assertEqual(desk_memory_ingest._DEFAULT_REPORTS_DIR, "docs/reports")
        root = os.path.join(self.tmp.name, "docs", "reports")
        os.makedirs(root)
        with open(os.path.join(root, "2026-08-06-note.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("## Finding\n\nThe stop was placed inside ordinary noise "
                     "so it was tripped by noise rather than by the thesis "
                     "actually failing on the tape.\n")
        os.environ["DESK_MEMORY_REPORTS_DIR"] = root
        try:
            out = desk_memory_ingest.maybe_ingest(now_epoch=99_000.0)
        finally:
            os.environ.pop("DESK_MEMORY_REPORTS_DIR", None)
        self.assertEqual(out.get("reports"), 1)
        self.assertTrue(desk_memory.search("tripped by noise",
                                           kind="monitoring"))

    def test_a_missing_reports_dir_is_a_no_op(self):
        os.environ["DESK_MEMORY_REPORTS_DIR"] = "/nonexistent/path/xyz"
        try:
            out = desk_memory_ingest.maybe_ingest(now_epoch=99_000.0)
        finally:
            os.environ.pop("DESK_MEMORY_REPORTS_DIR", None)
        self.assertNotIn("reports", out)

    def test_a_failing_corpus_never_kills_a_trading_tick(self):
        """A corpus that cannot be written is a lost lesson; a tick that dies
        is a position nobody is managing."""
        import asyncio
        from unittest.mock import patch

        import run_engine
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        try:
            with patch.object(run_engine.desk_memory_ingest, "maybe_ingest",
                              side_effect=RuntimeError("corpus is on fire")):
                out = asyncio.run(run_engine.tick())
            self.assertTrue(out.get("enabled"))
            self.assertNotIn("memory_ingested", out)
        finally:
            os.environ.pop("AUTO_TRADING_ENABLED", None)

    def test_a_successful_ingest_is_reported_on_the_tick(self):
        import asyncio

        import run_engine
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        try:
            out = asyncio.run(run_engine.tick())
            self.assertIn("memory_ingested", out)
            self.assertIn("decisions", out["memory_ingested"])
        finally:
            os.environ.pop("AUTO_TRADING_ENABLED", None)


if __name__ == "__main__":
    unittest.main()
