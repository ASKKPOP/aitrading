"""Phase-3 exit toolkit & vol sizing — parameter-upgrade plan.

Covers the plan's verify list:
  - vol sizing worked example + σ-None rejection + exposure deduction
  - trailing ratchet: arms at +1×trail, never lowers, survives a re-buy
    (execute_paper_trade never loosens SL/TP), clears TP when armed
  - time stop: losers only, anchored to first_opened_at (average-ins don't
    reset it), grandfathering via exit_policy, re-entry cooldown
  - put_risk_limits round-trip preserves the new fields
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
from routes import create_app


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


NOW = datetime.now(timezone.utc).replace(microsecond=0)


class Phase3TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        os.environ["RISK_ENGINE_ENABLED"] = "true"
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "p3-agent", "password": "pw123", "initial_balance": 100000.0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        self.agent_id = body["agent_id"]
        self.token = body["token"]

    def tearDown(self) -> None:
        os.environ["RISK_ENGINE_ENABLED"] = "false"
        os.environ.pop("VOL_SIZING_ENABLED", None)
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────

    def _insert_position(self, symbol="BTC", market="crypto", qty=1.0, entry=100.0,
                         current=None, stop_loss=None, take_profit=None,
                         exit_policy=None, first_opened_at=None):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO positions
               (agent_id, symbol, market, side, quantity, entry_price, current_price,
                opened_at, stop_loss, take_profit, exit_policy, first_opened_at)
               VALUES (?, ?, ?, 'long', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.agent_id, symbol, market, qty, entry, current,
             _iso(NOW), stop_loss, take_profit, exit_policy, first_opened_at),
        )
        conn.commit()
        conn.close()

    def _position(self, symbol="BTC", market="crypto"):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM positions WHERE agent_id = ? AND market = ? AND symbol = ?",
            (self.agent_id, market, symbol))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def _set_limits(self, **kw):
        from risk_engine import put_risk_limits
        return put_risk_limits(self.agent_id, kw)


class VolSizingTests(Phase3TestCase):
    def test_worked_example_100k_sigma_245(self):
        """$100k equity, 0.5% budget, σ_daily 2.45% → target ≈ $20,408."""
        from risk_engine import evaluate_order
        self._set_limits(max_symbol_exposure_usd=1_000_000)  # isolate vol sizing
        with patch.dict(os.environ, {"VOL_SIZING_ENABLED": "true"}):
            gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy",
                                  quantity=500.0, price=100.0, sigma_daily_pct=2.45)
        self.assertTrue(gate.allowed)
        self.assertAlmostEqual(gate.quantity * 100.0, 100000 * 0.005 / 0.0245, delta=1.0)
        self.assertIn("vol-sizing", gate.adjustment or "")

    def test_sigma_none_rejects_buy(self):
        from risk_engine import evaluate_order
        with patch.dict(os.environ, {"VOL_SIZING_ENABLED": "true"}):
            gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy",
                                  quantity=1.0, price=100.0, sigma_daily_pct=None)
        self.assertFalse(gate.allowed)
        self.assertIn("sigma unavailable", gate.reason)

    def test_existing_exposure_reduces_headroom(self):
        from risk_engine import evaluate_order
        self._set_limits(max_symbol_exposure_usd=1_000_000)  # isolate vol sizing
        # $15k held in BTC (inserted without cash deduction → equity $115k);
        # target = 115k×0.5%/2.45% ≈ $23.5k → headroom ≈ $8.5k
        self._insert_position(qty=150.0, entry=100.0, current=100.0)
        with patch.dict(os.environ, {"VOL_SIZING_ENABLED": "true"}):
            gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy",
                                  quantity=500.0, price=100.0, sigma_daily_pct=2.45)
        self.assertTrue(gate.allowed)
        self.assertAlmostEqual(gate.quantity * 100.0, 115000 * 0.005 / 0.0245 - 15000, delta=50.0)

    def test_target_reached_rejects(self):
        from risk_engine import evaluate_order
        self._insert_position(qty=300.0, entry=100.0, current=100.0)  # $30k > target
        with patch.dict(os.environ, {"VOL_SIZING_ENABLED": "true"}):
            gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy",
                                  quantity=10.0, price=100.0, sigma_daily_pct=2.45)
        self.assertFalse(gate.allowed)
        self.assertIn("target reached", gate.reason)

    def test_off_by_default(self):
        from risk_engine import evaluate_order
        gate = evaluate_order(self.agent_id, "BTC", "crypto", "buy",
                              quantity=5.0, price=100.0, sigma_daily_pct=None)
        self.assertTrue(gate.allowed, "vol sizing must be opt-in (default off)")

    def test_sells_never_vol_sized(self):
        from risk_engine import evaluate_order
        self._insert_position(qty=5.0, entry=100.0, current=100.0)
        with patch.dict(os.environ, {"VOL_SIZING_ENABLED": "true"}):
            gate = evaluate_order(self.agent_id, "BTC", "crypto", "sell",
                                  quantity=5.0, price=100.0, sigma_daily_pct=None)
        self.assertTrue(gate.allowed)


class TrailingStopTests(Phase3TestCase):
    def _tick(self):
        from risk_engine import run_sltp_watcher_tick
        return run_sltp_watcher_tick()

    def test_trail_arms_and_ratchets_and_clears_tp(self):
        self._set_limits(use_trailing=1, trail_pct=0.05)
        # +10% profit ≥ 1×trail → arms; stop ratchets to 110×0.95 = 104.5
        self._insert_position(entry=100.0, current=110.0, stop_loss=95.0,
                              take_profit=150.0, exit_policy="v1")
        self._tick()
        pos = self._position()
        self.assertAlmostEqual(pos["stop_loss"], 104.5)
        self.assertIsNone(pos["take_profit"], "TP must clear once the trail is armed")

    def test_trail_never_lowers_stop(self):
        self._set_limits(use_trailing=1, trail_pct=0.05)
        self._insert_position(entry=100.0, current=106.0, stop_loss=104.0,
                              exit_policy="v1")
        self._tick()
        pos = self._position()
        self.assertGreaterEqual(pos["stop_loss"], 104.0)

    def test_trail_not_armed_below_threshold(self):
        self._set_limits(use_trailing=1, trail_pct=0.05)
        self._insert_position(entry=100.0, current=103.0, stop_loss=95.0,
                              take_profit=110.0, exit_policy="v1")
        self._tick()
        pos = self._position()
        self.assertAlmostEqual(pos["stop_loss"], 95.0)
        self.assertAlmostEqual(pos["take_profit"], 110.0)

    def test_grandfathered_positions_untouched(self):
        self._set_limits(use_trailing=1, trail_pct=0.05)
        self._insert_position(entry=100.0, current=120.0, stop_loss=95.0,
                              take_profit=150.0, exit_policy=None)  # pre-feature row
        self._tick()
        pos = self._position()
        self.assertAlmostEqual(pos["stop_loss"], 95.0)
        self.assertAlmostEqual(pos["take_profit"], 150.0)

    def test_rebuy_never_loosens_ratcheted_stop(self):
        """Integration: buy → ratchet → automated re-buy → stop must not drop."""
        from automation import execute_paper_trade
        self._set_limits(use_trailing=1, trail_pct=0.05)
        self._insert_position(entry=100.0, current=110.0, stop_loss=95.0,
                              take_profit=150.0, exit_policy="v1")
        self._tick()
        self.assertAlmostEqual(self._position()["stop_loss"], 104.5)
        # re-buy at 104 with a fresh gate stop of 98.8 — must NOT overwrite
        signal_id, skip = execute_paper_trade(
            self.agent_id, "BTC", "crypto", "buy", 1.0, 104.0,
            stop_loss=98.8, take_profit=114.4)
        self.assertIsNotNone(signal_id, skip)
        pos = self._position()
        self.assertAlmostEqual(pos["stop_loss"], 104.5,
                               msg="re-buy loosened the ratcheted stop")


class TimeStopTests(Phase3TestCase):
    def _tick(self):
        from risk_engine import run_sltp_watcher_tick
        return run_sltp_watcher_tick()

    def test_old_loser_is_closed(self):
        self._set_limits(time_stop_days=14)
        self._insert_position(entry=100.0, current=97.0, exit_policy="v1",
                              first_opened_at=_iso(NOW - timedelta(days=20)))
        result = self._tick()
        self.assertEqual(result["closed"], 1)
        self.assertIsNone(self._position())

    def test_winner_rides(self):
        self._set_limits(time_stop_days=14)
        self._insert_position(entry=100.0, current=105.0, exit_policy="v1",
                              first_opened_at=_iso(NOW - timedelta(days=40)))
        result = self._tick()
        self.assertEqual(result["closed"], 0)
        self.assertIsNotNone(self._position())

    def test_young_loser_not_closed(self):
        self._set_limits(time_stop_days=14)
        self._insert_position(entry=100.0, current=97.0, exit_policy="v1",
                              first_opened_at=_iso(NOW - timedelta(days=5)))
        self.assertEqual(self._tick()["closed"], 0)

    def test_zero_days_disables(self):
        self._set_limits(time_stop_days=0)
        self._insert_position(entry=100.0, current=97.0, exit_policy="v1",
                              first_opened_at=_iso(NOW - timedelta(days=100)))
        self.assertEqual(self._tick()["closed"], 0)

    def test_no_first_opened_at_grandfathered(self):
        self._set_limits(time_stop_days=14)
        self._insert_position(entry=100.0, current=97.0, exit_policy="v1",
                              first_opened_at=None)
        self.assertEqual(self._tick()["closed"], 0)

    def test_average_in_does_not_reset_first_opened_at(self):
        """services average-in resets opened_at but must not touch first_opened_at."""
        from services import _update_position_from_signal
        first = _iso(NOW - timedelta(days=20))
        self._insert_position(entry=100.0, current=97.0, exit_policy="v1",
                              first_opened_at=first)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        _update_position_from_signal(self.agent_id, "BTC", "crypto", "buy",
                                     1.0, 97.0, _iso(NOW), cursor=cursor)
        conn.commit()
        conn.close()
        pos = self._position()
        self.assertEqual(pos["first_opened_at"], first)
        self.assertEqual(pos["opened_at"], _iso(NOW), "opened_at legacy reset preserved")

    def test_cooldown_blocks_reentry(self):
        from automation import _time_stop_cooldown_blocks
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO signals
               (signal_id, agent_id, message_type, market, signal_type, symbol,
                side, entry_price, quantity, content, timestamp, created_at, executed_at)
               VALUES (999001, ?, 'operation', 'crypto', 'automation', 'BTC',
                       'sell', 97.0, 1.0, 'risk: time_stop triggered at 97.0 (SL/TP watcher)',
                       0, ?, ?)""",
            (self.agent_id, _iso(NOW - timedelta(hours=2)), _iso(NOW - timedelta(hours=2))))
        conn.commit()
        conn.close()
        reason = _time_stop_cooldown_blocks(self.agent_id, "BTC", "crypto", "buy")
        self.assertIsNotNone(reason)
        self.assertIn("cooldown", reason)
        # sells never blocked; other symbols never blocked
        self.assertIsNone(_time_stop_cooldown_blocks(self.agent_id, "BTC", "crypto", "sell"))
        self.assertIsNone(_time_stop_cooldown_blocks(self.agent_id, "ETH", "crypto", "buy"))


class LimitsRoundTripTests(Phase3TestCase):
    def test_new_fields_survive_partial_put(self):
        from risk_engine import get_risk_limits, put_risk_limits
        put_risk_limits(self.agent_id, {"use_trailing": 1, "trail_pct": 0.07,
                                        "time_stop_days": 21})
        # A later PUT touching only an old field must not reset the new ones
        put_risk_limits(self.agent_id, {"max_daily_loss_usd": 500.0})
        limits = get_risk_limits(self.agent_id)
        self.assertEqual(limits["use_trailing"], 1)
        self.assertAlmostEqual(limits["trail_pct"], 0.07)
        self.assertEqual(limits["time_stop_days"], 21)
        self.assertAlmostEqual(limits["max_daily_loss_usd"], 500.0)

    def test_api_roundtrip(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        r = self.client.put("/api/risk/limits", headers=headers,
                            json={"use_trailing": True, "trail_pct": 0.06,
                                  "time_stop_days": 10})
        self.assertEqual(r.status_code, 200, r.text)
        limits = r.json()["limits"]
        self.assertEqual(limits["use_trailing"], 1)
        self.assertAlmostEqual(limits["trail_pct"], 0.06)
        self.assertEqual(limits["time_stop_days"], 10)
        bad = self.client.put("/api/risk/limits", headers=headers,
                              json={"time_stop_days": 999})
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
