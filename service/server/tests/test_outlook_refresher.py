"""Plan 26 Phase 2 — outlook freshness sweeper (cold path).

Due logic per market × session × slot state, cadence floors (30/30/30/60),
idempotence (two ticks, one event), unbound/disabled no-ops, freshness
respect, the payload contract (§3.1 shape + basis record, source 'sweeper',
NaN scrubbed, narrative non-empty), the pure algo_candidate rules, and the
algo ⇄ LLM discussion (model verdict recorded; any LLM failure → the algo
candidate becomes the plan). No network — llm_client.generate_text is
patched in every test (the known failure smell is sibling tests breaking
because a live call slipped through).
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import outlook_refresher as orf

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Wed 2026-08-12 15:00 UTC = 11:00 ET — nyse open (not a holiday), forex
# open, cme open, crypto always open.
OPEN_NOW = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
# Sat 2026-08-15 12:00 UTC — nyse, forex (24x5) and cme all closed;
# crypto (24x7) still open.
CLOSED_NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


class OutlookRefresherBase(unittest.TestCase):
    def setUp(self):
        # Env hygiene: the flag leaks across pytest otherwise.
        self._prior_flag = os.environ.get("OUTLOOK_ENABLED")
        os.environ["OUTLOOK_ENABLED"] = "1"
        # NO LIVE LLM CALLS EVER: default every test to the unconfigured
        # path (generate_text → None ⇒ algo fallback). LLM-path tests
        # override the return_value on this same mock.
        self._llm = patch("llm_client.generate_text", return_value=None)
        self.llm_mock = self._llm.start()
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('o@x.com', 'x', '2026-01-01T00:00:00Z')")
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('outlook-agent', 'oth1', 100000, ?, "
            "'2026-01-01T00:00:00Z')", (user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        self._llm.stop()
        if self._prior_flag is None:
            os.environ.pop("OUTLOOK_ENABLED", None)
        else:
            os.environ["OUTLOOK_ENABLED"] = self._prior_flag
        self.tmp.cleanup()

    # ── fixture builders ──────────────────────────────────────────────────

    def _fleet(self, status="active"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fleets (agent_id, status, n_runs, total_budget_usd, "
            "created_at) VALUES (?, ?, 3, 3000, '2026-01-01T00:00:00Z')",
            (self.agent_id, status))
        fleet_id = cur.lastrowid
        conn.commit()
        conn.close()
        return fleet_id

    def _run(self, symbol="FIL", market="crypto", status="running",
             thesis=None, stop_conditions=None):
        base_thesis = {
            "symbol": symbol, "market": market, "direction": "short",
            "entry_ref_price": 3.06, "expected_move_pct": 7.2,
            "invalidation": "daily close above 3.47",
            "horizon_hours": 18.0,
        }
        if thesis is not None:
            base_thesis.update(thesis)
        cfg = {"thesis": base_thesis}
        stops = stop_conditions if stop_conditions is not None else {
            "max_loss_usd": 50.0,
            "price_cross": {"direction": "above", "price": 3.47},
        }
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trading_runs (agent_id, symbol, market, status, "
            "config_snapshot_json, stop_conditions_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')",
            (self.agent_id, symbol, market, status,
             json.dumps(cfg), json.dumps(stops)))
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def _slot(self, fleet_id, run_id, slot_index=0, state="active"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fleet_slots (fleet_id, slot_index, "
            "original_allocation_usd, state, current_run_id, updated_at) "
            "VALUES (?, ?, 1000, ?, ?, '2026-01-01T00:00:00Z')",
            (fleet_id, slot_index, state, run_id))
        conn.commit()
        conn.close()

    def _seed_outlook(self, run_id, ts_dt):
        """Insert a prior outlook event the way the emitter would: next seq,
        and last_event_seq bumped so a later emit never collides."""
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE trading_runs SET last_event_seq = "
            "COALESCE(last_event_seq, 0) + 1 WHERE id = ?", (run_id,))
        cur.execute("SELECT last_event_seq FROM trading_runs WHERE id = ?",
                    (run_id,))
        seq = int(cur.fetchone()["last_event_seq"])
        cur.execute(
            "INSERT INTO run_events (run_id, seq, event_type, ts, payload) "
            "VALUES (?, ?, 'outlook', ?, '{}')",
            (run_id, seq, ts_dt.strftime(TS_FMT)))
        conn.commit()
        conn.close()

    def _outlook_events(self, run_id):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM run_events WHERE run_id = ? AND "
                    "event_type = 'outlook' ORDER BY ts", (run_id,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def _bound_slot(self, market="crypto", run_status="running",
                    slot_state="active", **run_kw):
        fleet_id = self._fleet()
        run_id = self._run(market=market, status=run_status, **run_kw)
        self._slot(fleet_id, run_id, state=slot_state)
        return run_id


class CadenceFloorTests(OutlookRefresherBase):
    def test_floor_dict_values(self):
        self.assertEqual(orf.OUTLOOK_CADENCE_MIN,
                         {"us-stock": 30, "crypto": 30, "forex": 30})
        self.assertEqual(orf.OUTLOOK_CADENCE_DEFAULT_MIN, 60)
        for market, floor in (("us-stock", 30), ("crypto", 30),
                              ("forex", 30), ("futures", 60),
                              ("prediction", 60)):
            self.assertEqual(orf.cadence_floor_min(market), floor, market)

    def test_futures_respects_60_min_floor(self):
        """A 45-min-old outlook is stale for the 30-min markets but still
        fresh for futures (60-min floor)."""
        run_id = self._bound_slot(market="futures", run_status="paused")
        self._seed_outlook(run_id, CLOSED_NOW - timedelta(minutes=45))
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 0)
        # ... and past the 60-min floor it emits.
        result = orf.outlook_refresher_tick(
            now=CLOSED_NOW + timedelta(minutes=20))
        self.assertEqual(result["emitted"], 1)

    def test_us_stock_45_min_stale_emits_when_closed(self):
        run_id = self._bound_slot(market="us-stock", run_status="running")
        self._seed_outlook(run_id, CLOSED_NOW - timedelta(minutes=45))
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 1)
        self.assertEqual(len(self._outlook_events(run_id)), 2)


class DueLogicTests(OutlookRefresherBase):
    def test_closed_session_emits_for_session_markets(self):
        """us-stock / forex / futures closed on Saturday: all due even with
        a running run in an active slot (no prior outlook)."""
        for market in ("us-stock", "forex", "futures"):
            with self.subTest(market=market):
                run_id = self._bound_slot(market=market,
                                          run_status="running")
                orf.outlook_refresher_tick(now=CLOSED_NOW)
                self.assertEqual(len(self._outlook_events(run_id)), 1)

    def test_open_cycling_run_is_never_double_written(self):
        """Open session + running run + active slot: the cycle owns the
        slot — no sweeper event even with no outlook at all."""
        for market in ("us-stock", "forex", "futures", "crypto"):
            with self.subTest(market=market):
                run_id = self._bound_slot(market=market,
                                          run_status="running")
                result = orf.outlook_refresher_tick(now=OPEN_NOW)
                self.assertEqual(result["emitted"], 0)
                self.assertEqual(self._outlook_events(run_id), [])

    def test_open_market_idle_run_emits(self):
        """Crypto never closes, so its cold path is run status: a paused
        run does not cycle and gets a standing outlook."""
        run_id = self._bound_slot(market="crypto", run_status="paused")
        orf.outlook_refresher_tick(now=OPEN_NOW)
        self.assertEqual(len(self._outlook_events(run_id)), 1)

    def test_stopped_run_is_never_swept(self):
        """A stopped run is terminal — no desk cycle will ever read a
        standing outlook for it, so the sweeper must not spend an LLM
        call on one (measured on prod: 19.8% of outlook writes went to
        stopped runs, ~13.8 wasted calls/hour)."""
        for market, now in (("crypto", OPEN_NOW), ("crypto", CLOSED_NOW),
                            ("us-stock", CLOSED_NOW)):
            with self.subTest(market=market, now=now):
                run_id = self._bound_slot(market=market,
                                          run_status="stopped")
                result = orf.outlook_refresher_tick(now=now)
                self.assertEqual(result["emitted"], 0)
                self.assertEqual(self._outlook_events(run_id), [])

    def test_open_market_idle_slot_states_emit(self):
        """waiting/dormant slots do not cycle even with a running run."""
        for state in ("waiting", "dormant"):
            with self.subTest(state=state):
                run_id = self._bound_slot(market="crypto",
                                          run_status="running",
                                          slot_state=state)
                orf.outlook_refresher_tick(now=OPEN_NOW)
                self.assertEqual(len(self._outlook_events(run_id)), 1)

    def test_inactive_fleet_is_skipped(self):
        fleet_id = self._fleet(status="paused")
        run_id = self._run(market="us-stock", status="running")
        self._slot(fleet_id, run_id)
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["checked"], 0)
        self.assertEqual(self._outlook_events(run_id), [])


class IdempotenceAndFreshnessTests(OutlookRefresherBase):
    def test_two_consecutive_ticks_emit_one_event(self):
        run_id = self._bound_slot(market="us-stock", run_status="running")
        first = orf.outlook_refresher_tick(now=CLOSED_NOW)
        second = orf.outlook_refresher_tick(
            now=CLOSED_NOW + timedelta(minutes=5))
        self.assertEqual(first["emitted"], 1)
        self.assertEqual(second["emitted"], 0)
        self.assertEqual(len(self._outlook_events(run_id)), 1)

    def test_fresh_outlook_blocks_emit_even_when_closed(self):
        """An outlook younger than the floor → no emit, closed session or
        not (the floor is a floor, not a trigger)."""
        run_id = self._bound_slot(market="us-stock", run_status="running")
        self._seed_outlook(run_id, CLOSED_NOW - timedelta(minutes=20))
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 0)
        self.assertEqual(len(self._outlook_events(run_id)), 1)


class NoOpTests(OutlookRefresherBase):
    def test_unbound_slot_gets_no_event(self):
        fleet_id = self._fleet()
        self._slot(fleet_id, run_id=None)
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result, {"enabled": True, "checked": 0,
                                  "emitted": 0})

    def test_flag_off_is_a_no_op(self):
        run_id = self._bound_slot(market="us-stock", run_status="running")
        os.environ["OUTLOOK_ENABLED"] = "0"
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result, {"enabled": False, "checked": 0,
                                  "emitted": 0})
        self.assertEqual(self._outlook_events(run_id), [])

    def test_unset_flag_defaults_off(self):
        """The pre-flip production state: OUTLOOK_ENABLED absent entirely.

        `test_flag_off_is_a_no_op` sets the var to "0" and so never exercises
        the DEFAULT. The sweeper writes run_events rows the desk reads back as
        its standing plan, so a default that read ON would start the loop on
        every box that never set the var — the kill switch has to hold when
        the switch is missing, not only when it is set to off."""
        run_id = self._bound_slot(market="us-stock", run_status="running")
        os.environ.pop("OUTLOOK_ENABLED", None)
        self.assertFalse(orf.outlook_enabled())
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result, {"enabled": False, "checked": 0,
                                  "emitted": 0})
        self.assertEqual(self._outlook_events(run_id), [])

    def test_stale_run_binding_is_skipped(self):
        """A current_run_id pointing at a deleted run must not crash the
        sweep or emit anything."""
        fleet_id = self._fleet()
        self._slot(fleet_id, run_id=999999)
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 0)


class PayloadContractTests(OutlookRefresherBase):
    CONTRACT_KEYS = {"cycle", "symbol", "market", "source", "bias", "entry",
                     "exit", "invalidation", "horizon_hours", "narrative",
                     "basis"}
    ALGO_KEYS = {"entry_low", "entry_high", "target_px", "stop_ref_px",
                 "time_exit"}

    def _emitted_payload(self, run_id):
        events = self._outlook_events(run_id)
        self.assertEqual(len(events), 1)
        return json.loads(events[0]["payload"])

    def test_fallback_payload_matches_contract(self):
        """LLM down (mock returns None): the algo candidate becomes the
        plan, verdict 'algo_fallback', discussion None."""
        run_id = self._bound_slot(market="us-stock", run_status="running",
                                  symbol="ORCL",
                                  thesis={"symbol": "ORCL",
                                          "market": "us-stock",
                                          "direction": "long",
                                          "entry_ref_price": 100.0,
                                          "expected_move_pct": 5.0})
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        payload = self._emitted_payload(run_id)
        self.assertEqual(set(payload.keys()), self.CONTRACT_KEYS)
        self.assertIsNone(payload["cycle"])
        self.assertEqual(payload["source"], "sweeper")
        self.assertEqual(payload["symbol"], "ORCL")
        self.assertEqual(payload["market"], "us-stock")
        self.assertEqual(payload["bias"], "long")
        # Algo levels: target_pct=5 → target 105, pullback band [98.75, 100].
        self.assertEqual(payload["entry"]["kind"], "zone")
        self.assertAlmostEqual(payload["entry"]["low"], 98.75)
        self.assertAlmostEqual(payload["entry"]["high"], 100.0)
        self.assertAlmostEqual(payload["exit"]["target_px"], 105.0)
        self.assertAlmostEqual(payload["exit"]["stop_ref_px"], 3.47)
        self.assertEqual(payload["exit"]["time_exit"],
                         (CLOSED_NOW + timedelta(hours=18)).strftime(TS_FMT))
        self.assertEqual(payload["invalidation"], "daily close above 3.47")
        self.assertAlmostEqual(payload["horizon_hours"], 18.0)
        self.assertTrue(payload["narrative"])
        self.assertIn("Market closed", payload["narrative"])
        # The basis record: both authors, algo_fallback verdict.
        basis = payload["basis"]
        self.assertEqual(set(basis.keys()), {"algo", "verdict", "discussion"})
        self.assertEqual(basis["verdict"], "algo_fallback")
        self.assertIsNone(basis["discussion"])
        self.assertEqual(set(basis["algo"].keys()), self.ALGO_KEYS)
        self.assertAlmostEqual(basis["algo"]["target_px"], 105.0)
        # Short bias flips: target below ref, entry band above.
        run2 = self._bound_slot(market="forex", run_status="running",
                                thesis={"direction": "short",
                                        "entry_ref_price": 100.0,
                                        "expected_move_pct": 5.0})
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        payload2 = self._emitted_payload(run2)
        self.assertAlmostEqual(payload2["exit"]["target_px"], 95.0)
        self.assertAlmostEqual(payload2["entry"]["low"], 100.0)
        self.assertAlmostEqual(payload2["entry"]["high"], 101.25)

    def test_numerics_scrubbed_and_json_safe(self):
        """NaN/inf thesis numbers must land as null — NaN in a persisted
        JSON column permanently 500s every read."""
        run_id = self._bound_slot(
            market="us-stock", run_status="running",
            thesis={"entry_ref_price": float("nan"),
                    "expected_move_pct": float("inf"),
                    "horizon_hours": float("-inf")},
            stop_conditions={"price_cross": {"price": float("nan")}})
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        payload = self._emitted_payload(run_id)
        self.assertEqual(payload["entry"], {"kind": "none", "low": None,
                                            "high": None, "trigger": None})
        self.assertIsNone(payload["exit"]["target_px"])
        self.assertIsNone(payload["exit"]["stop_ref_px"])
        self.assertIsNone(payload["horizon_hours"])
        self.assertIsNone(payload["basis"]["algo"]["target_px"])
        self.assertIsNone(payload["basis"]["algo"]["stop_ref_px"])
        self.assertTrue(payload["narrative"])
        # The stored row must round-trip strictly (no NaN/Infinity tokens).
        json.dumps(payload, allow_nan=False)
        for row in self._outlook_events(run_id):
            reparsed = json.loads(row["payload"])
            for v in (reparsed["horizon_hours"],
                      reparsed["exit"]["target_px"]):
                self.assertFalse(isinstance(v, float)
                                 and not math.isfinite(v))

    def test_empty_thesis_still_yields_valid_payload(self):
        run_id = self._bound_slot(
            market="us-stock", run_status="running",
            thesis={"direction": None, "entry_ref_price": None,
                    "expected_move_pct": None, "invalidation": None,
                    "horizon_hours": None},
            stop_conditions={})
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        payload = self._emitted_payload(run_id)
        self.assertEqual(set(payload.keys()), self.CONTRACT_KEYS)
        self.assertEqual(payload["bias"], "flat")
        self.assertEqual(payload["entry"]["kind"], "none")
        self.assertTrue(payload["narrative"])

    def test_sweeper_never_touches_stop_conditions_or_positions(self):
        """Hard guard: the sweep writes run_events rows only."""
        run_id = self._bound_slot(market="us-stock", run_status="running")
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT stop_conditions_json FROM trading_runs "
                    "WHERE id = ?", (run_id,))
        before = cur.fetchone()["stop_conditions_json"]
        cur.execute("SELECT COUNT(*) AS n FROM positions")
        pos_before = cur.fetchone()["n"]
        conn.close()
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT stop_conditions_json FROM trading_runs "
                    "WHERE id = ?", (run_id,))
        self.assertEqual(cur.fetchone()["stop_conditions_json"], before)
        cur.execute("SELECT COUNT(*) AS n FROM positions")
        self.assertEqual(cur.fetchone()["n"], pos_before)
        conn.close()


class AlgoCandidateTests(unittest.TestCase):
    """algo_candidate is pure — no DB fixture needed."""

    NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

    def test_long_short_mirroring(self):
        long_c = orf.algo_candidate("long", 100.0, 8.0, None, 90.0, self.NOW)
        short_c = orf.algo_candidate("short", 100.0, 8.0, None, 110.0,
                                     self.NOW)
        self.assertAlmostEqual(long_c["target_px"], 108.0)
        self.assertAlmostEqual(long_c["entry_low"], 98.0)   # ref*(1-0.25*8%)
        self.assertAlmostEqual(long_c["entry_high"], 100.0)
        self.assertAlmostEqual(short_c["target_px"], 92.0)
        self.assertAlmostEqual(short_c["entry_low"], 100.0)
        self.assertAlmostEqual(short_c["entry_high"], 102.0)
        self.assertAlmostEqual(long_c["stop_ref_px"], 90.0)
        self.assertAlmostEqual(short_c["stop_ref_px"], 110.0)

    def test_fee_hurdle_floor(self):
        """expected_move 1% is under the 2.4% flat-fee breakeven — the
        target is floored at the hurdle, never self-refuting on paper."""
        c = orf.algo_candidate("long", 100.0, 1.0, None, None, self.NOW)
        self.assertAlmostEqual(c["target_px"], 102.4)
        self.assertAlmostEqual(c["entry_low"], 99.4)  # 0.25*2.4% pullback
        # Missing move → same floor.
        c2 = orf.algo_candidate("long", 100.0, None, None, None, self.NOW)
        self.assertAlmostEqual(c2["target_px"], 102.4)

    def test_missing_inputs_yield_nones(self):
        no_ref = orf.algo_candidate("long", None, 5.0, 18.0, 90.0, self.NOW)
        for key in ("entry_low", "entry_high", "target_px"):
            self.assertIsNone(no_ref[key])
        self.assertAlmostEqual(no_ref["stop_ref_px"], 90.0)
        self.assertEqual(no_ref["time_exit"],
                         (self.NOW + timedelta(hours=18)).strftime(TS_FMT))
        no_dir = orf.algo_candidate(None, 100.0, 5.0, None, None, self.NOW)
        for key in ("entry_low", "entry_high", "target_px", "time_exit"):
            self.assertIsNone(no_dir[key])
        flat = orf.algo_candidate("flat", 100.0, 5.0, None, None, self.NOW)
        self.assertIsNone(flat["target_px"])
        no_now = orf.algo_candidate("long", 100.0, 5.0, 18.0, None, None)
        self.assertIsNone(no_now["time_exit"])

    def test_nan_inputs_scrubbed(self):
        c = orf.algo_candidate("long", float("nan"), float("inf"),
                               float("-inf"), float("nan"), self.NOW)
        self.assertEqual(c, {"entry_low": None, "entry_high": None,
                             "target_px": None, "stop_ref_px": None,
                             "time_exit": None})


class DiscussionTests(OutlookRefresherBase):
    """The algo ⇄ LLM discussion: verdict recorded on success, algo
    fallback on any failure. generate_text is mocked in the base class."""

    LLM_JSON = json.dumps({
        "bias": "short",
        "entry": {"kind": "zone", "low": 3.10, "high": 3.18,
                  "trigger": None},
        "exit": {"target_px": 2.79, "stop_ref_px": 9.99,
                 "time_exit": "2026-08-16T14:00:00Z"},
        "invalidation": "daily close above 3.47 kills the short",
        "horizon_hours": 20,
        "verdict": "adjusted",
        "discussion": "Candidate target inside chop; moved cover below "
                      "2.80 support retest.",
        "narrative": "Hold the short; cover into 2.79. Invalidation: "
                     "daily close above 3.47.",
    })

    def _emitted_payload(self, run_id):
        events = self._outlook_events(run_id)
        self.assertEqual(len(events), 1)
        return json.loads(events[0]["payload"])

    def test_llm_success_records_verdict_and_uses_model_levels(self):
        self.llm_mock.return_value = self.LLM_JSON
        run_id = self._bound_slot(market="us-stock", run_status="running")
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        payload = self._emitted_payload(run_id)
        self.assertEqual(payload["bias"], "short")
        self.assertAlmostEqual(payload["entry"]["low"], 3.10)
        self.assertAlmostEqual(payload["exit"]["target_px"], 2.79)
        self.assertEqual(payload["exit"]["time_exit"],
                         "2026-08-16T14:00:00Z")
        # The live stop is ECHOED, never the model's number (9.99).
        self.assertAlmostEqual(payload["exit"]["stop_ref_px"], 3.47)
        self.assertAlmostEqual(payload["horizon_hours"], 20)
        self.assertEqual(payload["narrative"],
                         json.loads(self.LLM_JSON)["narrative"])
        basis = payload["basis"]
        self.assertEqual(basis["verdict"], "adjusted")
        self.assertIn("Candidate target", basis["discussion"])
        # Both authors on record: the algo candidate rides along verbatim.
        self.assertAlmostEqual(basis["algo"]["target_px"],
                               round(3.06 * (1 - 0.072), 8))
        # The prompt carried the candidate and the discussion instruction.
        prompt = self.llm_mock.call_args[0][0]
        self.assertIn("algorithmic candidate plan", prompt)
        self.assertIn(json.dumps(orf.algo_candidate(
            "short", 3.06, 7.2, 18.0, 3.47, CLOSED_NOW)), prompt)

    def test_junk_verdict_defaults_to_adjusted(self):
        data = json.loads(self.LLM_JSON)
        data["verdict"] = "totally-new-plan"
        del data["discussion"]
        self.llm_mock.return_value = json.dumps(data)
        run_id = self._bound_slot(market="us-stock", run_status="running")
        orf.outlook_refresher_tick(now=CLOSED_NOW)
        basis = self._emitted_payload(run_id)["basis"]
        self.assertEqual(basis["verdict"], "adjusted")
        self.assertIsNone(basis["discussion"])

    def test_unparseable_llm_response_falls_back_to_algo(self):
        self.llm_mock.return_value = "sorry, I cannot produce JSON today"
        run_id = self._bound_slot(market="us-stock", run_status="running")
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 1)
        payload = self._emitted_payload(run_id)
        self.assertEqual(payload["basis"]["verdict"], "algo_fallback")
        # Algo levels became the plan (short ref 3.06, move 7.2).
        self.assertAlmostEqual(payload["exit"]["target_px"],
                               round(3.06 * (1 - 0.072), 8))

    def test_llm_raising_falls_back_to_algo(self):
        self.llm_mock.side_effect = RuntimeError("provider exploded")
        run_id = self._bound_slot(market="us-stock", run_status="running")
        result = orf.outlook_refresher_tick(now=CLOSED_NOW)
        self.assertEqual(result["emitted"], 1)
        payload = self._emitted_payload(run_id)
        self.assertEqual(payload["basis"]["verdict"], "algo_fallback")
        self.assertTrue(payload["narrative"])


class RegistryTests(OutlookRefresherBase):
    def test_registered_with_settlement_role(self):
        import tasks
        self.assertIn("outlook_refresher", tasks.BACKGROUND_TASK_REGISTRY)
        self.assertEqual(tasks.BACKGROUND_TASK_ROLES["outlook_refresher"],
                         "settlement")


if __name__ == "__main__":
    unittest.main()
