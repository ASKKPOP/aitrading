"""A claimed research window that produced nothing must not stay claimed.

2026-08-07: two windows burned in two hours, from two different causes, with
the same consequence — the fleet could not replenish until the next hour.

  * 496139 claimed 11:53:30, worker recreated by a deploy ~4.5 min later,
    right before persist. A killed process cannot clean up after itself.
  * 496140 claimed 12:58:34, refresh COMPLETED with `survivors: 0` because
    `event_window` and `regime_blocks_longs` were both true — gating crypto
    longs AND us-stock/futures/forex at once, i.e. the whole universe.
"""
import os
import tempfile
import unittest

import database
import symbol_research


class ClaimRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "r.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _thesis(self, symbol):
        """persist_batch expects the SCREEN's row shape, with the LLM output
        nested under `thesis` — not a flat dict."""
        return {
            "symbol": symbol, "market": "crypto",
            "factors": {}, "subscores": {}, "coverage": 0.5,
            "ev_per_day_pct": 1.0, "final_score": 0.5,
            "selectable": 1, "planner": "llm",
            "thesis": {"direction": "long", "thesis": "t", "risks": "r",
                       "invalidation": "i", "expected_move_pct": 2.0,
                       "horizon_hours": 24, "confidence": 0.6},
        }

    def _claims(self, batch_id):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) n FROM research_batches WHERE batch_id = ?",
                        (batch_id,))
            return int(dict(cur.fetchone())["n"])
        finally:
            conn.close()

    def _age_claim(self, batch_id, seconds):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE research_batches SET created_at = ? WHERE batch_id = ?",
                        (symbol_research._iso_seconds_ago(seconds), batch_id))
            conn.commit()
        finally:
            conn.close()

    def test_a_fresh_claim_still_blocks_a_second_runner(self):
        """The whole point of the sentinel: no duplicate LLM spend."""
        self.assertTrue(symbol_research.claim_batch("research:1"))
        self.assertFalse(symbol_research.claim_batch("research:1"),
                         "a live claim must still block a concurrent runner")

    def test_a_stale_EMPTY_claim_is_reclaimable(self):
        """The killed-mid-refresh case. Nothing else can free it."""
        self.assertTrue(symbol_research.claim_batch("research:2"))
        self._age_claim("research:2", symbol_research._CLAIM_STALE_SECONDS + 60)
        self.assertTrue(symbol_research.claim_batch("research:2"),
                        "an abandoned empty claim owns the window forever")

    def test_a_stale_claim_WITH_theses_is_NOT_reclaimable(self):
        """A completed window must never be redone — that is duplicate spend."""
        self.assertTrue(symbol_research.claim_batch("research:3"))
        symbol_research.persist_batch("research:3", [self._thesis("BTCUSDT")])
        self._age_claim("research:3", symbol_research._CLAIM_STALE_SECONDS + 60)
        self.assertFalse(symbol_research.claim_batch("research:3"),
                         "a window that produced theses was redone")

    def test_an_unproductive_claim_is_released_immediately(self):
        """The fully-gated case: the refresh completes, persists nothing, and
        must not go on owning the window."""
        self.assertTrue(symbol_research.claim_batch("research:4"))
        self.assertEqual(self._claims("research:4"), 1)
        symbol_research._release_unproductive_claim("research:4")
        self.assertEqual(self._claims("research:4"), 0,
                         "a window with zero theses stayed claimed")

    def test_release_never_drops_a_productive_claim(self):
        self.assertTrue(symbol_research.claim_batch("research:5"))
        symbol_research.persist_batch("research:5", [self._thesis("ETHUSDT")])
        symbol_research._release_unproductive_claim("research:5")
        self.assertEqual(self._claims("research:5"), 1,
                         "a productive claim was released — the window can now "
                         "be redone and re-billed")


if __name__ == "__main__":
    unittest.main()
