"""Plan 17 — Order Intent: parse, asymmetric rails, the total compiler, and
the run_cycle wiring.

The §6 table is tested cell by cell because run 776 proves an untested cell
is a live bug, and the §2 defect (exit size derived from max_bet_usd) gets a
permanent end-to-end tripwire.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import order_intent as OI  # noqa: E402
import run_engine  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_absent_or_garbage_is_none(self):
        for raw in (None, "reduce", 5, [], {}, {"intent": "banana"},
                    {"intent": ""}):
            self.assertIsNone(OI.parse(raw), raw)

    def test_reduce_carries_position_basis(self):
        p = OI.parse({"intent": "reduce", "size_frac": 0.5})
        self.assertEqual(p["size_basis"], "position")
        self.assertEqual(p["size_frac"], 0.5)

    def test_open_and_add_carry_budget_basis(self):
        for kind in ("open", "add", "flip"):
            p = OI.parse({"intent": kind, "size_frac": 0.3})
            self.assertEqual(p["size_basis"], "budget", kind)

    def test_model_supplied_basis_is_ignored(self):
        # A desk that says "reduce 0.5 of my budget" is confused; honouring
        # the confusion recreates the defect.
        p = OI.parse({"intent": "reduce", "size_frac": 0.5,
                      "size_basis": "budget"})
        self.assertEqual(p["size_basis"], "position")

    def test_close_forces_full_size_whatever_was_sent(self):
        for frac in (0.1, None, 7):
            p = OI.parse({"intent": "close", "size_frac": frac})
            self.assertEqual(p["size_frac"], 1.0, frac)

    def test_size_frac_bounds(self):
        for bad in (0.0, -0.5, 1.5, "x", None):
            self.assertIsNone(OI.parse({"intent": "reduce", "size_frac": bad}),
                              bad)

    def test_hold_needs_no_size(self):
        self.assertEqual(OI.parse({"intent": "hold"})["intent"], "hold")

    def test_arm_valid(self):
        p = OI.parse({"intent": "arm",
                      "arm": {"if": "price_above", "level": 27800,
                              "then": "reduce", "size_frac": 0.5}})
        self.assertEqual(p["arm"]["if"], "price_above")
        self.assertEqual(p["arm"]["size_frac"], 0.5)
        self.assertEqual(p["size_basis"], "position")

    def test_arm_then_close_forces_full(self):
        p = OI.parse({"intent": "arm",
                      "arm": {"if": "price_below", "level": 50.0,
                              "then": "close"}})
        self.assertEqual(p["arm"]["size_frac"], 1.0)

    def test_arm_may_only_shed_risk(self):
        # `then` outside reduce|close is refused — arm never opens anything.
        self.assertIsNone(OI.parse({"intent": "arm",
                                    "arm": {"if": "price_above", "level": 1.0,
                                            "then": "buy", "size_frac": 0.5}}))

    def test_arm_invalid_shapes(self):
        bad = [
            {"if": "price_sideways", "level": 1, "then": "reduce", "size_frac": 0.5},
            {"if": "price_above", "level": "x", "then": "reduce", "size_frac": 0.5},
            {"if": "price_above", "level": -3, "then": "reduce", "size_frac": 0.5},
            {"if": "health_below", "level": 1.5, "then": "close"},
            {"if": "price_above", "level": 1, "then": "reduce", "size_frac": 0},
            None, "sell half",
        ]
        for arm in bad:
            self.assertIsNone(OI.parse({"intent": "arm", "arm": arm}), arm)

    def test_health_below_accepts_a_health_scalar(self):
        p = OI.parse({"intent": "arm",
                      "arm": {"if": "health_below", "level": 0.35,
                              "then": "close"}})
        self.assertEqual(p["arm"]["level"], 0.35)


class RailTests(unittest.TestCase):
    """The asymmetry carries the whole safety argument."""

    def test_reduce_is_never_railed_down(self):
        p = OI.parse({"intent": "reduce", "size_frac": 1.0})
        railed = OI.rail(p, position_notional_usd=1_000_000.0)
        self.assertEqual(railed["size_frac"], 1.0)
        self.assertEqual(railed["railed"], {})

    def test_dust_reduce_is_grown_not_refused(self):
        # $100 book, 0.1% slice = $0.10 < $1 minimum -> grown to exactly $1.
        p = OI.parse({"intent": "reduce", "size_frac": 0.001})
        railed = OI.rail(p, position_notional_usd=100.0)
        self.assertAlmostEqual(railed["size_frac"], 0.01, places=9)
        self.assertEqual(railed["railed"]["size_frac"]["why"],
                         "dust_slice_grown")

    def test_dust_growth_caps_at_the_whole_position(self):
        # A book smaller than the minimum slice: grow to 1.0, never beyond.
        p = OI.parse({"intent": "reduce", "size_frac": 0.5})
        railed = OI.rail(p, position_notional_usd=0.40)
        self.assertEqual(railed["size_frac"], 1.0)

    def test_dust_remainder_compiles_to_full_close(self):
        """Plan 24 fix 4 (live run 1083, 2026-08-12): four correct 'cover
        half' calls left a $4.45 remainder no move can bank. A reduce whose
        REMAINDER would fall below the manage-worthy floor grows to a full
        close — shedding risk, so the rail may only grow."""
        p = OI.parse({"intent": "reduce", "size_frac": 0.5})
        railed = OI.rail(p, position_notional_usd=40.0)   # remainder $20 < $25
        self.assertEqual(railed["size_frac"], 1.0)
        self.assertEqual(railed["railed"]["size_frac"]["why"],
                         "dust_remainder_closed")

    def test_healthy_remainder_is_untouched(self):
        p = OI.parse({"intent": "reduce", "size_frac": 0.5})
        railed = OI.rail(p, position_notional_usd=200.0)  # remainder $100
        self.assertEqual(railed["size_frac"], 0.5)
        self.assertEqual(railed["railed"], {})

    def test_close_is_never_railed(self):
        p = OI.parse({"intent": "close"})
        railed = OI.rail(p, position_notional_usd=0.01)
        self.assertEqual(railed["size_frac"], 1.0)
        self.assertEqual(railed["railed"], {})

    def test_open_is_never_railed_up(self):
        p = OI.parse({"intent": "open", "size_frac": 0.02})
        railed = OI.rail(p, position_notional_usd=0.0)
        self.assertEqual(railed["size_frac"], 0.02)
        self.assertEqual(railed["railed"], {})


class CompilerTests(unittest.TestCase):
    """Every cell of the §6 table. An untested cell is a live bug."""

    def _c(self, kind, frac=0.5, *, fut, pos, bull=None):
        return OI.compile_intent(kind, frac, is_futures=fut,
                                 position_qty=pos, bull=bull)

    def _verbs(self, out):
        return [(s["verb"], s["basis"]) for s in out["steps"]]

    # ── open (bull) row ────────────────────────────────────────────────
    def test_open_bull_spot_flat(self):
        self.assertEqual(self._verbs(self._c("open", fut=False, pos=0, bull=True)),
                         [("buy", "budget")])

    def test_open_bull_futures_long(self):
        self.assertEqual(self._verbs(self._c("open", fut=True, pos=5, bull=True)),
                         [("buy", "budget")])

    def test_open_bull_futures_short_covers_then_buys(self):
        out = self._c("open", fut=True, pos=-5, bull=True)
        self.assertEqual(self._verbs(out),
                         [("cover", "position"), ("buy", "budget")])
        self.assertEqual(out["steps"][0]["size_frac"], 1.0)

    def test_open_bull_futures_flat(self):
        self.assertEqual(self._verbs(self._c("open", fut=True, pos=0, bull=True)),
                         [("buy", "budget")])

    # ── open (bear) row ────────────────────────────────────────────────
    def test_open_bear_spot_is_hold(self):
        out = self._c("open", fut=False, pos=3, bull=False)
        self.assertEqual(out["steps"], [])
        self.assertEqual(out["note"], "spot_bear_hold")

    def test_open_bear_futures_long_compiles_to_sell(self):
        self.assertEqual(self._verbs(self._c("open", fut=True, pos=5, bull=False)),
                         [("sell", "budget")])

    def test_open_bear_futures_short(self):
        self.assertEqual(self._verbs(self._c("open", fut=True, pos=-5, bull=False)),
                         [("short", "budget")])

    def test_open_bear_futures_flat(self):
        self.assertEqual(self._verbs(self._c("open", fut=True, pos=0, bull=False)),
                         [("short", "budget")])

    def test_open_without_direction_is_uncompilable(self):
        out = self._c("open", fut=True, pos=0, bull=None)
        self.assertEqual(out["steps"], [])
        self.assertEqual(out["note"], "no_direction")

    def test_add_compiles_like_open(self):
        for fut, pos, bull in ((False, 3, True), (True, -5, False), (True, 0, True)):
            self.assertEqual(
                self._verbs(self._c("add", fut=fut, pos=pos, bull=bull)),
                self._verbs(self._c("open", fut=fut, pos=pos, bull=bull)))

    # ── reduce row ─────────────────────────────────────────────────────
    def test_reduce_spot_long(self):
        out = self._c("reduce", 0.6, fut=False, pos=3)
        self.assertEqual(self._verbs(out), [("sell", "position")])
        self.assertEqual(out["steps"][0]["size_frac"], 0.6)

    def test_reduce_futures_long(self):
        self.assertEqual(self._verbs(self._c("reduce", fut=True, pos=3)),
                         [("sell", "position")])

    def test_reduce_futures_short_covers(self):
        self.assertEqual(self._verbs(self._c("reduce", fut=True, pos=-3)),
                         [("cover", "position")])

    def test_reduce_flat_is_noop(self):
        for fut in (False, True):
            out = self._c("reduce", fut=fut, pos=0)
            self.assertEqual(out["steps"], [])
            self.assertEqual(out["note"], "reduce_on_flat_noop")

    # ── close row ──────────────────────────────────────────────────────
    def test_close_spot_long_full(self):
        out = self._c("close", fut=False, pos=3)
        self.assertEqual(self._verbs(out), [("sell", "position")])
        self.assertEqual(out["steps"][0]["size_frac"], 1.0)

    def test_close_futures_long_full(self):
        out = self._c("close", fut=True, pos=3)
        self.assertEqual(self._verbs(out), [("sell", "position")])
        self.assertEqual(out["steps"][0]["size_frac"], 1.0)

    def test_close_futures_short_covers_full(self):
        out = self._c("close", fut=True, pos=-3)
        self.assertEqual(self._verbs(out), [("cover", "position")])
        self.assertEqual(out["steps"][0]["size_frac"], 1.0)

    def test_close_flat_is_noop(self):
        for fut in (False, True):
            self.assertEqual(self._c("close", fut=fut, pos=0)["steps"], [])

    # ── flip row ───────────────────────────────────────────────────────
    def test_flip_spot_long_degrades_to_close(self):
        out = self._c("flip", 0.4, fut=False, pos=3)
        self.assertEqual(self._verbs(out), [("sell", "position")])
        self.assertEqual(out["note"], "flip_spot_degrades_to_close")

    def test_flip_futures_long_sells_full_then_shorts(self):
        out = self._c("flip", 0.4, fut=True, pos=3)
        self.assertEqual(self._verbs(out),
                         [("sell", "position"), ("short", "budget")])
        self.assertEqual(out["steps"][0]["size_frac"], 1.0)
        self.assertEqual(out["steps"][1]["size_frac"], 0.4)

    def test_flip_futures_short_covers_full_then_buys(self):
        out = self._c("flip", 0.4, fut=True, pos=-3)
        self.assertEqual(self._verbs(out),
                         [("cover", "position"), ("buy", "budget")])

    def test_flip_flat_degrades_to_open(self):
        self.assertEqual(self._verbs(self._c("flip", fut=True, pos=0, bull=False)),
                         [("short", "budget")])
        self.assertEqual(self._c("flip", fut=True, pos=0, bull=None)["note"],
                         "no_direction")

    # ── hold / arm rows ────────────────────────────────────────────────
    def test_hold_and_arm_place_nothing_anywhere(self):
        for kind in ("hold", "arm"):
            for fut in (False, True):
                for pos in (-3, 0, 3):
                    self.assertEqual(
                        self._c(kind, fut=fut, pos=pos)["steps"], [],
                        (kind, fut, pos))

    def test_compiler_is_total(self):
        # No (intent x book x direction) combination may raise — totality is
        # the property run 776 proves the inline remap never had.
        for kind in OI.INTENTS:
            for fut in (False, True):
                for pos in (-3.0, 0.0, 3.0):
                    for bull in (True, False, None):
                        out = OI.compile_intent(kind, 0.5, is_futures=fut,
                                                position_qty=pos, bull=bull)
                        self.assertIsInstance(out["steps"], list,
                                              (kind, fut, pos, bull))


class ExitSizeTests(unittest.TestCase):
    def test_the_math(self):
        # 10 units @ 100 on 2x: full close commits 500 of margin.
        self.assertAlmostEqual(
            OI.exit_size_usd(1.0, position_qty=10, entry=100, leverage=2), 500.0)
        self.assertAlmostEqual(
            OI.exit_size_usd(0.5, position_qty=-10, entry=100, leverage=2), 250.0)

    def test_signature_has_no_budget_parameter(self):
        # The §2 tripwire at the unit level: the function CANNOT be handed a
        # budget. (The end-to-end tripwire is in WiringTests.)
        import inspect
        params = inspect.signature(OI.exit_size_usd).parameters
        self.assertNotIn("max_bet_usd", params)
        self.assertEqual(set(params) - {"size_frac"},
                         {"position_qty", "entry", "leverage"})


class BullFromActionTests(unittest.TestCase):
    def test_mapping(self):
        self.assertTrue(OI.bull_from_action("buy"))
        self.assertTrue(OI.bull_from_action("cover"))
        self.assertFalse(OI.bull_from_action("sell"))
        self.assertFalse(OI.bull_from_action("short"))
        self.assertIsNone(OI.bull_from_action("hold"))
        self.assertIsNone(OI.bull_from_action(None))


class ModeTests(unittest.TestCase):
    def test_default_is_shadow(self):
        old = os.environ.pop("RUN_ORDER_INTENT", None)
        try:
            self.assertEqual(OI.intent_mode(), "shadow")
        finally:
            if old is not None:
                os.environ["RUN_ORDER_INTENT"] = old

    def test_garbage_falls_back_to_shadow(self):
        with patch.dict(os.environ, {"RUN_ORDER_INTENT": "yolo"}):
            self.assertEqual(OI.intent_mode(), "shadow")
        with patch.dict(os.environ, {"RUN_ORDER_INTENT": "apply"}):
            self.assertEqual(OI.intent_mode(), "apply")
        with patch.dict(os.environ, {"RUN_ORDER_INTENT": "off"}):
            self.assertEqual(OI.intent_mode(), "off")


class WiringTests(unittest.TestCase):
    """Drives the real run_cycle. A mutation that unwires the intent from the
    cycle must fail HERE — the unit tests above cannot see the wire."""

    def setUp(self):
        import tempfile
        from fastapi.testclient import TestClient
        import database
        from routes import create_app
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self._env = {k: os.environ.get(k) for k in
                     ("AUTO_TRADING_ENABLED", "RUN_ORDER_INTENT",
                      "RUN_AI_ORDER_PARAMS", "RUN_SIZE_BY_CONVICTION")}
        os.environ["AUTO_TRADING_ENABLED"] = "true"
        os.environ["RUN_ORDER_INTENT"] = "apply"
        os.environ["RUN_AI_ORDER_PARAMS"] = "off"
        os.environ["RUN_SIZE_BY_CONVICTION"] = "false"
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        r = self.client.post("/api/claw/agents/selfRegister",
                             json={"name": "oi-agent", "password": "pw123",
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

    def _run(self, **extra):
        payload = {"symbol": "BTC", "market": "crypto",
                   "max_bet_usd": 1000.0, **extra}
        run_id = self.client.post("/api/runs", json=payload,
                                  headers=self._h()).json()["id"]
        self.client.post(f"/api/runs/{run_id}/start", headers=self._h())
        return run_id

    def _analysis(self, action, intent=None):
        d = {"action": action, "confidence": 0.9, "entry": 100.0, "report": "r"}
        if intent is not None:
            d["order_intent"] = intent
        return {"symbol": "BTC", "market": "crypto",
                "analysts": {"technical": {"brief": "t", "data": {
                    "sigma_daily_pct": 2.5, "current_price": 100.0}}},
                "decision": d}

    def _held(self, run_id):
        return run_engine._position_quantity(self.agent_id, "crypto", "BTC",
                                             run_id)

    def _cycle(self, run_id, action, intent=None):
        with patch("analysis_agents.run_analysis",
                   return_value=self._analysis(action, intent)):
            return run_engine.run_cycle(run_id)

    def _events(self, run_id, kind):
        import json as _json
        import trading_runs
        rows = trading_runs.list_events(run_id, self.agent_id, limit=500) or []
        return [{**e, "payload": _json.loads(e["payload"])}
                for e in rows if e.get("event_type") == kind]

    def test_reduce_intent_sheds_exactly_the_stated_fraction(self):
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        opened = self._held(run_id)
        self.assertGreater(opened, 0)

        res = self._cycle(run_id, "sell",
                          {"intent": "reduce", "size_frac": 0.6})
        self.assertTrue(res["executed"], res)
        self.assertAlmostEqual(self._held(run_id), opened * 0.4, places=6)

    def test_the_section_2_tripwire_exit_never_sized_from_budget(self):
        # max_bet is 20x the position. A budget-derived exit would flatten;
        # the intent must shed exactly 30% of the BOOK. This is the defect —
        # it deserves a permanent end-to-end alarm.
        run_id = self._run(max_bet_usd=100.0)
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        opened = self._held(run_id)

        import sqlite3
        con = sqlite3.connect(os.path.join(self.tmp.name, "t.db"))
        con.execute("UPDATE trading_runs SET config_snapshot_json = "
                    "REPLACE(config_snapshot_json, '\"max_bet_usd\": 100.0', "
                    "'\"max_bet_usd\": 2000.0')")
        con.commit()
        con.close()

        res = self._cycle(run_id, "sell",
                          {"intent": "reduce", "size_frac": 0.3})
        self.assertTrue(res["executed"], res)
        self.assertAlmostEqual(self._held(run_id), opened * 0.7, places=6,
                               msg="exit was sized from max_bet_usd — the §2 "
                                   "defect is back")

    def test_close_flattens_and_ignores_the_confidence_gate(self):
        run_id = self._run(min_confidence=0.99)
        # The open needs to clear the 0.99 floor to build a book.
        with patch("analysis_agents.run_analysis",
                   return_value={**self._analysis("buy"),
                                 "decision": {"action": "buy",
                                              "confidence": 1.0,
                                              "entry": 100.0, "report": "r"}}):
            self.assertTrue(run_engine.run_cycle(run_id)["executed"])
        self.assertGreater(self._held(run_id), 0)

        # confidence 0.1 against a 0.99 floor: an entry would be refused;
        # the close must not be — there is no safe reason to refuse a flatten.
        with patch("analysis_agents.run_analysis",
                   return_value={**self._analysis("sell"),
                                 "decision": {"action": "sell",
                                              "confidence": 0.1,
                                              "entry": 100.0, "report": "r",
                                              "order_intent": {"intent": "close"}}}):
            res = run_engine.run_cycle(run_id)
        self.assertTrue(res["executed"], res)
        self.assertEqual(self._held(run_id), 0)

    def test_intent_exit_bypasses_the_percentile_gate(self):
        # The percentile gate needs agent history to trip, which a fresh test
        # agent lacks — so force it to refuse everything and prove the intent
        # exit never consults it. A mutation that re-applies the gate to
        # exits fails here and nowhere else.
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        self.assertGreater(self._held(run_id), 0)

        with patch.object(run_engine, "_conf_percentile_skip",
                          return_value=("confidence rank refused", 0.99)):
            res = self._cycle(run_id, "sell", {"intent": "close"})
        self.assertTrue(res["executed"], res)
        self.assertEqual(self._held(run_id), 0)

    def test_close_intent_on_a_hold_verb_still_closes(self):
        # The intent IS the decision. A desk that says action=hold but
        # intent=close means close — the legacy verb would have died at the
        # gate ("decision is 'hold'"), and before Plan 17 'close it' was
        # literally unreachable from the decision layer.
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        self.assertGreater(self._held(run_id), 0)
        res = self._cycle(run_id, "hold", {"intent": "close"})
        self.assertTrue(res["executed"], res)
        self.assertEqual(self._held(run_id), 0)

    def test_no_intent_key_runs_the_legacy_path_unchanged(self):
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        res = self._cycle(run_id, "sell")     # plain verb, no intent
        self.assertTrue(res["executed"], res)
        # Legacy sell is entry-sized (max_bet 1000 vs 1000 book -> flattens).
        self.assertEqual(self._held(run_id), 0)

    def test_shadow_journals_but_does_not_touch_the_order(self):
        os.environ["RUN_ORDER_INTENT"] = "shadow"
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        opened = self._held(run_id)

        res = self._cycle(run_id, "sell",
                          {"intent": "reduce", "size_frac": 0.25})
        self.assertTrue(res["executed"], res)
        # Shadow: the legacy entry-sized sell flattened the book anyway...
        self.assertEqual(self._held(run_id), 0)
        # ...but the intent was journalled beside it, with both sizes.
        events = self._events(run_id, "order_intent")
        self.assertEqual(len(events), 1)
        payload = events[0]["payload"]
        self.assertEqual(payload["intent"], "reduce")
        self.assertEqual(payload["mode"], "shadow")
        self.assertEqual(payload["size_basis"], "position")
        self.assertAlmostEqual(payload["intent_size_usd"],
                               opened * 100.0 * 0.25, places=2)
        self.assertEqual(payload["compiled"]["steps"][0]["verb"], "sell")

    def test_off_mode_journals_nothing(self):
        os.environ["RUN_ORDER_INTENT"] = "off"
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        self._cycle(run_id, "sell", {"intent": "reduce", "size_frac": 0.5})
        self.assertEqual(self._events(run_id, "order_intent"), [])

    def test_apply_ignores_non_exit_intents(self):
        # Phase 1 is exits only: an `open` intent journals and the legacy
        # path runs unchanged.
        run_id = self._run()
        res = self._cycle(run_id, "buy",
                          {"intent": "open", "size_frac": 0.1})
        self.assertTrue(res["executed"], res)
        events = self._events(run_id, "order_intent")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["intent"], "open")
        # Legacy sizing: full max_bet, not 10% of it.
        self.assertAlmostEqual(self._held(run_id) * 100.0, 1000.0, delta=20)

    def test_invalid_intent_falls_back_to_legacy(self):
        run_id = self._run()
        self.assertTrue(self._cycle(run_id, "buy")["executed"])
        res = self._cycle(run_id, "sell",
                          {"intent": "reduce", "size_frac": 99})
        self.assertTrue(res["executed"], res)
        self.assertEqual(self._held(run_id), 0)   # legacy entry-sized sell


if __name__ == "__main__":
    unittest.main()


class ArmPredicateTests(unittest.TestCase):
    """`arm_fires` is the pure trigger predicate for the arm executor. It is
    guarded twice on purpose (here and in run_engine._fire_armed_order); this
    class pins THIS layer so the redundancy cannot rot away unnoticed."""

    LONG_BANK = {"if": "price_above", "then": "reduce",
                 "level": 100.0, "size_frac": 0.5}
    PROTECT = {"if": "price_below", "then": "close", "level": 100.0}

    def test_fires_only_on_the_correct_side_of_the_level(self):
        self.assertTrue(OI.arm_fires(self.LONG_BANK, mark=100.01))
        self.assertFalse(OI.arm_fires(self.LONG_BANK, mark=100.0))
        self.assertFalse(OI.arm_fires(self.LONG_BANK, mark=99.99))
        self.assertTrue(OI.arm_fires(self.PROTECT, mark=99.99))
        self.assertFalse(OI.arm_fires(self.PROTECT, mark=100.0))

    def test_a_missing_mark_never_fires(self):
        # Never price an exit on data already declared untrustworthy.
        self.assertFalse(OI.arm_fires(self.PROTECT, mark=None))
        self.assertFalse(OI.arm_fires(self.PROTECT, mark=0))
        self.assertFalse(OI.arm_fires(self.PROTECT, mark="x"))

    def test_a_garbage_arm_never_fires(self):
        # Firing on a malformed arm would exit a position nobody asked to exit.
        for bad in (None, {}, "arm", {"if": "price_below"},
                    {"if": "price_below", "then": "close", "level": 0},
                    {"if": "price_below", "then": "close", "level": "x"},
                    {"if": "nonsense", "then": "close", "level": 100.0},
                    {"if": "price_below", "then": "open", "level": 100.0}):
            self.assertFalse(OI.arm_fires(bad, mark=99.0), bad)

    def test_health_below_parses_but_is_not_executable(self):
        # Explicitly inert rather than silently ignored — margin health is
        # not carried on the control pass.
        arm = {"if": "health_below", "then": "close", "level": 0.5}
        self.assertIsNotNone(OI.parse({"intent": "arm", "arm": arm}))
        self.assertNotIn("health_below", OI.EXECUTABLE_ARM_CONDITIONS)
        self.assertFalse(OI.arm_fires(arm, mark=0.1))

    def test_it_fires_through_an_arbitrarily_large_gap(self):
        # ARM_THEN is exits-only so an arm can only SHED risk, and this
        # module never refuses that. Distance is journalled, not vetoed.
        self.assertTrue(OI.arm_fires(self.PROTECT, mark=1.0))

    def test_exit_fraction_close_is_whole_book_reduce_carries_its_own(self):
        self.assertEqual(OI.arm_exit_fraction(self.PROTECT), 1.0)
        self.assertEqual(OI.arm_exit_fraction(self.LONG_BANK), 0.5)
        for bad in (None, {}, {"then": "reduce"},
                    {"then": "reduce", "size_frac": 0},
                    {"then": "reduce", "size_frac": 1.5},
                    {"then": "reduce", "size_frac": "x"}):
            self.assertEqual(OI.arm_exit_fraction(bad), 0.0, bad)
