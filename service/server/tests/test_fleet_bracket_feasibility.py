"""R15 build-time bracket-feasibility gate (2026-08-14).

The composer built runs whose loss rail (retire_drawdown_frac x max_loss)
could not carry a 1-sigma stop on even the minimum meaningful position, and
the R10-taught desks refused them at cycle 1 — ~18 zero-P&L quick refusals
in one day across 3 fleets (prod runs 1205/1206/1211/1213/1214/1235: FDX,
INTU, COP, NOW). Arithmetic knowable at build time belongs at build time.

Calibration fixtures below are the PROD numbers, not invented ones:
  FDX f31 (run 1206):  max_bet 59.43, max_loss 1.78, sigma 1.4024%,
                       last 339.35 -> rail 1.25 < half-share stop 2.38.
  PLTR f31 (run 1177): max_bet 371.75, max_loss 11.15, sigma 8.3412%,
                       last 175.25 -> rail 7.81 >= half-share stop 7.31 —
                       the tightest entry that actually traded that day.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fleet_planner as fp


def _thesis(market="us-stock", sigma=None, last=None, symbol="FDX"):
    t = {"symbol": symbol, "market": market, "direction": "long",
         "confidence": 0.7, "expected_move_pct": 3.0, "horizon_hours": 48}
    factors = {}
    if sigma is not None:
        factors["vol_daily_pct"] = sigma
    if last is not None:
        factors["last"] = last
    if factors:
        t["factor_scores_json"] = json.dumps({"factors": factors})
    return t


def _settings(max_bet, max_loss, market="us-stock", leverage=1.0,
              feedback=True):
    return {"market": market, "max_bet_usd": max_bet, "leverage": leverage,
            "feedback": feedback,
            "stop_conditions": {"max_loss_usd": max_loss}}


class BracketPredicateTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("FLEET_BRACKET_FEASIBILITY", None)

    def test_prod_fdx_f31_is_dropped_with_the_numbers(self):
        """Run 1206 verbatim: rail 0.7 x 1.78 = 1.25, half-share 1-sigma
        stop 0.5 x 339.35 x 1.4024% = 2.38 — the desk could never author an
        honest bracket, so the run must never be built."""
        why = fp.bracket_infeasible(
            _thesis(sigma=1.4024, last=339.35),
            _settings(max_bet=59.43, max_loss=1.78))
        self.assertIsNotNone(why)
        self.assertIn("bracket_infeasible", why)
        # the honest event carries the arithmetic, not just a verdict
        self.assertIn("sigma_daily_pct=1.402", why)
        self.assertIn("min_stop_usd=2.38", why)
        self.assertIn("loss_rail_usd=1.25", why)

    def test_prod_intu_f33_is_dropped(self):
        """Run 1213: rail 0.69, half-share stop 0.5 x 358.29 x 2.9856% =
        5.35 — refused 9 straight cycles on prod."""
        self.assertIsNotNone(fp.bracket_infeasible(
            _thesis(sigma=2.9856, last=358.29, symbol="INTU"),
            _settings(max_bet=49.5, max_loss=0.99)))

    def test_prod_pltr_the_tightest_traded_entry_passes(self):
        """Run 1177 traded 4 orders; its rail 7.81 supports the half-share
        stop 7.31 with 6% to spare. The gate must sit BELOW every accepted
        entry — dropping a tradeable candidate is starving, not honesty."""
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(sigma=8.3412, last=175.25, symbol="PLTR"),
            _settings(max_bet=371.75, max_loss=11.15)))

    def test_prod_orcl_f31_passes(self):
        """Run 1164 (traded): rail 3.78 vs half-share stop 2.80."""
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(sigma=3.5452, last=157.85, symbol="ORCL"),
            _settings(max_bet=180.09, max_loss=5.40)))

    def test_non_usstock_uses_the_dust_floor_times_leverage(self):
        """Crypto/forex have no share unit: min size is the engine's own
        dust floor (max($10, 2% max_bet) margin) x leverage. SOLUSDT run
        1175 (traded): rail 19.6 vs 42-notional 1-sigma stop 0.58."""
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(market="crypto", sigma=1.3849, symbol="SOLUSDT"),
            _settings(max_bet=700.0, max_loss=28.0, market="crypto",
                      leverage=3.0)))
        # …and a micro budget on a violent coin IS infeasible: rail
        # 0.7 x 0.30 = 0.21 < $10-margin x 3 lev x 25%/day = 7.50.
        why = fp.bracket_infeasible(
            _thesis(market="crypto", sigma=25.0, symbol="MEME"),
            _settings(max_bet=15.0, max_loss=0.30, market="crypto",
                      leverage=3.0))
        self.assertIsNotNone(why)
        self.assertIn("bracket_infeasible", why)

    def test_missing_sigma_passes_through(self):
        """Fail-open on data absence — the gate must never starve fleets on
        missing measurement; the desk remains the judge."""
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(sigma=None, last=339.35),
            _settings(max_bet=59.43, max_loss=1.78)))
        # unreadable factors likewise
        broken = _thesis()
        broken["factor_scores_json"] = "{not json"
        self.assertIsNone(fp.bracket_infeasible(
            broken, _settings(max_bet=59.43, max_loss=1.78)))

    def test_missing_last_price_falls_back_to_dust_floor(self):
        """us-stock with sigma but no last price: the half-share term is
        unavailable, the dust-floor term still applies (here it passes)."""
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(sigma=1.4024, last=None),
            _settings(max_bet=59.43, max_loss=1.78)))

    def test_kill_switch_restores_old_behavior(self):
        os.environ["FLEET_BRACKET_FEASIBILITY"] = "0"
        self.assertIsNone(fp.bracket_infeasible(
            _thesis(sigma=1.4024, last=339.35),
            _settings(max_bet=59.43, max_loss=1.78)))

    def test_non_feedback_settings_get_the_full_rail(self):
        """Mirrors run_engine._brake_room_usd: the drawdown brake exists
        only for feedback runs; without it the rail is the full max_loss.
        1.78 >= 0.79 x 1.78? — pick numbers that flip across the 0.70."""
        thesis = _thesis(sigma=1.0, last=300.0)          # half-share stop 1.50
        s = _settings(max_bet=59.43, max_loss=1.78)      # rail 1.25 < 1.50
        self.assertIsNotNone(fp.bracket_infeasible(thesis, s))
        s_nofb = _settings(max_bet=59.43, max_loss=1.78, feedback=False)
        self.assertIsNone(fp.bracket_infeasible(thesis, s_nofb))  # rail 1.78


class ProbationScalingTests(unittest.TestCase):
    """#416: probation multiplies max_bet (and therefore max_loss) by 0.33
    inside compose_run_settings. The gate takes the COMPOSED settings, so
    the condition must price the SCALED rail — prod fleet 31's refusals
    were exactly probation-scaled builds."""

    def tearDown(self):
        os.environ.pop("FLEET_BRACKET_FEASIBILITY", None)

    def _compose(self, frac):
        thesis = _thesis(sigma=1.4024, last=339.35)
        with patch.object(fp, "_probation_size_frac", return_value=frac), \
             patch.object(fp, "_market_confidence_ceiling", return_value=None), \
             patch.object(fp, "_exposure_cap_usd", return_value=0.0):
            return thesis, fp.compose_run_settings(
                thesis, 400.21, {"risk_appetite": "aggressive", "lang": "en",
                                 "agent_id": 1})

    def test_probation_scaled_rail_is_the_one_judged(self):
        """400.21 x 0.45 x 0.33 = 59.43 max_bet -> max_loss 1.78, rail
        1.25 < 2.38: infeasible — the prod fleet 31 build verbatim."""
        thesis, settings = self._compose(0.33)
        self.assertAlmostEqual(settings["max_bet_usd"], 59.43, places=2)
        why = fp.bracket_infeasible(thesis, settings)
        self.assertIsNotNone(why)
        self.assertIn("loss_rail_usd=1.25", why)

    def test_full_size_same_slot_is_feasible(self):
        """Probation lifted (frac 1.0): max_bet 180.09, max_loss 5.40,
        rail 3.78 >= 2.38 — the same symbol+budget builds. The gate keys
        on the scaled numbers, not the pre-probation ones."""
        thesis, settings = self._compose(1.0)
        self.assertAlmostEqual(settings["max_bet_usd"], 180.09, places=2)
        self.assertIsNone(fp.bracket_infeasible(thesis, settings))


class DBTestBase(unittest.TestCase):
    """_do_build drops an infeasible candidate with the honest event, marks
    it skipped, and leaves the slot for the normal replacement flow — the
    fleet still activates (partial) on the feasible remainder."""

    def setUp(self):
        import tempfile
        import database
        self.database = database
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES ('h@x.com', 'x', '2026-01-01T00:00:00Z')")
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO agents (name, token_hash, cash, user_id, created_at) "
            "VALUES ('fleet-agent', 'th1', 100000, ?, '2026-01-01T00:00:00Z')",
            (user_id,))
        self.agent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()

    def tearDown(self):
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
        os.environ.pop("FLEET_BRACKET_FEASIBILITY", None)
        self.plan.stop()
        self.probe.stop()
        self.tmp.cleanup()

    def _seed_batch(self):
        import symbol_research as sr

        def _candles(n=60, drift=0.8, volume=5_000_000):
            out, price = [], 100.0
            for i in range(n):
                price *= 1 + drift / 100.0
                out.append({"ts": i, "open": price, "high": price,
                            "low": price, "close": price, "volume": volume})
            return out

        universe = [{"symbol": s, "market": "crypto"}
                    for s in ("AAA", "BBB", "CCC", "DDD")]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None):
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())

class BuildWiringTests(DBTestBase):
    """_do_build drops an infeasible candidate with the honest event, marks
    it skipped, and leaves the slot for the normal replacement flow — the
    fleet still activates (partial) on the feasible remainder."""

    def test_infeasible_candidate_skipped_fleet_activates_partial(self):
        self._seed_batch()
        fleet_id = fp.create_fleet(self.agent_id, 2, 1000.0)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        # poison ONE selected candidate: violent daily sigma vs a tiny slot
        conn = self.database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT thesis_key FROM fleet_candidates WHERE "
                    "fleet_id = ? AND state = 'selected' "
                    "ORDER BY slot_index LIMIT 1", (fleet_id,))
        key = cur.fetchone()["thesis_key"]
        batch_id, market, symbol = key.rsplit(":", 2)
        cur.execute(
            "UPDATE research_theses SET factor_scores_json = ? WHERE "
            "batch_id = ? AND market = ? AND symbol = ?",
            (json.dumps({"factors": {"vol_daily_pct": 60.0}}),
             batch_id, market, symbol))
        conn.commit()
        conn.close()
        fp._do_build(fp.get_fleet(fleet_id))
        # the poisoned candidate never became a run…
        members = fp.list_members(fleet_id)
        self.assertNotIn(symbol, {m["symbol"] for m in members})
        self.assertEqual(len(members), 1)
        # …the fleet still activates partial (slot left to the E3 backfill)
        fleet = fp.get_fleet(fleet_id)
        self.assertEqual(fleet["status"], fp.STATUS_ACTIVE)
        self.assertTrue((fleet["status_reason"] or "").startswith("partial:"))
        # …and the journal carries the honest arithmetic
        conn = self.database.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT payload FROM fleet_events WHERE fleet_id = ? "
                    "AND event_type = 'candidate_skipped'", (fleet_id,))
        reasons = [json.loads(r["payload"]).get("reason") or ""
                   for r in cur.fetchall()]
        cur.execute("SELECT state FROM fleet_candidates WHERE fleet_id = ? "
                    "AND thesis_key = ?", (fleet_id, key))
        cand_state = cur.fetchone()["state"]
        conn.close()
        bracket = [r for r in reasons if r.startswith("bracket_infeasible:")]
        self.assertEqual(len(bracket), 1)
        self.assertIn("sigma_daily_pct=60.000", bracket[0])
        self.assertIn("loss_rail_usd=", bracket[0])
        self.assertIn("min_stop_usd=", bracket[0])
        self.assertEqual(cand_state, "skipped")


class ReplacementParityTests(DBTestBase):
    """The fee gate was once missed on the replacement path and shipped
    three permanently-blocked runs. _try_build must refuse BEFORE any run
    exists, with the bracket reason, so _build_replacement's candidate loop
    journals candidate_skipped and moves to the next name — and the kill
    switch must restore the old build-everything behavior on this path."""

    def _fleet(self):
        fleet_id = fp.create_fleet(self.agent_id, 1, 500.0)
        return fp.get_fleet(fleet_id)

    def test_try_build_raises_bracket_infeasible_before_any_run(self):
        import fleet_supervisor as fs
        fleet = self._fleet()
        thesis = _thesis(market="crypto", sigma=60.0, symbol="AAA")
        with self.assertRaises(ValueError) as ctx:
            fs._try_build(fleet, thesis, 500.0)
        self.assertIn("bracket_infeasible", str(ctx.exception))
        self.assertEqual(fp.list_members(fleet["id"]), [])

    def test_kill_switch_restores_replacement_builds(self):
        import fleet_supervisor as fs
        os.environ["FLEET_BRACKET_FEASIBILITY"] = "0"
        fleet = self._fleet()
        thesis = _thesis(market="crypto", sigma=60.0, symbol="AAA")
        run_id = fs._try_build(fleet, thesis, 500.0)
        self.assertIsNotNone(run_id)
        self.assertEqual(len(fp.list_members(fleet["id"])), 1)


if __name__ == "__main__":
    unittest.main()
