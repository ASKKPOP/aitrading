"""Plan 06 C3 — named config profiles.

The contract under test:
  * risk limits ARE the deterministic safety limits, so NO profile path may
    write one the PUT endpoint would reject (P-1). Import is the dangerous
    door: it takes arbitrary pasted JSON.
  * saving or importing never changes the live setup — only apply does
  * profiles are per-agent and cannot be read or written across agents
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import config_profiles
import database
from config_profiles import (ProfileError, apply_profile, capture_current,
                             delete_profile, import_profile, list_profiles,
                             save_profile, validate_limits)
from database import get_db_connection
from risk_engine import get_risk_limits, put_risk_limits


def _mk_agent(name: str, user_id: int | None = None) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO agents (name, user_id) VALUES (?, ?)", (name, user_id))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _mk_user(email: str) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (email, "x"))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _guidelines_of(agent_id: int) -> str:
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT u.trading_guidelines FROM users u
               JOIN agents a ON a.user_id = u.id WHERE a.id = ?""", (agent_id,)).fetchone()
    finally:
        conn.close()
    return (row["trading_guidelines"] or "") if row else ""


class ProfileTestBase(unittest.TestCase):
    def setUp(self):
        # Isolated temp DB per test, matching the rest of the suite — these
        # tests write limits, and must never touch a real one.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.uid = _mk_user("prof@example.com")
        self.agent_id = _mk_agent("prof-agent", self.uid)


class ValidationTests(ProfileTestBase):
    """Import is arbitrary pasted JSON — the door that must not open."""

    def test_import_cannot_smuggle_an_absurd_limit(self):
        with self.assertRaises(ProfileError) as ctx:
            import_profile(self.agent_id, {"name": "evil",
                                           "limits": {"max_daily_loss_usd": 1e12}})
        self.assertIn("max_daily_loss_usd", str(ctx.exception))

    def test_import_cannot_disable_a_stop_loss_by_overflow(self):
        """stop_loss_pct must stay 0<=x<1 — 5.0 would mean a 500% stop."""
        with self.assertRaises(ProfileError):
            import_profile(self.agent_id, {"name": "x", "limits": {"stop_loss_pct": 5.0}})

    def test_import_rejects_negative_limits(self):
        with self.assertRaises(ProfileError):
            import_profile(self.agent_id, {"name": "x",
                                           "limits": {"max_symbol_exposure_usd": -1}})

    def test_unknown_keys_are_dropped_not_stored(self):
        """Junk must not be persisted only to be applied later."""
        p = import_profile(self.agent_id, {"name": "j",
                                           "limits": {"max_daily_loss_usd": 500,
                                                      "sudo_disable_risk": True}})
        self.assertNotIn("sudo_disable_risk", p["limits"])
        self.assertEqual(p["limits"]["max_daily_loss_usd"], 500)

    def test_valid_limits_pass(self):
        out = validate_limits({"max_daily_loss_usd": 500, "stop_loss_pct": 0.03})
        self.assertEqual(out["max_daily_loss_usd"], 500)
        self.assertEqual(out["stop_loss_pct"], 0.03)

    def test_import_rejects_non_object(self):
        for bad in ([], "string", 5):
            with self.assertRaises(ProfileError):
                import_profile(self.agent_id, bad)

    def test_name_is_required_and_bounded(self):
        with self.assertRaises(ProfileError):
            save_profile(self.agent_id, "   ")
        with self.assertRaises(ProfileError):
            save_profile(self.agent_id, "n" * 61)

    def test_guidelines_ceiling_matches_the_endpoint(self):
        with self.assertRaises(ProfileError):
            save_profile(self.agent_id, "g", {"limits": {}, "guidelines": "x" * 2001})


class SaveApplyTests(ProfileTestBase):
    def test_save_captures_the_live_setup(self):
        put_risk_limits(self.agent_id, {"max_daily_loss_usd": 777, "stop_loss_pct": 0.04})
        p = save_profile(self.agent_id, "mine")
        self.assertEqual(p["limits"]["max_daily_loss_usd"], 777)
        self.assertEqual(p["limits"]["stop_loss_pct"], 0.04)

    def test_saving_does_not_change_live_limits(self):
        put_risk_limits(self.agent_id, {"max_daily_loss_usd": 100})
        save_profile(self.agent_id, "other", {"limits": {"max_daily_loss_usd": 900},
                                              "guidelines": "be bold"})
        self.assertEqual(get_risk_limits(self.agent_id)["max_daily_loss_usd"], 100)

    def test_importing_does_not_change_live_limits(self):
        """A paste must never silently retune live risk."""
        put_risk_limits(self.agent_id, {"max_daily_loss_usd": 100})
        import_profile(self.agent_id, {"name": "pasted", "limits": {"max_daily_loss_usd": 900}})
        self.assertEqual(get_risk_limits(self.agent_id)["max_daily_loss_usd"], 100)

    def test_apply_writes_limits_and_guidelines(self):
        p = save_profile(self.agent_id, "cautious",
                         {"limits": {"max_daily_loss_usd": 250, "stop_loss_pct": 0.02},
                          "guidelines": "no leverage"})
        out = apply_profile(self.agent_id, p["id"])
        self.assertEqual(out["applied"], "cautious")
        self.assertEqual(get_risk_limits(self.agent_id)["max_daily_loss_usd"], 250)
        self.assertEqual(get_risk_limits(self.agent_id)["stop_loss_pct"], 0.02)
        self.assertEqual(_guidelines_of(self.agent_id), "no leverage")

    def test_apply_revalidates_a_stored_payload(self):
        """A row written before bounds tightened must not slip through apply."""
        p = save_profile(self.agent_id, "legacy", {"limits": {"max_daily_loss_usd": 100}})
        conn = get_db_connection()
        conn.execute("UPDATE config_profiles SET payload_json = ? WHERE id = ?",
                     (json.dumps({"limits": {"max_daily_loss_usd": 1e12}, "guidelines": ""}),
                      p["id"]))
        conn.commit()
        conn.close()
        with self.assertRaises(ProfileError):
            apply_profile(self.agent_id, p["id"])
        # and the live limit is untouched by the failed apply
        self.assertNotEqual(get_risk_limits(self.agent_id)["max_daily_loss_usd"], 1e12)

    def test_apply_unreadable_payload_raises_not_crashes(self):
        p = save_profile(self.agent_id, "broken")
        conn = get_db_connection()
        conn.execute("UPDATE config_profiles SET payload_json = ? WHERE id = ?",
                     ("{not json", p["id"]))
        conn.commit()
        conn.close()
        with self.assertRaises(ProfileError):
            apply_profile(self.agent_id, p["id"])

    def test_booleans_survive_the_round_trip(self):
        put_risk_limits(self.agent_id, {"use_trailing": 1, "use_kelly": 0})
        p = save_profile(self.agent_id, "flags")
        put_risk_limits(self.agent_id, {"use_trailing": 0, "use_kelly": 1})
        apply_profile(self.agent_id, p["id"])
        limits = get_risk_limits(self.agent_id)
        self.assertEqual(limits["use_trailing"], 1)
        self.assertEqual(limits["use_kelly"], 0)

    def test_apply_missing_profile(self):
        with self.assertRaises(ProfileError):
            apply_profile(self.agent_id, 999999)


class ListDeleteTests(ProfileTestBase):
    def test_save_overwrites_same_name_rather_than_duplicating(self):
        save_profile(self.agent_id, "dup", {"limits": {"max_daily_loss_usd": 1}})
        save_profile(self.agent_id, "dup", {"limits": {"max_daily_loss_usd": 2}})
        names = [p["name"] for p in list_profiles(self.agent_id)]
        self.assertEqual(names.count("dup"), 1)
        got = [p for p in list_profiles(self.agent_id) if p["name"] == "dup"][0]
        self.assertEqual(got["limits"]["max_daily_loss_usd"], 2)

    def test_delete_removes_only_that_profile(self):
        a = save_profile(self.agent_id, "a")
        save_profile(self.agent_id, "b")
        self.assertTrue(delete_profile(self.agent_id, a["id"]))
        self.assertEqual([p["name"] for p in list_profiles(self.agent_id)], ["b"])

    def test_delete_missing_returns_false(self):
        self.assertFalse(delete_profile(self.agent_id, 999999))

    def test_profile_cap_is_enforced(self):
        for i in range(config_profiles.MAX_PROFILES_PER_AGENT):
            save_profile(self.agent_id, f"p{i}")
        with self.assertRaises(ProfileError):
            save_profile(self.agent_id, "one-too-many")
        # ...but overwriting an existing name still works at the cap
        self.assertEqual(save_profile(self.agent_id, "p0")["name"], "p0")

    def test_unreadable_row_is_skipped_not_served(self):
        p = save_profile(self.agent_id, "ok")
        bad = save_profile(self.agent_id, "bad")
        conn = get_db_connection()
        conn.execute("UPDATE config_profiles SET payload_json = ? WHERE id = ?",
                     ("{{{", bad["id"]))
        conn.commit()
        conn.close()
        self.assertEqual([x["name"] for x in list_profiles(self.agent_id)], ["ok"])
        self.assertEqual(p["name"], "ok")


class IsolationTests(ProfileTestBase):
    """Profiles are per-agent — one account must not reach another's."""

    def setUp(self):
        super().setUp()
        self.other_uid = _mk_user("other@example.com")
        self.other_agent = _mk_agent("other-agent", self.other_uid)

    def test_list_is_scoped_to_the_agent(self):
        save_profile(self.agent_id, "mine")
        self.assertEqual(list_profiles(self.other_agent), [])

    def test_cannot_apply_another_agents_profile(self):
        p = save_profile(self.agent_id, "mine", {"limits": {"max_daily_loss_usd": 42}})
        with self.assertRaises(ProfileError):
            apply_profile(self.other_agent, p["id"])

    def test_cannot_delete_another_agents_profile(self):
        p = save_profile(self.agent_id, "mine")
        self.assertFalse(delete_profile(self.other_agent, p["id"]))
        self.assertEqual([x["name"] for x in list_profiles(self.agent_id)], ["mine"])

    def test_same_name_allowed_on_different_agents(self):
        save_profile(self.agent_id, "shared")
        save_profile(self.other_agent, "shared")
        self.assertEqual(len(list_profiles(self.agent_id)), 1)
        self.assertEqual(len(list_profiles(self.other_agent)), 1)


class CaptureTests(ProfileTestBase):
    def test_capture_excludes_updated_at(self):
        """updated_at is a storage artifact, not a setting to restore."""
        put_risk_limits(self.agent_id, {"max_daily_loss_usd": 5})
        self.assertNotIn("updated_at", capture_current(self.agent_id)["limits"])

    def test_capture_on_agent_without_user(self):
        orphan = _mk_agent("orphan", None)
        self.assertEqual(capture_current(orphan)["guidelines"], "")


if __name__ == "__main__":
    unittest.main()
