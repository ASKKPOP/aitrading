"""Money tests for isolated-margin leverage on POST /api/signals/realtime.

The manual terminal path must mirror execute_paper_trade's model exactly:
  open  — debit MARGIN = notional/L + fee (L=1 ⇒ full notional, byte-identical
          to the pre-leverage code)
  close — return the escrowed margin using the POSITION's leverage
          (entry×qty/pos_lev) + realized P&L − fee; legacy L=1 rows keep the
          exact old credit expressions (trade_value − fee / (2E−P)q − fee)
  adds  — debit at the CALLER's leverage, position row keeps its original
          leverage (mixed-leverage add semantics, same as automation)
"""

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
from fees import TRADE_FEE_RATE
from routes import create_app

# A Tuesday within NYSE market hours (10:00 AM ET).
_MARKET_TS = "2024-01-02T15:00:00Z"
_BALANCE = 100000.0
_NO_FETCH = {"ALLOW_SYNC_PRICE_FETCH_IN_API": "false"}


class RealtimeLeverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "test.db")
        database.init_database()
        self.client = TestClient(create_app())
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "lev-agent", "password": "pw123",
                  "initial_balance": _BALANCE},
        )
        assert resp.status_code == 200, resp.text
        self.agent_id = resp.json()["agent_id"]
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ── helpers ────────────────────────────────────────────────────────────

    def _trade(self, action: str, price: float, qty: float,
               leverage=None, expect: int = 200, headers=None):
        body = {"market": "us-stock", "action": action, "symbol": "AAPL",
                "price": price, "quantity": qty, "executed_at": _MARKET_TS}
        if leverage is not None:
            body["leverage"] = leverage
        with patch.dict(os.environ, _NO_FETCH):
            resp = self.client.post("/api/signals/realtime", json=body,
                                    headers=headers or self.headers)
        self.assertEqual(resp.status_code, expect, resp.text)
        return resp

    def _cash(self, agent_id=None) -> float:
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT cash FROM agents WHERE id = ?",
                        (agent_id or self.agent_id,))
            return float(cur.fetchone()["cash"])
        finally:
            conn.close()

    def _position(self, agent_id=None):
        conn = database.get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT quantity, entry_price, leverage FROM positions "
                "WHERE agent_id = ? AND symbol = 'AAPL' AND run_id IS NULL",
                (agent_id or self.agent_id,))
            return cur.fetchone()
        finally:
            conn.close()

    # ── open: margin debit ─────────────────────────────────────────────────

    def test_open_buy_debits_margin_and_stamps_leverage(self) -> None:
        price, qty, lev = 150.0, 4.0, 5.0
        notional = price * qty
        fee = notional * TRADE_FEE_RATE
        self._trade("buy", price, qty, leverage=lev)
        self.assertEqual(self._cash(), _BALANCE - (notional / lev + fee))
        pos = self._position()
        self.assertIsNotNone(pos)
        self.assertEqual(float(pos["leverage"]), lev)
        self.assertEqual(float(pos["quantity"]), qty)

    def test_open_short_debits_margin(self) -> None:
        price, qty, lev = 200.0, 3.0, 4.0
        notional = price * qty
        fee = notional * TRADE_FEE_RATE
        self._trade("short", price, qty, leverage=lev)
        self.assertEqual(self._cash(), _BALANCE - (notional / lev + fee))
        pos = self._position()
        self.assertEqual(float(pos["quantity"]), -qty)
        self.assertEqual(float(pos["leverage"]), lev)

    def test_margin_makes_bigger_notional_affordable(self) -> None:
        # notional 400k > cash 100k, but margin 400k/5 = 80k + fee fits.
        price, qty, lev = 400.0, 1000.0, 5.0
        notional = price * qty
        fee = notional * TRADE_FEE_RATE
        self._trade("buy", price, qty, leverage=lev)
        self.assertEqual(self._cash(), _BALANCE - (notional / lev + fee))

    def test_insufficient_margin_rejected(self) -> None:
        # margin 2M/10 = 200k > 100k cash even at max leverage.
        resp = self._trade("buy", 2000.0, 1000.0, leverage=10.0, expect=400)
        self.assertIn("Insufficient cash", resp.json()["detail"])

    # ── close: margin return at the POSITION's leverage ───────────────────

    def test_sell_returns_margin_plus_pnl(self) -> None:
        entry, exit_p, qty, lev = 100.0, 110.0, 10.0, 5.0
        self._trade("buy", entry, qty, leverage=lev)
        cash_after_open = self._cash()
        self._trade("sell", exit_p, qty)
        fee = exit_p * qty * TRADE_FEE_RATE
        credit = entry * qty / lev + (exit_p - entry) * qty - fee
        self.assertEqual(self._cash(), cash_after_open + credit)
        self.assertIsNone(self._position())

    def test_cover_returns_margin_plus_pnl(self) -> None:
        entry, exit_p, qty, lev = 100.0, 90.0, 10.0, 4.0
        self._trade("short", entry, qty, leverage=lev)
        cash_after_open = self._cash()
        self._trade("cover", exit_p, qty)
        fee = exit_p * qty * TRADE_FEE_RATE
        credit = entry * qty / lev + (entry - exit_p) * qty - fee
        self.assertEqual(self._cash(), cash_after_open + credit)
        self.assertIsNone(self._position())

    def test_partial_close_returns_partial_margin(self) -> None:
        entry, exit_p, lev = 100.0, 105.0, 5.0
        self._trade("buy", entry, 10.0, leverage=lev)
        cash_after_open = self._cash()
        self._trade("sell", exit_p, 4.0)
        fee = exit_p * 4.0 * TRADE_FEE_RATE
        credit = entry * 4.0 / lev + (exit_p - entry) * 4.0 - fee
        self.assertEqual(self._cash(), cash_after_open + credit)
        pos = self._position()
        self.assertEqual(float(pos["quantity"]), 6.0)
        self.assertEqual(float(pos["leverage"]), lev)

    # ── L=1 byte-identity with the pre-leverage code ───────────────────────

    def test_l1_buy_sell_matches_legacy_formulas_exactly(self) -> None:
        # Expected values use the EXACT legacy expressions (trade_value + fee
        # debit / trade_value - fee credit) — not the margin formulas.
        price, qty = 150.0, 2.0
        trade_value = price * qty
        fee = trade_value * TRADE_FEE_RATE
        self._trade("buy", price, qty)          # leverage omitted
        self.assertEqual(self._cash(), _BALANCE - (trade_value + fee))
        exit_p = 160.0
        exit_value = exit_p * qty
        exit_fee = exit_value * TRADE_FEE_RATE
        self._trade("sell", exit_p, qty)
        self.assertEqual(
            self._cash(),
            _BALANCE - (trade_value + fee) + (exit_value - exit_fee))

    def test_l1_short_cover_matches_legacy_formulas_exactly(self) -> None:
        entry, exit_p, qty = 100.0, 95.0, 3.0
        trade_value = entry * qty
        fee = trade_value * TRADE_FEE_RATE
        self._trade("short", entry, qty)        # leverage omitted
        self.assertEqual(self._cash(), _BALANCE - (trade_value + fee))
        exit_fee = exit_p * qty * TRADE_FEE_RATE
        cover_credit = ((2 * entry) - exit_p) * qty - exit_fee
        self._trade("cover", exit_p, qty)
        self.assertEqual(
            self._cash(), _BALANCE - (trade_value + fee) + cover_credit)

    def test_explicit_l1_identical_to_omitted(self) -> None:
        # Second agent trades the same sequence with leverage=1.0 explicit;
        # cash trajectories must be exactly equal.
        resp = self.client.post(
            "/api/claw/agents/selfRegister",
            json={"name": "lev-agent-b", "password": "pw123",
                  "initial_balance": _BALANCE})
        other_id = resp.json()["agent_id"]
        other_headers = {"Authorization": f"Bearer {resp.json()['token']}"}
        self._trade("buy", 150.0, 2.0)
        self._trade("buy", 150.0, 2.0, leverage=1.0, headers=other_headers)
        self.assertEqual(self._cash(), self._cash(other_id))
        self._trade("sell", 160.0, 2.0)
        self._trade("sell", 160.0, 2.0, leverage=1.0, headers=other_headers)
        self.assertEqual(self._cash(), self._cash(other_id))

    # ── clamps ─────────────────────────────────────────────────────────────

    def test_leverage_clamped_to_10(self) -> None:
        price, qty = 100.0, 5.0
        notional = price * qty
        fee = notional * TRADE_FEE_RATE
        self._trade("buy", price, qty, leverage=100.0)
        self.assertEqual(self._cash(), _BALANCE - (notional / 10.0 + fee))
        self.assertEqual(float(self._position()["leverage"]), 10.0)

    def test_leverage_below_1_clamped_to_1(self) -> None:
        price, qty = 100.0, 5.0
        notional = price * qty
        fee = notional * TRADE_FEE_RATE
        self._trade("buy", price, qty, leverage=0.5)
        self.assertEqual(self._cash(), _BALANCE - (notional + fee))
        self.assertEqual(float(self._position()["leverage"]), 1.0)

    # ── mixed-leverage adds (mirror execute_paper_trade) ───────────────────

    def test_add_keeps_position_leverage_debits_at_caller_leverage(self) -> None:
        # Open 10 @100 at 5x, add 10 @110 at 2x: second debit is notional/2;
        # the position row keeps 5x and the close returns avg_entry×qty/5.
        self._trade("buy", 100.0, 10.0, leverage=5.0)
        cash_after_first = self._cash()
        self._trade("buy", 110.0, 10.0, leverage=2.0)
        add_notional = 110.0 * 10.0
        add_fee = add_notional * TRADE_FEE_RATE
        self.assertEqual(self._cash(),
                         cash_after_first - (add_notional / 2.0 + add_fee))
        pos = self._position()
        self.assertEqual(float(pos["leverage"]), 5.0)
        avg_entry = (100.0 * 10.0 + 110.0 * 10.0) / 20.0
        self.assertEqual(float(pos["entry_price"]), avg_entry)
        cash_before_close = self._cash()
        self._trade("sell", 120.0, 20.0)
        close_fee = 120.0 * 20.0 * TRADE_FEE_RATE
        credit = avg_entry * 20.0 / 5.0 + (120.0 - avg_entry) * 20.0 - close_fee
        self.assertEqual(self._cash(), cash_before_close + credit)

    # ── polymarket guard ───────────────────────────────────────────────────

    def test_polymarket_rejects_leverage(self) -> None:
        with patch.dict(os.environ, _NO_FETCH):
            resp = self.client.post(
                "/api/signals/realtime",
                json={"market": "polymarket", "action": "buy",
                      "symbol": "some-market", "price": 0.5, "quantity": 10.0,
                      "executed_at": "now", "token_id": "123",
                      "leverage": 2.0},
                headers=self.headers)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("leverage", resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
