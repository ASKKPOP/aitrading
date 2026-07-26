"""E2 v1 — hot-issue daemon: hourly watch over every user's RUN symbols.

Three-stage design (2026-07-25): (1) GLOBAL detection — deterministic, zero-
LLM triggers from feeds that already ship (macro event window, crypto psych
shock/regime, a large daily price move); (2) PER-USER verification — the same
hot issue is checked against each affected run's own book: only position
holders are alerted (personalized, direction-aware), flat runs get no alert;
(3) every affected run gets a 'hot_issue' run-event and the E1 classifier
escalates its next cycle to the full analyst pipeline. A per-symbol cooldown
stops re-alerting the same state. Gated by HOT_ISSUE_DAEMON_ENABLED.
"""

from __future__ import annotations

import json
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
import hot_issue_daemon as hid


QUIET = {
    "event": ("market_events.active_event_window", None),
    "psych": ("psych_feed.get_psych_payload", {"available": False}),
    "regime": ("regime.current_regime_state", None),
}


def _flat_candles(price=100.0):
    return [{"close": price}, {"close": price}]


class DaemonBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        for name in ("alpha", "beta"):
            cur.execute("INSERT INTO agents (name, cash) VALUES (?, 100000)", (name,))
        # two agents each running BTC; alpha also runs ETH
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type, status,"
            " config_snapshot_json, start_condition_json, stop_conditions_json,"
            " created_at) VALUES (1,'BTC','crypto','spot','running','{}','{}','{}',"
            "'2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type, status,"
            " config_snapshot_json, start_condition_json, stop_conditions_json,"
            " created_at) VALUES (2,'BTC','crypto','spot','running','{}','{}','{}',"
            "'2026-01-01T00:00:00Z')")
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, market_type, status,"
            " config_snapshot_json, start_condition_json, stop_conditions_json,"
            " created_at) VALUES (1,'ETH','crypto','spot','running','{}','{}','{}',"
            "'2026-01-01T00:00:00Z')")
        # agent 1 HOLDS a BTC position (short); agent 2 is flat
        cur.execute(
            "INSERT INTO positions (agent_id, symbol, market, side, quantity,"
            " entry_price, opened_at, run_id) VALUES (1,'BTC','crypto','short',-1,"
            " 64000,'2026-01-01T00:00:00Z',1)")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _tick(self, overrides=None, candles=None):
        patches = dict(QUIET)
        patches.update(overrides or {})
        ctxs = [patch(t, return_value=v) for t, v in patches.values()]
        ctxs.append(patch("price_fetcher.get_daily_candles",
                          return_value=candles if candles is not None
                          else _flat_candles()))
        sent = []
        ctxs.append(patch("alerts.send_alert",
                          side_effect=lambda *a, **k: sent.append((a, k)) or {}))
        for c in ctxs:
            c.start()
        try:
            out = hid.run_daemon_tick()
        finally:
            for c in ctxs:
                c.stop()
        return out, sent

    def _issues(self):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM hot_issues ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def _events(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM run_events WHERE run_id = ? AND "
                    "event_type = 'hot_issue'", (run_id,))
        rows = [json.loads(r["payload"]) for r in cur.fetchall()]
        conn.close()
        return rows


class DetectionTests(DaemonBase):
    def test_quiet_feeds_produce_no_issues(self):
        out, sent = self._tick()
        self.assertEqual(out["hot"], 0)
        self.assertEqual(self._issues(), [])
        self.assertEqual(sent, [])

    def test_psych_shock_flags_all_crypto_watch_symbols(self):
        out, _ = self._tick(overrides={"psych": (
            "psych_feed.get_psych_payload",
            {"available": True, "shock": [{"symbol": "BTC"}]})})
        self.assertEqual(out["hot"], 2)                    # BTC + ETH
        syms = {(r["market"], r["symbol"]) for r in self._issues()}
        self.assertEqual(syms, {("crypto", "BTC"), ("crypto", "ETH")})
        self.assertTrue(all("psych_shock" in r["triggers_json"]
                            for r in self._issues()))

    def test_price_move_flags_only_the_moving_symbol(self):
        def candles(symbol, market, days=2):
            if symbol == "ETH":
                return [{"close": 100.0}, {"close": 92.0}]   # −8% day
            return _flat_candles()
        patches = dict(QUIET)
        ctxs = [patch(t, return_value=v) for t, v in patches.values()]
        ctxs.append(patch("price_fetcher.get_daily_candles", side_effect=candles))
        ctxs.append(patch("alerts.send_alert", return_value={}))
        for c in ctxs:
            c.start()
        try:
            out = hid.run_daemon_tick()
        finally:
            for c in ctxs:
                c.stop()
        self.assertEqual(out["hot"], 1)
        rows = self._issues()
        self.assertEqual(rows[0]["symbol"], "ETH")
        self.assertIn("price_move", rows[0]["triggers_json"])

    def test_cooldown_suppresses_repeat_issue(self):
        shock = {"psych": ("psych_feed.get_psych_payload",
                           {"available": True, "shock": [{"symbol": "BTC"}]})}
        self._tick(overrides=shock)
        out2, sent2 = self._tick(overrides=shock)
        self.assertEqual(out2["hot"], 0)                   # cooled down
        self.assertEqual(len(self._issues()), 2)           # no new rows
        self.assertEqual(sent2, [])


class PerUserVerificationTests(DaemonBase):
    def test_alert_only_position_holders_events_for_all(self):
        out, sent = self._tick(overrides={"psych": (
            "psych_feed.get_psych_payload",
            {"available": True, "shock": [{"symbol": "BTC"}]})})
        # alert: ONLY agent 1 (holds a BTC short); agent 2 is flat on BTC and
        # nobody holds ETH — one alert total
        self.assertEqual(len([s for s in sent
                              if s[0][0] == 1]), 1)
        self.assertEqual([s for s in sent if s[0][0] == 2], [])
        # the alert wording is personalized to the held side
        args, kwargs = sent[0]
        text = " ".join(str(a) for a in args) + " " + " ".join(
            f"{k}={v}" for k, v in kwargs.items())
        self.assertIn("short", text.lower())
        # run_events: BOTH BTC runs (1: holder, 2: flat) + the ETH run
        self.assertEqual(len(self._events(1)), 1)
        self.assertEqual(len(self._events(2)), 1)
        self.assertEqual(len(self._events(3)), 1)


class E1EscalationTests(DaemonBase):
    def test_classifier_picks_up_recent_hot_issue(self):
        import run_engine
        self._tick(overrides={"psych": (
            "psych_feed.get_psych_payload",
            {"available": True, "shock": [{"symbol": "BTC"}]})})
        run = {"id": 1, "agent_id": 1, "symbol": "BTC", "market": "crypto",
               "market_type": "spot", "stop_conditions_json": "{}"}
        quiet = [patch(t, return_value=v) for t, v in QUIET.values()]
        for c in quiet:
            c.start()
        try:
            out = run_engine._classify_situation(run, {})
        finally:
            for c in quiet:
                c.stop()
        self.assertEqual(out["route"], "full")
        self.assertIn("hot_issue", out["triggers"])

    def test_no_hot_issue_row_no_trigger(self):
        import run_engine
        run = {"id": 1, "agent_id": 1, "symbol": "BTC", "market": "crypto",
               "market_type": "spot", "stop_conditions_json": "{}"}
        quiet = [patch(t, return_value=v) for t, v in QUIET.values()]
        for c in quiet:
            c.start()
        try:
            out = run_engine._classify_situation(run, {})
        finally:
            for c in quiet:
                c.stop()
        self.assertEqual(out["route"], "light")


class I18nAlertTests(DaemonBase):
    """Alerts go through the notifications_i18n catalogue (msg_id + params),
    not pre-rendered English — so each user reads them in their language."""

    SHOCK = {"psych": ("psych_feed.get_psych_payload",
                       {"available": True, "shock": [{"symbol": "BTC"}]})}

    def test_alert_uses_msg_id_params_form(self):
        _, sent = self._tick(overrides=self.SHOCK)
        self.assertEqual(len(sent), 1)
        args, kwargs = sent[0]
        # new form: (agent_id, kind, msg_id, params_dict)
        self.assertEqual(args[2], "hot_issue_position")
        self.assertIsInstance(args[3], dict)
        self.assertEqual(args[3]["side"], "short")
        self.assertIn("symbol", args[3])

    def test_catalogue_entry_renders_in_all_languages(self):
        import notifications_i18n as n18
        variants = n18.MESSAGES.get("hot_issue_position")
        self.assertIsNotNone(variants, "catalogue entry missing")
        params = {"symbol": "BTC", "market": "crypto", "side": "short",
                  "run_id": 7, "triggers": "psych_shock",
                  "verdict": "AGAINST your short (high): shock rally."}
        for lang in ("en", "ko", "ja", "th", "vi"):
            title, body = variants[lang]
            title.format(**params)   # must not raise
            body.format(**params)


class LlmVerifyTests(DaemonBase):
    """Stage 2′: optional personalized LLM verification per material user —
    fail-soft to the deterministic verdict, never called when disabled."""

    SHOCK = {"psych": ("psych_feed.get_psych_payload",
                       {"available": True, "shock": [{"symbol": "BTC"}]})}

    def tearDown(self):
        os.environ.pop("HOT_ISSUE_LLM_VERIFY", None)
        super().tearDown()

    def _tick_llm(self, llm):
        os.environ["HOT_ISSUE_LLM_VERIFY"] = "true"
        from unittest.mock import patch as _p
        calls = []

        def gen(prompt, **kw):
            calls.append(prompt)
            if isinstance(llm, Exception):
                raise llm
            return llm
        with _p("llm_client.generate_text", side_effect=gen):
            out, sent = self._tick(overrides=self.SHOCK)
        return out, sent, calls

    def test_llm_verdict_enriches_alert(self):
        out, sent, calls = self._tick_llm(
            '{"stance": "against", "urgency": "high", '
            '"note": "shock rally squeezes shorts"}')
        self.assertEqual(len(calls), 1)          # one call, only for the holder
        params = sent[0][0][3]
        self.assertIn("AGAINST", params["verdict"])
        self.assertIn("shock rally", params["verdict"])

    def test_llm_failure_falls_back_to_deterministic(self):
        out, sent, calls = self._tick_llm(RuntimeError("llm down"))
        self.assertEqual(len(sent), 1)           # alert still goes out
        self.assertIn("position", sent[0][0][3]["verdict"].lower())

    def test_disabled_flag_never_calls_llm(self):
        os.environ.pop("HOT_ISSUE_LLM_VERIFY", None)
        from unittest.mock import patch as _p
        calls = []
        with _p("llm_client.generate_text",
                side_effect=lambda *a, **k: calls.append(1)):
            _, sent = self._tick(overrides=self.SHOCK)
        self.assertEqual(calls, [])
        self.assertEqual(len(sent), 1)


class GateTests(unittest.TestCase):
    def test_env_gate_default_off(self):
        os.environ.pop("HOT_ISSUE_DAEMON_ENABLED", None)
        self.assertFalse(hid.daemon_enabled())
        os.environ["HOT_ISSUE_DAEMON_ENABLED"] = "true"
        try:
            self.assertTrue(hid.daemon_enabled())
        finally:
            os.environ.pop("HOT_ISSUE_DAEMON_ENABLED", None)


if __name__ == "__main__":
    unittest.main()
