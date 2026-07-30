"""The desk authors eight order-block fields; four were discarded.

Prod run 825 (2026-07-30 02:59) authored a complete, internally consistent
plan and the engine kept less than half of it:

    {"size_frac":0.6, "leverage":1.5, "stop_pct":8, "target_pct":27,
     "trail_arm_pct":12, "trail_give":0.3, "horizon_hours":72, "max_adds":1}

  honoured : size_frac (wrong basis), leverage, stop_pct/target_pct
  discarded: horizon_hours, trail_arm_pct, trail_give, max_adds

The anchor test is ReduceBasisTests.test_replays_the_825_flatten: the desk
asked to reduce by 60% and the machine sold 308.4643 of 308.4643 units,
because size_frac was resolved against max_bet_usd instead of the book.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import run_engine  # noqa: E402
import trading_runs  # noqa: E402
from order_params import OrderParams  # noqa: E402


class _EnvMixin(unittest.TestCase):
    def setUp(self):
        self._saved: dict = {}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def env(self, key, value):
        self._saved.setdefault(key, os.environ.get(key))
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _sized(action, size_frac, *, held, entry, max_bet, cfg_lev, order_lev,
           enabled=True):
    """Drive the SHIPPED sizing function, not a mirror of it.

    The first version of this helper re-implemented run_cycle's arithmetic and
    a mutation reverting production to the old basis passed the entire suite —
    the test was green against its own copy of the logic. _order_size_usd now
    exists precisely so the test and the shipped path cannot diverge.
    """
    lev = max(1.0, float(cfg_lev))
    if order_lev is not None:
        lev = max(1.0, min(lev, float(order_lev)))
    if not enabled:                      # the pre-fix behaviour, for contrast
        return max_bet * size_frac, lev
    return run_engine._order_size_usd(
        action, size_frac, max_bet_usd=max_bet, held_qty=held,
        entry=entry, leverage=lev), lev


def _quantity(size_usd, lev, price):
    """The gate is handed size_usd x lev as notional; quantity = notional/price."""
    return size_usd * lev / price


class ReduceBasisTests(_EnvMixin):
    """An open asks 'how much risk should I take?'; a reduce asks 'how much of
    what I HOLD should I give up?'. Different questions, different units."""

    P = dict(held=308.464259, entry=1.2011, max_bet=1000.0,
             cfg_lev=3.0, order_lev=1.0)

    def test_replays_the_825_flatten(self):
        """THE anchor: the old basis turns a 60% trim into a 100% flatten."""
        size_usd, lev = _sized("sell", 0.6, enabled=False, **self.P)
        qty = _quantity(size_usd, 1.0, self.P["entry"])
        self.assertAlmostEqual(size_usd, 600.0, places=6)
        self.assertGreater(qty, self.P["held"])          # overshoots the book
        self.assertAlmostEqual(min(qty, self.P["held"]), 308.464259, places=6)

    def test_new_basis_reduces_by_exactly_the_fraction_asked(self):
        size_usd, lev = _sized("sell", 0.6, **self.P)
        qty = _quantity(size_usd, lev, self.P["entry"])
        self.assertAlmostEqual(qty, 0.6 * self.P["held"], places=6)
        self.assertLess(qty, self.P["held"])             # no longer a flatten

    def test_size_frac_one_still_closes_the_book(self):
        size_usd, lev = _sized("cover", 1.0, **self.P)
        self.assertAlmostEqual(_quantity(size_usd, lev, self.P["entry"]),
                               self.P["held"], places=6)

    def test_cover_uses_the_same_basis_as_sell(self):
        a, la = _sized("sell", 0.5, **self.P)
        b, lb = _sized("cover", 0.5, **self.P)
        self.assertAlmostEqual(a, b, places=9)

    def test_opens_keep_the_budget_basis(self):
        for action in ("buy", "short"):
            size_usd, _ = _sized(action, 0.25, **self.P)
            self.assertAlmostEqual(size_usd, 250.0, places=6)

    def test_leverage_is_applied_before_the_reduce_basis(self):
        """The reduce basis divides by lev, so the desk's leverage override
        must land first or the quantity is wrong by that factor."""
        size_usd, lev = _sized("sell", 1.0, held=100.0, entry=10.0,
                               max_bet=1000.0, cfg_lev=3.0, order_lev=1.0)
        self.assertAlmostEqual(lev, 1.0)
        self.assertAlmostEqual(_quantity(size_usd, lev, 10.0), 100.0, places=6)

    def test_kill_switch_restores_the_old_basis(self):
        self.env("RUN_ORDER_PLAN", "false")
        size_usd, _ = _sized("sell", 0.6, **self.P)
        self.assertAlmostEqual(size_usd, 600.0, places=6)

    def test_reduce_divides_by_leverage(self):
        """size_usd is MARGIN and the gate is handed margin x leverage, so a
        reduce must divide or it sells L times too much. Every other test here
        happened to run at leverage 1.0, where the divide is a no-op — a
        mutation dropping it survived the whole suite until this case existed.
        """
        size_usd, lev = _sized("sell", 0.5, held=100.0, entry=10.0,
                               max_bet=1000.0, cfg_lev=3.0, order_lev=None)
        self.assertAlmostEqual(lev, 3.0)
        self.assertAlmostEqual(size_usd, 100.0 * 10.0 * 0.5 / 3.0, places=6)
        # and the round trip through the gate lands on exactly half the book
        self.assertAlmostEqual(_quantity(size_usd, lev, 10.0), 50.0, places=6)


class HorizonTests(_EnvMixin):
    def _run(self, until=None):
        cond = {} if until is None else {"horizon_until": until}
        return {"id": 825, "agent_id": 6, "symbol": "KAITO", "market": "crypto",
                "stop_conditions_json": json.dumps(cond)}

    def test_no_horizon_never_skips(self):
        self.assertIsNone(run_engine._horizon_skip(self._run(), None, True))

    def test_elapsed_horizon_never_skips(self):
        self.assertIsNone(run_engine._horizon_skip(
            self._run("2020-01-01T00:00:00Z"), {"triggers": []}, True))

    def test_live_horizon_skips_the_cycle(self):
        reason = run_engine._horizon_skip(
            self._run("2099-01-01T00:00:00Z"), {"triggers": []}, True)
        self.assertIsNotNone(reason)
        self.assertIn("desk horizon holds", reason)

    def test_a_flat_book_is_never_horizon_held(self):
        """The horizon governs a position, not a run: with nothing open the
        desk must be free to enter."""
        self.assertIsNone(run_engine._horizon_skip(
            self._run("2099-01-01T00:00:00Z"), {"triggers": []}, False))

    def test_ambient_flags_do_not_bypass(self):
        """psych_shock and hot_issue are market-wide and stay on for long
        stretches — all four live runs carried both simultaneously on
        2026-07-30. Letting them bypass would make the horizon inert."""
        for trig in ([], ["psych_shock"], ["hot_issue"],
                     ["psych_shock", "hot_issue"]):
            self.assertIsNotNone(
                run_engine._horizon_skip(self._run("2099-01-01T00:00:00Z"),
                                         {"triggers": trig}, True), msg=trig)

    def test_symbol_specific_triggers_bypass(self):
        for trig in (["near_stop"], ["event_window"], ["regime:panic"],
                     ["psych_shock", "near_stop"]):
            self.assertIsNone(
                run_engine._horizon_skip(self._run("2099-01-01T00:00:00Z"),
                                         {"triggers": trig}, True), msg=trig)

    def test_unreadable_triggers_do_not_suppress_the_cycle(self):
        self.assertIsNone(run_engine._horizon_skip(
            self._run("2099-01-01T00:00:00Z"), {"triggers": 7}, True))

    def test_kill_switch_disables_the_hold(self):
        self.env("RUN_ORDER_PLAN", "false")
        self.assertIsNone(run_engine._horizon_skip(
            self._run("2099-01-01T00:00:00Z"), {"triggers": []}, True))


class PlanPersistenceTests(_EnvMixin):
    def _run(self, cond=None):
        return {"id": 825, "stop_conditions_json": json.dumps(cond or {})}

    def test_trail_pct_becomes_the_shape_the_lock_already_reads(self):
        """trail_arm_pct is a % of position NOTIONAL; the trailing lock speaks
        activate_usd/giveback_frac, so convert rather than add new keys."""
        p = OrderParams(trail_arm_pct=12.0, trail_give=0.3)
        plan = run_engine._plan_stop_conditions(
            self._run(), p, entry=1.2157, quantity=308.464259, leverage=1.5)
        notional = 308.464259 * 1.2157
        self.assertAlmostEqual(plan["trail"]["activate_usd"],
                               round(notional * 0.12, 2), places=2)
        self.assertAlmostEqual(plan["trail"]["giveback_frac"], 0.3)

    def test_the_converted_trail_survives_the_validator(self):
        """A key validate_stop_conditions does not whitelist is a SILENT
        no-op — the trap that made three authored trails vanish."""
        p = OrderParams(trail_arm_pct=12.0, trail_give=0.3, horizon_hours=72.0)
        plan = run_engine._plan_stop_conditions(
            self._run(), p, entry=1.2157, quantity=308.464259, leverage=1.5)
        cleaned = trading_runs.validate_stop_conditions(plan)
        self.assertIn("trail", cleaned)
        self.assertIn("horizon_until", cleaned)

    def test_horizon_hours_becomes_a_timestamp(self):
        p = OrderParams(horizon_hours=72.0)
        plan = run_engine._plan_stop_conditions(
            self._run(), p, entry=1.0, quantity=1.0, leverage=1.0)
        self.assertIn("horizon_until", plan)
        self.assertGreater(plan["horizon_until"], run_engine._now_iso())

    def test_existing_stop_conditions_are_preserved(self):
        p = OrderParams(horizon_hours=1.0)
        plan = run_engine._plan_stop_conditions(
            self._run({"max_loss_usd": 97.11}), p,
            entry=1.0, quantity=1.0, leverage=1.0)
        self.assertEqual(plan["max_loss_usd"], 97.11)

    def test_half_specified_trail_is_ignored(self):
        """A trail with an arm and no giveback would arm and never release."""
        for p in (OrderParams(trail_arm_pct=12.0), OrderParams(trail_give=0.3)):
            plan = run_engine._plan_stop_conditions(
                self._run(), p, entry=1.0, quantity=1.0, leverage=1.0)
            self.assertIsNone(plan)

    def test_no_authored_fields_writes_nothing(self):
        self.assertIsNone(run_engine._plan_stop_conditions(
            self._run(), OrderParams(size_frac=0.5), entry=1.0,
            quantity=1.0, leverage=1.0))
        self.assertIsNone(run_engine._plan_stop_conditions(
            self._run(), None, entry=1.0, quantity=1.0, leverage=1.0))

    def test_kill_switch_writes_nothing(self):
        self.env("RUN_ORDER_PLAN", "false")
        self.assertIsNone(run_engine._plan_stop_conditions(
            self._run(), OrderParams(horizon_hours=72.0), entry=1.0,
            quantity=1.0, leverage=1.0))

    def test_persist_goes_through_the_validator(self):
        """Raw JSON would let a future field look stored while being invisible
        to _evaluate_stop."""
        with patch.object(trading_runs, "validate_stop_conditions",
                          side_effect=ValueError("nope")) as v, \
                patch.object(run_engine, "get_db_connection") as db:
            run_engine._persist_order_plan(825, {"horizon_until": "x"})
        v.assert_called_once()
        db.assert_not_called()


class MaxAddsTests(_EnvMixin):
    """The desk's max_adds is shrink-only against the house limit — it may
    always be MORE cautious than the config, never less."""

    def _skip(self, house, desk, adds_done=1):
        run = {"id": 1, "agent_id": 6, "symbol": "X", "market": "crypto",
               "market_type": "spot"}
        cfg = {"add_limits": {"max_adds": house, "cooldown_minutes": 0}}
        rows = [{"executed_at": "2020-01-01T00:00:00Z"}] * (adds_done + 1)

        class _Cur:
            def execute(self, *a, **k): pass
            def fetchall(self): return rows
            def fetchone(self): return None

        class _Conn:
            def cursor(self): return _Cur()
            def close(self): pass

        with patch.object(run_engine, "_position_quantity", return_value=5.0), \
                patch.object(run_engine, "get_db_connection", return_value=_Conn()), \
                patch.object(run_engine, "_adds_require_profit", return_value=False):
            return run_engine._add_limit_skip(run, cfg, "buy",
                                              max_adds_override=desk)

    def test_desk_zero_blocks_every_add(self):
        r = self._skip(house=2, desk=0)
        self.assertIsNotNone(r)
        self.assertIn("max_adds=0", r)

    def test_desk_may_tighten_below_the_house_limit(self):
        self.assertIsNotNone(self._skip(house=3, desk=1, adds_done=1))

    def test_desk_may_not_loosen_beyond_the_house_limit(self):
        self.assertIsNotNone(self._skip(house=1, desk=3, adds_done=1))

    def test_no_override_leaves_the_house_limit_alone(self):
        self.assertIsNone(self._skip(house=3, desk=None, adds_done=1))

    def test_kill_switch_ignores_the_desk(self):
        self.env("RUN_ORDER_PLAN", "false")
        self.assertIsNone(self._skip(house=3, desk=0, adds_done=1))


class EndToEndReduceTests(unittest.TestCase):
    """Drives the real run_cycle.

    The unit tests above call _order_size_usd directly, so they prove the
    FUNCTION is right and say nothing about whether run_cycle calls it with
    the held quantity. A mutation that stopped passing the book through
    survived every one of them. This is the wiring test.
    """

    def setUp(self):
        import tempfile
        from fastapi.testclient import TestClient
        import database
        from routes import create_app
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.db = database
        self._env = {k: os.environ.get(k) for k in
                     ("AUTO_TRADING_ENABLED", "RUN_AI_ORDER_PARAMS",
                      "RUN_SIZE_BY_CONVICTION", "RISK_ENGINE_ENABLED")}
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_AI_ORDER_PARAMS"] = "apply"
        os.environ["RUN_SIZE_BY_CONVICTION"] = "false"   # isolate size_frac
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "ob-agent", "password": "pw123",
                                   "initial_balance": 100000.0}).json()
        self.token, self.agent_id = r["token"], r["agent_id"]

    def tearDown(self):
        self.probe.stop()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _analysis(self, action, order=None):
        d = {"action": action, "confidence": 0.9, "entry": 100.0, "report": "r"}
        if order is not None:
            d["order"] = order
        return {"symbol": "BTC", "market": "crypto",
                "analysts": {"technical": {"brief": "t", "data": {
                    "sigma_daily_pct": 2.5, "current_price": 100.0}}},
                "decision": d}

    def _held(self, run_id):
        return run_engine._position_quantity(self.agent_id, "crypto", "BTC",
                                             run_id)

    def test_a_60pct_reduce_leaves_40pct_of_the_book(self):
        run_id = self.client.post(
            "/api/runs", json={"symbol": "BTC", "market": "crypto",
                               "max_bet_usd": 1000.0},
            headers=self._h()).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())

        with patch("analysis_agents.run_analysis",
                   return_value=self._analysis("buy", {"size_frac": 1.0})):
            self.assertTrue(run_engine.run_cycle(run_id)["executed"])
        opened = self._held(run_id)
        self.assertGreater(opened, 0)

        with patch("analysis_agents.run_analysis",
                   return_value=self._analysis("sell", {"size_frac": 0.6})):
            res = run_engine.run_cycle(run_id)
        self.assertTrue(res["executed"], res)
        left = self._held(run_id)
        # 60% of the BOOK went, not 60% of the budget (which would have
        # overshot and flattened it) — this is prod run 825's exact failure.
        self.assertAlmostEqual(left, opened * 0.4, places=6)
        self.assertGreater(left, 0, "a 60% reduce must not flatten the book")


if __name__ == "__main__":
    unittest.main()
