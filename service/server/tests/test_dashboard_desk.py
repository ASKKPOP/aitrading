"""The four after-login desk panels (2026-07-28).

docs/design/dashboard-gate-preview.html specifies seven sections; the page
shipped with three of them. These are the four that were missing:

    확인이 필요합니다   a run whose own desk has stopped believing its thesis
    내 AI가 한 일        the last decisions, WITH the reason
    내 시각 기준 개장    which markets are open, on the member's clock
    내 순위              where this book actually stands

The properties that matter here are the ones a dashboard gets wrong quietly:
scope (never another member's rows), honesty (an unranked agent stays
unranked rather than being given a position), and per-panel fail-soft — the
screen someone opens when something already looks wrong is the last place
that should 500.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fastapi.testclient import TestClient

import dashboard
import database
from routes import create_app
from services import _hash_token


def _now():
    return datetime.now(timezone.utc)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.client = TestClient(create_app())

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, token="claw_a", email="a@t.io", tz="Asia/Seoul"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email,password_hash,created_at,lang,timezone) "
                    "VALUES (?,?,?,?,?)", (email, "x", "2026-01-01T00:00:00Z", "ko", tz))
        uid = cur.lastrowid
        cur.execute("INSERT INTO agents (name,password_hash,token,token_hash,cash,user_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (email, "x", token, _hash_token(token), 100000.0, uid))
        aid = cur.lastrowid
        conn.commit()
        conn.close()
        return aid

    def _run_with_decisions(self, agent_id, symbol="ZC", market="futures",
                            decisions=((0.30, "hold", "정합도 0.30"),)):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO trading_runs (agent_id,symbol,market,market_type,"
                    "status,created_at) VALUES (?,?,?,?,?,?)",
                    (agent_id, symbol, market, "futures", "running",
                     _now().strftime("%Y-%m-%dT%H:%M:%SZ")))
        rid = cur.lastrowid
        for i, (align, action, report) in enumerate(decisions, start=1):
            ts = (_now() - timedelta(minutes=10 * (len(decisions) - i))
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
            cur.execute("INSERT INTO run_events (run_id,seq,event_type,ts,payload) "
                        "VALUES (?,?,?,?,?)",
                        (rid, i, "decision", ts, json.dumps(
                            {"cycle": i, "action": action, "confidence": 0.7,
                             "scores": {"thesis_alignment": align},
                             "report": report}, ensure_ascii=False)))
        conn.commit()
        conn.close()
        return rid

    def _get(self, token="claw_a"):
        r = self.client.get("/api/dashboard/desk",
                            headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class Attention(_Base):

    def test_a_decayed_thesis_surfaces(self):
        aid = self._agent()
        self._run_with_decisions(aid, decisions=(
            (0.30, "hold", "a"), (0.30, "hold", "b"), (0.28, "hold", "c")))
        got = self._get()["attention"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["symbol"], "ZC")
        self.assertEqual(got[0]["streak"], 3)
        self.assertTrue(got[0]["at_rail"])

    def test_a_healthy_thesis_does_not(self):
        aid = self._agent()
        self._run_with_decisions(aid, decisions=(
            (0.80, "buy", "a"), (0.75, "hold", "b")))
        self.assertEqual(self._get()["attention"], [])

    def test_one_weak_read_is_not_an_alert(self):
        """A single dip is a market wobble. The card must not cry wolf."""
        aid = self._agent()
        self._run_with_decisions(aid, decisions=((0.80, "buy", "a"), (0.30, "hold", "b")))
        self.assertEqual(self._get()["attention"], [])

    def test_it_warns_one_cycle_before_the_rail_fires(self):
        """At strikes-1 there is still a decision to make; at `strikes` the
        slot is already going back."""
        aid = self._agent()
        self._run_with_decisions(aid, decisions=((0.30, "hold", "a"), (0.30, "hold", "b")))
        got = self._get()["attention"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["streak"], 2)
        self.assertFalse(got[0]["at_rail"])

    def test_a_stopped_run_is_not_flagged(self):
        aid = self._agent()
        rid = self._run_with_decisions(aid, decisions=(
            (0.30, "hold", "a"), (0.30, "hold", "b"), (0.28, "hold", "c")))
        conn = database.get_db_connection()
        conn.cursor().execute("UPDATE trading_runs SET status='stopped' WHERE id=?", (rid,))
        conn.commit(); conn.close()
        self.assertEqual(self._get()["attention"], [])


class Decisions(_Base):

    def test_the_reason_is_carried_through(self):
        aid = self._agent()
        self._run_with_decisions(aid, decisions=(
            (0.7, "buy", "20일 모멘텀 −5.3%로 달러 약세 확인."),))
        got = self._get()["decisions"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["reason"], "20일 모멘텀 −5.3%로 달러 약세 확인.")
        self.assertEqual(got[0]["action"], "enter")

    def test_actions_collapse_to_the_three_panel_states(self):
        for raw, expected in (("buy", "enter"), ("short", "enter"),
                              ("sell", "exit"), ("cover", "exit"),
                              ("hold", "hold"), ("", "hold")):
            with self.subTest(raw=raw):
                self.assertEqual(dashboard._decision_action({"action": raw}), expected)

    def test_newest_first(self):
        aid = self._agent()
        self._run_with_decisions(aid, decisions=(
            (0.7, "buy", "older"), (0.6, "hold", "newer")))
        self.assertEqual([d["reason"] for d in self._get()["decisions"]],
                         ["newer", "older"])

    def test_another_members_decisions_are_never_visible(self):
        mine = self._agent(token="claw_a", email="a@t.io")
        theirs = self._agent(token="claw_b", email="b@t.io")
        self._run_with_decisions(theirs, symbol="SECRET",
                                 decisions=((0.7, "buy", "not yours"),))
        self._run_with_decisions(mine, symbol="MINE",
                                 decisions=((0.7, "buy", "mine"),))
        got = self._get("claw_a")["decisions"]
        self.assertEqual({d["symbol"] for d in got}, {"MINE"})

    def test_a_decision_with_no_report_still_appears(self):
        """'The desk decided and said nothing' is itself worth seeing."""
        aid = self._agent()
        self._run_with_decisions(aid, decisions=((0.7, "buy", ""),))
        got = self._get()["decisions"]
        self.assertEqual(len(got), 1)
        self.assertIsNone(got[0]["reason"])


class Sessions(_Base):

    def test_seoul_matches_the_published_market_hours(self):
        """Same numbers the generated market-hours guide prints: Shanghai
        09:30 CST is 10:30 in Seoul, NYSE 09:30 ET is 22:30."""
        s = dashboard.sessions("Asia/Seoul",
                               datetime(2026, 7, 29, 2, 0, tzinfo=timezone.utc))
        by = {m["market"]: m for m in s["markets"]}
        self.assertEqual(s["timezone"], "Asia/Seoul")
        self.assertEqual(by["crypto"]["bands"], [[0.0, 24.0]])
        self.assertEqual(by["a-stock"]["bands"][0][0], 10.5)
        self.assertEqual(by["a-stock"]["bands"][1][0], 14.0)
        self.assertEqual(by["us-stock"]["bands"][-1][0], 22.5)

    def test_a_different_zone_shifts_the_bands(self):
        seoul = dashboard.sessions("Asia/Seoul",
                                   datetime(2026, 7, 29, 2, 0, tzinfo=timezone.utc))
        ny = dashboard.sessions("America/New_York",
                                datetime(2026, 7, 29, 2, 0, tzinfo=timezone.utc))
        s_us = [m for m in seoul["markets"] if m["market"] == "us-stock"][0]
        n_us = [m for m in ny["markets"] if m["market"] == "us-stock"][0]
        self.assertNotEqual(s_us["bands"], n_us["bands"])
        self.assertEqual(n_us["bands"], [[9.5, 16.0]])

    def test_an_unknown_zone_falls_back_rather_than_raising(self):
        s = dashboard.sessions("Mars/Olympus")
        self.assertEqual(s["timezone"], "UTC")
        self.assertTrue(s["markets"])

    def test_the_endpoint_uses_the_members_stored_zone(self):
        """Not a query parameter — one member must not be able to render
        another member's day, and it has to agree with Settings."""
        self._agent(tz="America/New_York")
        got = self._get()["sessions"]
        self.assertEqual(got["timezone"], "America/New_York")

    def test_each_member_gets_their_own_zone_not_the_first_one_found(self):
        """Two members, two clocks. With one member on file, any lookup at
        all appears to work — including one that ignores the caller."""
        self._agent(token="claw_a", email="a@t.io", tz="Asia/Seoul")
        self._agent(token="claw_b", email="b@t.io", tz="America/New_York")
        self.assertEqual(self._get("claw_a")["sessions"]["timezone"], "Asia/Seoul")
        self.assertEqual(self._get("claw_b")["sessions"]["timezone"], "America/New_York")


class Rank(_Base):

    def test_an_agent_with_no_operation_is_unranked(self):
        self._agent()
        self.assertIsNone(self._get()["rank"])

    def _publish(self, agent_id, signal_id):
        conn = database.get_db_connection()
        conn.cursor().execute(
            "INSERT INTO signals (signal_id,agent_id,market,message_type,content,"
            "timestamp,created_at) VALUES (?,?,?,?,?,?,?)",
            (signal_id, agent_id, "crypto", "operation", "op",
             "2026-07-28T00:00:00Z", "2026-07-28T00:00:00Z"))
        conn.commit(); conn.close()

    def test_a_rankable_agent_gets_its_own_position(self):
        aid = self._agent()
        self._publish(aid, "900001")
        got = self._get()["rank"]
        self.assertIsNotNone(got)
        self.assertEqual(got["agent_id"], aid)
        self.assertGreaterEqual(got["rank"], 1)
        self.assertLessEqual(got["rank"], got["of"])

    def test_it_returns_MY_row_not_the_top_row(self):
        """With a single rankable agent, "return the first row" is
        indistinguishable from "find me" — so rank two of them."""
        mine = self._agent(token="claw_a", email="a@t.io")
        other = self._agent(token="claw_b", email="b@t.io")
        self._publish(mine, "900001")
        self._publish(other, "900002")
        a = self._get("claw_a")["rank"]
        b = self._get("claw_b")["rank"]
        self.assertEqual(a["agent_id"], mine)
        self.assertEqual(b["agent_id"], other)
        self.assertEqual(a["of"], 2)
        self.assertNotEqual(a["rank"], b["rank"])
        self.assertEqual({a["rank"], b["rank"]}, {1, 2})


class FailSoft(_Base):

    def test_one_broken_panel_does_not_blank_the_others(self):
        aid = self._agent()
        self._run_with_decisions(aid, decisions=((0.7, "buy", "still here"),))
        with patch.object(dashboard, "sessions", side_effect=RuntimeError("boom")):
            got = self._get()
        self.assertEqual(got["sessions"], {"timezone": "UTC", "markets": []})
        self.assertEqual(len(got["decisions"]), 1)

    def test_every_panel_broken_still_returns_200(self):
        self._agent()
        with patch.object(dashboard, "attention", side_effect=RuntimeError), \
             patch.object(dashboard, "recent_decisions", side_effect=RuntimeError), \
             patch.object(dashboard, "sessions", side_effect=RuntimeError), \
             patch.object(dashboard, "my_rank", side_effect=RuntimeError):
            got = self._get()
        self.assertEqual(got["attention"], [])
        self.assertEqual(got["decisions"], [])
        self.assertIsNone(got["rank"])

    def test_an_unauthenticated_call_is_rejected(self):
        r = self.client.get("/api/dashboard/desk")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
