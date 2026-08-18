"""Exploration on the LOSING side, scoped to statistical ties.

WHY (measured on prod 2026-08-18, and it inverts the premise of the
exclusion). `_recall_explore_allowed` refuses to explore any losing position,
justified by the mandate's asymmetry: never loosen an unproven thing on the
losing side. That was right while the incumbent was a CHOICE.

It is not a choice. Every journalled crypto losing-class row shows the second
slot EXACTLY TIED with chunks the desk was never shown — margin ~9.52 with
three candidates at the same score, decided by the sort's tiebreak. Measured
across all 16 live cells, 7 have a tied slot 2; on the live journal the
disclosure fires on 6 of 9 rows.

So on the losing side — the cut/hold/bank decision carrying 74% of measured
loss — the desk has been reading an arbitrary pick, and the class contributes
ZERO variance by design, which is precisely what keeps plan 22's (b) gate
shut at one qualifying class.

Drawing among EXACT TIES cannot loosen anything: the drawn chunk scored within
1% of the one it replaces. The asymmetry is honoured and the variance appears
in the class that matters most.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_engine  # noqa: E402


class TieScopedExplorationTests(unittest.TestCase):
    def setUp(self):
        os.environ["DESK_RECALL_EXPLORE"] = "1"

    def tearDown(self):
        for k in ("DESK_RECALL_EXPLORE", "DESK_RECALL_EXPLORE_TIES"):
            os.environ.pop(k, None)

    def _hits(self, *scores):
        return [{"sha": f"{i:064d}", "score": s} for i, s in enumerate(scores)]

    def test_a_losing_run_now_explores_among_its_ties(self):
        """The live crypto losing shape: slot 2 at 9.5225 with two more
        chunks at exactly 9.5225 and one at 9.43 (0.97% below)."""
        hits = self._hits(10.1016, 9.5225, 9.5225, 9.5225, 9.43)
        seconds = set()
        for _ in range(400):
            chosen, meta = run_engine._recall_select(hits, True, tie_only=True)
            self.assertEqual(chosen[0]["sha"], hits[0]["sha"],
                             "the head must never be displaced")
            seconds.add(chosen[1]["sha"])
        self.assertGreaterEqual(
            len(seconds), 3,
            "the losing class still produces one chunk-pair — the (b) gate "
            "cannot open")

    def test_only_statistical_ties_are_drawn(self):
        """A chunk that is genuinely WORSE must never be substituted on the
        losing side. That is the loosening the mandate forbids."""
        hits = self._hits(10.0, 9.0, 8.9999, 7.0, 5.0)
        drawn = set()
        for _ in range(400):
            chosen, _m = run_engine._recall_select(hits, True, tie_only=True)
            drawn.add(chosen[1]["sha"])
        self.assertEqual(drawn, {hits[1]["sha"], hits[2]["sha"]},
                         "a chunk outside the 1% tie band was drawn on the "
                         "losing side")

    def test_no_tie_means_no_exploration_at_all(self):
        """With a clear runner-up the incumbent IS a choice, and the
        exclusion still applies."""
        hits = self._hits(10.0, 9.0, 6.0, 5.0)
        for _ in range(200):
            chosen, meta = run_engine._recall_select(hits, True, tie_only=True)
            self.assertEqual([c["sha"] for c in chosen],
                             [hits[0]["sha"], hits[1]["sha"]])
            self.assertFalse(meta["explore"])
            self.assertEqual(meta["propensity"], 1.0)

    def test_it_is_journaled_as_a_DIFFERENT_scheme(self):
        """A tie-scoped draw is a different policy, so its rows are a
        different dataset — pooling them with eps-head-fixed-v1 unlabelled
        would corrupt every estimate (c) computes, and cannot be retrofitted."""
        _c, meta = run_engine._recall_select(
            self._hits(10.0, 9.5, 9.5, 9.5), True, tie_only=True)
        self.assertEqual(meta["scheme"], "eps-tie-only-v1")
        self.assertNotEqual(meta["scheme"], "eps-head-fixed-v1")

    def test_the_propensity_stays_bounded(self):
        hits = self._hits(10.0, 9.5, 9.5, 9.5)
        for _ in range(300):
            _c, meta = run_engine._recall_select(hits, True, tie_only=True)
            self.assertGreaterEqual(meta["propensity"], 0.05,
                                    "IPS blows up on small propensities")

    def test_the_winning_path_is_untouched(self):
        """The 0.60-of-head floor still governs the classes that were already
        explorable — this change must not silently re-scope them."""
        _c, meta = run_engine._recall_select(
            self._hits(30.0, 22.0, 21.0, 20.0, 19.0), True)
        self.assertEqual(meta["scheme"], "eps-head-fixed-v1")
        self.assertEqual(meta["pool"], 3)

    def test_a_single_hit_cannot_be_tie_explored(self):
        chosen, meta = run_engine._recall_select(self._hits(10.0), True,
                                                 tie_only=True)
        self.assertEqual(len(chosen), 1)
        self.assertFalse(meta["explore"])

    def test_the_kill_switch_restores_the_exclusion(self):
        os.environ["DESK_RECALL_EXPLORE_TIES"] = "0"
        self.assertFalse(run_engine._recall_tie_explore_enabled())

    def test_it_is_wired_so_a_losing_run_reaches_the_tie_path(self):
        """The standing trap: a brief line tested for rendering and never for
        being CALLED. `_recall_explore_allowed` returns False for a losing
        position, so without an explicit tie_only branch at the call site this
        whole file would be dead code."""
        import inspect
        src = "\n".join(ln.split("#")[0]
                        for ln in inspect.getsource(
                            run_engine._recall_line).splitlines())
        self.assertIn("tie_only", src,
                      "the losing class never reaches the tie-scoped path")
        self.assertIn("_recall_tie_explore_enabled", src,
                      "the kill switch is not consulted at the call site")


if __name__ == "__main__":
    unittest.main()
