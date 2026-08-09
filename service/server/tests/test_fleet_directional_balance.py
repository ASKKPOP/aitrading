"""Directional-balance guard in fleet composition (Finding L2).

A fleet used to be able to stack same-direction correlated positions in one
asset class (e.g. 2 crypto shorts + 1 crypto long), so a single broad tape move
whipsawed the whole sleeve in lockstep. `_select_from_eligible` now keeps each
market directionally balanced in the diversity pass (majority − minority ≤ 1),
while still reaching N (pass 2 fills regardless when balance isn't achievable).
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import unittest

from symbol_research import _select_from_eligible


def _t(market: str, symbol: str, direction: str | None):
    return {"market": market, "symbol": symbol, "direction": direction}


def _dir_counts(picked, market):
    longs = sum(1 for p in picked if p["market"] == market and p["direction"] == "long")
    shorts = sum(1 for p in picked if p["market"] == market and p["direction"] == "short")
    return longs, shorts


class DirectionalBalanceTests(unittest.TestCase):
    # score order (highest first): 3 crypto shorts, 1 crypto long, 1 futures long
    ELIGIBLE = [
        _t("crypto", "ZEC", "short"),
        _t("crypto", "SOL", "short"),
        _t("crypto", "BTC", "short"),
        _t("crypto", "ETH", "long"),
        _t("futures", "CL", "long"),
    ]

    def test_guard_balances_the_crypto_sleeve(self):
        picked = _select_from_eligible(self.ELIGIBLE, 3, dir_balance=True)
        self.assertEqual(len(picked), 3)
        longs, shorts = _dir_counts(picked, "crypto")
        # majority − minority ≤ 1: never a fully one-directional crypto sleeve
        self.assertLessEqual(abs(longs - shorts), 1)
        self.assertGreaterEqual(longs, 1)  # a long got pulled in over a 2nd short

    def test_guard_off_stacks_same_direction(self):
        picked = _select_from_eligible(self.ELIGIBLE, 3, dir_balance=False)
        longs, shorts = _dir_counts(picked, "crypto")
        # old behaviour: two crypto shorts, no long — the imbalance L2 flagged
        self.assertEqual((longs, shorts), (0, 2))

    def test_guard_changes_the_pick(self):
        on = {(p["market"], p["symbol"]) for p in _select_from_eligible(self.ELIGIBLE, 3, True)}
        off = {(p["market"], p["symbol"]) for p in _select_from_eligible(self.ELIGIBLE, 3, False)}
        self.assertNotEqual(on, off)

    def test_best_effort_two_one_is_allowed(self):
        # only 3 crypto theses (2 short 1 long) — 2-1 is the best achievable, and allowed
        elig = [_t("crypto", "ZEC", "short"), _t("crypto", "ETH", "long"), _t("crypto", "SOL", "short")]
        picked = _select_from_eligible(elig, 5, dir_balance=True)
        self.assertEqual(len(picked), 3)
        longs, shorts = _dir_counts(picked, "crypto")
        self.assertEqual((longs, shorts), (1, 2))

    def test_bearish_only_batch_still_reaches_n(self):
        # nothing to balance against → N-priority fills all shorts (pass 2)
        elig = [_t("crypto", "ZEC", "short"), _t("crypto", "SOL", "short"), _t("crypto", "BTC", "short")]
        picked = _select_from_eligible(elig, 3, dir_balance=True)
        self.assertEqual(len(picked), 3)

    def test_one_way_book_across_markets_is_braked(self):
        """Per-market balance says nothing about ES + a mega-cap + BTC all
        long — four markets, one bet. The diversity pass keeps the WHOLE book
        within ceil(n/3) of neutral before it starts spending slots on a fifth
        instance of the same directional view."""
        elig = [
            _t("crypto", "BTC", "long"),
            _t("us-stock", "AAPL", "long"),
            _t("futures", "ES", "long"),
            _t("forex", "EURUSD", "long"),
            _t("crypto", "ETH", "short"),
            _t("us-stock", "PFE", "short"),
        ]
        picked = _select_from_eligible(elig, 4, dir_balance=True)
        self.assertEqual(len(picked), 4)
        longs = sum(1 for p in picked if p["direction"] == "long")
        shorts = sum(1 for p in picked if p["direction"] == "short")
        self.assertLessEqual(abs(longs - shorts), 2)  # ceil(4/3) = 2
        self.assertGreaterEqual(shorts, 1)

    def test_one_way_only_batch_still_reaches_n_across_markets(self):
        """The brake is a preference, never a reason to under-fill: with
        nothing to balance against, pass 2 still delivers N."""
        elig = [_t("crypto", "BTC", "long"), _t("us-stock", "AAPL", "long"),
                _t("futures", "ES", "long"), _t("forex", "EURUSD", "long")]
        self.assertEqual(len(_select_from_eligible(elig, 4, dir_balance=True)), 4)

    def test_non_directional_markets_unconstrained(self):
        # polymarket theses carry no long/short — never blocked by the guard
        elig = [_t("polymarket", "A", None), _t("polymarket", "B", None), _t("polymarket", "C", None)]
        picked = _select_from_eligible(elig, 3, dir_balance=True)
        self.assertEqual(len(picked), 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
