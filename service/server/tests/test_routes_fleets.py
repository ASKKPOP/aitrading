"""Plan 14 Phase 5 gates — fleet API + master control routes.

Auth (401 / cross-tenant 404 / agent-bearer refused on the master endpoint),
the entitlements echo, rails tighten-only + 409-confirm, resume-warning, and
the master hold/resume/remove fan-out with marker discipline.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import database
import fleet_planner as fp
import symbol_research as sr
from routes import create_app


def _candles(n=60, drift=0.8, volume=5_000_000):
    out, price = [], 100.0
    for i in range(n):
        price *= 1 + drift / 100.0
        out.append({"ts": i, "open": price, "high": price, "low": price,
                    "close": price, "volume": volume})
    return out


class FleetRouteTests(unittest.TestCase):
    def setUp(self):
        # Synthetic theses are ~1.5%, below the build-time fee/edge hurdle
        # (~2.4% claimed). These fixtures are about the fleet HTTP routes, not that gate —
        # test_build_gates.py owns it.
        os.environ["RUN_FEE_EDGE_MULTIPLE"] = "0"
        os.environ["FLEET_EXPECTANCY_GATE"] = "false"
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.plan = patch("entitlements.plan_code_for_user",
                          return_value="professional")
        self.plan.start()
        self.probe = patch("routes_runs._probe_price", return_value=100.0)
        self.probe.start()
        self.client = TestClient(create_app())
        # agent (bearer) principal
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "fleet-route-agent", "password": "pw123",
                  "initial_balance": 100000.0})
        self.token = resp.json()["token"]
        self.agent_id = resp.json()["agent_id"]
        self.auth = {"Authorization": f"Bearer {self.token}"}
        # user principal linked to the agent + a session token
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('u@x.com', 'x', '2026-01-01T00:00:00Z')")
        self.user_id = cur.lastrowid
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                    (self.user_id, self.agent_id))
        self.user_token = "utok-" + hashlib.sha1(b"t").hexdigest()
        cur.execute(
            "INSERT INTO user_tokens (user_id, token, expires_at, created_at) "
            "VALUES (?, ?, '2099-01-01 00:00:00', '2026-01-01 00:00:00')",
            (self.user_id, self.user_token))
        conn.commit()
        conn.close()
        self.user_auth = {"Authorization": f"Bearer {self.user_token}"}

    def tearDown(self):
        os.environ.pop("RUN_FEE_EDGE_MULTIPLE", None)
        os.environ.pop("FLEET_EXPECTANCY_GATE", None)
        self.plan.stop()
        self.probe.stop()
        self.tmp.cleanup()

    def _seed_and_build(self, n=2, budget=2000.0):
        universe = [{"symbol": s, "market": "crypto"}
                    for s in ("AAA", "BBB", "CCC", "DDD", "EEE")]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None):
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())
        r = self.client.post("/api/fleets",
                             json={"n_runs": n, "total_budget_usd": budget},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fleet_id = r.json()["id"]
        r = self.client.post(f"/api/fleets/{fleet_id}/start", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fleet_id

    # ── auth surface ───────────────────────────────────────────────────────

    def test_401_without_token(self):
        self.assertEqual(self.client.get("/api/fleets").status_code, 401)
        self.assertEqual(
            self.client.post("/api/automation/master",
                             json={"action": "hold"}).status_code, 401)

    def test_same_user_second_agent_sees_and_controls_fleet(self):
        """The uniqueness guard is per USER, so visibility/control must be
        too — hit live 2026-07-21: fleet built under agent A, user browsing
        as agent B got the one-fleet 409 for a fleet the panel couldn't show."""
        fleet_id = self._seed_and_build()
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "second-agent", "password": "pw123"})
        second_id = resp.json()["agent_id"]
        second = {"Authorization": f"Bearer {resp.json()['token']}"}
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE agents SET user_id = ? WHERE id = ?",
                    (self.user_id, second_id))
        conn.commit()
        conn.close()
        # list shows the user's fleet from the second agent
        r = self.client.get("/api/fleets", headers=second)
        self.assertIn(fleet_id, [f["id"] for f in r.json()["fleets"]])
        # detail + control work cross-agent within the same user
        self.assertEqual(
            self.client.get(f"/api/fleets/{fleet_id}", headers=second)
            .status_code, 200)
        r = self.client.post(f"/api/fleets/{fleet_id}/stop", json={},
                             headers=second)
        self.assertEqual(r.status_code, 200, r.text)

    def test_cross_tenant_404(self):
        fleet_id = self._seed_and_build()
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "intruder", "password": "pw123"})
        other = {"Authorization": f"Bearer {resp.json()['token']}"}
        self.assertEqual(
            self.client.get(f"/api/fleets/{fleet_id}", headers=other)
            .status_code, 404)

    def test_agent_bearer_refused_on_master_endpoint(self):
        """The master switch is a USER action — a claw_ agent token is 401."""
        r = self.client.post("/api/automation/master",
                             json={"action": "hold"}, headers=self.auth)
        self.assertEqual(r.status_code, 401)

    # ── entitlements echo ─────────────────────────────────────────────────

    def test_entitlements_me(self):
        r = self.client.get("/api/entitlements/me", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["plan"], "professional")
        self.assertEqual(body["max_fleet_size"], 10)
        self.assertGreater(body["default_budget_usd"], 0)

    # ── rails ─────────────────────────────────────────────────────────────

    def test_rails_tighten_only_and_confirm(self):
        fleet_id = self._seed_and_build()
        # loosen ⇒ 400
        r = self.client.put(f"/api/fleets/{fleet_id}/rails",
                            json={"warn_loss_frac": 0.35}, headers=self.auth)
        self.assertEqual(r.status_code, 400)
        # tighten ⇒ ok, latch rebased
        r = self.client.put(f"/api/fleets/{fleet_id}/rails",
                            json={"warn_loss_frac": 0.20,
                                  "stop_loss_frac": 0.30}, headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fleet = fp.get_fleet(fleet_id)
        self.assertAlmostEqual(float(fleet["warn_loss_frac"]), 0.20)
        # stop at/inside current drawdown ⇒ 409 without confirm
        total = float(fleet["total_budget_usd"])
        with patch.object(fp, "marked_equity",
                          return_value={"equity": total * 0.75, "ok": True,
                                        "zombie_basis": 0.0, "pnl": 0}):
            r = self.client.put(f"/api/fleets/{fleet_id}/rails",
                                json={"warn_loss_frac": 0.10,
                                      "stop_loss_frac": 0.20},
                                headers=self.auth)
            self.assertEqual(r.status_code, 409)
            r = self.client.put(f"/api/fleets/{fleet_id}/rails",
                                json={"warn_loss_frac": 0.10,
                                      "stop_loss_frac": 0.20,
                                      "confirm": True}, headers=self.auth)
            self.assertEqual(r.status_code, 200, r.text)

    # ── master control ────────────────────────────────────────────────────

    def test_master_hold_resume_marker_discipline(self):
        """Hold pauses running members with the marker; a USER-paused run is
        untouched by master resume (round-4/5 marker discipline)."""
        fleet_id = self._seed_and_build(n=2)
        members = fp.list_members(fleet_id)
        # user pauses one member themselves first
        import trading_runs
        trading_runs.pause_run(members[0]["id"], self.agent_id)
        r = self.client.post("/api/automation/master",
                             json={"action": "hold"}, headers=self.user_auth)
        self.assertEqual(r.status_code, 200, r.text)
        after = {m["id"]: m for m in fp.list_members(fleet_id)}
        self.assertEqual(after[members[1]["id"]]["paused_reason"], "master_hold")
        self.assertIsNone(after[members[0]["id"]]["paused_reason"])
        # state endpoint reflects the hold
        r = self.client.get("/api/automation/master", headers=self.user_auth)
        self.assertEqual(r.json()["state"], "held")
        # resume: ONLY the marker-carrying member wakes
        r = self.client.post("/api/automation/master",
                             json={"action": "resume"}, headers=self.user_auth)
        self.assertEqual(r.status_code, 200, r.text)
        after = {m["id"]: m for m in fp.list_members(fleet_id)}
        self.assertEqual(after[members[1]["id"]]["status"], "running")
        self.assertEqual(after[members[0]["id"]]["status"], "paused",
                         "user-paused member must stay paused")

    def test_master_hold_blocks_cycles_account_wide(self):
        fleet_id = self._seed_and_build(n=1)
        member = fp.list_members(fleet_id)[0]
        self.client.post("/api/automation/master", json={"action": "hold"},
                         headers=self.user_auth)
        import run_engine
        with patch("llm_client.generate_text",
                   side_effect=AssertionError("LLM under hold")):
            result = run_engine.run_cycle(member["id"])
        self.assertFalse(result["executed"])

    def test_master_remove_stops_everything(self):
        fleet_id = self._seed_and_build(n=2)
        r = self.client.post("/api/automation/master",
                             json={"action": "remove"}, headers=self.user_auth)
        self.assertEqual(r.status_code, 200, r.text)
        for m in fp.list_members(fleet_id):
            self.assertIn(m["status"], ("stopping", "stopped"))
        fleet = fp.get_fleet(fleet_id)
        self.assertIn(fleet["status"], (fp.STATUS_STOPPING, fp.STATUS_STOPPED))

    # ── resume-warning ────────────────────────────────────────────────────

    def test_resume_warning_409_when_not_warned(self):
        fleet_id = self._seed_and_build()
        r = self.client.post(f"/api/fleets/{fleet_id}/resume-warning",
                             headers=self.auth)
        self.assertEqual(r.status_code, 409)

    # ── stop + delete lifecycle ───────────────────────────────────────────

    def test_stop_all_and_delete(self):
        fleet_id = self._seed_and_build(n=2)
        r = self.client.post(f"/api/fleets/{fleet_id}/stop", json={},
                             headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        # finalize via supervision, then delete
        import fleet_supervisor as fs
        for m in fp.list_members(fleet_id):
            conn = database.get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE trading_runs SET status='stopped', "
                        "active_key=NULL WHERE id = ?", (m["id"],))
            conn.commit()
            conn.close()
        fs.supervise_fleet(fp.get_fleet(fleet_id))
        r = self.client.delete(f"/api/fleets/{fleet_id}", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        conn = database.get_db_connection()
        cur = conn.cursor()
        for table in ("fleet_events", "fleet_candidates", "fleet_slots"):
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            self.assertEqual(int(cur.fetchone()["n"]), 0, table)
        conn.close()


if __name__ == "__main__":
    unittest.main()


class MemberPnlFieldsTests(FleetRouteTests):
    """Plan 15 O2 — member cards need the marked total, not just the fee
    ledger (realized is fees-only until the first close)."""

    def test_members_carry_unrealized_and_total(self):
        fleet_id = self._seed_and_build()
        r = self.client.get(f"/api/fleets/{fleet_id}", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        members = r.json().get("members") or []
        self.assertTrue(members)
        for m in members:
            self.assertIn("unrealized_pnl_usd", m)
            self.assertIn("total_pnl_usd", m)
            # flat freshly-built member: total == realized (fees so far)
            if m.get("total_pnl_usd") is not None and m.get("realized_pnl_usd") is not None:
                self.assertAlmostEqual(float(m["total_pnl_usd"]),
                                       float(m["realized_pnl_usd"]), places=6)

    def _stop_member(self, run_id, reason, stamp):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trading_runs SET status = 'stopped', "
                    "status_reason = ?, realized_pnl_usd = ? WHERE id = ?",
                    (reason, stamp, run_id))
        conn.commit()
        conn.close()

    def _leg(self, run_id, seq, side, price, qty, fee, kind="operation"):
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO signals (signal_id, agent_id, run_id, message_type, "
            "market, symbol, side, entry_price, quantity, fee_usd, timestamp, "
            "created_at) VALUES (?, ?, ?, ?, 'crypto', 'AAA', ?, ?, "
            "?, ?, ?, '2026-11-20T00:00:00Z')",
            (90000 + seq, self.agent_id, run_id, kind, side, price, qty, fee,
             seq))
        conn.commit()
        conn.close()

    def _get_with_replay_spy(self, fleet_id):
        import run_engine
        replayed = []
        real = run_engine.compute_run_pnl

        def spy(run):
            replayed.append(run["id"])
            return real(run)

        with patch.object(run_engine, "compute_run_pnl", side_effect=spy):
            r = self.client.get(f"/api/fleets/{fleet_id}", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        return replayed, {m["run_id"]: m for m in r.json()["members"]}

    def test_cleanly_stopped_members_replay_from_bulk_legs(self):
        """Prod 2026-11-20: GET /api/fleets/44 ran compute_run_pnl (one new
        MySQL connection each, ~46 ms) for all 3,697 members on the event
        loop — ~169 s per request; every API route 504'd while the page
        polled it. Stopped members now replay from one bulk leg read, and
        still from the LEDGER, not the stamp: request_stop's direct
        running->stopped path never re-stamps realized_pnl_usd."""
        fleet_id = self._seed_and_build()
        live, done = fp.list_members(fleet_id)[:2]
        self._stop_member(done["id"], "idle_retired", -1.25)  # stale stamp
        self._leg(done["id"], 1, "buy", 100.0, 1.0, 0.1)
        self._leg(done["id"], 2, "sell", 103.0, 1.0, 0.1)
        # a non-ledger row on the run must not count as a leg
        self._leg(done["id"], 3, "sell", 50.0, 1.0, 0.1, kind="strategy")
        replayed, by_id = self._get_with_replay_spy(fleet_id)
        self.assertIn(live["id"], replayed)
        self.assertNotIn(done["id"], replayed)
        self.assertAlmostEqual(float(by_id[done["id"]]["total_pnl_usd"]), 2.8)
        self.assertEqual(by_id[done["id"]]["unrealized_pnl_usd"], 0.0)

    def test_positions_held_member_still_replays(self):
        fleet_id = self._seed_and_build()
        held = fp.list_members(fleet_id)[1]
        self._stop_member(held["id"], "positions_held", 0.0)
        replayed, _ = self._get_with_replay_spy(fleet_id)
        self.assertIn(held["id"], replayed)

    def test_fleet_routes_run_off_the_event_loop(self):
        """Sync DB work inside these async handlers blocks every other
        route; it must run in a worker thread (no running loop there)."""
        import asyncio
        import run_engine
        fleet_id = self._seed_and_build()
        on_loop = []

        def has_loop():
            try:
                asyncio.get_running_loop()
                return True
            except RuntimeError:
                return False

        real_pnl, real_eq = run_engine.compute_run_pnl, fp.marked_equity

        def pnl_spy(run):
            on_loop.append(("get_fleet", has_loop()))
            return real_pnl(run)

        def eq_spy(fleet):
            on_loop.append(("marked_equity", has_loop()))
            return real_eq(fleet)

        with patch.object(run_engine, "compute_run_pnl", side_effect=pnl_spy), \
             patch.object(fp, "marked_equity", side_effect=eq_spy):
            self.assertEqual(self.client.get(
                f"/api/fleets/{fleet_id}", headers=self.auth).status_code, 200)
            self.assertEqual(self.client.get(
                "/api/fleets", headers=self.auth).status_code, 200)
        self.assertTrue(on_loop)
        self.assertGreaterEqual(
            sum(1 for k, _ in on_loop if k == "marked_equity"), 2)
        self.assertEqual([c for c in on_loop if c[1]], [])

class FleetLeverageTests(FleetRouteTests):
    """2026-07-23 — fleet-level leverage: None ⇒ auto by tier, a number
    overrides it for every run the fleet builds."""

    def _build_with(self, **fleet_kwargs):
        universe = [{"symbol": s, "market": "crypto"}
                    for s in ("AAA", "BBB", "CCC")]
        with patch.object(sr, "build_universe", return_value=universe), \
             patch.object(sr, "_read_overlays",
                          return_value={"event_window": False,
                                        "regime_blocks_longs": False,
                                        "policy": {}}), \
             patch("cache.acquire_lock", return_value=None):
            sr.refresh_research_batch(
                generate_text=lambda *a, **k: None,
                fetch_candles=lambda s, m: _candles())
        body = {"n_runs": 1, "total_budget_usd": 2000.0}
        body.update(fleet_kwargs)
        r = self.client.post("/api/fleets", json=body, headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        fleet_id = r.json()["id"]
        self.client.post(f"/api/fleets/{fleet_id}/start", headers=self.auth)
        fp._do_research(fp.get_fleet(fleet_id))
        fp._do_build(fp.get_fleet(fleet_id))
        return fleet_id

    def _member_leverage(self, fleet_id):
        import json as _j
        m = fp.list_members(fleet_id)[0]
        return _j.loads(m["config_snapshot_json"])["leverage"]

    def test_extreme_tier_auto_leverage_is_3x(self):
        fid = self._build_with(risk_appetite="extreme")
        self.assertEqual(self._member_leverage(fid), 3.0)

    def test_explicit_leverage_overrides_tier(self):
        fid = self._build_with(risk_appetite="extreme", leverage=5)
        self.assertEqual(self._member_leverage(fid), 5.0)

    def test_balanced_default_leverage_is_1x(self):
        fid = self._build_with(risk_appetite="balanced")
        self.assertEqual(self._member_leverage(fid), 1.0)
