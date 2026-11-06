"""Desk-adopted 2026-07-31 — I2 (per-run max_loss ceiling) and I5
(conviction-collapse exit). Both ship dark; these lock the behaviour of the
flip. Each I5 case would return None on origin/main (the rail did not exist);
each I2 case would keep the un-clamped value."""
import json
import unittest
from unittest.mock import patch

import run_engine
import trading_runs


# ── I2: per-run max_loss ceiling ────────────────────────────────────────────
class MaxLossCeiling(unittest.TestCase):
    def test_off_by_default_is_a_noop(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("RUN_MAX_LOSS_CEILING_USD", None)
            out = trading_runs.validate_stop_conditions({"max_loss_usd": 2600})
        self.assertEqual(out["max_loss_usd"], 2600.0)

    def test_clamps_down_to_ceiling(self):
        with patch.dict("os.environ", {"RUN_MAX_LOSS_CEILING_USD": "1000"}):
            out = trading_runs.validate_stop_conditions({"max_loss_usd": 2600})
        self.assertEqual(out["max_loss_usd"], 1000.0)  # 83/76/62 would be bounded

    def test_leaves_a_smaller_loss_alone(self):
        with patch.dict("os.environ", {"RUN_MAX_LOSS_CEILING_USD": "1000"}):
            out = trading_runs.validate_stop_conditions({"max_loss_usd": 40})
        self.assertEqual(out["max_loss_usd"], 40.0)  # the fleet is untouched


# ── I5: conviction-collapse exit ────────────────────────────────────────────
def _held_pnl(total=-0.5):
    return {"total": total, "realized": 0.0, "trades": 1, "mark_age_ok": True,
            "position": {"quantity": 1.0, "entry_price": 100.0,
                         "current_price": 100.0, "leverage": 1.0}}


class ConvictionCollapseExit(unittest.TestCase):
    RUN = {"id": 999, "stop_conditions_json": "{}", "cycle_seq": 5}

    def _evaluate(self, convs, enabled=True):
        with patch.object(run_engine, "compute_run_pnl", return_value=_held_pnl()), \
             patch.object(run_engine, "_conviction_exit_enabled", return_value=enabled), \
             patch.object(run_engine, "_recent_run_convictions", return_value=convs):
            return run_engine._evaluate_stop(dict(self.RUN))

    def test_fires_when_two_cycles_below_floor(self):
        self.assertEqual(self._evaluate([0.27, 0.30]),
                         "stop_event:conviction_collapse")

    def test_does_not_fire_above_floor(self):
        self.assertIsNone(self._evaluate([0.60, 0.62]))

    def test_does_not_fire_on_a_single_wobble(self):
        # one low read among the last two is not a collapse
        self.assertIsNone(self._evaluate([0.27, 0.55]))

    def test_disarmed_is_inert(self):
        self.assertIsNone(self._evaluate([0.10, 0.10], enabled=False))

    def test_insufficient_history_does_not_fire(self):
        # fewer readings than strikes (2) — an absent score never triggers it
        self.assertIsNone(self._evaluate([0.10]))

    def test_no_position_is_inert(self):
        flat = {"total": 0.0, "realized": 0.0, "trades": 0, "mark_age_ok": True,
                "position": None}
        with patch.object(run_engine, "compute_run_pnl", return_value=flat), \
             patch.object(run_engine, "_conviction_exit_enabled", return_value=True), \
             patch.object(run_engine, "_recent_run_convictions", return_value=[0.1, 0.1]):
            self.assertNotEqual(run_engine._evaluate_stop(dict(self.RUN)),
                                "stop_event:conviction_collapse")

    def test_classified_for_replacement(self):
        import fleet_planner
        self.assertIn("stop_event:conviction_collapse",
                      fleet_planner.REPLACE_IMMEDIATE)

    def _reader(self, rows):
        class _Cur:
            def execute(self, *a): pass
            def fetchall(self): return rows

        class _Conn:
            def cursor(self): return _Cur()
            def close(self): pass
        with patch.object(run_engine, "get_db_connection", return_value=_Conn()):
            return run_engine._recent_run_convictions(1, 2)

    def test_reader_extracts_conviction(self):
        rows = [{"payload": json.dumps({"conviction": 0.27, "held": True})},
                {"payload": json.dumps({"confidence": 0.9, "held": True})},  # no conviction key
                {"payload": "{bad json"}]
        self.assertEqual(self._reader(rows), [0.27])

    # 2026-11-06 (docs/reports/2026-11-06-one-month-loss-analysis.md §2.9):
    # 15 trips closed 0–76s after entry because the rail counted conviction
    # reads from the FLAT cycles before the entry (13 on agent 60, median hold
    # 0.3 min, pure fee burn). Only reads taken while holding count; a flat
    # read ends the streak, and a legacy read without the flag is a flat read.
    def test_reader_counts_only_reads_taken_while_holding(self):
        rows = [{"payload": json.dumps({"conviction": 0.20, "held": True})},   # newest
                {"payload": json.dumps({"conviction": 0.10, "held": False})},  # flat: streak ends
                {"payload": json.dumps({"conviction": 0.10, "held": True})}]
        self.assertEqual(self._reader(rows), [0.20])

    def test_reader_never_skips_across_an_absent_score(self):
        """A held read with no conviction neither counts nor is skipped over:
        the old LIMIT-window read went silent on it, and so must this one
        (adversarial review 2026-11-06: over-fetch + continue would have let
        three low reads separated by up to nine scoreless cycles fire)."""
        rows = [{"payload": json.dumps({"conviction": 0.20, "held": True})},
                {"payload": json.dumps({"conviction": None, "held": True})},
                {"payload": json.dumps({"conviction": 0.10, "held": True})}]
        self.assertEqual(self._reader(rows), [0.20])

    def test_reader_treats_a_legacy_read_as_flat(self):
        rows = [{"payload": json.dumps({"conviction": 0.20, "held": True})},
                {"payload": json.dumps({"conviction": 0.10})}]  # pre-flag decision
        self.assertEqual(self._reader(rows), [0.20])


if __name__ == "__main__":
    unittest.main()
