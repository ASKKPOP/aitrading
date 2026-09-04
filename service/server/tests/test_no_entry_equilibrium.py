"""No-entry equilibrium fixes (owner order 2026-09-04, "make solutions").

Measured cause, not hypothesis. After the hold-wall fix the fleet settled
into build -> 3 desk holds -> switch -> build, forever, with zero entries:

  * 82% of the desk's outlooks carried a CONCRETE entry plan (123 zones
    with numbers + 36 triggers vs 34 `none`), e.g. HYPE {"kind":"zone",
    "low":76.8,"high":83.5,"trigger":"pullback into MA5/MA20 support"}.
  * 51 runs holding such a plan were stopped `no_prospect_switched` — the
    rail measured the absence of a TRADE and called it absence of a PLAN.
  * Within a slot's 1-hour life the authored zone was reached 0 times out
    of 49; across the whole day ~9 of 19 zones sat inside the day's range.
    The desk plans on a daily clock, the platform granted an hourly one.
  * Selection ranks by |mom_2d| x volume AND technical_subscore ADDS
    sma20_dist/10 — the scorer rewards extension while 53% of hold reports
    refuse those same names as "extended above MA20, wait for a pullback".

S2+S4 (plan-aware switch window, inside the owner's own 1-5h band) and S3
(extension-aware ordering) are pinned here.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import run_engine
import symbol_research as sr


def _fresh_ts(hours_ago=0.0):
    """A timestamp relative to NOW. The plan-staleness bound makes any
    hardcoded date a time bomb: a fixture stamped 07:00Z passes this
    morning and fails every run after noon."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc)
            - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _outlook(kind="zone", low=76.8, high=83.5, trigger=None, horizon=None):
    return {"bias": "long",
            "entry": {"kind": kind, "low": low, "high": high,
                      "trigger": trigger},
            "exit": {"target_px": None, "stop_ref_px": None},
            "horizon_hours": horizon}


class LiveEntryPlanTests(unittest.TestCase):
    """What counts as the desk having named a prospect."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def _emit(self, run_id, payload):
        conn = database.get_db_connection()
        cur = conn.cursor()
        self.seq += 1
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, ?, 'outlook', ?, ?)",
            (run_id, self.seq, _fresh_ts(), json.dumps(payload)))
        conn.commit()
        conn.close()

    def test_zone_with_numbers_is_a_live_plan(self):
        self._emit(1, _outlook())
        plan = run_engine._live_entry_plan(1)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["kind"], "zone")

    def test_trigger_with_text_is_a_live_plan(self):
        self._emit(2, _outlook(kind="trigger", low=None, high=None,
                               trigger="breakout and hold above 1.50"))
        self.assertIsNotNone(run_engine._live_entry_plan(2))

    def test_kind_none_is_not_a_plan(self):
        """21% of outlooks — the desk genuinely saying nothing is here.
        These MUST keep rotating on the owner's hour."""
        self._emit(3, _outlook(kind="none", low=None, high=None))
        self.assertIsNone(run_engine._live_entry_plan(3))

    def test_zone_without_numbers_is_not_a_plan(self):
        self._emit(4, _outlook(low=None, high=None))
        self.assertIsNone(run_engine._live_entry_plan(4))

    def test_trigger_without_text_is_not_a_plan(self):
        self._emit(5, _outlook(kind="trigger", low=None, high=None,
                               trigger="   "))
        self.assertIsNone(run_engine._live_entry_plan(5))

    def test_newest_outlook_wins(self):
        """The desk re-authors every cycle; a plan it dropped must not keep
        the slot alive."""
        self._emit(6, _outlook())
        self._emit(6, _outlook(kind="none", low=None, high=None))
        self.assertIsNone(run_engine._live_entry_plan(6))

    def test_sweeper_algo_fallback_is_not_the_desks_plan(self):
        """Adversarial review 2026-09-04: outlook_refresher._fallback_payload
        fires precisely when the LLM is unavailable and mechanically builds
        a numeric zone from the algo candidate — same infra-authorship class
        as the scaffold and rule-hold guards, one door over. It self-labels
        `basis.verdict: algo_fallback`."""
        payload = _outlook()
        payload["source"] = "sweeper"
        payload["basis"] = {"verdict": "algo_fallback", "discussion": ""}
        self._emit(20, payload)
        self.assertIsNone(run_engine._live_entry_plan(20))

    def test_the_sweepers_llm_authored_standing_plan_still_counts(self):
        """Same source, real verdict: that one IS the desk speaking."""
        payload = _outlook()
        payload["source"] = "sweeper"
        payload["basis"] = {"verdict": "agree", "discussion": "holds"}
        self._emit(21, payload)
        self.assertIsNotNone(run_engine._live_entry_plan(21))

    def test_a_plan_the_desk_stopped_renewing_goes_stale(self):
        """A slot whose outlooks went silent may not keep claiming the wide
        window forever."""
        stale = _fresh_ts(9)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (22, 1, 'outlook', ?, ?)",
            (stale, json.dumps(_outlook())))
        conn.commit()
        conn.close()
        self.assertIsNone(run_engine._live_entry_plan(22))

    def test_every_timestamp_shape_the_tape_can_carry_is_read(self):
        """Independent verification 2026-09-04: the staleness bound first
        used the STRICT `_age_seconds` while `_flat_hold_span` beside it
        parses tolerantly ("signals and run_events may disagree on 'T' vs
        space format"). One format drift would have aged every plan to
        infinity and switched the plan-aware window off silently, with the
        whole suite green. Each shape below must still read as live."""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc) - timedelta(minutes=3)
        shapes = {
            30: now.strftime("%Y-%m-%dT%H:%M:%SZ"),      # canonical
            31: now.strftime("%Y-%m-%d %H:%M:%S"),       # MySQL space form
            32: now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",   # microseconds
            33: now.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00",  # offset
        }
        for run_id, ts in shapes.items():
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
                "VALUES (?, 1, 'outlook', ?, ?)",
                (run_id, ts, json.dumps(_outlook())))
            conn.commit()
            conn.close()
            self.assertIsNotNone(run_engine._live_entry_plan(run_id),
                                 f"timestamp shape {ts!r} silently killed "
                                 f"the plan-aware window")
            self.assertEqual(run_engine._no_prospect_window_hours(run_id), 5.0)

    def test_no_outlook_and_junk_fail_soft(self):
        self.assertIsNone(run_engine._live_entry_plan(999))
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (7, 1, 'outlook', ?, 'not json')", (_fresh_ts(),))
        conn.commit()
        conn.close()
        self.assertIsNone(run_engine._live_entry_plan(7))


class PlanAwareWindowTests(unittest.TestCase):
    """S2+S4: the window is the owner's hour without a plan, and may reach
    the top of the owner's own 1-5h band with one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        os.environ.pop("RUN_NO_PROSPECT_SWITCH_HOURS", None)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("RUN_NO_PROSPECT_SWITCH_HOURS", None)

    def _emit(self, run_id, payload):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, 1, 'outlook', ?, ?)",
            (run_id, _fresh_ts(), json.dumps(payload)))
        conn.commit()
        conn.close()

    def test_no_plan_keeps_the_owners_hour(self):
        self.assertEqual(run_engine._no_prospect_window_hours(1), 1.0)
        self._emit(2, _outlook(kind="none", low=None, high=None))
        self.assertEqual(run_engine._no_prospect_window_hours(2), 1.0)

    def test_a_plan_extends_to_the_top_of_the_owner_band(self):
        self._emit(3, _outlook())
        self.assertEqual(run_engine._no_prospect_window_hours(3), 5.0)

    def test_a_short_plan_horizon_shortens_the_wait(self):
        self._emit(4, _outlook(horizon=2.0))
        self.assertEqual(run_engine._no_prospect_window_hours(4), 2.0)

    def test_a_plan_never_shortens_below_the_configured_floor(self):
        self._emit(5, _outlook(horizon=0.25))
        self.assertEqual(run_engine._no_prospect_window_hours(5), 1.0)

    def test_a_long_plan_horizon_is_capped_by_the_owner_band(self):
        """The owner's band is 1-5h. A 48h thesis horizon may not turn the
        rail off — that is how a slot goes dead for two days."""
        self._emit(6, _outlook(horizon=48.0))
        self.assertEqual(run_engine._no_prospect_window_hours(6), 5.0)

    def test_env_floor_still_leads_when_raised(self):
        os.environ["RUN_NO_PROSPECT_SWITCH_HOURS"] = "4"
        self.assertEqual(run_engine._no_prospect_window_hours(7), 4.0)
        self._emit(8, _outlook(horizon=2.0))
        self.assertEqual(run_engine._no_prospect_window_hours(8), 4.0)

    def test_rail_reads_the_plan_aware_window(self):
        """Wiring pin: a helper nobody calls fixes nothing. Kept as a cheap
        smoke check — the BEHAVIOURAL guarantee is the end-to-end pair in
        RailEndToEndTests, which is what actually defends this rail."""
        import inspect
        src = inspect.getsource(run_engine._evaluate_stop)
        self.assertIn("_no_prospect_window_hours(", src)


class RailEndToEndTests(unittest.TestCase):
    """The behavioural guarantee, through _evaluate_stop rather than the
    helper.

    Added after independent verification 2026-09-04 proved the textual
    wiring pin above is not enough: a mutation that KEEPS the call but
    neuters its effect — `span_h >= min(_no_prospect_switch_hours(),
    _no_prospect_window_hours(run_id))` — passed all 33 tests while
    killing Ship A's entire premise. A source-text assertion checks that a
    string appears, not that the plan changes the outcome. Same lesson as
    the brief-line wiring rule, one level deeper."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.seq = 0
        os.environ.pop("RUN_NO_PROSPECT_SWITCH_HOURS", None)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("RUN_NO_PROSPECT_SWITCH_HOURS", None)

    def _run(self, run_id):
        return {"id": run_id, "agent_id": 6, "symbol": "NVDA",
                "market": "us-stock", "status": "running", "cycle_seq": 3,
                "config_snapshot_json": json.dumps(
                    {"symbol": "NVDA", "market": "us-stock",
                     "thesis": {"expected_move_pct": 5.0}}),
                "stop_conditions_json": "{}"}

    def _event(self, run_id, kind, payload, hours_ago):
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc)
              - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = database.get_db_connection()
        cur = conn.cursor()
        self.seq += 1
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, self.seq, kind, ts, json.dumps(payload)))
        conn.commit()
        conn.close()

    def _holds(self, run_id, *hours_ago):
        for h in hours_ago:
            self._event(run_id, "decision",
                        {"action": "hold", "confidence": 0.6}, h)

    def _evaluate(self, run):
        from unittest.mock import patch
        pnl = {"total": 0.0, "realized": 0.0, "trades": 0,
               "mark_age_ok": True, "position": None}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            return run_engine._evaluate_stop(run)

    def test_a_live_plan_keeps_the_slot_past_the_owners_hour(self):
        """1.5h of flat holds + an authored zone: the desk named a
        prospect, so the rail must NOT retire it (the 51-run defect)."""
        run = self._run(3001)
        self._holds(3001, 1.5, 0.05)
        self._event(3001, "outlook", _outlook(), 0.05)
        self.assertIsNone(self._evaluate(run))

    def test_the_same_slot_without_a_plan_still_switches_on_the_hour(self):
        """Identical shape, `kind: none` — the owner's hourly rotation is
        untouched for slots that genuinely see nothing."""
        run = self._run(3002)
        self._holds(3002, 1.5, 0.05)
        self._event(3002, "outlook",
                    _outlook(kind="none", low=None, high=None), 0.05)
        self.assertEqual(self._evaluate(run), "no_prospect_switched")

    def test_no_outlook_at_all_preserves_the_old_behaviour(self):
        run = self._run(3003)
        self._holds(3003, 1.5, 0.05)
        self.assertEqual(self._evaluate(run), "no_prospect_switched")

    def test_a_planned_slot_still_switches_past_the_band_ceiling(self):
        """5.5h of holds against a 48h plan horizon: the owner's 1-5h band
        bounds the wait, so a plan can never park a slot indefinitely."""
        run = self._run(3004)
        self._holds(3004, 5.5, 0.05)
        self._event(3004, "outlook", _outlook(horizon=48.0), 0.05)
        self.assertEqual(self._evaluate(run), "no_prospect_switched")

    def test_the_plans_own_horizon_bounds_the_wait(self):
        run = self._run(3005)
        self._holds(3005, 1.5, 0.05)
        self._event(3005, "outlook", _outlook(horizon=2.0), 0.05)
        self.assertIsNone(self._evaluate(run))
        run2 = self._run(3006)
        self._holds(3006, 2.6, 0.05)
        self._event(3006, "outlook", _outlook(horizon=2.0), 0.05)
        self.assertEqual(self._evaluate(run2), "no_prospect_switched")


class ExtensionAwareSelectionTests(unittest.TestCase):
    """S3: stop leading with names the desk has already decided it will not
    chase — without shrinking the pool (that is what starved fleet 43)."""

    def setUp(self):
        for k in ("EXTENSION_SORT", "EXTENSION_BAR_PCT"):
            os.environ.pop(k, None)

    tearDown = setUp

    def _t(self, sym, ext, market="crypto"):
        return {"symbol": sym, "market": market,
                "factor_scores_json": json.dumps(
                    {"factors": {"sma20_dist": ext}})}

    def test_extended_names_stop_leading_but_stay_eligible(self):
        rows = [self._t("HOT1", 25.0), self._t("CALM1", 1.0),
                self._t("HOT2", 12.0), self._t("CALM2", -3.0)]
        out = sr._deprioritise_extended(rows)
        self.assertEqual([t["symbol"] for t in out],
                         ["CALM1", "CALM2", "HOT1", "HOT2"])
        self.assertEqual(len(out), 4, "no candidate may be dropped")

    def test_order_is_stable_inside_each_group(self):
        """The owner's mover ranking must survive within the groups."""
        rows = [self._t("HOT_FIRST", 30.0), self._t("HOT_SECOND", 20.0),
                self._t("CALM_FIRST", 2.0), self._t("CALM_SECOND", 0.5)]
        out = [t["symbol"] for t in sr._deprioritise_extended(rows)]
        self.assertEqual(out, ["CALM_FIRST", "CALM_SECOND",
                               "HOT_FIRST", "HOT_SECOND"])

    def test_extension_is_measured_in_the_direction_traded(self):
        """Adversarial review 2026-09-04: sma20_dist is SIGNED and the
        screen assigns short to every negative-momentum name, so shorts
        were "calm" by construction — a short sitting 30% BELOW its mean
        (the mirror mistake: selling an exhausted downside move into a
        bounce) took the lead over a mildly extended long. Both sides must
        measure the same thing: how far this entry chases a move that has
        already happened."""
        rows = [self._t("SHORT_EXHAUSTED", -30.0),   # chasing a dump
                self._t("LONG_MILD", 3.0),           # near its mean
                self._t("SHORT_FRESH", -2.0)]        # short, barely extended
        rows[0]["direction"] = "short"
        rows[2]["direction"] = "short"
        out = [t["symbol"] for t in sr._deprioritise_extended(rows)]
        self.assertEqual(out[-1], "SHORT_EXHAUSTED",
                         "a 30%-extended short must not lead a calm long")
        self.assertEqual(out[:2], ["LONG_MILD", "SHORT_FRESH"])

    def test_a_uniformly_extended_pool_is_left_untouched(self):
        """No starvation: when every candidate is extended the partition
        cannot shrink or reorder the pool — it degrades to identity."""
        rows = [self._t("A", 30.0), self._t("B", 25.0), self._t("C", 40.0)]
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended(rows)],
                         ["A", "B", "C"])
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended([])], [])

    def test_unreadable_extension_is_never_penalised(self):
        rows = [{"symbol": "NOFACTORS", "market": "crypto"},
                self._t("HOT", 40.0)]
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended(rows)],
                         ["NOFACTORS", "HOT"])

    def test_bar_and_kill_switch(self):
        rows = [self._t("A", 9.0), self._t("B", 1.0)]
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended(rows)],
                         ["B", "A"])
        os.environ["EXTENSION_BAR_PCT"] = "20"   # 9% no longer "extended"
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended(rows)],
                         ["A", "B"])
        os.environ.pop("EXTENSION_BAR_PCT")
        os.environ["EXTENSION_SORT"] = "0"
        self.assertEqual([t["symbol"] for t in sr._deprioritise_extended(rows)],
                         ["A", "B"])

    def test_select_targets_applies_it(self):
        """Wiring pin, and the owner's hot-tech MUST still wins for
        us-stock: the extension sort orders the REST, it never displaces a
        pinned lead."""
        import inspect
        src = inspect.getsource(sr.select_targets)
        self.assertIn("_deprioritise_extended(", src)
        self.assertLess(src.index("_deprioritise_extended("),
                        src.index("_hot_tech_first_us_stock("),
                        "extension sort must run BEFORE the pinned hot-tech "
                        "reorder, or it would override the owner's order")


if __name__ == "__main__":
    unittest.main()
