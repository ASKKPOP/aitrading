"""Mark refresh must cover every market that can trade (2026-07-28).

Third time this shape has bitten:

  2026-07-23  the list was "crypto" alone. CL/ZC/ZS marks froze at entry, the
              fail-closed stop evaluator killed every futures run ~18 min in,
              and the fleet churned six CL replacements in 95 minutes.
  2026-07-28  the list was "crypto,futures,us-stock". forex was absent because
              the flat fee gate refused 100% of forex theses, so no forex mark
              had ever needed refreshing. Per-market fees removed that block
              and USDZAR froze the WHOLE fleet inside twenty minutes: mark
              stuck at 08:40:19, _zombie_pnl unable to value the position,
              marked_equity ok=False, 63 consecutive breaker_eval_failed ticks
              with two runs paused behind it.

The list must name every market that CAN HOLD A POSITION, not the ones that
happen to be trading today — a forgotten market fails at entry+staleness,
silently, long after the deploy that forgot it. That includes markets runs
cannot target: `options` is automatable=False, but a manual options position
needs a mark or the SL/TP watcher cannot see it. This test found that one on
its first run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import markets
import tasks


class RefreshCoversEveryTradeableMarket(unittest.TestCase):
    def _default(self):
        return {m.strip() for m in
                tasks.REFRESH_PRICED_MARKETS_DEFAULT.split(",") if m.strip()}

    def test_no_tradeable_market_is_left_without_marks(self):
        """The regression test proper: this fails the moment a new market
        becomes tradeable and nobody adds it here. It caught `options` the
        first time it ran."""
        missing = set()
        for m in markets.tradeable_markets():
            # polymarket prices settle through their own path, not the
            # position price refresh.
            if m == "polymarket":
                continue
            if m not in self._default():
                missing.add(m)
        self.assertEqual(missing, set(),
                         f"tradeable markets with no mark refresh: {sorted(missing)}")

    def test_forex_specifically(self):
        """The 2026-07-28 outage."""
        self.assertIn("forex", self._default())

    def test_futures_specifically(self):
        """The 2026-07-23 outage."""
        self.assertIn("futures", self._default())

    def test_a_manual_only_market_is_covered_too(self):
        """automatable=False does not mean position-free: a hand-opened
        options position still needs a mark for the SL/TP watcher."""
        import markets
        self.assertFalse(markets.get_spec("options").automatable)
        self.assertIn("options", self._default())

    def test_the_env_override_still_wins(self):
        """Operators must be able to narrow this during an incident."""
        import os
        from unittest.mock import patch
        with patch.dict(os.environ,
                        {"POSITION_PRICE_REFRESH_PRICED_MARKETS": "crypto"}):
            got = tasks._env_csv_set("POSITION_PRICE_REFRESH_PRICED_MARKETS",
                                     tasks.REFRESH_PRICED_MARKETS_DEFAULT)
        self.assertEqual(got, {"crypto"})


if __name__ == "__main__":
    unittest.main()
