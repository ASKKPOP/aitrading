"""Wiring of the long exit policy (owner 2026-11-21) into the paths that
actually close a long: the shared executor, the ledger backstop, the SL/TP
watcher, the run stop rails and the run flatten.

conftest runs the suite with LONG_EXIT_POLICY=0; every test here unsets it
(the production default, ON) unless it is testing the kill switch.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import long_exit_policy

NOW = "2026-11-21T00:00:00Z"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.env = patch.dict(os.environ, {"RISK_ENGINE_ENABLED": "true",
                                           "FUTURES_TRADING_BLOCKED": "0"})
        self.env.start()
        os.environ.pop("LONG_EXIT_POLICY", None)      # production default: ON
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('l@x.com', 'x', ?)", (NOW,))
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
                    "VALUES ('lep', 'th', 100000, ?, ?)", (uid, NOW))
        self.agent_id = cur.lastrowid
        cur.execute("INSERT INTO trading_runs (agent_id, symbol, market, market_type, "
                    "status, created_at) VALUES (?, 'BTCUSDT', 'crypto', 'spot', "
                    "'running', ?)", (self.agent_id, NOW))
        self.run_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _q(self, sql, args=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _x(self, sql, args=()):
        conn = database.get_db_connection()
        try:
            conn.cursor().execute(sql, args)
            conn.commit()
        finally:
            conn.close()

    def _buy(self, run_id=None, price=100.0, qty=1.0):
        from automation import execute_paper_trade
        sid, skip = execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "buy",
                                        qty, price, run_id=run_id)
        self.assertIsNotNone(sid, skip)

    def _sell(self, price, run_id=None, human=False):
        from automation import execute_paper_trade
        return execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "sell",
                                   1.0, price, run_id=run_id,
                                   human_initiated=human)

    def _held(self, run_id=None):
        rows = self._q("SELECT quantity FROM positions WHERE agent_id = ? AND "
                       + ("run_id = ?" if run_id else "run_id IS NULL"),
                       (self.agent_id, run_id) if run_id else (self.agent_id,))
        return sum(float(r["quantity"]) for r in rows)


class ExecutorTests(_Base):
    def test_automated_sell_below_buy_price_is_held(self):
        self._buy(self.run_id)
        sid, skip = self._sell(97.5, run_id=self.run_id)
        self.assertIsNone(sid)
        self.assertIn("long exit policy", skip)
        self.assertNotIn("position", skip)   # trend_module deletes state on "position"
        self.assertEqual(self._held(self.run_id), 1.0)

    def test_automated_sell_above_breakeven_fills(self):
        self._buy(self.run_id)
        sid, skip = self._sell(101.0, run_id=self.run_id)
        self.assertIsNotNone(sid, skip)
        self.assertEqual(self._held(self.run_id), 0.0)

    def test_emergency_level_fills(self):
        self._buy(self.run_id)
        sid, skip = self._sell(85.0, run_id=self.run_id)
        self.assertIsNotNone(sid, skip)

    def test_human_sell_at_a_loss_fills(self):
        self._buy(self.run_id)
        sid, skip = self._sell(97.5, run_id=self.run_id, human=True)
        self.assertIsNotNone(sid, skip)

    def test_kill_switch_restores_old_behaviour(self):
        self._buy(self.run_id)
        with patch.dict(os.environ, {"LONG_EXIT_POLICY": "0"}):
            sid, skip = self._sell(97.5, run_id=self.run_id)
        self.assertIsNotNone(sid, skip)

    def test_automated_buy_pins_minus_15_plus_5_off_the_average_entry(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "buy", 1.0, 100.0,
                            stop_loss=97.5, take_profit=110.0, run_id=self.run_id)
        execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "buy", 1.0, 120.0,
                            stop_loss=117.0, take_profit=126.0, run_id=self.run_id)
        row = self._q("SELECT entry_price, stop_loss, take_profit FROM positions "
                      "WHERE run_id = ?", (self.run_id,))[0]
        self.assertAlmostEqual(row["entry_price"], 110.0)
        self.assertAlmostEqual(row["stop_loss"], 93.5)
        self.assertAlmostEqual(row["take_profit"], 115.5)

    def test_human_buy_keeps_its_own_bracket(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "buy", 1.0, 100.0,
                            stop_loss=97.5, take_profit=110.0, human_initiated=True)
        row = self._q("SELECT stop_loss, take_profit FROM positions")[0]
        self.assertEqual((row["stop_loss"], row["take_profit"]), (97.5, 110.0))

    def test_cover_of_a_short_is_untouched(self):
        from automation import execute_paper_trade
        sid, skip = execute_paper_trade(self.agent_id, "ETHUSDT", "crypto", "short",
                                        1.0, 100.0, run_id=self.run_id)
        self.assertIsNotNone(sid, skip)
        sid, skip = execute_paper_trade(self.agent_id, "ETHUSDT", "crypto", "cover",
                                        1.0, 103.0, run_id=self.run_id)
        self.assertIsNotNone(sid, skip)


class LedgerBackstopTests(_Base):
    def _ledger_sell(self, price, **kw):
        from services import _update_position_from_signal
        conn = database.get_db_connection()
        try:
            _update_position_from_signal(self.agent_id, "BTCUSDT", "crypto", "sell",
                                         1.0, price, NOW, cursor=conn.cursor(), **kw)
            conn.commit()
        finally:
            conn.close()

    def test_automated_ledger_sell_below_buy_price_raises(self):
        self._buy()
        with self.assertRaises(ValueError):
            self._ledger_sell(97.5, automated=True)
        self.assertEqual(self._held(), 1.0)

    def test_manual_ledger_sell_is_untouched(self):
        self._buy()
        self._ledger_sell(97.5)          # default: not automated
        self.assertEqual(self._held(), 0.0)


class WatcherTests(_Base):
    def _tick(self):
        import risk_engine
        with patch.object(risk_engine, "_route_stop_hit_to_desk", return_value=False), \
             patch.object(risk_engine, "_trend_managed_agents", return_value=set()), \
             patch("alerts.send_alert"):
            return risk_engine.run_sltp_watcher_tick()

    def _mark(self, price, stop=None, tp=None):
        self._x("UPDATE positions SET current_price = ?, stop_loss = ?, "
                "take_profit = ? WHERE agent_id = ?",
                (price, stop, tp, self.agent_id))

    def test_run_long_ignores_its_stored_stop_until_minus_15(self):
        self._buy(self.run_id)
        self._mark(97.0, stop=97.5, tp=105.0)       # desk's 2.5% stop crossed
        self._tick()
        self.assertEqual(self._held(self.run_id), 1.0)
        self._mark(84.9, stop=97.5, tp=105.0)       # past the emergency level
        self._tick()
        self.assertEqual(self._held(self.run_id), 0.0)

    def test_run_long_takes_profit_at_plus_5_even_without_a_stored_target(self):
        self._buy(self.run_id)
        self._mark(104.9)
        self._tick()
        self.assertEqual(self._held(self.run_id), 1.0)
        self._mark(105.0)
        self._tick()
        self.assertEqual(self._held(self.run_id), 0.0)

    def _manual_long(self, price=100.0):
        """A person's own long: written straight to the ledger, the way the
        manual signal route does (no automation, no marker)."""
        from services import _update_position_from_signal
        conn = database.get_db_connection()
        try:
            _update_position_from_signal(self.agent_id, "BTCUSDT", "crypto", "buy",
                                         1.0, price, NOW, cursor=conn.cursor())
            conn.commit()
        finally:
            conn.close()

    def test_no_trailing_ratchet_on_a_legacy_run_long(self):
        self._buy(self.run_id)
        self._x("UPDATE positions SET exit_policy = 'v1' WHERE agent_id = ?",
                (self.agent_id,))                       # stamped before the policy
        self._x("INSERT INTO risk_limits (agent_id, use_trailing, trail_pct) "
                "VALUES (?, 1, 0.02)", (self.agent_id,))
        self._x("UPDATE positions SET current_price = 103 WHERE agent_id = ?",
                (self.agent_id,))
        self._tick()
        row = self._q("SELECT stop_loss, take_profit FROM positions")[0]
        self.assertAlmostEqual(row["stop_loss"], 85.0)   # not ratcheted up
        self._x("UPDATE positions SET current_price = 99.8 WHERE agent_id = ?",
                (self.agent_id,))
        self._tick()
        self.assertEqual(self._held(self.run_id), 1.0)   # no loss sale

    def test_no_time_stop_on_a_legacy_run_long(self):
        self._buy(self.run_id)
        self._x("UPDATE positions SET exit_policy = 'v1', "
                "first_opened_at = '2026-10-01T00:00:00Z', current_price = 95 "
                "WHERE agent_id = ?", (self.agent_id,))
        self._x("INSERT INTO risk_limits (agent_id, time_stop_days) VALUES (?, 1)",
                (self.agent_id,))
        self._tick()
        self.assertEqual(self._held(self.run_id), 1.0)

    def test_rule_long_on_the_unowned_book_is_automation(self):
        self._buy()                                    # rule long: run_id NULL
        row = self._q("SELECT exit_policy FROM positions")[0]
        self.assertEqual(row["exit_policy"], "long_policy")
        self._mark(97.0, stop=97.5, tp=105.0)          # stop overwritten later
        self._tick()
        self.assertEqual(self._held(), 1.0)            # held, not a "human" stop
        self._mark(84.0, stop=97.5, tp=105.0)
        self._tick()
        self.assertEqual(self._held(), 0.0)            # emergency

    def test_manual_users_own_stop_still_fires(self):
        self._manual_long()
        self._mark(97.0, stop=97.5)
        self._tick()
        self.assertEqual(self._held(), 0.0)

    def test_manual_users_own_trailing_still_trails(self):
        self._manual_long()
        self._x("UPDATE positions SET exit_policy = 'v1', stop_loss = 90 "
                "WHERE agent_id = ?", (self.agent_id,))
        self._x("INSERT INTO risk_limits (agent_id, use_trailing, trail_pct) "
                "VALUES (?, 1, 0.02)", (self.agent_id,))
        self._x("UPDATE positions SET current_price = 103 WHERE agent_id = ?",
                (self.agent_id,))
        self._tick()
        row = self._q("SELECT stop_loss FROM positions")[0]
        self.assertGreater(row["stop_loss"], 100.0)

    def test_rule_buy_does_not_convert_a_persons_manual_long(self):
        self._manual_long()
        self._x("UPDATE positions SET stop_loss = 97, take_profit = 120 "
                "WHERE agent_id = ?", (self.agent_id,))
        self._buy()                                   # rule buy, same unowned key
        row = self._q("SELECT stop_loss, take_profit, exit_policy FROM positions")[0]
        self.assertNotEqual(row["exit_policy"], "long_policy")
        self.assertEqual((row["stop_loss"], row["take_profit"]), (97.0, 120.0))

    def test_pin_never_lands_on_a_short_row(self):
        from automation import execute_paper_trade
        execute_paper_trade(self.agent_id, "BTCUSDT", "crypto", "short", 1.0, 100.0)
        self._buy()
        for r in self._q("SELECT quantity, stop_loss, exit_policy FROM positions"):
            if float(r["quantity"]) < 0:
                self.assertNotEqual(r["exit_policy"], "long_policy")
                self.assertNotEqual(r["stop_loss"], 85.0)

    def test_kill_switch_makes_a_marked_row_trail_again(self):
        self._buy()                                   # marked long_policy
        self._x("INSERT INTO risk_limits (agent_id, use_trailing, trail_pct) "
                "VALUES (?, 1, 0.02)", (self.agent_id,))
        self._x("UPDATE positions SET current_price = 103 WHERE agent_id = ?",
                (self.agent_id,))
        with patch.dict(os.environ, {"LONG_EXIT_POLICY": "0"}):
            self._tick()
        row = self._q("SELECT stop_loss FROM positions")[0]
        self.assertGreater(row["stop_loss"], 100.0)

    def test_follower_long_gets_the_bracket_and_marker(self):
        from services import _update_position_from_signal
        conn = database.get_db_connection()
        try:
            _update_position_from_signal(self.agent_id, "BTCUSDT", "crypto", "buy",
                                         1.0, 100.0, NOW, cursor=conn.cursor(),
                                         automated=True)
            conn.commit()
        finally:
            conn.close()
        row = self._q("SELECT stop_loss, take_profit, exit_policy FROM positions")[0]
        self.assertEqual((row["stop_loss"], row["take_profit"], row["exit_policy"]),
                         (85.0, 105.0, "long_policy"))


class RunRailTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {})
        self.env.start()
        os.environ.pop("LONG_EXIT_POLICY", None)

    def tearDown(self):
        self.env.stop()

    def _eval(self, reason, holding_long):
        import run_engine

        def fake(run, seen=None):
            if seen is not None:
                seen["holding_long"] = holding_long
            return reason
        with patch.object(run_engine, "_evaluate_stop_rails", side_effect=fake):
            return run_engine._evaluate_stop({"id": 1})

    def test_no_rail_flattens_a_held_long(self):
        for reason in ("stop_event:trailing_lock", "stop_event:max_loss",
                       "stop_event:at_time", "thesis_decayed",
                       "stop_event:profit_target", "stop_event:price_cross"):
            self.assertIsNone(self._eval(reason, True), reason)

    def test_liquidation_rails_still_fire_on_a_held_long(self):
        for reason in ("synthetic_liquidation", "stop_event:liq_cushion"):
            self.assertEqual(self._eval(reason, True), reason)

    def test_rails_still_fire_on_shorts_and_flat_runs(self):
        self.assertEqual(self._eval("stop_event:max_loss", False), "stop_event:max_loss")
        self.assertEqual(self._eval("idle_retired", False), "idle_retired")

    def test_kill_switch(self):
        with patch.dict(os.environ, {"LONG_EXIT_POLICY": "0"}):
            self.assertEqual(self._eval("stop_event:max_loss", True),
                             "stop_event:max_loss")

    def test_holding_long_flag_comes_from_the_real_rail_evaluator(self):
        import run_engine
        pnl = {"position": {"quantity": 2.0}, "realized": 0.0, "unrealized": 0.0,
               "total": 0.0, "mark_age_ok": True}
        seen: dict = {}
        with patch.object(run_engine, "compute_run_pnl", return_value=pnl):
            try:
                run_engine._evaluate_stop_rails({"id": 1, "stop_conditions_json": "{}"},
                                                seen)
            except Exception:  # noqa: BLE001 — only the flag matters here
                pass
        self.assertTrue(seen.get("holding_long"))


class StoppingHoldTests(unittest.TestCase):
    def _stop(self, why):
        import run_engine

        class _Cur:
            def execute(self, *a, **k):
                pass

            def fetchone(self):
                return {"id": 1}                      # the run holds a position

        class _Conn:
            def cursor(self):
                return _Cur()

            def close(self):
                pass
        run = {"id": 9, "agent_id": 1, "symbol": "BTCUSDT", "status": "stopping",
               "status_reason": "fleet_breaker", "stop_flatten": 1,
               "stopped_at": "2099-01-01T00:00:00Z", "market": "crypto"}
        # A simulator run: the fake cursor cannot answer the live-run lookup,
        # which fails SAFE (treated as live → never hand off). Say it plainly.
        with patch.object(run_engine, "_flush_pending_close_adapts"), \
             patch.object(run_engine, "get_db_connection", return_value=_Conn()), \
             patch("trading_runs.run_is_live", return_value=False), \
             patch("markets.is_market_open", return_value=True), \
             patch.object(run_engine, "_flatten_run", return_value=(False, why)), \
             patch.object(run_engine, "_simple_transition", return_value=True) as tr, \
             patch.object(run_engine, "_handoff_held_position") as ho, \
             patch.object(run_engine, "_alert_run") as al, \
             patch.object(run_engine, "emit_telemetry_event"):
            run_engine._control_stopping(run, {"stopping_finished": 0})
        self.alert = al
        return tr, ho

    def test_policy_refusal_holds_at_once_instead_of_retrying_an_hour(self):
        tr, ho = self._stop("long exit policy: held")
        self.assertTrue(any(c.args[2] == "positions_held" for c in tr.call_args_list))
        ho.assert_called_once()
        self.alert.assert_not_called()      # not a "stuck past N min" flatten

    def test_other_failures_still_wait_for_the_timeout(self):
        tr, ho = self._stop("no mark price to flatten at")
        ho.assert_not_called()


class BookRetireTests(unittest.TestCase):
    def _eval(self, market_type, has_position, shorts_env):
        import run_engine

        def fake(run, seen=None):
            if seen is not None:
                seen["has_position"] = has_position
                seen["holding_long"] = False
            return None
        env = {"FUTURES_TRADING_BLOCKED": "1"}
        if shorts_env is not None:
            env["SHORTS_TRADING_BLOCKED"] = shorts_env
        with patch.dict(os.environ, env):
            if shorts_env is None:
                os.environ.pop("SHORTS_TRADING_BLOCKED", None)
            with patch.object(run_engine, "_evaluate_stop_rails", side_effect=fake):
                return run_engine._evaluate_stop(
                    {"id": 1, "market": "crypto", "market_type": market_type})

    # Long-only is an explicit opt-in since 2026-11-23 (owner: "Allow
    # shorts again"), so these pass SHORTS_TRADING_BLOCKED=1.
    def test_flat_futures_book_run_retires_under_long_only(self):
        self.assertEqual(self._eval("futures", False, "1"), "no_prospect_switched")

    def test_futures_book_holding_a_short_keeps_running_to_cover(self):
        self.assertIsNone(self._eval("futures", True, "1"))

    def test_spot_run_and_two_way_are_untouched(self):
        self.assertIsNone(self._eval("spot", False, "1"))
        self.assertIsNone(self._eval("futures", False, "0"))

    def test_flat_futures_book_run_keeps_running_by_default(self):
        # Unset switch = two-way: a flat perp book can still open a short.
        self.assertIsNone(self._eval("futures", False, None))


class FlattenTests(unittest.TestCase):
    def _flatten(self, reason):
        import run_engine
        run = {"id": 7, "agent_id": 1, "symbol": "BTCUSDT", "market": "crypto",
               "status_reason": reason}
        conn_pos = {"quantity": 1.0, "current_price": 97.0}

        class _Cur:
            def execute(self, *a, **k):
                pass

            def fetchone(self):
                return conn_pos

        class _Conn:
            def cursor(self):
                return _Cur()

            def close(self):
                pass
        with patch.object(run_engine, "get_db_connection", return_value=_Conn()), \
             patch.object(run_engine, "_manual_halt_blocks", return_value=False), \
             patch.object(run_engine, "compute_run_pnl", return_value={"realized": 0}), \
             patch("automation.execute_paper_trade",
                   return_value=(None, "held")) as ept:
            run_engine._flatten_run(run)
        return ept.call_args.kwargs["human_initiated"]

    def test_user_and_fleet_stop_all_are_human(self):
        self.assertTrue(self._flatten("user_stop"))
        self.assertTrue(self._flatten("fleet_stop_all"))

    def test_liquidation_flatten_fills(self):
        self.assertTrue(self._flatten("synthetic_liquidation"))
        self.assertTrue(self._flatten("stop_event:liq_cushion"))

    def test_machine_stops_are_automated(self):
        for r in ("fleet_breaker", "stop_event:max_loss", "adapt_retired",
                  "fleet_profit_target", None):
            self.assertFalse(self._flatten(r), r)


def test_policy_module_is_on_by_default():
    with patch.dict(os.environ, {}):
        os.environ.pop("LONG_EXIT_POLICY", None)
        assert long_exit_policy.enabled()


if __name__ == "__main__":
    unittest.main()
