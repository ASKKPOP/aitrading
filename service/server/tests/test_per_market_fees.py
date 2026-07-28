"""Per-market fee rates (2026-07-28).

One flat 0.1%/side was charged to every market — roughly right for a crypto
taker, badly wrong everywhere else, and damaging twice over:

  P&L        the desk paid $363.31 in fees across 140 legs in the week to
             2026-07-28 while 58 closed round trips netted +$14.88. The
             trading was approximately break-even; the fees were the loss.
  Selection  _fee_edge_skip needs a claimed move of 3x the round trip — >=
             2.40% at 0.1%/side. Of all 2,141 theses ever generated, 711
             (33%) could never clear it, and forex was 308 of 308: no FX run
             has ever opened a position on this platform.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import fees
import run_engine


def _on():
    """The table is dark by default; these tests are about what it does when
    it is ON."""
    return patch.dict("os.environ", {"FEE_PER_MARKET": "true"})


class DarkByDefault(unittest.TestCase):
    """Off, every market pays exactly what it paid before — that is what makes
    this safe to merge ahead of the flip."""

    def test_disabled_is_byte_identical_to_the_legacy_flat_rate(self):
        with patch.dict("os.environ", {"FEE_PER_MARKET": "false"}):
            for m in ("crypto", "futures", "forex", "us-stock", "a-stock", None):
                self.assertEqual(fees.fee_rate(m), fees.TRADE_FEE_RATE)

    def test_an_explicit_override_still_applies_while_dark(self):
        """One venue can be corrected without flipping the whole table."""
        with patch.dict("os.environ", {"FEE_PER_MARKET": "false"}), \
             patch("platform_settings.get_setting", return_value="0.0002"):
            self.assertAlmostEqual(fees.fee_rate("forex"), 0.0002)


class Rates(unittest.TestCase):
    def setUp(self):
        self._p = _on(); self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_crypto_is_a_perp_taker_not_a_spot_taker(self):
        self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)

    def test_every_table_market_is_cheaper_than_the_legacy_flat(self):
        for m in ("crypto", "futures", "forex", "us-stock", "a-stock", "polymarket"):
            self.assertLess(fees.fee_rate(m), fees.TRADE_FEE_RATE,
                            f"{m} should not still pay the crypto-taker rate")

    def test_unknown_market_falls_back_to_the_legacy_rate(self):
        """Charging too much only refuses trades — the safe direction."""
        self.assertEqual(fees.fee_rate("dogecoin-futures-9000"), fees.TRADE_FEE_RATE)
        self.assertEqual(fees.fee_rate(None), fees.TRADE_FEE_RATE)
        self.assertEqual(fees.fee_rate(""), fees.TRADE_FEE_RATE)

    def test_case_and_whitespace_tolerant(self):
        self.assertEqual(fees.fee_rate(" CRYPTO "), fees.fee_rate("crypto"))

    def test_round_trip_is_both_legs(self):
        self.assertAlmostEqual(fees.round_trip_rate("futures"),
                               fees.fee_rate("futures") * 2)


class OperatorOverride(unittest.TestCase):
    def setUp(self):
        self._p = _on(); self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_override_wins(self):
        with patch("platform_settings.get_setting", return_value="0.002"):
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.002)

    def test_blank_or_missing_falls_through(self):
        for v in ("", None):
            with patch("platform_settings.get_setting", return_value=v):
                self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)

    def test_garbage_falls_through(self):
        with patch("platform_settings.get_setting", return_value="free"):
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)

    def test_negative_is_refused(self):
        """A negative fee would pay the desk to trade."""
        with patch("platform_settings.get_setting", return_value="-0.01"):
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)

    def test_absurd_is_refused(self):
        """Above 10% is a typo, not a venue."""
        with patch("platform_settings.get_setting", return_value="0.5"):
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)

    def test_settings_failure_never_breaks_a_fill(self):
        with patch("platform_settings.get_setting", side_effect=RuntimeError("db")):
            self.assertAlmostEqual(fees.fee_rate("crypto"), 0.00045)


class GateUnblocksTheRealTheses(unittest.TestCase):
    """The live numbers that were permanently refused."""

    def setUp(self):
        self._p = _on(); self._p.start()

    def tearDown(self):
        self._p.stop()

    def _blocked(self, move, market):
        return run_engine._fee_edge_skip(move, market=market) is not None

    def test_forex_was_universally_blocked_at_the_flat_rate(self):
        for claim in (0.443, 0.6578, 0.6623, 1.2466, 2.00):
            self.assertTrue(self._blocked(claim, "unknown-market"),
                            f"{claim}% cleared the OLD flat hurdle unexpectedly")

    def test_forex_now_passes_at_a_realistic_fx_cost(self):
        for claim, sym in ((0.443, "AUDJPY"), (0.6623, "USDKRW"),
                           (1.2466, "USDZAR"), (2.00, "USDZAR")):
            self.assertFalse(self._blocked(claim, "forex"),
                             f"{sym} at {claim}% should now be tradeable")

    def test_the_zc_four_basis_point_miss_now_clears(self):
        """ZC claimed 2.37%: 2.37 x 0.25 = 0.5925% vs a 0.60% hurdle — refused
        by four hundredths of a percent, repeatedly, for hours."""
        self.assertTrue(self._blocked(2.37, "unknown-market"))
        self.assertFalse(self._blocked(2.37, "futures"))

    def test_a_genuinely_tiny_move_is_still_refused(self):
        """The gate must not become a rubber stamp — 0.02% cannot pay for
        even a cheap round trip."""
        self.assertTrue(self._blocked(0.02, "futures"))
        self.assertTrue(self._blocked(0.02, "crypto"))

    def test_crypto_hurdle_still_bites_where_it_should(self):
        # crypto round trip 0.09%, x3 = 0.27% required of the DISCOUNTED move
        self.assertTrue(self._blocked(1.0, "crypto"))    # 1.0 x .25 = 0.25%
        self.assertFalse(self._blocked(1.2, "crypto"))   # 1.2 x .25 = 0.30%

    def test_unknown_market_keeps_the_old_strict_hurdle(self):
        self.assertTrue(self._blocked(2.23, "unknown-market"))


class FillsChargeTheMarketRate(unittest.TestCase):
    """The rate existing is not the fix — the fill must USE it. Asserted on
    the multiplication, not on the word: a comment mentioning the legacy
    constant is not a bug, charging it is."""

    def _fee_math(self, fn):
        import inspect
        import re
        src = inspect.getsource(fn)
        # strip comments so prose about the old constant cannot fail this
        code = "\n".join(re.sub(r"#.*$", "", ln) for ln in src.splitlines())
        return code

    def test_execute_paper_trade_charges_the_market_rate(self):
        import automation
        code = self._fee_math(automation.execute_paper_trade)
        self.assertIn("fee_rate(market)", code)
        self.assertNotIn("* TRADE_FEE_RATE", code)

    def test_preview_mirror_charges_the_same_rate(self):
        """A mirror charging a different fee would refuse previews the real
        trade accepts."""
        import automation
        code = self._fee_math(automation._execution_feasibility)
        self.assertIn("fee_rate(market)", code)
        self.assertNotIn("TRADE_FEE_RATE", code)


if __name__ == "__main__":
    unittest.main()
