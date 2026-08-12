"""Replenish stall (live 2026-08-12, fleets 31 & 32): three defects that
each froze a fleet below its slot target while headroom sat unused.

1. `_build_replacement` passed only `_open_markets_scope()` to
   `select_targets`, DISCARDING the fleet's explicit `market_scope_json` —
   a us-stock-scoped fleet was offered ETHUSDT/AUDCHF/ZC candidates which
   the swing gate then rejected every tick (2/25 forever).
2. `_slot_pass`'s dormancy floor `total/(2n)` assumes equal-share slot
   allocations; vol-parity funding creates far smaller slots ($500–$1,580
   on a $99,999/10 fleet, floor $5,000) so every empty slot went dormant
   with ~$97k headroom (1/10 and shrinking).
3. `fleet_auto_tune` recommended slots above the plan's entitlement cap and
   let `set_fleet_size` raise `EntitlementDenied` every pass (log noise,
   and the resize never lands).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import fleet_supervisor as fs
import symbol_research as sr

from test_fleet_supervision import SupervisionBase, _candles, _null_ctx


def _live(fleet_id):
    return [m for m in fp.list_members(fleet_id)
            if m["status"] in ("running", "armed", "paused")]


class ReplacementScopeTests(SupervisionBase):
    """The replacement path must honour the fleet's explicit market scope."""

    def _seed_mixed_research(self, batch_id=None):
        universe = [{"symbol": "AAPL", "market": "us-stock"},
                    {"symbol": "MSFT", "market": "us-stock"},
                    {"symbol": "AAA", "market": "crypto"},
                    {"symbol": "BBB", "market": "crypto"},
                    {"symbol": "CCC", "market": "crypto"}]
        ctx = (patch.object(sr, "current_batch_id", return_value=batch_id)
               if batch_id else _null_ctx())
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None), ctx:
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())

    def _scoped_fleet(self, scope):
        self._seed_mixed_research()
        fleet_id = fp.create_fleet(self.agent_id, 1, 1000.0,
                                   market_scope=scope)
        fp.start_fleet(fleet_id, self.agent_id)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fleet_id

    def _orphan_slot(self, fleet_id, slot_index=0):
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        run_id = slot_runs[slot_index]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (run_id,))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = ?",
                    (fleet_id, slot_index))
        conn.commit()
        conn.close()

    def test_replacement_stays_inside_fleet_scope(self):
        """us-stock fleet, us-stock market open ⇒ the replacement must be a
        us-stock symbol even when crypto theses outrank it."""
        fleet_id = self._scoped_fleet(["us-stock"])
        self.assertEqual(len(_live(fleet_id)), 1)
        self._orphan_slot(fleet_id)
        captured = {}
        real_select = sr.select_targets

        def spy(cur, aid, n, **kw):
            captured["markets_scope"] = kw.get("markets_scope")
            return real_select(cur, aid, n, **kw)

        with patch.object(fp, "_open_markets_scope",
                          return_value=["crypto", "us-stock"]), \
             patch.object(sr, "select_targets", side_effect=spy):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        self.assertEqual(captured.get("markets_scope"), ["us-stock"])
        members = _live(fleet_id)
        self.assertEqual(len(members), 1, "slot must refill")
        self.assertEqual(members[0]["market"], "us-stock")

    def test_scoped_fleet_waits_while_its_market_is_closed(self):
        """us-stock fleet, only crypto open ⇒ NO cross-market build; the
        slot waits for the market to open."""
        fleet_id = self._scoped_fleet(["us-stock"])
        self._orphan_slot(fleet_id)
        with patch.object(fp, "_open_markets_scope",
                          return_value=["crypto"]):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        members = _live(fleet_id)
        self.assertEqual(len(members), 0,
                         "must not build a crypto run into a us-stock fleet")


class VolParityDormancyTests(SupervisionBase):
    """A slot whose vol-parity allocation is below the equal-share floor must
    still fund when headroom covers its own allocation."""

    def _orphan_slot(self, fleet_id, slot_index=0):
        slot_runs = {s["slot_index"]: s.get("current_run_id")
                     for s in fs._slots(fleet_id)}
        run_id = slot_runs[slot_index]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM trading_runs WHERE id = ?", (run_id,))
        cur.execute("UPDATE fleet_slots SET current_run_id = NULL, "
                    "state = 'active' WHERE fleet_id = ? AND slot_index = ?",
                    (fleet_id, slot_index))
        conn.commit()
        conn.close()

    def test_small_allocation_slot_is_not_dormant(self):
        # n=2, budget 2000 ⇒ equal-share floor total/(2n) = 500. Vol-parity
        # style allocation of 300 sits BELOW that floor but headroom (≥300)
        # fully covers it — the slot must build, not sleep.
        fleet_id = self._built_fleet(n=2, budget=2000.0)
        self._orphan_slot(fleet_id, 0)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE fleet_slots SET original_allocation_usd = 300 "
                    "WHERE fleet_id = ? AND slot_index = 0", (fleet_id,))
        conn.commit()
        conn.close()
        with patch.object(fs.fp, "marked_equity",
                          return_value={"equity": 2000.0, "ok": True,
                                        "zombie_basis": 0.0, "pnl": 0.0}):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        states = {s["slot_index"]: s["state"] for s in fs._slots(fleet_id)}
        self.assertNotEqual(states.get(0), "dormant",
                            "fundable slot must not be dormant")
        self.assertEqual(len(_live(fleet_id)), 2, "slot must refill")

    def test_true_dust_headroom_still_goes_dormant(self):
        # Headroom genuinely too small for the slot's allocation ⇒ dormant
        # (the floor still protects against dust builds).
        fleet_id = self._built_fleet(n=2, budget=2000.0)
        self._orphan_slot(fleet_id, 0)
        # equity 1450 keeps loss (27.5%) under the warn rail (30%) so the
        # slot pass actually runs; the live member's ~$963 budget leaves
        # ~$487 headroom — under the ~$500 floor for a ~$1037 slot.
        with patch.object(fs.fp, "marked_equity",
                          return_value={"equity": 1450.0, "ok": True,
                                        "zombie_basis": 0.0, "pnl": 0.0}):
            fs.supervise_fleet(fp.get_fleet(fleet_id))
        states = {s["slot_index"]: s["state"] for s in fs._slots(fleet_id)}
        self.assertEqual(states.get(0), "dormant")
        self.assertEqual(len(_live(fleet_id)), 1)


class AutoTuneEntitlementClampTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        import fleet_auto_tune
        fleet_auto_tune._last_run_epoch = None
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (id, email, password_hash, created_at)"
                    " VALUES (1, 'h@x.com', 'x', '2026-01-01T00:00:00Z')")
        cur.execute("INSERT INTO agents (id, name, token, starting_capital,"
                    " user_id) VALUES (6, 'a', 't', 100000.0, 1)")
        cur.execute(
            "INSERT INTO fleets (id, agent_id, name, status, n_runs,"
            " total_budget_usd, risk_appetite, active_fleet_key, created_at,"
            " started_at) VALUES (32, 6, 'f', 'active', 10, 99999.0,"
            " 'extreme', 'user:1', '2026-01-01T00:00:00Z',"
            " '2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recommendation_clamped_to_plan_cap(self):
        """Budget recommends 25 slots but the plan caps at 10 ⇒ auto-tune
        must clamp (no EntitlementDenied churn every pass)."""
        import fleet_auto_tune
        calls = []

        def spy(fleet_id, n):
            calls.append(n)
            return fp.set_fleet_size(fleet_id, n)

        with patch("entitlements.limits_for_agent",
                   return_value=(1, {"max_fleet_size": 10})), \
             patch.object(fleet_auto_tune, "set_fleet_size",
                          side_effect=spy):
            fleet_auto_tune.auto_tune_fleets()
        self.assertTrue(all(n <= 10 for n in calls),
                        f"set_fleet_size called above plan cap: {calls}")
        fleet = fp.get_fleet(32)
        self.assertEqual(int(fleet["n_runs"]), 10)


if __name__ == "__main__":
    unittest.main()
