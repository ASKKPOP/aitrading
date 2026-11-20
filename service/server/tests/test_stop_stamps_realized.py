"""A flat run stopped through request_stop must leave a correct stamp
(2026-11-20, docs/reports/2026-11-20-marked-equity-stamp-drift-experiment.md).

`trading_runs.realized_pnl_usd` is written only by run_engine's control pass:
every tick in `_control_active` (BEFORE the armed exit fires in that tick)
and after `_control_stopping` finishes. `request_stop`'s no-position branch
goes running/paused -> stopped directly and never stamped, so a member whose
position closed after the tick's stamp and that was then stopped by hand in
the same tick kept a stamp missing that closing leg forever. fleet_planner's
`marked_equity` sums those stamps for stopped members, and a fleet that keeps
trading reads them on every rail check.

The fix: the direct branch writes the replayed realized P&L in the same
UPDATE that stops the run.
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
import run_engine
import trading_runs

RUN_ID = 8801
AGENT_ID = 7


class StopStampsRealized(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO users (id, email, "
                        "password_hash, created_at) VALUES (1, 'p@x.com', "
                        "'x', '2026-01-01T00:00:00Z')")
            cur.execute("INSERT OR IGNORE INTO agents (id, name, token_hash, "
                        "cash, user_id, created_at) VALUES (?, 'pf', 'th', "
                        "1000, 1, '2026-01-01T00:00:00Z')", (AGENT_ID,))
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, status="running", stamp=0.0):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO trading_runs (id, agent_id, symbol, "
                        "market, status, active_key, realized_pnl_usd, "
                        "created_at) VALUES (?, ?, 'BTC', 'crypto', ?, ?, ?, "
                        "'2026-11-20T00:00:00Z')",
                        (RUN_ID, AGENT_ID, status, f"k-{RUN_ID}", stamp))
            conn.commit()
        finally:
            conn.close()

    def _leg(self, sid, side, price, qty, fee):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO signals (id, signal_id, agent_id, message_type, "
                "market, symbol, side, entry_price, quantity, fee_usd, run_id, "
                "client_order_id, timestamp, created_at) VALUES (?, ?, ?, "
                "'operation', 'crypto', 'BTC', ?, ?, ?, ?, ?, ?, "
                "'2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z')",
                (sid, f"sig-{sid}", AGENT_ID, side, price, qty, fee, RUN_ID,
                 f"run:{RUN_ID}:cyc:{sid}"))
            conn.commit()
        finally:
            conn.close()

    def _open_position(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO positions (agent_id, symbol, market, side, "
                "quantity, entry_price, opened_at, run_id) VALUES (?, 'BTC', "
                "'crypto', 'long', 1.0, 100.0, '2026-11-20T00:00:00Z', ?)",
                (AGENT_ID, RUN_ID))
            conn.commit()
        finally:
            conn.close()

    def _stamp(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status, realized_pnl_usd FROM trading_runs "
                        "WHERE id = ?", (RUN_ID,))
            row = dict(cur.fetchone())
            return row["status"], row["realized_pnl_usd"]
        finally:
            conn.close()

    def _round_trip(self):
        # buy 1 @100 fee 0.10, sell 1 @110 fee 0.11 -> +10 - 0.21 = 9.79
        self._leg(1, "buy", 100.0, 1.0, 0.10)
        self._leg(2, "sell", 110.0, 1.0, 0.11)

    def test_flat_stop_stamps_the_closing_leg(self):
        """The window: the tick stamped after the buy only (-0.10), the sell
        landed after that stamp, and the member was stopped while flat."""
        self._run(stamp=-0.10)
        self._round_trip()
        out = trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        status, stamp = self._stamp()
        self.assertEqual(status, trading_runs.STATUS_STOPPED)
        self.assertAlmostEqual(stamp, 9.79, places=9)
        self.assertAlmostEqual(
            stamp, run_engine.replay_realized(
                [{"side": "buy", "entry_price": 100.0, "quantity": 1.0,
                  "fee_usd": 0.10},
                 {"side": "sell", "entry_price": 110.0, "quantity": 1.0,
                  "fee_usd": 0.11}]), places=9)
        # the caller (routes_runs' Stop) returns this dict to the UI
        self.assertAlmostEqual(out["realized_pnl_usd"], 9.79, places=9)

    def test_only_this_runs_operation_legs_count(self):
        """A discussion/strategy signal on the run, and another run's legs,
        are not part of this run's realized P&L."""
        self._run(stamp=-0.10)
        self._round_trip()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO signals (id, signal_id, agent_id, message_type, "
                "market, symbol, side, entry_price, quantity, fee_usd, run_id, "
                "timestamp, created_at) VALUES (3, 'sig-3', ?, 'strategy', "
                "'crypto', 'BTC', 'buy', 100.0, 1.0, 3.0, ?, "
                "'2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z')",
                (AGENT_ID, RUN_ID))
            cur.execute(
                "INSERT INTO signals (id, signal_id, agent_id, message_type, "
                "market, symbol, side, entry_price, quantity, fee_usd, run_id, "
                "client_order_id, timestamp, created_at) VALUES (4, 'sig-4', ?, "
                "'operation', 'crypto', 'BTC', 'buy', 100.0, 1.0, 7.0, ?, "
                "'other:1', '2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z')",
                (AGENT_ID, RUN_ID + 1))
            conn.commit()
        finally:
            conn.close()
        trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        self.assertAlmostEqual(self._stamp()[1], 9.79, places=9)

    def test_paused_member_is_stamped_too(self):
        self._run(status="paused")
        self._round_trip()
        trading_runs.request_stop(RUN_ID, AGENT_ID, False, reason="user_stop")
        self.assertAlmostEqual(self._stamp()[1], 9.79, places=9)

    def test_marked_equity_reads_the_corrected_stamp(self):
        """The rails' input: a stopped member contributes its stamp."""
        import fleet_planner
        self._run(stamp=-0.10)
        self._round_trip()
        trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        member = trading_runs.get_run(RUN_ID, AGENT_ID)
        self.assertAlmostEqual(
            float(member["realized_pnl_usd"]), 9.79, places=9)
        self.assertEqual(member["status"], fleet_planner.trading_runs.STATUS_STOPPED)

    def test_a_replay_failure_never_blocks_the_stop(self):
        """A stop is a safety action: if the leg read fails, the run still
        stops, with its previous stamp."""
        self._run(stamp=-0.10)
        self._round_trip()
        with patch.object(run_engine, "replay_realized",
                          side_effect=RuntimeError("boom")):
            trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        status, stamp = self._stamp()
        self.assertEqual(status, trading_runs.STATUS_STOPPED)
        self.assertAlmostEqual(stamp, -0.10, places=9)

    def test_holding_stop_goes_to_stopping_and_leaves_the_stamp(self):
        """With a position the engine finishes the stop and stamps after the
        flatten (_control_stopping) — unchanged."""
        self._run(stamp=-0.10)
        self._leg(1, "buy", 100.0, 1.0, 0.10)
        self._open_position()
        trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        status, stamp = self._stamp()
        self.assertEqual(status, trading_runs.STATUS_STOPPING)
        self.assertAlmostEqual(stamp, -0.10, places=9)

    def test_armed_stop_is_unchanged(self):
        """An armed run has no entries; nothing to stamp."""
        self._run(status="armed")
        trading_runs.request_stop(RUN_ID, AGENT_ID, True)
        status, stamp = self._stamp()
        self.assertEqual(status, trading_runs.STATUS_STOPPED)
        self.assertEqual(stamp, 0.0)


if __name__ == "__main__":
    unittest.main()
