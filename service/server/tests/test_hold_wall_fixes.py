"""Hold-wall / replenish-starvation fixes (investigation 2026-09-03).

Prod incident: both owner fleets (43 us-stock 0/8, 44 crypto 3/8) made ZERO
trades since 2026-08-29 across 1,076+ decisions. Three interacting defects:

1. Risk budget inexpressible — max_loss_usd = 2% of max_bet gave a $6.45
   loss budget on a $1,074 slot; the retire brake (0.70 × max_loss) left
   $4.51 of room, below one ordinary day of noise (±1.4–3.6%) at size. The
   desk correctly reported "no stop that clears noise fits the rail at
   meaningful size" and held every cycle.
2. Cooldown flood — every no-prospect switch benches its symbol for 12h;
   with the whole pool holding, 8 slots benched ~18 symbols concurrently,
   collapsing select_targets to a single candidate that the backtest
   expectancy gate then rejected forever (kept: [] loop).
3. us-stock universe shrink — the 08-31 reading of hot-5-MUST dropped every
   non-tech us-stock candidate, leaving a 5-name universe an 8-slot fleet
   could never fill. Owner clarification 2026-09-04: the 5 hot tech names
   are the mandatory FIRST picks; the remaining slots choose from the rest
   of the market.
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
import fleet_planner as fp
import symbol_research as sr


def _candles(n=60, start=100.0, drift=0.5, volume=1_000_000):
    out, price = [], start
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class RiskBudgetExpressibilityTests(unittest.TestCase):
    """Fix 1: the per-run loss budget must let a noise-clearing stop fit at
    meaningful size. room/bet = 0.70 × stop_loss_frac_of_bet must clear the
    measured ordinary-day band (ETH ±1.40%, HYPE ±2.39%, WLD ±3.6%)."""

    # room-per-bet floor a tier must clear (0.70 × frac ≥ this)
    ROOM_FLOOR = {"stable": 0.020, "balanced": 0.030,
                  "aggressive": 0.045, "extreme": 0.060}
    # and the run's total risk stays a sane slice of its slot budget
    MAX_RISK_OF_SLOT = 0.08

    def test_brake_room_clears_ordinary_day_noise_at_full_bet(self):
        for tier, floor in self.ROOM_FLOOR.items():
            frac = fp._tier("stop_loss_frac_of_bet", tier)
            room_per_bet = 0.70 * frac  # run_feedback retire_drawdown_frac
            self.assertGreaterEqual(
                room_per_bet, floor,
                f"{tier}: brake room {room_per_bet:.3%} of the bet is below "
                f"the {floor:.1%} noise bar — the desk cannot express any "
                f"entry (prod 09-03: $4.51 room on a $322 bet, 0 trades)")

    def test_risk_per_run_stays_a_sane_slice_of_the_slot(self):
        for tier in ("stable", "balanced", "aggressive", "extreme"):
            frac_of_slot = (fp._tier("max_bet_frac_of_run_budget", tier)
                            * fp._tier("stop_loss_frac_of_bet", tier))
            self.assertLessEqual(
                frac_of_slot, self.MAX_RISK_OF_SLOT,
                f"{tier}: {frac_of_slot:.2%} of the slot at risk per run")

    def test_balanced_1250_slot_composes_a_tradeable_loss_budget(self):
        """The exact prod shape: fleet 44, $1,250 slot, balanced."""
        thesis = {"symbol": "HYPEUSDT", "market": "crypto",
                  "market_type": "spot", "direction": "long",
                  "confidence": 0.65, "expected_move_pct": 5.0,
                  "horizon_hours": 24.0}
        settings = fp.compose_run_settings(
            thesis, 1250.0, {"risk_appetite": "balanced", "lang": "en",
                             "leverage": 1})
        max_loss = settings["stop_conditions"]["max_loss_usd"]
        self.assertGreaterEqual(
            max_loss, 15.0,
            f"$1,250 balanced slot composed max_loss ${max_loss} — the prod "
            f"$7.50 budget made every entry inexpressible")


class CooldownFloodTests(unittest.TestCase):
    """Fix 2: cooldowns exclude at most N symbols per market from selection
    (newest benches win); a flood can no longer starve select_targets."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        for k in ("FLEET_SYMBOL_COOLDOWN_CAP",
                  "FLEET_SYMBOL_COOLDOWN_CAP_US_STOCK"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("FLEET_SYMBOL_COOLDOWN_CAP",
                  "FLEET_SYMBOL_COOLDOWN_CAP_US_STOCK"):
            os.environ.pop(k, None)

    def _refresh(self, symbols=("AAA", "BBB", "CCC", "DDD")):
        universe = [{"symbol": s, "market": "crypto"} for s in symbols]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}):
            return sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles(drift=0.8,
                                                    volume=5_000_000))

    def test_cap_defaults(self):
        # One default across markets — a low us-stock cap would re-release
        # hot roster names into the forced tech lead ~3h after their
        # no-prospect switch (adversarial re-review 2026-09-04).
        self.assertEqual(sr._cooldown_cap("crypto"), 8)
        self.assertEqual(sr._cooldown_cap("us-stock"), 8)
        os.environ["FLEET_SYMBOL_COOLDOWN_CAP"] = "3"
        os.environ["FLEET_SYMBOL_COOLDOWN_CAP_US_STOCK"] = "4"
        self.assertEqual(sr._cooldown_cap("crypto"), 3)
        self.assertEqual(sr._cooldown_cap("us-stock"), 4)

    def _bench(self, cur, sym, until, reason="no_prospect_switched"):
        """One cooldown row backed by a stopped source run carrying
        `reason` (None ⇒ a durable NULL-source block)."""
        src = None
        if reason is not None:
            cur.execute(
                "INSERT INTO trading_runs (agent_id, symbol, market, status, "
                "status_reason, created_at) "
                "VALUES (1, ?, 'crypto', 'stopped', ?, '2026-01-01T00:00:00Z')",
                (sym, reason))
            src = cur.lastrowid
        cur.execute(
            "INSERT INTO fleet_symbol_cooldowns "
            "(agent_id, market, symbol, until_ts, source_run_id) "
            "VALUES (1, 'crypto', ?, ?, ?)", (sym, until, src))

    def test_flood_frees_the_oldest_benches(self):
        """All four symbols vary-benched; cap 2 keeps only the two NEWEST
        benches excluded, so selection still has candidates (prod 09-03: 18
        active cooldowns left exactly one candidate, which the expectancy
        gate rejected — kept: [] forever)."""
        self._refresh()
        os.environ["FLEET_SYMBOL_COOLDOWN_CAP"] = "2"
        conn = database.get_db_connection()
        cur = conn.cursor()
        stagger = {"AAA": "2099-01-01T01:00:00Z",   # oldest bench
                   "BBB": "2099-01-01T02:00:00Z",
                   "CCC": "2099-01-01T03:00:00Z",
                   "DDD": "2099-01-01T04:00:00Z"}   # newest bench
        for sym, until in stagger.items():
            self._bench(cur, sym, until)
        conn.commit()
        picked = {t["symbol"] for t in
                  sr.select_targets(cur, agent_id=1, n=4)}
        conn.close()
        self.assertEqual(picked, {"AAA", "BBB"},
                         "the two oldest benches must be released; the two "
                         "newest stay excluded")

    def test_loss_and_durable_benches_never_release(self):
        """Adversarial review 2026-09-03: until_ts ordering alone released a
        one-minute-old LOSS bench (6h window) before hour-old idle benches
        (12h window). Protective benches — loss stops, adapt retires, and
        NULL-source durable blocks — must survive any flood; only the vary
        class is releasable."""
        self._refresh()
        os.environ["FLEET_SYMBOL_COOLDOWN_CAP"] = "1"
        conn = database.get_db_connection()
        cur = conn.cursor()
        # AAA: fresh LOSS bench whose 6h window expires FIRST (sorts oldest)
        self._bench(cur, "AAA", "2099-01-01T01:00:00Z",
                    reason="stop_event:max_loss")
        # BBB: durable NULL-source block, also early-expiring
        self._bench(cur, "BBB", "2099-01-01T02:00:00Z", reason=None)
        # CCC, DDD: vary benches; cap 1 keeps only DDD (newest) excluded
        self._bench(cur, "CCC", "2099-01-01T03:00:00Z")
        self._bench(cur, "DDD", "2099-01-01T04:00:00Z")
        conn.commit()
        picked = {t["symbol"] for t in
                  sr.select_targets(cur, agent_id=1, n=4)}
        conn.close()
        self.assertEqual(picked, {"CCC"},
                         "only the oldest VARY bench may be released — the "
                         "loss and durable benches must stay excluded")

    def test_under_cap_flood_still_excludes_everything(self):
        """Below the cap the exclusion is exact — no behaviour change."""
        self._refresh()
        conn = database.get_db_connection()
        cur = conn.cursor()
        self._bench(cur, "AAA", "2099-01-01T00:00:00Z")
        conn.commit()
        picked = {t["symbol"] for t in
                  sr.select_targets(cur, agent_id=1, n=4)}
        conn.close()
        self.assertNotIn("AAA", picked)
        self.assertEqual(picked, {"BBB", "CCC", "DDD"})


class HotTechMustGuaranteeTests(unittest.TestCase):
    """Fix 3 (owner clarification 2026-09-04, superseding the 08-31
    drop-all reading: "not limit 5 usa stock … ex slot 10 then 5 must be
    tech stock, and then other 5"): a us-stock-only selection FORCES the
    top-5 hottest tech names first and fills the remaining slots from the
    rest of the market — the universe is never shrunk to 5 names again
    (that shrink is what starved fleet 43 to 0/8)."""

    TECH = [("NVDA", 5.0), ("AMD", 4.0), ("META", 3.0), ("MSFT", 2.0),
            ("PLTR", 1.0), ("INTC", 0.5)]
    NON_TECH = [("KO", 9.0), ("WMT", 8.0), ("JPM", 7.0), ("XOM", 6.0)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        for k in ("US_TECH_HOT_SEED", "US_TECH_HOT_MUST"):
            os.environ.pop(k, None)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES ('x@x', 'x')")
        cur.execute("INSERT INTO agents (name, user_id) VALUES ('a', 1)")
        self.agent_id = cur.lastrowid
        cur.execute(
            "INSERT INTO research_batches (batch_id, created_at) "
            "VALUES (1, '2026-09-04T00:00:00Z')")
        far = "2099-01-01T00:00:00Z"
        for sym, mom in self.TECH + self.NON_TECH:
            cur.execute(
                """INSERT INTO research_theses
                   (batch_id, market, symbol, market_type, direction, thesis,
                    risks, invalidation, expected_move_pct, horizon_hours,
                    confidence, ev_per_day_pct, final_score, selectable,
                    planner, factor_scores_json, created_at, expires_at)
                   VALUES (1, 'us-stock', ?, 'spot', 'long', 't', 'r', 'i',
                           5.0, 24, 0.7, 1.0, 0.9, 1, 'llm', ?,
                           '2026-09-04T00:00:00Z', ?)""",
                (sym,
                 json.dumps({"factors": {"mom_2d": mom, "vol_ratio": 1.0}}),
                 far))
        conn.commit()
        self.conn, self.cur = conn, cur

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()
        for k in ("US_TECH_HOT_SEED", "US_TECH_HOT_MUST"):
            os.environ.pop(k, None)

    def test_eight_slots_pick_five_tech_first_then_others(self):
        """The owner's example shape: hotter NON-tech names (KO mom 9.0)
        must not displace the mandatory tech lead, and the remaining slots
        still fill from the rest of the market."""
        picked = sr.select_targets(self.cur, self.agent_id, 8)
        syms = [t["symbol"] for t in picked]
        self.assertEqual(syms[:5], ["NVDA", "AMD", "META", "MSFT", "PLTR"])
        self.assertEqual(len(syms), 8)
        self.assertTrue(set(syms[5:]) <= {"KO", "WMT", "JPM", "XOM", "INTC"})

    def test_small_n_takes_only_the_hottest_tech(self):
        picked = sr.select_targets(self.cur, self.agent_id, 2)
        self.assertEqual([t["symbol"] for t in picked], ["NVDA", "AMD"])

    def test_tech_lead_survives_directional_balance(self):
        """Independent verification 2026-09-04: with an all-long fixture the
        pre-branch reorder alone reproduces the forced output, so the FORCED
        branch itself was untestable — and without it, a mixed-direction
        pool lets the directional-balance pass break the tech lead (probe:
        NVDA, KO, WMT, INTC, AMD…). Shorts on the non-tech names make the
        guarantee itself load-bearing."""
        self.cur.execute(
            "UPDATE research_theses SET direction = 'short' "
            "WHERE symbol IN ('KO', 'WMT', 'JPM', 'XOM')")
        self.conn.commit()
        picked = sr.select_targets(self.cur, self.agent_id, 8)
        syms = [t["symbol"] for t in picked]
        self.assertEqual(syms[:5], ["NVDA", "AMD", "META", "MSFT", "PLTR"],
                         f"the tech lead must survive direction balance: {syms}")
        self.assertEqual(len(syms), 8)

    def test_non_tech_is_never_dropped_from_the_pool(self):
        """The 08-31 drop-all reading shrank the universe to 5 names and
        starved the fleet; the clarified rule keeps the whole market."""
        picked = sr.select_targets(self.cur, self.agent_id, 10)
        self.assertEqual(len(picked), 10)
        self.assertIn("KO", [t["symbol"] for t in picked])


if __name__ == "__main__":
    unittest.main()
