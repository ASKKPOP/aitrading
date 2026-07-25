"""Gateway routing for automation rules — simulator | shadow | live.

The invariant under test: account_type is the only switch deciding where a fill
lands, live is refused (never silently simulated) without a usable gateway, and
a broker rejection in live never leaves a platform position behind.
"""
from __future__ import annotations

import hashlib
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
from routes_shared import utc_now_iso_z


def _create_agent(name: str = "gw-agent", cash: float = 100_000.0) -> int:
    token_hash = hashlib.sha256(name.encode()).hexdigest()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO agents (name, token, token_hash, cash) VALUES (?, NULL, ?, ?)",
        (name, token_hash, cash),
    )
    agent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return agent_id


def _add_broker_account(agent_id: int, broker: str = "alpaca",
                        mode: str = "live", creds: bool = True) -> int:
    from execution.crypto import encrypt_credentials
    blob = encrypt_credentials({"key": "k", "secret": "s"}) if creds else ""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO broker_accounts
           (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
           VALUES (?,?,?,?,1,?,?)""",
        (agent_id, broker, mode, blob, utc_now_iso_z(), utc_now_iso_z()),
    )
    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id


def _accept_tcs(agent_id: int, broker: str = "alpaca") -> None:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO broker_live_optins
           (agent_id, broker, tcs_version, ip_address, user_agent, created_at)
           VALUES (?,?,?,?,?,?)""",
        (agent_id, broker, "v1", "127.0.0.1", "test", utc_now_iso_z()),
    )
    conn.commit()
    conn.close()


class _GatewayTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.agent_id = _create_agent()

    def tearDown(self):
        self.tmp.cleanup()


class TestAccountTypeNormalization(_GatewayTestCase):
    def test_real_maps_to_live(self):
        """Rules written before the gateway landed say 'real'; they must behave
        as their owner asked rather than silently simulating."""
        from execution.gateway import LIVE, normalize_account_type
        self.assertEqual(normalize_account_type("real"), LIVE)

    def test_known_modes_pass_through(self):
        from execution.gateway import normalize_account_type
        for value in ("simulator", "shadow", "live"):
            self.assertEqual(normalize_account_type(value), value)

    def test_unknown_and_empty_fall_back_to_simulator(self):
        from execution.gateway import normalize_account_type
        self.assertEqual(normalize_account_type("nonsense"), "simulator")
        self.assertEqual(normalize_account_type(None), "simulator")


class TestLiveRefusal(_GatewayTestCase):
    def test_live_without_gateway_is_refused(self):
        from execution.gateway import NOT_CONFIGURED, live_refusal_reason
        self.assertEqual(live_refusal_reason(self.agent_id, "live"), NOT_CONFIGURED)

    def test_live_with_account_but_no_credentials_is_refused(self):
        from execution.gateway import NOT_CONFIGURED_NO_CREDS, live_refusal_reason
        _add_broker_account(self.agent_id, creds=False)
        self.assertEqual(live_refusal_reason(self.agent_id, "live"),
                         NOT_CONFIGURED_NO_CREDS)

    def test_live_without_accepted_tcs_is_refused(self):
        """Consent is recorded per broker. routes_execution only checks it when
        switching the ACCOUNT's mode, so routing live off the rule's
        account_type must check it too or consent is bypassable."""
        from execution.gateway import NOT_ACCEPTED_TCS, live_refusal_reason
        _add_broker_account(self.agent_id, creds=True)
        self.assertEqual(live_refusal_reason(self.agent_id, "live"), NOT_ACCEPTED_TCS)

    def test_live_with_usable_gateway_and_consent_is_allowed(self):
        from execution.gateway import live_refusal_reason
        _add_broker_account(self.agent_id, creds=True)
        _accept_tcs(self.agent_id, "alpaca")
        self.assertIsNone(live_refusal_reason(self.agent_id, "live"))

    def test_consent_for_a_different_broker_does_not_count(self):
        from execution.gateway import NOT_ACCEPTED_TCS, live_refusal_reason
        _add_broker_account(self.agent_id, broker="alpaca", creds=True)
        _accept_tcs(self.agent_id, "binance")
        self.assertEqual(live_refusal_reason(self.agent_id, "live"), NOT_ACCEPTED_TCS)

    def test_simulator_and_shadow_never_refused(self):
        """Both always have somewhere to land, so neither needs a gateway."""
        from execution.gateway import live_refusal_reason
        self.assertIsNone(live_refusal_reason(self.agent_id, "simulator"))
        self.assertIsNone(live_refusal_reason(self.agent_id, "shadow"))

    def test_legacy_real_is_gated_like_live(self):
        from execution.gateway import NOT_CONFIGURED, live_refusal_reason
        self.assertEqual(live_refusal_reason(self.agent_id, "real"), NOT_CONFIGURED)


class TestIbkrCredentialShape(_GatewayTestCase):
    """IBKR has no key/secret — its gateway session is the credential — so
    "usable" means a gateway URL and account id instead."""

    def _add_ibkr(self, creds: dict) -> None:
        from execution.crypto import encrypt_credentials
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (self.agent_id, "ibkr", "live", encrypt_credentials(creds),
             utc_now_iso_z(), utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

    def test_gateway_url_and_account_id_count_as_usable(self):
        from execution.gateway import active_broker_account, _has_usable_credentials
        self._add_ibkr({"gateway_url": "https://gw:5000/v1/api", "account_id": "DU1"})
        self.assertTrue(_has_usable_credentials(active_broker_account(self.agent_id)))

    def test_missing_account_id_is_not_usable(self):
        from execution.gateway import active_broker_account, _has_usable_credentials
        self._add_ibkr({"gateway_url": "https://gw:5000/v1/api"})
        self.assertFalse(_has_usable_credentials(active_broker_account(self.agent_id)))

    def test_alpaca_style_key_secret_does_not_satisfy_ibkr(self):
        from execution.gateway import active_broker_account, _has_usable_credentials
        self._add_ibkr({"key": "k", "secret": "s"})
        self.assertFalse(_has_usable_credentials(active_broker_account(self.agent_id)))

    def test_live_refusal_mentions_reconnecting_when_ibkr_is_half_configured(self):
        from execution.gateway import NOT_CONFIGURED_NO_CREDS, live_refusal_reason
        self._add_ibkr({"gateway_url": "https://gw:5000/v1/api"})
        _accept_tcs(self.agent_id, "ibkr")
        self.assertEqual(live_refusal_reason(self.agent_id, "live"),
                         NOT_CONFIGURED_NO_CREDS)


class TestGateChain(_GatewayTestCase):
    """evaluate_execution_gates must surface the refusal as a skip_reason."""

    def _gates(self, account_type: str):
        from automation import evaluate_execution_gates
        config = {"auto_execute": 1, "account_type": account_type,
                  "min_confidence": 0.1, "size_usd": 100}
        return evaluate_execution_gates(config, self.agent_id, "BTC", "crypto",
                                        "buy", 0.9, 50_000.0)

    def test_live_without_gateway_skips_with_configure_message(self):
        from execution.gateway import NOT_CONFIGURED
        self.assertEqual(self._gates("live")["skip_reason"], NOT_CONFIGURED)

    def test_auto_execute_off_still_wins(self):
        """Ordering matters: an unarmed rule reports that, not a gateway error."""
        from automation import evaluate_execution_gates
        config = {"auto_execute": 0, "account_type": "live", "min_confidence": 0.1,
                  "size_usd": 100}
        gates = evaluate_execution_gates(config, self.agent_id, "BTC", "crypto",
                                         "buy", 0.9, 50_000.0)
        self.assertEqual(gates["skip_reason"], "auto_execute off")

    def test_simulator_passes_the_gateway_gate(self):
        self.assertIsNone(self._gates("simulator")["skip_reason"])


class TestFillRouting(_GatewayTestCase):
    """_execute_for_account_type sends each mode to the right place."""

    def _execute(self, account_type: str):
        from automation import _execute_for_account_type
        result: dict = {}
        signal_id, skip = _execute_for_account_type(
            {"account_type": account_type}, self.agent_id, "BTC", "crypto",
            "buy", 0.01, 50_000.0, None, None, result)
        return signal_id, skip, result

    def test_simulator_never_contacts_a_broker(self):
        with patch("execution.gateway.submit_live") as live, \
             patch("execution.gateway.submit_shadow") as shadow:
            signal_id, skip, result = self._execute("simulator")
        self.assertIsNotNone(signal_id, msg=f"simulator fill failed: {skip}")
        self.assertEqual(result["execution_mode"], "simulator")
        live.assert_not_called()
        shadow.assert_not_called()

    def test_shadow_writes_the_ledger_and_never_routes_live(self):
        with patch("execution.gateway.submit_live") as live:
            signal_id, skip, result = self._execute("shadow")
        self.assertIsNotNone(signal_id, msg=f"shadow fill failed: {skip}")
        self.assertEqual(result["execution_mode"], "shadow")
        live.assert_not_called()

    def test_shadow_without_gateway_is_plain_simulation(self):
        """No broker configured => submit_shadow returns None, trade still fills."""
        signal_id, skip, _ = self._execute("shadow")
        self.assertIsNotNone(signal_id)
        self.assertIsNone(skip)

    def test_live_rejection_leaves_no_position(self):
        """The broker is authoritative in live: a rejection must not create a
        platform position out of thin air."""
        from execution.base import Order, OrderStatus
        rejected = Order(agent_id=self.agent_id, symbol="BTC", market="crypto",
                         side="buy", quantity=0.01, price=50_000.0)
        rejected.status = OrderStatus.REJECTED
        rejected.error_message = "insufficient buying power"

        _add_broker_account(self.agent_id, creds=True)
        _accept_tcs(self.agent_id, "alpaca")
        with patch("execution.gateway.submit_live", return_value=rejected):
            signal_id, skip, _ = self._execute("live")

        self.assertIsNone(signal_id)
        self.assertIn("insufficient buying power", skip)

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM positions WHERE agent_id = ?",
                       (self.agent_id,))
        self.assertEqual(dict(cursor.fetchone())["n"], 0)
        conn.close()

    def test_live_fill_mirrors_broker_quantity_into_the_ledger(self):
        """A partial fill must land in the ledger at the filled size, not the
        requested size, or the platform and the broker disagree."""
        from execution.base import Order, OrderStatus
        filled = Order(agent_id=self.agent_id, symbol="BTC", market="crypto",
                       side="buy", quantity=0.01, price=50_000.0)
        filled.status = OrderStatus.FILLED
        filled.filled_qty = 0.004
        filled.broker = "alpaca"
        filled.broker_order_id = "abc-123"

        _add_broker_account(self.agent_id, creds=True)
        _accept_tcs(self.agent_id, "alpaca")
        with patch("execution.gateway.submit_live", return_value=filled):
            signal_id, skip, result = self._execute("live")

        self.assertIsNotNone(signal_id, msg=f"live mirror failed: {skip}")
        self.assertEqual(result["broker_order_id"], "abc-123")

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity FROM positions WHERE agent_id = ? AND symbol = 'BTC'",
            (self.agent_id,))
        self.assertAlmostEqual(dict(cursor.fetchone())["quantity"], 0.004, places=6)
        conn.close()


class TestBrokerEndpointPinning(_GatewayTestCase):
    """The rule's mode picks the venue — never the stored broker_accounts row.

    router._build_real_broker reads account["execution_mode"] to choose the
    sandbox vs the live endpoint. An account the user once flipped to live
    would therefore send a REAL order for a rule that asked for shadow. These
    tests pin the endpoint to the mode actually being executed.
    """

    def test_shadow_uses_the_sandbox_even_when_account_says_live(self):
        from execution.base import ExecutionMode
        from execution.gateway import _broker_for
        account = {"agent_id": self.agent_id, "broker": "alpaca",
                   "execution_mode": "live", "credentials_enc": ""}
        broker = _broker_for(account, ExecutionMode.SHADOW)
        self.assertTrue(broker._paper,
                        "shadow must never reach the live Alpaca endpoint")

    def test_live_uses_the_real_endpoint_even_when_account_says_shadow(self):
        from execution.base import ExecutionMode
        from execution.gateway import _broker_for
        account = {"agent_id": self.agent_id, "broker": "alpaca",
                   "execution_mode": "shadow", "credentials_enc": ""}
        broker = _broker_for(account, ExecutionMode.LIVE)
        self.assertFalse(broker._paper,
                         "live must reach the real endpoint the user asked for")

    def test_binance_shadow_uses_testnet_when_account_says_live(self):
        from execution.base import ExecutionMode
        from execution.gateway import _broker_for
        account = {"agent_id": self.agent_id, "broker": "binance",
                   "execution_mode": "live", "credentials_enc": ""}
        broker = _broker_for(account, ExecutionMode.SHADOW)
        self.assertTrue(broker._testnet,
                        "shadow must never reach the live Binance endpoint")


if __name__ == "__main__":
    unittest.main()


class TestGatewayHealth(_GatewayTestCase):
    """Credentials on file is not the same as the venue accepting orders."""

    def test_no_gateway_reports_unconfigured(self):
        from execution.gateway import gateway_health
        h = gateway_health(self.agent_id)
        self.assertFalse(h["configured"])
        self.assertIn("no trading gateway", h["detail"])

    def test_undecryptable_credentials_report_not_ok(self):
        from execution.gateway import gateway_health
        _add_broker_account(self.agent_id, creds=False)
        h = gateway_health(self.agent_id)
        self.assertTrue(h["configured"])
        self.assertFalse(h["ok"])
        self.assertIn("cannot be decrypted", h["detail"])

    def test_keysecret_broker_is_configured_but_not_probed(self):
        """Alpaca has no session to check, and we will not send a live order
        just to run a health check."""
        from execution.gateway import gateway_health
        _add_broker_account(self.agent_id, broker="alpaca", creds=True)
        h = gateway_health(self.agent_id)
        self.assertTrue(h["configured"])
        self.assertFalse(h["checked"])
        self.assertIsNone(h["ok"])

    def _add_ibkr_account(self):
        from execution.crypto import encrypt_credentials
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (self.agent_id, "ibkr", "live",
             encrypt_credentials({"gateway_url": "https://gw/v1/api", "account_id": "DU1"}),
             utc_now_iso_z(), utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

    def test_ibkr_healthy_session_reports_ok(self):
        from unittest.mock import patch
        from execution.gateway import gateway_health
        self._add_ibkr_account()
        healthy = {"ok": True, "detail": "", "paper": True, "account_id": "DU1"}
        with patch("execution.gateway._run_coro", return_value=healthy):
            h = gateway_health(self.agent_id)
        self.assertTrue(h["checked"])
        self.assertTrue(h["ok"])

    def test_ibkr_lapsed_session_reports_the_reason(self):
        from unittest.mock import patch
        from execution.gateway import gateway_health
        self._add_ibkr_account()
        lapsed = {"ok": False, "detail": "gateway session is not authenticated",
                  "paper": True, "account_id": "DU1"}
        with patch("execution.gateway._run_coro", return_value=lapsed):
            h = gateway_health(self.agent_id)
        self.assertTrue(h["checked"])
        self.assertFalse(h["ok"])
        self.assertIn("not authenticated", h["detail"])

    def test_probe_failure_never_raises(self):
        from unittest.mock import patch
        from execution.gateway import gateway_health
        self._add_ibkr_account()
        with patch("execution.gateway._run_coro", side_effect=RuntimeError("boom")):
            h = gateway_health(self.agent_id)
        self.assertFalse(h["ok"])
        self.assertIn("health check failed", h["detail"])


class TestGatewayFailureAlert(_GatewayTestCase):
    """A live rule that stops filling must not do so silently."""

    def test_live_rejection_raises_an_alert(self):
        from unittest.mock import patch
        from execution.base import Order, OrderStatus
        from automation import _execute_for_account_type

        rejected = Order(agent_id=self.agent_id, symbol="BTC", market="crypto",
                         side="buy", quantity=0.01, price=50_000.0)
        rejected.status = OrderStatus.REJECTED
        rejected.error_message = "gateway unreachable: connection refused"

        _add_broker_account(self.agent_id, creds=True)
        _accept_tcs(self.agent_id, "alpaca")
        with patch("execution.gateway.submit_live", return_value=rejected), \
             patch("alerts.send_alert") as alert:
            signal_id, skip = _execute_for_account_type(
                {"account_type": "live"}, self.agent_id, "BTC", "crypto",
                "buy", 0.01, 50_000.0, None, None, {})

        self.assertIsNone(signal_id)
        alert.assert_called_once()
        self.assertEqual(alert.call_args[0][1], "gateway_down")
        self.assertEqual(alert.call_args[0][2], "gateway_down_live_order_failed")
        self.assertIn("connection refused", alert.call_args[0][3]["reason"])

    def test_a_simulator_rule_never_alerts(self):
        from unittest.mock import patch
        from automation import _execute_for_account_type
        with patch("alerts.send_alert") as alert:
            _execute_for_account_type({"account_type": "simulator"}, self.agent_id,
                                      "BTC", "crypto", "buy", 0.01, 50_000.0,
                                      None, None, {})
        alert.assert_not_called()


class TestKeepalive(_GatewayTestCase):
    """The IBKR session keepalive sweep (worker task gateway_keepalive)."""

    def _add_ibkr(self, agent_id=None):
        from execution.crypto import encrypt_credentials
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO broker_accounts
               (agent_id, broker, execution_mode, credentials_enc, is_active, created_at, updated_at)
               VALUES (?,?,?,?,1,?,?)""",
            (agent_id or self.agent_id, "ibkr", "live",
             encrypt_credentials({"gateway_url": "https://gw/v1/api", "account_id": "DU1"}),
             utc_now_iso_z(), utc_now_iso_z()),
        )
        conn.commit()
        conn.close()

    def test_no_ibkr_accounts_is_a_free_noop(self):
        from unittest.mock import patch
        from execution.gateway import keepalive_tick
        _add_broker_account(self.agent_id, broker="alpaca", creds=True)  # not ibkr
        with patch("execution.gateway._run_coro") as rc:
            out = keepalive_tick()
        self.assertEqual(out, {"accounts": 0, "alive": 0, "revived": 0, "dead": 0})
        rc.assert_not_called()

    def test_healthy_session_counts_alive_and_never_alerts(self):
        from unittest.mock import patch
        from execution.gateway import keepalive_tick
        self._add_ibkr()
        seq = iter([True, {"ok": True, "reachable": True}])
        with patch("execution.gateway._run_coro", side_effect=lambda c: next(seq)), \
             patch("alerts.send_alert") as alert:
            out = keepalive_tick()
        self.assertEqual((out["alive"], out["dead"]), (1, 0))
        alert.assert_not_called()

    def test_lapsed_session_revived_by_reauth_does_not_alert(self):
        from unittest.mock import patch
        from execution.gateway import keepalive_tick
        self._add_ibkr()
        seq = iter([
            True,                                        # tickle
            {"ok": False, "reachable": True},            # status: lapsed
            True,                                        # reauthenticate
            {"ok": True, "reachable": True},             # status: back
        ])
        with patch("execution.gateway._run_coro", side_effect=lambda c: next(seq)), \
             patch("alerts.send_alert") as alert:
            out = keepalive_tick()
        self.assertEqual((out["alive"], out["revived"], out["dead"]), (1, 1, 0))
        alert.assert_not_called()

    def test_dead_session_alerts_the_owner_once_per_day(self):
        from unittest.mock import patch
        from execution.gateway import keepalive_tick
        self._add_ibkr()
        def seq_factory():
            return iter([
                True,                                              # tickle
                {"ok": False, "reachable": True, "detail": "not authenticated"},
                False,                                             # reauth fails
            ])
        seq = seq_factory()
        with patch("execution.gateway._run_coro", side_effect=lambda c: next(seq)), \
             patch("alerts.send_alert") as alert:
            out = keepalive_tick()
        self.assertEqual(out["dead"], 1)
        alert.assert_called_once()
        self.assertEqual(alert.call_args[0][1], "gateway_down")
        # per-day dedupe key so a dead-all-day session is one alert, not 24+
        self.assertIn("gateway_session:", alert.call_args[1]["dedupe_key"])

    def test_one_broken_account_does_not_stop_the_sweep(self):
        from unittest.mock import patch
        from execution.gateway import keepalive_tick
        other = _create_agent("gw-agent-2")
        self._add_ibkr()
        self._add_ibkr(agent_id=other)
        calls = {"n": 0}
        def flaky(coro):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")             # first account explodes
            # remaining calls serve the second account: tickle then status
            return True if calls["n"] == 2 else {"ok": True, "reachable": True}
        with patch("execution.gateway._run_coro", side_effect=flaky), \
             patch("alerts.send_alert"):
            out = keepalive_tick()
        self.assertEqual(out["accounts"], 2)
        self.assertEqual(out["alive"], 1, "second account still processed")
        self.assertEqual(out["dead"], 1)
