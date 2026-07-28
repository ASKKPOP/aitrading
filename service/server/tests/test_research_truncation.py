"""Stage-2 thesis batching (2026-07-28).

Prod evidence: **2,099 of 2,099 theses ever generated carry planner='fallback'**
— the LLM research layer had never once produced a usable thesis since it
shipped 2026-07-21. Every symbol the fleet has ever traded was chosen by the
`momentum + volume + volatility fit` heuristic.

Cause, reproduced live inside the prod container: `generate_theses` sent all 14
screened survivors in ONE call with max_tokens=2000. A thesis object costs ~300
tokens, so the reply needed ~4,200 and was cut mid-object at candidate ~11.
With no closing `]`, `_JSON_ARRAY_RE` matched nothing, `_parse_thesis_array`
returned [], and the per-symbol `else` handed **all 14** a fallback. Nothing
raised; the only visible signal was `'llm': 0` in the batch summary.

Two independent fixes, either one sufficient on its own — chunk small enough to
finish, and salvage the objects that did finish.
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

import symbol_research as sr


def _obj(sym, market="crypto"):
    return {"symbol": sym, "market": market, "direction": "long",
            "expected_move_pct": 3.5, "horizon_hours": 72, "confidence": 0.55,
            "thesis": "t", "risks": "r", "invalidation": "i"}


def _truncated(n_complete, next_sym="ORCL"):
    """A reply cut mid-object — exactly the shape prod produced."""
    body = ",\n".join(json.dumps(_obj(f"S{i}")) for i in range(n_complete))
    return '```json\n[\n' + body + ',\n  {\n    "symbol": "' + next_sym


class SalvageTruncatedReply(unittest.TestCase):
    def test_whole_array_still_wins_when_complete(self):
        text = "```json\n" + json.dumps([_obj("BTC"), _obj("ETH")]) + "\n```"
        got = sr._parse_thesis_array(text)
        self.assertEqual([g["symbol"] for g in got], ["BTC", "ETH"])

    def test_truncated_reply_yields_the_completed_objects(self):
        """The regression: this returned [] and cost every symbol its thesis."""
        got = sr._parse_thesis_array(_truncated(10))
        self.assertEqual(len(got), 10)
        self.assertEqual(got[0]["symbol"], "S0")

    def test_the_exact_prod_shape(self):
        """Cut at candidate 11 of 14 — 4,874 chars, no closing bracket."""
        text = _truncated(10, next_sym="ORCL")
        self.assertNotIn("]", text.split('"symbol": "ORCL')[-1])
        self.assertEqual(len(sr._parse_thesis_array(text)), 10)

    def test_braces_inside_prose_do_not_unbalance_the_scan(self):
        o = _obj("BTC")
        o["thesis"] = 'Breaks {resistance} and "holds" it {{'
        text = "[" + json.dumps(o) + ",\n  {\n   \"symbol\": \"CUT"
        got = sr._parse_thesis_array(text)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["symbol"], "BTC")

    def test_escaped_quote_inside_a_string(self):
        o = _obj("ETH")
        o["risks"] = 'a \\" b {'
        text = "[" + json.dumps(o) + ",\n {\"symbol\": \"CUT"
        self.assertEqual(len(sr._parse_thesis_array(text)), 1)

    def test_garbage_is_still_empty(self):
        self.assertEqual(sr._parse_thesis_array("no json here at all"), [])
        self.assertEqual(sr._parse_thesis_array(""), [])

    def test_partial_object_alone_yields_nothing(self):
        self.assertEqual(sr._parse_thesis_array('[{"symbol": "BTC"'), [])


class Batching(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in
                     ("FLEET_RESEARCH_BATCH_SIZE", "FLEET_RESEARCH_MAX_TOKENS")}

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_defaults_are_sized_for_the_measured_cost(self):
        """~300 tokens per thesis: 5 x 300 = 1,500, well inside 4,000."""
        self.assertEqual(sr._thesis_batch_size(), 5)
        self.assertEqual(sr._thesis_max_tokens(), 4000)
        self.assertGreater(sr._thesis_max_tokens(),
                           sr._thesis_batch_size() * 300 * 2,
                           "token budget must leave 2x headroom per batch")

    def test_chunking_covers_every_item_exactly_once(self):
        for n in range(0, 31):
            for size in (1, 3, 5, 14):
                chunks = sr._chunked(list(range(n)), size)
                self.assertEqual([x for c in chunks for x in c], list(range(n)))
                self.assertTrue(all(len(c) <= size for c in chunks))

    def test_bad_env_falls_back_to_defaults(self):
        os.environ["FLEET_RESEARCH_BATCH_SIZE"] = "not-a-number"
        os.environ["FLEET_RESEARCH_MAX_TOKENS"] = ""
        self.assertEqual(sr._thesis_batch_size(), 5)
        self.assertEqual(sr._thesis_max_tokens(), 4000)


class GenerateThesesWiring(unittest.TestCase):
    """The predicates existing is not the fix — generate_theses must USE them."""

    def setUp(self):
        import database
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()

    def tearDown(self):
        self.tmp.cleanup()

    def _survivors(self, n):
        return [{"symbol": f"S{i}", "market": "crypto", "eps_raw": None,
                 "momentum_sign": 1, "session_open": True,
                 "factors": {"mom_5d": .01, "mom_20d": .02,
                             "vol_daily_pct": 2.0, "vol_ratio": 1.1,
                             "last_ts": i, "composite": 0.5}}
                for i in range(n)]

    def test_fourteen_survivors_are_split_into_batches(self):
        calls = []

        def fake(prompt, **kw):
            rows = json.loads(prompt.split("CANDIDATES:\n")[1])
            calls.append((len(rows), kw.get("max_tokens")))
            return json.dumps([_obj(r["symbol"]) for r in rows])

        out = sr.generate_theses(self._survivors(14), generate_text=fake)
        self.assertEqual([c[0] for c in calls], [5, 5, 4],
                         "14 survivors must not go out as one 14-wide call")
        self.assertTrue(all(c[1] >= 4000 for c in calls))
        self.assertTrue(all(t["planner"] == "llm" for t in out),
                        "every survivor should get an LLM thesis")

    def test_a_truncated_batch_still_delivers_its_completed_objects(self):
        """The end-to-end regression: prod got 0 of 14; this must get most."""
        def fake(prompt, **kw):
            rows = json.loads(prompt.split("CANDIDATES:\n")[1])
            full = ",".join(json.dumps(_obj(r["symbol"])) for r in rows[:-1])
            return "[" + full + ',{"symbol":"' + rows[-1]["symbol"]

        out = sr.generate_theses(self._survivors(10), generate_text=fake)
        llm = [t for t in out if t["planner"] == "llm"]
        self.assertEqual(len(llm), 8, "4 of 5 per batch should survive")
        self.assertTrue(any(t["planner"] == "fallback" for t in out),
                        "the truncated tail still falls back, per symbol")

    def test_llm_failure_still_degrades_to_fallback(self):
        def boom(prompt, **kw):
            raise RuntimeError("provider down")

        out = sr.generate_theses(self._survivors(6), generate_text=boom)
        self.assertEqual(len(out), 6)
        self.assertTrue(all(t["planner"] == "fallback" for t in out))

    def test_no_survivors_makes_no_call(self):
        def fail(prompt, **kw):
            raise AssertionError("must not call the LLM with nothing to price")

        self.assertEqual(sr.generate_theses([], generate_text=fail), [])


if __name__ == "__main__":
    unittest.main()
