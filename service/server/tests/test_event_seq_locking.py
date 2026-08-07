"""run_events seq allocation must take a row lock.

2026-08-07: `_emit_event` did a plain `SELECT last_event_seq`, added one, and
INSERTed. Two writers on the same run read the same value and collided on the
unique index — twice in one session, and the second only after the fleet grew
from 6 runs to 10:

    (1062, "Duplicate entry '981-191' for key uq_run_events_run_seq")
    (1062, "Duplicate entry '983-784' for key uq_run_events_run_seq")

Impact was contained both times because the loser happened to be a fail-soft
telemetry row. That was luck about which writer lost, not design.
"""
import os
import tempfile
import unittest

import database
import trading_runs


class EventSeqTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "s.db")
        database.init_database()
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO agents (name, cash) VALUES (?, ?)", ("a", 1000.0))
            cur.execute(
                "INSERT INTO trading_runs (agent_id, symbol, market, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (1, "X", "crypto", "running", "2026-08-07T00:00:00Z"))
            conn.commit()
            cur.execute("SELECT id FROM trading_runs ORDER BY id DESC")
            self.run_id = dict(cur.fetchone())["id"]
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _seqs(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT seq FROM run_events WHERE run_id = ? ORDER BY seq",
                        (self.run_id,))
            return [dict(r)["seq"] for r in cur.fetchall()]
        finally:
            conn.close()

    def test_sequential_emissions_are_dense_and_unique(self):
        for i in range(25):
            trading_runs.emit_telemetry_event(self.run_id, "equity", {"i": i})
        seqs = self._seqs()
        self.assertEqual(seqs, list(range(1, 26)),
                         "seq allocation is not dense and gap-free")
        self.assertEqual(len(seqs), len(set(seqs)), "duplicate seq allocated")

    def test_the_counter_is_incremented_BEFORE_the_read(self):
        """The row lock comes from the UPDATE. If the SELECT runs first the
        lock is not held and two writers can read the same value — which is
        exactly the collision this fixes."""
        import inspect
        src = inspect.getsource(trading_runs._emit_event)
        upd = src.index("UPDATE trading_runs SET last_event_seq")
        sel = src.index("SELECT last_event_seq FROM trading_runs")
        ins = src.index("INSERT INTO run_events")
        self.assertLess(upd, sel, "the counter is read before it is locked")
        self.assertLess(sel, ins, "the seq is inserted before it is read")

    def test_a_missing_run_still_yields_a_usable_seq(self):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            database.begin_write_transaction(cur)
            seq = trading_runs._emit_event(cur, 999999, "equity", {})
            conn.rollback()
        finally:
            conn.close()
        self.assertEqual(seq, 1)

    def test_counter_and_journal_agree_after_many_writes(self):
        for i in range(15):
            trading_runs.emit_telemetry_event(self.run_id, "equity", {"i": i})
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT last_event_seq FROM trading_runs WHERE id = ?",
                        (self.run_id,))
            counter = int(dict(cur.fetchone())["last_event_seq"])
        finally:
            conn.close()
        self.assertEqual(counter, max(self._seqs()),
                         "the run's counter drifted from the journal")


if __name__ == "__main__":
    unittest.main()
