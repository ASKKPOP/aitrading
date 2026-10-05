"""Plan 32 stage B — dedicated trend accounts.

A user's account handed to the trend rule: enrolled clean, traded by the
module alone (long-only, exits on the daily close), fenced against every
other writer, and — for a `shadow` account — every fill mirrored to the
connected broker as a dry run. `live` cannot be enrolled.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import database
import fleet_planner
import orphan_reclaim as orc
import trading_runs
import trend_accounts as ta
import trend_module as tm
from automation import execute_paper_trade
from test_trend_module import _bars_down, _bars_up, _next_bar

_PRO = patch("entitlements.limits_for_agent",
             return_value=("professional", {"max_fleet_size": 25}))

_RUN = {"symbol": "SOLUSDT", "market": "crypto", "market_type": "spot",
        "max_bet_usd": 100.0, "run_budget_usd": None, "interval_minutes": 60,
        "min_confidence": 0.7, "provider": "openai", "lang": "en",
        "leverage": 1.0}


class _Base(unittest.TestCase):
    """tmp DB with two users' agents (U, V) and the module's own agent (D)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('u@t.dev', 'x')")
        self.user_u = cur.lastrowid
        cur.execute("INSERT INTO users (email, password_hash) VALUES ('v@t.dev', 'x')")
        user_v = cur.lastrowid
        ids = []
        for name, token, user in (("user-u", "tu", self.user_u),
                                  ("user-v", "tv", user_v),
                                  ("trend-agent", "td", None)):
            cur.execute(
                "INSERT INTO agents (name, token_hash, cash, user_id, created_at)"
                " VALUES (?, ?, 100000, ?, '2026-01-01T00:00:00Z')",
                (name, token, user))
            ids.append(cur.lastrowid)
        conn.commit()
        conn.close()
        self.U, self.V, self.D = ids
        env = patch.dict(os.environ, {
            "TREND_MODULE_ENABLED": "1", "TREND_AGENT_ID": str(self.D),
            "TREND_UNIVERSE": "BTCUSDT,ETHUSDT"})
        env.start()
        self.addCleanup(env.stop)
        for k in ("TREND_RISK_USD", "TREND_MAX_POSITIONS",
                  "ENTITLEMENTS_ENFORCED", "AGENT_ENTRY_FREEZE"):
            os.environ.pop(k, None)
        mark = patch.object(tm, "_mark",
                            side_effect=lambda symbol, fallback: fallback)
        mark.start()
        self.addCleanup(mark.stop)

    def _q(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _x(self, sql, params=()):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _position(self, agent_id, symbol="SOLUSDT", run_id=None, pid=None):
        return self._x(
            "INSERT INTO positions (id,agent_id,symbol,market,side,quantity,"
            "entry_price,current_price,opened_at,run_id) VALUES "
            "(?,?,?,'crypto','long',1.0,100.0,100.0,'2026-08-11T18:46:50Z',?)",
            (pid, agent_id, symbol, run_id))

    def _open(self, agent_id):
        return self._q("SELECT * FROM positions WHERE agent_id = ? "
                       "AND quantity != 0", (agent_id,))

    def _cycle(self, bars_by_symbol, adx=30.0):
        def bars(symbol):
            return bars_by_symbol.get(symbol, [])
        with patch.object(tm, "_get_bars", side_effect=bars), \
             patch.object(tm, "wilder_adx", return_value=adx), \
             patch.object(tm, "_fear_greed_value", return_value=50), \
             patch("llm_client.generate_text", return_value=None):
            return tm.run_trend_cycle()

    def _state(self, agent_id):
        from platform_settings import get_setting
        raw = get_setting(f"{tm.STATE_KEY}:{agent_id}")
        return json.loads(raw) if raw else {}

    def _account(self, summary, agent_id):
        return next(a for a in summary["accounts"] if a["agent_id"] == agent_id)


class Enrolment(_Base):
    def test_a_valid_entry_is_normalized(self):
        self.assertEqual(
            ta.normalize([{"agent_id": "6", "account_type": " Shadow ",
                           "risk_usd": "40"}]),
            [{"agent_id": 6, "account_type": "shadow", "risk_usd": 40.0}])
        entry = ta.normalize([{"agent_id": 6}])[0]
        self.assertEqual((entry["account_type"], entry["risk_usd"]),
                         ("simulator", ta.DEFAULT_RISK_USD))

    def test_live_cannot_be_enrolled(self):
        """Real money is the owner's four steps on the Accounts page, not a
        value typed into this list — and the module has no live branch, so
        a stored `live` would be a simulated fill dressed as a real one."""
        self.assertEqual(ta.ACCOUNT_TYPES, ("simulator", "shadow"))
        for account_type in ("live", "LIVE", "paper", "real"):
            with self.assertRaises(ta.AccountError, msg=account_type):
                ta.normalize([{"agent_id": 6, "account_type": account_type}])
            with self.assertRaises(ta.AccountError, msg=account_type):
                ta.enrol(self.U, account_type)
        self.assertEqual(ta.stored(), ([], None))

    def test_bad_entries_are_refused_not_repaired(self):
        bad = [
            "not a list", ["not an object"], [{"agent_id": "abc"}], [{}],
            [{"agent_id": 6}, {"agent_id": 6}],
            [{"agent_id": 6, "risk_usd": 0}],
            [{"agent_id": 6, "risk_usd": -5}],
            [{"agent_id": 6, "risk_usd": ta.MAX_RISK_USD + 1}],
            [{"agent_id": 6, "risk_usd": "lots"}],
            [{"agent_id": True}],                 # not agent 1
            [{"agent_id": 6.9}],                  # not agent 6
            [{"agent_id": 10 ** 30}], [{"agent_id": 0}],
            [{"agent_id": 6, "risk_usd": True}],
            [{"agent_id": 6, "risk_usd": float("nan")}],
            [{"agent_id": 6, "risk_usd": float("inf")}],
        ]
        for entries in bad:
            with self.assertRaises(ta.AccountError, msg=str(entries)):
                ta.normalize(entries)
        self.assertEqual(
            ta.normalize([{"agent_id": 6, "risk_usd": ta.MAX_RISK_USD}])[0]
            ["risk_usd"], ta.MAX_RISK_USD)

    def test_only_a_users_agent_can_be_enrolled(self):
        with self.assertRaises(ta.AccountError):
            ta.enrol(self.D)                 # the module's own account
        with self.assertRaises(ta.AccountError):
            ta.enrol(987654)                 # nobody
        self.assertEqual(ta.accounts(), [])
        ta.enrol(self.U)
        self.assertEqual([a["agent_id"] for a in ta.accounts()], [self.U])

    def test_an_account_must_be_flat_to_be_enrolled(self):
        """The rule owns every lot on its account. A position that was there
        first is not the rule's, and the shared-account book showed what
        managing one does: it sold a manual long under its own order id."""
        pid = self._position(self.U, "DOGEUSDT")
        with self.assertRaises(ta.AccountError) as ctx:
            ta.enrol(self.U)
        self.assertIn("DOGEUSDT", str(ctx.exception))
        self.assertFalse(ta.is_trend_account(self.U))
        self._x("UPDATE positions SET quantity = 0 WHERE id = ?", (pid,))
        ta.enrol(self.U)

    def test_an_account_with_an_active_run_or_fleet_cannot_be_enrolled(self):
        run_id = trading_runs.create_run(self.U, _RUN, {"type": "manual"}, {}, True)
        ta.enrol(self.V)                     # a DRAFT elsewhere is no obstacle
        for status in ("armed", "running", "paused", "stopping"):
            self._x("UPDATE trading_runs SET status = ? WHERE id = ?",
                    (status, run_id))
            with self.assertRaises(ta.AccountError, msg=status) as ctx:
                ta.enrol(self.U)
            self.assertIn("active run", str(ctx.exception))
        self._x("UPDATE trading_runs SET status = 'stopped' WHERE id = ?", (run_id,))
        with _PRO:
            fleet_id = fleet_planner.create_fleet(self.U, 2, 5000.0)
        for status in ("researching", "building", "active", "paused", "stopping"):
            self._x("UPDATE fleets SET status = ? WHERE id = ?", (status, fleet_id))
            with self.assertRaises(ta.AccountError, msg=status) as ctx:
                ta.enrol(self.U)
            self.assertIn("active fleet", str(ctx.exception))
        self._x("UPDATE fleets SET status = 'stopped' WHERE id = ?", (fleet_id,))
        ta.enrol(self.U)

    def test_an_enrolled_account_can_change_type_and_risk_while_holding(self):
        ta.enrol(self.U, "simulator", 25)
        self._position(self.U, "BTCUSDT")
        entry = ta.enrol(self.U, "shadow", 40)
        self.assertEqual(entry, {"agent_id": self.U, "account_type": "shadow",
                                 "risk_usd": 40.0})
        self.assertEqual(ta.stored()[0], [entry])

    def test_one_operation_touches_one_account(self):
        """Enrolment used to be "save the whole list": a console showing a
        stale list dropped whoever it had not loaded."""
        ta.enrol(self.U)
        ta.enrol(self.V, "shadow", 50)
        self.assertEqual([a["agent_id"] for a in ta.stored()[0]],
                         sorted([self.U, self.V]))
        ta.remove(self.U)
        self.assertEqual(ta.stored()[0], [{"agent_id": self.V,
                                           "account_type": "shadow",
                                           "risk_usd": 50.0}])
        with self.assertRaises(ta.AccountError):
            ta.remove(self.U)                # not enrolled any more

    def test_an_account_holding_a_position_cannot_be_removed(self):
        """Removed with a position open, nothing is left to exit it and the
        desk is let onto an account that is not flat."""
        ta.enrol(self.U)
        pid = self._position(self.U, "BTCUSDT")
        with self.assertRaises(ta.AccountError) as ctx:
            ta.remove(self.U)
        self.assertIn("BTCUSDT", str(ctx.exception))
        self.assertTrue(ta.is_trend_account(self.U))
        self._x("DELETE FROM positions WHERE id = ?", (pid,))
        ta.remove(self.U)
        self.assertFalse(ta.is_trend_account(self.U))

    def test_the_module_switch_stops_trading_but_not_the_fence(self):
        ta.enrol(self.U)
        with patch.dict(os.environ, {"TREND_MODULE_ENABLED": "0"}):
            self.assertEqual(ta.accounts(), [])
            self.assertTrue(ta.is_trend_account(self.U))
            self.assertEqual(ta.entry_fence(None, self.U, "buy"), ta.FENCED)

    def test_a_stored_value_that_does_not_validate_runs_and_fences_nobody(self):
        from platform_settings import set_setting
        for raw in ("{not json", json.dumps([{"agent_id": self.U,
                                              "account_type": "live"}])):
            set_setting(ta.ACCOUNTS_KEY, raw, "test")
            self.assertEqual(ta.accounts(), [], raw)
            self.assertFalse(ta.is_trend_account(self.U), raw)
            entries, problem = ta.stored()
            self.assertEqual(entries, [])
            self.assertIn("invalid", problem)
            # ...and it is not silently overwritten by the next enrolment
            with self.assertRaises(ta.AccountError):
                ta.enrol(self.V)
            with self.assertRaises(ta.AccountError):
                ta.remove(self.U)

    def test_an_unreadable_enrolment_trades_nothing(self):
        ta.enrol(self.U)
        with patch.object(ta, "_query", side_effect=RuntimeError("db down")):
            self.assertEqual(ta.accounts(), [])
            entries, problem = ta.stored()
            self.assertEqual(entries, [])
            self.assertIn("could not be read", problem)
            with self.assertRaises(RuntimeError):
                ta.is_trend_account(self.U)


class EntryFence(_Base):
    def setUp(self):
        super().setUp()
        ta.enrol(self.U)

    def test_nothing_but_the_rule_opens_on_a_trend_account(self):
        for side in ("buy", "short"):
            sid, err = execute_paper_trade(self.U, "SOLUSDT", "crypto", side,
                                           1.0, 100.0)
            self.assertIsNone(sid, side)
            self.assertEqual(err, ta.FENCED)
            # a run's order id, or another account's trend id, is not the rule
            for order_id in ("run:7:cyc:1", f"trend:{self.V}:SOLUSDT:{side}:x",
                             f"trend:{self.U}", f"xtrend:{self.U}:SOLUSDT"):
                sid, err = execute_paper_trade(
                    self.U, "SOLUSDT", "crypto", side, 1.0, 100.0,
                    client_order_id=order_id)
                self.assertIsNone(sid, order_id)
                self.assertEqual(err, ta.FENCED, order_id)
        self.assertEqual(self._open(self.U), [])
        self.assertEqual(self._q("SELECT id FROM signals WHERE agent_id = ?",
                                 (self.U,)), [])

    def test_the_rules_own_order_opens_and_anyone_may_close(self):
        sid, err = execute_paper_trade(
            self.U, "BTCUSDT", "crypto", "buy", 2.0, 100.0,
            client_order_id=f"trend:{self.U}:BTCUSDT:buy:2026-10-05")
        self.assertIsNotNone(sid, err)
        # reductions are never fenced — nobody is locked into a position
        sid, err = execute_paper_trade(self.U, "BTCUSDT", "crypto", "sell",
                                       1.0, 100.0)
        self.assertIsNotNone(sid, err)
        self.assertEqual(self._open(self.U)[0]["quantity"], 1.0)

    def test_other_accounts_are_untouched(self):
        for agent in (self.V, self.D):
            sid, err = execute_paper_trade(agent, "SOLUSDT", "crypto", "buy",
                                           1.0, 100.0)
            self.assertIsNotNone(sid, err)

    def test_an_unreadable_enrolment_fences_nobody(self):
        """The fence sits on every simulated entry on the platform; a
        settings read that fails must not stop all of them."""
        with patch.object(ta, "_read", side_effect=RuntimeError("db down")):
            for agent in (self.U, self.V):
                sid, err = execute_paper_trade(agent, "SOLUSDT", "crypto",
                                               "buy", 1.0, 100.0)
                self.assertIsNotNone(sid, err)

    def test_a_run_cannot_start_on_a_trend_account(self):
        run_id = trading_runs.create_run(self.U, _RUN, {"type": "manual"}, {}, True)
        with self.assertRaises(trading_runs.EntitlementDenied) as ctx:
            trading_runs.start_run(run_id, self.U)
        self.assertEqual(str(ctx.exception), ta.NO_RUNS)
        self.assertEqual(self._q("SELECT status FROM trading_runs WHERE id = ?",
                                 (run_id,))[0]["status"], "draft")
        other = trading_runs.create_run(self.V, _RUN, {"type": "manual"}, {}, True)
        trading_runs.start_run(other, self.V)

    def test_resolving_conflicts_cannot_sell_the_rules_position(self):
        """"Resolve conflicts" closes the unowned position on the symbol
        before a start — on a trend account that is the rule's position."""
        sid, err = execute_paper_trade(
            self.U, "SOLUSDT", "crypto", "buy", 1.0, 100.0,
            client_order_id=f"trend:{self.U}:SOLUSDT:buy:2026-10-05")
        self.assertIsNotNone(sid, err)
        run_id = trading_runs.create_run(self.U, _RUN, {"type": "manual"}, {}, True)
        with self.assertRaises(trading_runs.EntitlementDenied):
            trading_runs.resolve_start_conflicts(run_id, self.U)
        self.assertEqual(len(self._open(self.U)), 1, "the rule's position was sold")

    def test_a_fleet_cannot_be_created_or_started_on_a_trend_account(self):
        with _PRO, self.assertRaises(trading_runs.EntitlementDenied) as ctx:
            fleet_planner.create_fleet(self.U, 2, 5000.0)
        self.assertEqual(str(ctx.exception), ta.NO_RUNS)
        self.assertEqual(self._q("SELECT id FROM fleets"), [])
        # a draft made BEFORE the account was handed over cannot start either
        with _PRO:
            draft = fleet_planner.create_fleet(self.V, 2, 5000.0)
        ta.enrol(self.V)
        with _PRO, self.assertRaises(trading_runs.EntitlementDenied) as ctx:
            fleet_planner.start_fleet(draft, self.V)
        self.assertEqual(str(ctx.exception), ta.NO_RUNS)
        self.assertEqual(self._q("SELECT status FROM fleets WHERE id = ?",
                                 (draft,))[0]["status"], "draft")

    def test_the_orphan_sweep_leaves_a_trend_account_alone(self):
        """Run-less is how the rule's positions look. To the sweep that was
        "unowned and unprotected": a 5% stop and a desk read (prod 09-18)."""
        self._position(self.U, "BTCUSDT", pid=1)
        self._position(self.V, "BTCUSDT", pid=2)
        self._position(self.D, "BTCUSDT", pid=3)
        with patch.dict(os.environ, {"ORPHAN_RECLAIM_ENABLED": "true"}):
            self.assertEqual([r["id"] for r in orc.find_orphans()], [2])
            orc.sweep(blocking={})
            stops = {r["id"]: r["stop_loss"] for r in
                     self._q("SELECT id, stop_loss FROM positions")}
            self.assertIsNone(stops[1], "a foreign stop on the rule's position")
            self.assertIsNotNone(stops[2])
            self.assertIsNone(stops[3])
            # enrolment unreadable: the sweep sits the pass out
            with patch.object(ta, "_read", side_effect=RuntimeError("db down")):
                self.assertEqual(orc.find_orphans(), [])
            # a stored value that enrols nobody still shields the module agent
            with patch.object(ta, "_read", side_effect=ValueError("bad")):
                self.assertEqual(sorted(r["id"] for r in orc.find_orphans()),
                                 [1, 2])
        # module off: nobody manages those rows, they are orphans again
        with patch.dict(os.environ, {"ORPHAN_RECLAIM_ENABLED": "true",
                                     "TREND_MODULE_ENABLED": "0"}):
            self.assertEqual(sorted(r["id"] for r in orc.find_orphans()),
                             [1, 2, 3])


class ManualAndCopyOrders(unittest.TestCase):
    """POST /api/signals/realtime: the account's own manual order and a
    leader's fill copied into it."""

    _TS = "2024-01-02T15:00:00Z"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        from routes import create_app
        self.client = TestClient(create_app())
        self.agents = {}
        for name in ("leader", "trend", "plain"):
            r = self.client.post("/api/claw/agents/selfRegister", json={
                "name": name, "password": "pw123", "initial_balance": 100000.0})
            assert r.status_code == 200, r.text
            self.agents[name] = (r.json()["agent_id"],
                                 {"Authorization": f"Bearer {r.json()['token']}"})
        conn = database.get_db_connection()
        cur = conn.cursor()
        for name in ("leader", "trend", "plain"):
            cur.execute("INSERT INTO users (email, password_hash) VALUES (?, 'x')",
                        (f"{name}@t.dev",))
            cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                        (cur.lastrowid, self.agents[name][0]))
        for follower in ("trend", "plain"):
            cur.execute("INSERT INTO subscriptions (leader_id, follower_id, status)"
                        " VALUES (?, ?, 'active')",
                        (self.agents["leader"][0], self.agents[follower][0]))
        conn.commit()
        conn.close()
        ta.enrol(self.agents["trend"][0])

    def _trade(self, who, action, qty=1.0):
        with patch.dict(os.environ, {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}):
            return self.client.post("/api/signals/realtime", headers=self.agents[who][1], json={
                "market": "us-stock", "action": action, "symbol": "AAPL",
                "price": 150.0, "quantity": qty, "executed_at": self._TS})

    def _qty(self, who):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(SUM(quantity), 0) AS q FROM positions "
                        "WHERE agent_id = ?", (self.agents[who][0],))
            return float(cur.fetchone()["q"])
        finally:
            conn.close()

    def test_a_manual_order_cannot_open_on_a_trend_account(self):
        for action in ("buy", "short"):
            r = self._trade("trend", action)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(r.json()["detail"], ta.FENCED)
        self.assertEqual(self._qty("trend"), 0.0)
        self.assertEqual(self._trade("plain", "buy").status_code, 200)

    def test_a_copied_fill_does_not_open_on_a_trend_account(self):
        r = self._trade("leader", "buy", 2.0)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._qty("leader"), 2.0)
        self.assertEqual(self._qty("plain"), 2.0, "fixture: copies must work")
        self.assertEqual(self._qty("trend"), 0.0)


class Trading(_Base):
    def test_an_account_takes_the_long_with_its_own_risk_and_state(self):
        ta.enrol(self.U, "simulator", 50)
        bars = _bars_up()
        summary = self._cycle({"BTCUSDT": bars})
        account = self._account(summary, self.U)
        self.assertEqual((account["entries"], account.get("error")), (1, None))
        self.assertEqual(account["account_type"], "simulator")
        self.assertEqual(summary["entries"], 1)      # the module's own account
        pos = self._state(self.U)["positions"]["BTCUSDT"]
        own = json.loads(self._q(
            "SELECT setting_value FROM platform_settings WHERE setting_key = ?",
            (tm.STATE_KEY,))[0]["setting_value"])["positions"]["BTCUSDT"]
        self.assertEqual(pos["side"], "long")
        # $50 of risk against the module's default $25: twice the size
        self.assertAlmostEqual(pos["qty"], 2 * own["qty"])
        fills = self._q("SELECT side, client_order_id, run_id FROM signals "
                        "WHERE agent_id = ?", (self.U,))
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["side"], "buy")
        self.assertTrue(fills[0]["client_order_id"]
                        .startswith(f"trend:{self.U}:BTCUSDT:buy:"))
        self.assertIsNone(fills[0]["run_id"])
        self.assertNotIn(self.V, [a["agent_id"] for a in summary["accounts"]])
        self.assertEqual(self._open(self.V), [])

    def test_no_stop_goes_on_an_accounts_row(self):
        """The SL/TP watcher closes on the ledger alone. On the module's own
        simulated account that is its intraday stop; on an account a broker
        mirrors it would be a close the broker never hears of."""
        ta.enrol(self.U)
        self._cycle({"BTCUSDT": _bars_up()})
        row_u, = self._open(self.U)
        row_d, = self._open(self.D)
        self.assertIsNone(row_u["stop_loss"])
        self.assertIsNotNone(row_d["stop_loss"])
        self._cycle({"BTCUSDT": _bars_up()})          # the per-cycle re-sync too
        self.assertIsNone(self._open(self.U)[0]["stop_loss"])

    def test_an_account_is_long_only(self):
        ta.enrol(self.U)
        summary = self._cycle({"BTCUSDT": _bars_down()})
        self.assertEqual(summary["entries"], 1, "fixture: the module shorts this")
        self.assertLess(self._open(self.D)[0]["quantity"], 0)
        account = self._account(summary, self.U)
        self.assertEqual((account["entries"], account["signals"]), (0, 0))
        self.assertEqual(self._open(self.U), [])

    def test_an_account_exits_on_the_daily_close(self):
        ta.enrol(self.U)
        bars = _bars_up()
        self._cycle({"BTCUSDT": bars})
        crashed = _next_bar(bars, bars[-1]["close"] - 20.0)
        summary = self._cycle({"BTCUSDT": crashed})
        account = self._account(summary, self.U)
        self.assertEqual(account["exits"], 1)
        self.assertEqual(self._open(self.U), [])
        self.assertEqual(self._state(self.U)["positions"], {})
        stats = tm.trend_stats(self.U)
        self.assertEqual((stats["agent_id"], stats["entries"], stats["n_trades"]),
                         (self.U, 1, 1))
        self.assertLess(stats["total_pnl"], 0)
        self.assertEqual(tm.trend_stats()["agent_id"], self.D)

    def test_the_master_hold_stops_entries_and_never_exits(self):
        """The account's kill switch. The module does not go through
        run_cycle, where the hold lives for the desk."""
        ta.enrol(self.U)
        ta.enrol(self.V)
        bars = _bars_up()
        self._x("UPDATE users SET ai_automation_state = 'held' WHERE id = ?",
                (self.user_u,))
        summary = self._cycle({"BTCUSDT": bars})
        held = self._account(summary, self.U)
        self.assertEqual(held["entries"], 0)
        self.assertEqual([e["reason"] for e in held["actions"]
                          if e["event"] == "entries_blocked"],
                         ["account is on master hold"])
        self.assertEqual(self._account(summary, self.V)["entries"], 1)
        # held AFTER the entry: the exit still goes through
        self._x("UPDATE users SET ai_automation_state = 'held' "
                "WHERE id = (SELECT user_id FROM agents WHERE id = ?)", (self.V,))
        summary = self._cycle({"BTCUSDT": _next_bar(bars, bars[-1]["close"] - 20.0)})
        self.assertEqual(self._account(summary, self.V)["exits"], 1)
        self.assertEqual(self._open(self.V), [])

    def test_the_other_account_gates_block_entries_too(self):
        ta.enrol(self.U)
        bars = {"BTCUSDT": _bars_up()}
        import automation
        import risk_engine
        import run_engine
        cases = (
            (patch.object(run_engine, "_entry_frozen", return_value=True), "frozen"),
            (patch.object(risk_engine, "_is_halted", return_value="daily loss"),
             "halted: daily loss"),
            (patch.object(automation, "_entitlement_blocks",
                          return_value="plan does not allow it"), "plan"),
            (patch.object(run_engine, "_master_held",
                          side_effect=RuntimeError("db down")), "unavailable"),
        )
        for gate, text in cases:
            with gate:
                account = self._account(self._cycle(bars), self.U)
            self.assertEqual(account["entries"], 0, text)
            reasons = [e["reason"] for e in account["actions"]
                       if e["event"] == "entries_blocked"]
            self.assertEqual(len(reasons), 1, text)
            self.assertIn(text, reasons[0])
        self.assertEqual(self._account(self._cycle(bars), self.U)["entries"], 1)

    def test_an_enrolment_never_trades_an_agent_without_a_user(self):
        from platform_settings import set_setting
        set_setting(ta.ACCOUNTS_KEY, json.dumps(
            [{"agent_id": self.D, "account_type": "simulator", "risk_usd": 25}]),
            "test")
        summary = self._cycle({"BTCUSDT": _bars_up()})
        self.assertEqual(self._account(summary, self.D)["error"],
                         "agent belongs to no user")
        self.assertEqual(len(self._q("SELECT id FROM signals")), 1)  # module's

    def test_one_account_failing_does_not_stop_the_others(self):
        ta.enrol(self.U)
        ta.enrol(self.V)
        real = tm._run_book

        def run_book(book, summary):
            if book["agent_id"] in (self.U, self.D):
                raise RuntimeError("boom")
            return real(book, summary)

        with patch.object(tm, "_run_book", side_effect=run_book):
            summary = self._cycle({"BTCUSDT": _bars_up()})
        self.assertEqual(summary["error"], "boom")
        self.assertEqual(self._account(summary, self.U)["error"], "boom")
        self.assertEqual(self._account(summary, self.V)["entries"], 1)

    def test_nothing_runs_with_the_module_off(self):
        ta.enrol(self.U)
        with patch.dict(os.environ, {"TREND_MODULE_ENABLED": "0"}):
            summary = self._cycle({"BTCUSDT": _bars_up()})
        self.assertNotIn("accounts", summary)
        self.assertEqual(self._q("SELECT id FROM signals"), [])


class ShadowLeg(_Base):
    """A `shadow` account: the ledger fill, then a dry run at the broker."""

    def _order(self, status="validated", error=None):
        return SimpleNamespace(broker="coinbase", error_message=error,
                               status=SimpleNamespace(value=status))

    def _shadow_events(self, account):
        return [e for e in account["actions"] if e["event"] == "shadow"]

    def test_every_fill_of_a_shadow_account_is_mirrored_once(self):
        ta.enrol(self.U, "shadow")
        ta.enrol(self.V, "simulator")
        bars = _bars_up()
        with patch("execution.gateway.submit_shadow",
                   return_value=self._order()) as shadow, \
             patch("execution.gateway.submit_live") as live:
            entry = self._cycle({"BTCUSDT": bars})
            fill, = self._q("SELECT id, quantity, entry_price FROM signals "
                            "WHERE agent_id = ?", (self.U,))
            # only U: not the simulator account, not the module's own
            self.assertEqual(shadow.call_count, 1)
            args, kwargs = shadow.call_args
            self.assertEqual(args[:4], (self.U, "BTCUSDT", "crypto", "buy"))
            self.assertAlmostEqual(args[4], fill["quantity"])
            self.assertAlmostEqual(args[5], fill["entry_price"])
            self.assertAlmostEqual(kwargs["ledger_quantity"], fill["quantity"])
            self.assertEqual(kwargs["signal_id"], fill["id"])
            event, = self._shadow_events(self._account(entry, self.U))
            self.assertEqual((event["status"], event["broker"], event["side"]),
                             ("validated", "coinbase", "buy"))
            self.assertEqual(self._shadow_events(self._account(entry, self.V)), [])
            # a second tick in the same bar places nothing and mirrors nothing
            self._cycle({"BTCUSDT": bars})
            self.assertEqual(shadow.call_count, 1)
            # the exit is mirrored too
            out = self._cycle({"BTCUSDT": _next_bar(bars, bars[-1]["close"] - 20.0)})
            self.assertEqual(self._account(out, self.U)["exits"], 1)
            self.assertEqual(shadow.call_count, 2)
            self.assertEqual(shadow.call_args[0][:4],
                             (self.U, "BTCUSDT", "crypto", "sell"))
            live.assert_not_called()

    def test_a_refused_ledger_order_never_reaches_the_broker(self):
        """The order id is checked at the ledger, before any venue call."""
        ta.enrol(self.U, "shadow")
        with patch("execution.gateway.submit_shadow",
                   return_value=self._order()) as shadow, \
             patch("automation.execute_paper_trade",
                   return_value=(None, "insufficient cash")):
            account = self._account(self._cycle({"BTCUSDT": _bars_up()}), self.U)
        shadow.assert_not_called()
        self.assertEqual(account["entries"], 0)
        self.assertEqual([e["reason"] for e in account["actions"]
                          if e["event"] == "entry_failed"], ["insufficient cash"])

    def test_a_broker_problem_does_not_undo_the_ledger_fill(self):
        ta.enrol(self.U, "shadow")
        for broker, status in (
                ({"side_effect": RuntimeError("venue down")}, "error"),
                ({"return_value": None}, "no_broker_order"),
                ({"return_value": self._order("rejected", "min size")}, "rejected")):
            self._x("DELETE FROM signals")
            self._x("DELETE FROM positions")
            self._x("DELETE FROM platform_settings WHERE setting_key LIKE ?",
                    (tm.STATE_KEY + "%",))
            with patch("execution.gateway.submit_shadow", **broker):
                account = self._account(
                    self._cycle({"BTCUSDT": _bars_up()}), self.U)
            self.assertEqual(account["entries"], 1, status)
            self.assertEqual(len(self._open(self.U)), 1, status)
            event, = self._shadow_events(account)
            self.assertEqual(event["status"], status)
        self.assertEqual(event["error"], "min size")

    def test_without_a_broker_link_shadow_is_simulation(self):
        """The real gateway, no patch: an account with no broker link has
        nowhere to send a dry run, and that is not an error."""
        ta.enrol(self.U, "shadow")
        account = self._account(self._cycle({"BTCUSDT": _bars_up()}), self.U)
        self.assertEqual(account["entries"], 1)
        event, = self._shadow_events(account)
        self.assertEqual(event["status"], "no_broker_order")
        self.assertEqual(self._q("SELECT id FROM broker_orders"), [])


class AdminApi(_Base):
    URL = "/api/admin/settings/trend-accounts"

    def setUp(self):
        super().setUp()
        from routes import create_app
        self.client = TestClient(create_app())
        from admin_auth import create_admin
        create_admin("root@test.com", "rootpass123", "superadmin")
        r = self.client.post("/api/admin/login", json={
            "email": "root@test.com", "password": "rootpass123"})
        self.admin = {"Authorization": f"Bearer {r.json()['token']}"}

    def test_requires_admin(self):
        self.assertIn(self.client.get(self.URL).status_code, (401, 403))
        self.assertIn(self.client.post(
            self.URL, json={"agent_id": self.U}).status_code, (401, 403))
        self.assertIn(self.client.delete(
            f"{self.URL}/{self.U}").status_code, (401, 403))
        self.assertEqual(ta.stored(), ([], None))

    def test_enrol_list_and_remove(self):
        r = self.client.post(self.URL, headers=self.admin, json={
            "agent_id": self.U, "account_type": "shadow", "risk_usd": 30})
        self.assertEqual(r.status_code, 200, r.text)
        self.client.post(self.URL, headers=self.admin, json={"agent_id": self.V})
        self._position(self.U, "BTCUSDT")
        body = self.client.get(self.URL, headers=self.admin).json()
        rows = {a["agent_id"]: a for a in body["accounts"]}
        self.assertEqual(sorted(rows), sorted([self.U, self.V]))
        self.assertEqual((rows[self.U]["account_type"], rows[self.U]["risk_usd"]),
                         ("shadow", 30.0))
        self.assertEqual(rows[self.U]["open_positions"], ["BTCUSDT"])
        self.assertIsNone(rows[self.U]["broker"])    # no broker link
        self.assertEqual(rows[self.V]["account_type"], "simulator")
        self.assertEqual(body["account_types"], ["simulator", "shadow"])
        self.assertEqual(body["symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertTrue(body["module_enabled"])
        # holding: cannot be removed; the flat one can
        r = self.client.delete(f"{self.URL}/{self.U}", headers=self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("BTCUSDT", r.json()["detail"])
        r = self.client.delete(f"{self.URL}/{self.V}", headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([a["agent_id"] for a in r.json()["accounts"]], [self.U])

    def test_live_and_bad_accounts_are_400_and_nothing_is_stored(self):
        for body in ({"agent_id": self.U, "account_type": "live"},
                     {"agent_id": self.D},
                     {"agent_id": self.U, "risk_usd": 5000}):
            r = self.client.post(self.URL, headers=self.admin, json=body)
            self.assertEqual(r.status_code, 400, body)
        self.assertEqual(ta.stored(), ([], None))

    def test_the_console_sees_what_is_stored_not_what_is_running(self):
        ta.enrol(self.U)
        with patch.dict(os.environ, {"TREND_MODULE_ENABLED": "0"}):
            body = self.client.get(self.URL, headers=self.admin).json()
        self.assertEqual([a["agent_id"] for a in body["accounts"]], [self.U])
        self.assertFalse(body["module_enabled"])
        self.assertIsNone(body["problem"])


if __name__ == "__main__":
    unittest.main()
