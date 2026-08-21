"""The research screen ENFORCED an advisory regime verdict (2026-08-21).

`regime.evaluate_market_regime()` stamps `enforced = REGIME_FILTER_ENABLED`
(default FALSE) and carries its own note: "bands are unvalidated placeholders
pending Phase-4 walk-forward; advisory-only until REGIME_FILTER_ENABLED".

Every consumer honours that — `automation._regime_blocks` returns None on
`not enforced` with the comment "advisory-only until the Phase-4 flip" — with
ONE exception: `symbol_research._read_overlays` read `allow_new_buys is False`
and handed it to `apply_gates` as a HARD gate on crypto longs.

Measured on prod at the 2026-08-21T12:21:42Z anchor, reproduced live:

    regime: 'panic'   allow_new_buys: False   ENFORCED: False
    reasons: ["unresolved volatility/liquidation shock"]
    fng_value: 72 (Greed)  vol_percentile: 56.7  crypto_composite: 72.7

    crypto universe 39 -> 17 dropped on liquidity -> 22 reached the gate
    -> ALL 22 scored direction "long" (crypto in a broad uptrend)
    -> ALL 22 gated to zero -> survivors: 0

Consequence: 3 of the last 8 research batches carried ZERO crypto theses,
`live_crypto_theses = 0`, and fleet 38 sat at 2 of 7 slots unable to build
for over an hour with $10k of crypto capital idle. The batch still reported
`survivors: 36, persisted: 36, llm: 36` — a partial, single-market blackout
looks exactly like success, so the 2026-08-07 burned-window guard
(`_release_unproductive_claim`, which needs survivors == 0) never fires.

This restores CANDIDATES, not trades. The desk still decides; the fee gate,
backtest gate, cooldowns and every downstream rail are untouched.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import symbol_research as sr


def _snap(*, allow_new_buys, enforced):
    return {"regime": "panic", "allow_new_buys": allow_new_buys,
            "enforced": enforced, "reasons": ["unresolved volatility shock"],
            "crypto_composite": {"score": 72.7}}


class RegimeOverlayRespectsEnforced(unittest.TestCase):
    """An advisory regime must not hard-gate the research screen."""

    def _overlays(self, snap):
        fake = type("M", (), {"evaluate_market_regime": staticmethod(
            lambda persist=False: snap)})
        with patch.dict(sys.modules, {"regime": fake}):
            return sr._read_overlays()

    # ---- the defect ----------------------------------------------------

    def test_advisory_panic_does_NOT_block_longs(self):
        """The live 12:21Z shape: panic, buys off, but enforced FALSE."""
        ov = self._overlays(_snap(allow_new_buys=False, enforced=False))
        self.assertFalse(
            ov["regime_blocks_longs"],
            "an advisory regime (enforced=False) must not gate the screen")

    def test_enforced_panic_DOES_block_longs(self):
        """When the Phase-4 flip is on, the gate must still bite."""
        ov = self._overlays(_snap(allow_new_buys=False, enforced=True))
        self.assertTrue(ov["regime_blocks_longs"])

    def test_enforced_but_buys_allowed_does_not_block(self):
        ov = self._overlays(_snap(allow_new_buys=True, enforced=True))
        self.assertFalse(ov["regime_blocks_longs"])

    def test_missing_enforced_key_does_not_block(self):
        """Fail-open toward candidate supply: an unreadable/absent `enforced`
        must not silently enforce — that is the defect being fixed."""
        ov = self._overlays({"regime": "panic", "allow_new_buys": False})
        self.assertFalse(ov["regime_blocks_longs"])

    def test_a_dead_regime_module_leaves_the_screen_open(self):
        boom = type("M", (), {"evaluate_market_regime": staticmethod(
            lambda persist=False: (_ for _ in ()).throw(RuntimeError("down")))})
        with patch.dict(sys.modules, {"regime": boom}):
            ov = sr._read_overlays()
        self.assertFalse(ov["regime_blocks_longs"])

    # ---- it must match the house pattern exactly -----------------------

    def test_it_agrees_with_automation_regime_blocks(self):
        """The order path and the screen must never disagree about whether
        the regime is in force — that divergence IS this bug."""
        import automation
        for allow, enf in ((False, False), (False, True), (True, True)):
            snap = _snap(allow_new_buys=allow, enforced=enf)
            screen = self._overlays(snap)["regime_blocks_longs"]
            order = automation._regime_blocks(snap, "buy") is not None
            self.assertEqual(screen, order,
                             f"screen/order disagree for allow={allow} "
                             f"enforced={enf}")

    # ---- end-to-end: the gate is what zeroed crypto --------------------

    def test_apply_gates_zeroes_a_long_only_when_blocking(self):
        self.assertEqual(
            sr.apply_gates(1.0, event_window=False, regime_blocks_longs=True,
                           direction="long", session_open=True), 0)
        self.assertGreater(
            sr.apply_gates(1.0, event_window=False, regime_blocks_longs=False,
                           direction="long", session_open=True), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
