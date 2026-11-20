"""Full Auto — the fleet's 30-minute AI analysis feed (read-side composition).

The tests write the same rows the fleet planner and the desk journal write,
then assert the feed folds them per 30-minute window:
target finding (ranked / kept / dropped / skipped / research_empty / opened)
and the desk's decisions + fills for the fleet's own TRADINGs only.
"""

from __future__ import annotations

import json
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
import fleet_ai_feed
import trading_runs
from routes import create_app


def _ts(dt: datetime) -> str:
    return dt.strftime(trading_runs.TS_FMT)


class FleetAiFeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "feed-agent", "password": "pw123",
                  "initial_balance": 10000.0})
        assert resp.status_code == 200, resp.text
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        # Inside the 03:00–03:30 window.
        self.now = datetime(2026, 11, 20, 3, 10, 0, tzinfo=timezone.utc)
        self.fseq = 0
        self.rseq = 0
        self.fleet_id = self._fleet(self.agent_id)

    def tearDown(self):
        self.tmp.cleanup()

    # ── fixtures ──────────────────────────────────────────────────────────
    def _sql(self, sql: str, args: tuple) -> int:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, args)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _fleet(self, agent_id: int) -> int:
        return self._sql(
            """INSERT INTO fleets (agent_id, status, n_runs, total_budget_usd, created_at)
               VALUES (?, 'active', 6, 10000, ?)""",
            (agent_id, _ts(self.now - timedelta(days=1))))

    def _fev(self, kind: str, payload: dict, at: datetime, fleet_id: int | None = None):
        self.fseq += 1
        self._sql("""INSERT INTO fleet_events (fleet_id, seq, ts, event_type, payload)
                     VALUES (?, ?, ?, ?, ?)""",
                  (fleet_id or self.fleet_id, self.fseq, _ts(at), kind, json.dumps(payload)))

    def _run(self, run_id: int, symbol: str, fleet_id: int | None, stopped_at: str | None = None):
        self._sql("""INSERT INTO trading_runs (id, agent_id, symbol, market, status,
                                               fleet_id, stopped_at, created_at)
                     VALUES (?, ?, ?, 'crypto', 'running', ?, ?, ?)""",
                  (run_id, self.agent_id, symbol, fleet_id, stopped_at,
                   _ts(self.now - timedelta(days=1))))

    def _rev(self, run_id: int, kind: str, payload: dict, at: datetime):
        self.rseq += 1
        self._sql("""INSERT INTO run_events (run_id, seq, event_type, ts, payload)
                     VALUES (?, ?, ?, ?, ?)""",
                  (run_id, self.rseq, kind, _ts(at), json.dumps(payload)))

    def _feed(self, limit: int = 3) -> list[dict]:
        return fleet_ai_feed.fleet_feed(self.fleet_id, limit, now=self.now)

    # ── target finding ────────────────────────────────────────────────────
    def test_target_finding_is_folded_into_its_window(self):
        at = self.now - timedelta(minutes=5)
        self._fev("research_ranked", {"selected": [
            {"symbol": "MSFT", "market": "us-stock", "final_score": 0.9},
            {"symbol": "ZEC", "market": "crypto", "final_score": 0.4}]}, at)
        self._fev("backtest_gate", {"kept": ["MSFT"],
                                    "dropped": {"ZEC": "non-positive expectancy -12 USD/trade"}}, at)
        self._fev("run_started", {"run_id": 7, "symbol": "MSFT", "market": "us-stock",
                                  "slot_index": 1, "budget": 1666.0}, at)
        msg = self._feed()[0]
        t = msg["targets"]
        self.assertEqual(msg["start"], "2026-11-20T03:00:00Z")
        self.assertEqual([r["symbol"] for r in t["ranked"]], ["MSFT", "ZEC"])
        self.assertEqual([k["symbol"] for k in t["kept"]], ["MSFT"])
        self.assertEqual(t["dropped"][0]["symbol"], "ZEC")
        self.assertIn("expectancy", t["dropped"][0]["reason"])
        self.assertEqual(t["opened"][0]["symbol"], "MSFT")
        self.assertAlmostEqual(t["opened"][0]["budget"], 1666.0)

    def test_repeated_empty_research_and_skips_are_counted_not_listed(self):
        """The 11-20 failure mode: 20 research_empty rows in a row must read
        as one line with a count, not 20 lines."""
        for i in range(20):
            self._fev("research_empty", {"reason": "no eligible candidates"},
                      self.now - timedelta(minutes=9) + timedelta(seconds=i * 20))
        for _ in range(3):
            self._fev("candidate_skipped", {"symbol": "TGT", "reason": "no subscription"},
                      self.now - timedelta(minutes=2))
        t = self._feed()[0]["targets"]
        self.assertEqual(t["research_empty"], 20)
        self.assertEqual(len(t["skipped"]), 1)
        self.assertEqual(t["skipped"][0]["count"], 3)

    def _thesis(self, market: str, direction: str, symbol: str, at: datetime):
        self._sql("""INSERT INTO research_theses (batch_id, market, symbol, direction,
                                                  factor_scores_json, planner,
                                                  created_at, expires_at)
                     VALUES (?, ?, ?, ?, '{}', 'test', ?, ?)""",
                  (f"research:{_ts(at)}", market, symbol, direction,
                   _ts(at), _ts(at + timedelta(hours=6))))

    def test_research_counts_annotate_only_windows_where_the_fleet_searched(self):
        """Says WHY a search came back empty (11-20: every batch was shorts),
        but never invents a message for a window the fleet was not in."""
        at = self.now - timedelta(minutes=6)
        self._fev("research_empty", {}, at)
        self._thesis("crypto", "short", "BTCUSDT", at)
        self._thesis("crypto", "short", "ETHUSDT", at)
        self._thesis("us-stock", "long", "SLV", at)
        # An OLDER batch in the same window: superseded, not summed.
        self._thesis("crypto", "short", "XRPUSDT", at - timedelta(minutes=3))
        # A batch in a window with no fleet activity: must not surface.
        self._thesis("crypto", "long", "SOLUSDT", self.now - timedelta(hours=2))
        feed = self._feed()
        self.assertEqual(len(feed), 1)
        research = {r["market"]: r for r in feed[0]["targets"]["research"]}
        self.assertEqual(research["crypto"], {"market": "crypto", "long": 0, "short": 2})
        self.assertEqual(research["us-stock"]["long"], 1)

    def test_research_counts_skip_a_window_with_decisions_but_no_search(self):
        """A window that exists only because the desk decided something must
        not carry the global research counts (the fleet was not searching)."""
        self._run(401, "BTCUSDT", self.fleet_id)
        at = self.now - timedelta(minutes=5)
        self._rev(401, "decision", {"action": "hold"}, at)
        self._thesis("crypto", "short", "ETHUSDT", at)
        msg = self._feed()[0]
        self.assertEqual(msg["decisions"]["counts"], {"hold": 1})
        self.assertEqual(msg["targets"]["research"], [])

    def test_status_transitions_keep_journal_order_within_one_second(self):
        at = self.now - timedelta(minutes=4)
        self._fev("fleet_status", {"from": None, "to": "draft"}, at)
        self._fev("fleet_status", {"to": "researching", "reason": "start"}, at)
        status = self._feed()[0]["targets"]["status"]
        self.assertEqual([x["to"] for x in status], ["draft", "researching"])

    # ── decisions ─────────────────────────────────────────────────────────
    def test_latest_decision_per_trading_and_fills_reach_the_message(self):
        self._run(101, "BTCUSDT", self.fleet_id)
        self._rev(101, "decision", {"action": "hold", "confidence": 0.5,
                                    "report": "Waiting for a reclaim."},
                  self.now - timedelta(minutes=8))
        self._rev(101, "decision", {"action": "buy", "confidence": 0.71,
                                    "report": "Reclaimed the 20-day mean."},
                  self.now - timedelta(minutes=3))
        self._rev(101, "trade", {"side": "buy", "symbol": "BTCUSDT",
                                 "quantity": 0.01, "price": 61500.0},
                  self.now - timedelta(minutes=3))
        d = self._feed()[0]["decisions"]
        self.assertEqual(d["counts"], {"hold": 1, "buy": 1})
        self.assertEqual(len(d["runs"]), 1)
        self.assertEqual(d["runs"][0]["action"], "buy")
        self.assertIn("Reclaimed", d["runs"][0]["report"])
        self.assertEqual(d["fills"][0]["side"], "buy")
        self.assertAlmostEqual(d["fills"][0]["price"], 61500.0)

    def test_other_fleets_and_unattached_runs_never_appear(self):
        other = self._fleet(self.agent_id)
        self._run(201, "ETHUSDT", other)
        self._run(202, "SOLUSDT", None)
        for rid in (201, 202):
            self._rev(rid, "decision", {"action": "sell"}, self.now - timedelta(minutes=4))
        self._fev("research_empty", {}, self.now - timedelta(minutes=4), fleet_id=other)
        self.assertEqual(self._feed(), [])

    # ── the window ────────────────────────────────────────────────────────
    def test_newest_three_non_empty_windows_newest_first(self):
        # Activity in 5 different windows, plus a quiet gap between them.
        for minutes in (5, 35, 125, 155, 185):
            self._fev("research_empty", {}, self.now - timedelta(minutes=minutes))
        feed = self._feed(3)
        self.assertEqual([m["start"] for m in feed],
                         ["2026-11-20T03:00:00Z", "2026-11-20T02:30:00Z",
                          "2026-11-20T01:00:00Z"])

    def test_rows_older_than_the_lookback_are_ignored(self):
        self._fev("research_empty", {}, self.now - timedelta(hours=30))
        self.assertEqual(self._feed(), [])

    def test_a_run_stopped_before_the_window_is_not_read(self):
        self._run(301, "BNBUSDT", self.fleet_id, stopped_at=_ts(self.now - timedelta(days=3)))
        self._rev(301, "decision", {"action": "sell"}, self.now - timedelta(minutes=4))
        self.assertEqual(self._feed(), [])

    def test_limit_is_clamped(self):
        for minutes in range(5, 600, 30):
            self._fev("research_empty", {}, self.now - timedelta(minutes=minutes))
        self.assertEqual(len(self._feed(0)), 1)
        self.assertEqual(len(self._feed(999)), fleet_ai_feed.MAX_MESSAGES)

    # ── review fixes (2026-11-20) ────────────────────────────────────────
    def test_an_open_run_is_read_even_behind_many_newer_stopped_runs(self):
        """Verifier + adversarial review: ORDER BY id DESC LIMIT let rotated
        runs hide an open run's current sell."""
        self._run(5, "OLDUSDT", self.fleet_id)
        stopped = _ts(self.now - timedelta(hours=1))
        for rid in range(1000, 1000 + fleet_ai_feed.MAX_STOPPED_RUNS + 25):
            self._run(rid, "NEWUSDT", self.fleet_id, stopped_at=stopped)
        self._rev(5, "decision", {"action": "sell", "report": "exit now"},
                  self.now - timedelta(minutes=2))
        rows = self._feed()[0]["decisions"]["runs"]
        self.assertEqual([(r["symbol"], r["action"]) for r in rows], [("OLDUSDT", "sell")])

    def test_missing_or_malformed_fields_never_crash_or_read_as_hold(self):
        self._run(501, "AUSDT", self.fleet_id)
        self._run(502, "BUSDT", self.fleet_id)
        at = self.now - timedelta(minutes=3)
        self._rev(501, "decision", {"action": None}, at)
        self._rev(502, "decision", {"action": 1, "report": {"x": 1}}, at)
        self._fev("backtest_gate", {"kept": "MSFT"}, at)
        msg = self._feed()[0]
        self.assertEqual(msg["decisions"]["counts"], {"none": 2})
        self.assertNotIn("hold", msg["decisions"]["counts"])
        self.assertEqual([k["symbol"] for k in msg["targets"]["kept"]], ["MSFT"])

    def test_trades_first_then_newest_and_fills_keep_the_newest(self):
        at = self.now - timedelta(minutes=10)
        for i in range(12):
            self._run(600 + i, f"S{i}USDT", self.fleet_id)
            self._rev(600 + i, "decision", {"action": "hold"}, at + timedelta(seconds=i))
        self._rev(611, "decision", {"action": "buy"}, at + timedelta(seconds=30))
        for i in range(12):
            self._rev(600, "trade", {"side": "buy", "price": float(i)},
                      at + timedelta(seconds=40 + i))
        d = self._feed()[0]["decisions"]
        self.assertEqual(d["runs"][0]["action"], "buy")
        self.assertEqual(len(d["fills"]), fleet_ai_feed.MAX_ITEMS)
        self.assertEqual(d["fills"][0]["price"], 11.0)
        self.assertEqual(d["fills_more"], 12 - fleet_ai_feed.MAX_ITEMS)

    def test_research_respects_the_fleet_market_scope_and_now(self):
        self._sql("UPDATE fleets SET market_scope_json = ? WHERE id = ?",
                  ('["us-stock"]', self.fleet_id))
        at = self.now - timedelta(minutes=5)
        self._fev("research_empty", {}, at)
        self._thesis("crypto", "short", "BTCUSDT", at)
        self._thesis("us-stock", "long", "AAPL", at)
        self._thesis("us-stock", "long", "LATE", self.now + timedelta(minutes=1))
        research = self._feed()[0]["targets"]["research"]
        self.assertEqual(research, [{"market": "us-stock", "long": 1, "short": 0}])

    def test_a_fleet_stopped_before_the_lookback_returns_nothing(self):
        self._sql("UPDATE fleets SET stopped_at = ? WHERE id = ?",
                  (_ts(self.now - timedelta(days=3)), self.fleet_id))
        self._fev("research_empty", {}, self.now - timedelta(minutes=5))
        self.assertEqual(self._feed(), [])

    def test_a_window_cut_by_the_row_cap_is_marked_partial(self):
        for minutes in (65, 35, 5):   # oldest first: seq rises with time
            for _ in range(4):
                self._fev("research_empty", {}, self.now - timedelta(minutes=minutes))
        with patch.object(fleet_ai_feed, "FLEET_EVENT_CAP", 6):
            feed = fleet_ai_feed.fleet_feed(self.fleet_id, 3, now=self.now)
        # 6 newest rows = 4 in 03:00 + 2 of the 4 in 02:30 → 02:30 is shown
        # but marked partial; 03:00 is complete.
        self.assertEqual([m["start"] for m in feed], ["2026-11-20T03:00:00Z", "2026-11-20T02:30:00Z"])
        self.assertEqual(feed[0]["targets"]["research_empty"], 4)
        self.assertFalse(feed[0]["partial"])
        self.assertTrue(feed[1]["partial"])

    def test_one_busy_run_cuts_only_its_own_rows(self):
        """Review round 2: a capped run must not drop other runs' windows."""
        self._run(701, "BUSYUSDT", self.fleet_id)
        self._run(702, "CALMUSDT", self.fleet_id)
        self._rev(702, "decision", {"action": "sell"}, self.now - timedelta(minutes=95))
        for i in range(10):   # oldest first: 02:45 … 03:03, every 2 min
            self._rev(701, "decision", {"action": "hold"},
                      self.now - timedelta(minutes=25) + timedelta(minutes=2 * i))
        with patch.object(fleet_ai_feed, "RUN_EVENT_CAP_PER_RUN", 6):
            feed = fleet_ai_feed.fleet_feed(self.fleet_id, 3, now=self.now)
        starts = [m["start"] for m in feed]
        self.assertIn("2026-11-20T03:00:00Z", starts)
        # 01:30 (CALM's sell) survives; BUSY's partly-read 02:30 rows are cut.
        self.assertIn("2026-11-20T01:30:00Z", starts)
        calm = next(m for m in feed if m["start"] == "2026-11-20T01:30:00Z")
        self.assertEqual(calm["decisions"]["counts"], {"sell": 1})
        # It may be missing BUSY's older rows — so it says so.
        self.assertTrue(calm["partial"])
        self.assertFalse(next(m for m in feed if m["start"] == "2026-11-20T03:00:00Z")["partial"])
        for m in feed:
            if m["start"] == "2026-11-20T03:00:00Z":
                self.assertEqual(m["decisions"]["counts"], {"hold": 2})
            self.assertNotEqual(m["start"], "2026-11-20T02:30:00Z")

    def test_non_list_and_non_string_platform_fields_never_crash(self):
        at = self.now - timedelta(minutes=3)
        self._fev("research_ranked", {"selected": 3}, at)
        self._fev("backtest_gate", {"kept": 5, "dropped": {"X": {"a": 1}}}, at)
        self._fev("candidate_skipped", {"symbol": {"a": 1}, "reason": "r"}, at)
        self._fev("fleet_status", {"to": "active", "reason": ["x"]}, at)
        t = self._feed()[0]["targets"]
        self.assertEqual(t["ranked"], [])
        self.assertEqual(t["kept"], [])
        self.assertEqual(t["skipped"], [])
        self.assertEqual(t["dropped"][0]["reason"], "")
        self.assertEqual(t["status"], [{"to": "active", "reason": None}])

    def test_a_read_that_exactly_fills_the_cap_is_complete(self):
        """Verifier round 2 (A): exactly CAP rows = everything was read."""
        for minutes in (65, 35, 5):
            for _ in range(2):
                self._fev("research_empty", {}, self.now - timedelta(minutes=minutes))
        with patch.object(fleet_ai_feed, "FLEET_EVENT_CAP", 6):
            feed = fleet_ai_feed.fleet_feed(self.fleet_id, 3, now=self.now)
        self.assertEqual(len(feed), 3)
        self.assertTrue(all(m["targets"]["research_empty"] == 2 for m in feed))
        self.assertFalse(any(m["partial"] for m in feed))

    def test_leaked_open_drafts_cannot_hide_the_active_run(self):
        """Verifier round 2 (D): open runs are ranked by recent activity."""
        self._run(801, "REALUSDT", self.fleet_id)
        self._sql("UPDATE trading_runs SET last_cycle_at = ? WHERE id = 801",
                  (_ts(self.now - timedelta(minutes=2)),))
        for rid in range(900, 900 + fleet_ai_feed.MAX_OPEN_RUNS + 3):
            self._run(rid, "DRAFTUSDT", self.fleet_id)
        self._rev(801, "decision", {"action": "sell"}, self.now - timedelta(minutes=2))
        msg = self._feed()[0]
        self.assertEqual(msg["decisions"]["runs"][0]["symbol"], "REALUSDT")
        self.assertTrue(msg["partial"])   # some open rows were not read: say so

    def test_stopped_run_limit_marks_older_windows_partial(self):
        """Verifier round 2 (E): the 41st stopped run is missing — say so."""
        base = self.now - timedelta(hours=3)
        for i in range(fleet_ai_feed.MAX_STOPPED_RUNS + 1):
            self._run(2000 + i, f"R{i}USDT", self.fleet_id,
                      stopped_at=_ts(base + timedelta(minutes=i)))
        self._rev(2040, "decision", {"action": "sell"}, self.now - timedelta(minutes=3))
        self._rev(2000, "decision", {"action": "buy"}, base - timedelta(minutes=10))
        feed = self._feed(3)
        newest = feed[0]
        self.assertFalse(newest["partial"])
        self.assertEqual(newest["decisions"]["counts"], {"sell": 1})

    # ── route ─────────────────────────────────────────────────────────────
    def test_route_requires_auth_and_ownership(self):
        r = self.client.get(f"/api/fleets/{self.fleet_id}/ai-feed")
        self.assertEqual(r.status_code, 401)
        resp = self.client.post("/api/claw/agents/selfRegister",
                                json={"name": "intruder", "password": "pw123",
                                      "initial_balance": 1000.0})
        other_token = resp.json()["token"]
        r = self.client.get(f"/api/fleets/{self.fleet_id}/ai-feed",
                            headers={"Authorization": f"Bearer {other_token}"})
        self.assertEqual(r.status_code, 404)

    def test_route_returns_messages_for_the_owner(self):
        self._fev("research_empty", {}, datetime.now(timezone.utc) - timedelta(minutes=1))
        r = self.client.get(f"/api/fleets/{self.fleet_id}/ai-feed?limit=3",
                            headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["cycle_minutes"], 30)
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["targets"]["research_empty"], 1)


if __name__ == "__main__":
    unittest.main()
