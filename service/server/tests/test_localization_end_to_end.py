"""Every localized surface, every language, against a REAL database.

Written after a member received this, on a `lang='ko'` account, AFTER the fix
that was supposed to prevent exactly it had shipped:

    ETHUSDT(crypto): sentiment shock. NEUTRAL your long (high): A psych_shock
    volatility event has no clear direction and raises risk for both long and
    short sides, so the automated LO
    런 #811의 다음 사이클은 풀 AI 데스크로 승격됩니다.

Cause: hot_issue_daemon._recipient_lang queried `ai_agents`, a table that has
never existed. Every call raised, the fail-soft except swallowed it, and it
returned 'en' for EVERY recipient — so the note, verdict and triggers were
always English while send_alert rendered the frame in the member's language.

Why the existing tests all passed:

  * the happy-path test patched `_recipient_lang` itself, so the SQL never ran
  * the fail-soft test patched get_db_connection to raise, which is what the
    broken code did anyway — it asserted the bug

The lesson generalises past this one typo: a mocked dependency cannot catch a
wrong table name, and a fail-soft except turns a permanent misconfiguration
into a silent downgrade. Everything here therefore runs against a real schema
with real rows, and asserts on OUTPUT a member would read.
"""
from __future__ import annotations

import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import alerts
import database
import hot_issue_daemon
import notifications_i18n as n
import regions
from analysis_agents import LANG_NAMES, normalize_lang
from email_i18n import verification_email
from i18n_errors import translate
from services import _hash_token

# ko/ja/th are non-Latin, so "an ASCII word survived" is a sound leak test.
# vi and id are Latin-script and share words with English, so they get the
# differs-from-English check instead.
NON_LATIN = ("ko", "ja", "th")
LATIN_NON_EN = ("vi", "id")


def _ascii_words(text: str) -> set[str]:
    out = set()
    for w in text.replace("(", " ").replace(")", " ").split():
        core = w.strip(".,:;!?·—")
        if core and core.isascii() and any(c.isalpha() for c in core):
            out.add(core)
    return out


class _RealDb(unittest.TestCase):
    """A real schema with one member per language — no mocked lookups."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_URL = ""
        database._SQLITE_DB_PATH = os.path.join(self.tmp.name, "t.db")
        database.init_database()
        self.agent = {}
        conn = database.get_db_connection()
        cur = conn.cursor()
        for i, lang in enumerate(LANG_NAMES):
            cur.execute(
                "INSERT INTO users (email,password_hash,created_at,lang) "
                "VALUES (?,?,?,?)",
                (f"{lang}@t.io", "x", "2026-01-01T00:00:00Z", lang))
            uid = cur.lastrowid
            tok = f"claw_{lang}"
            cur.execute(
                "INSERT INTO agents (name,password_hash,token,token_hash,cash,user_id) "
                "VALUES (?,?,?,?,?,?)",
                (f"agent-{lang}", "x", tok, _hash_token(tok), 100000.0, uid))
            self.agent[lang] = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _last_alert(self, agent_id):
        conn = database.get_db_connection()
        try:
            row = conn.cursor().execute(
                "SELECT title, body FROM alert_log WHERE agent_id=? "
                "ORDER BY id DESC LIMIT 1", (agent_id,)).fetchone()
        finally:
            conn.close()
        return (row["title"], row["body"]) if row else (None, None)


class TheRecipientLookup(_RealDb):
    """The bug itself — real SQL, real rows, no mocks anywhere."""

    def test_it_returns_each_members_own_language(self):
        for lang, aid in self.agent.items():
            with self.subTest(lang=lang):
                self.assertEqual(hot_issue_daemon._recipient_lang(aid), lang)

    def test_it_does_not_collapse_everyone_to_english(self):
        """The precise shape of the regression: every lookup answering 'en'."""
        got = {lang: hot_issue_daemon._recipient_lang(aid)
               for lang, aid in self.agent.items()}
        self.assertGreater(len({v for v in got.values()}), 1,
                           f"every recipient resolved to the same language: {got}")

    def test_an_unknown_agent_still_falls_back(self):
        self.assertEqual(hot_issue_daemon._recipient_lang(999999), "en")


class TheReportedEmail(_RealDb):
    """The hot-issue alert, driven through send_alert end to end."""

    def _render(self, lang):
        aid = self.agent[lang]
        resolved = hot_issue_daemon._recipient_lang(aid)
        verdict = n.verdict_default("long", resolved)
        triggers = n.triggers_text(["psych_shock", "price_move:+6.0%"], resolved)
        with patch.object(alerts, "_send_email", return_value=False), \
             patch.object(alerts, "_send_sms", return_value=False):
            alerts.send_alert(aid, "custom", "hot_issue_position",
                              {"symbol": "ETHUSDT", "market": "crypto",
                               "side": "buy", "run_id": 811,
                               "triggers": triggers, "verdict": verdict})
        return self._last_alert(aid)

    def test_the_trigger_is_never_a_raw_identifier(self):
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                _, body = self._render(lang)
                self.assertNotIn("psych_shock", body)
                self.assertIn("6.0%", body)      # the number survives

    def test_no_english_fragment_survives_in_non_latin(self):
        for lang in NON_LATIN:
            with self.subTest(lang=lang):
                _, body = self._render(lang)
                leaked = {w for w in _ascii_words(body)
                          if w.isalpha() and w not in ("ETHUSDT", "crypto", "AI", "SL", "TP")}
                self.assertFalse(leaked, f"{lang}: {leaked} left in {body!r}")

    def test_latin_languages_differ_from_english(self):
        en = self._render("en")[1]
        for lang in LATIN_NON_EN:
            with self.subTest(lang=lang):
                self.assertNotEqual(self._render(lang)[1], en)


class EveryAlertInEveryLanguage(_RealDb):

    def test_every_catalogue_message_renders_per_language(self):
        """No msg_id may fall through to render()'s key=value debug path."""
        probe = {
            "symbol": "BTC", "market": "crypto", "side": "buy", "run_id": 1,
            "fleet_id": 2, "triggers": "x", "verdict": "y", "scope": "agent:1",
            "reason": "user_stop", "trigger_label": "stop_loss", "price": "1",
            "name": "w", "metric": "m", "where": "", "value": "1", "unit": "%",
            "comparator": "above", "threshold": "2", "period_start": "a",
            "period_end": "b", "pnl": "1", "trades": 1, "status": "running",
            "loss_pct": "5", "profit_pct": "5", "total": "1", "base": "1",
            "action": "buy", "action_upper": "BUY", "qty": "1", "entry": "1",
            "confidence": "0.7", "final": "rejected", "requested": "1",
            "filled_txt": "an unknown amount", "detail": "gateway session down",
            "hours": 1, "failures": 2, "exc": "boom", "outcome": "flatten",
            "new_run_id": 2, "why": "no mark price to flatten at", "minutes": 5,
            "count": 3, "fails": 3, "stop_loss_pct": "40", "n": 9,
            "gain_pct": "15.0",
        }
        for msg_id in n.MESSAGES:
            for lang in LANG_NAMES:
                with self.subTest(msg_id=msg_id, lang=lang):
                    title, body = n.render(msg_id, lang, **probe)
                    self.assertNotEqual(title, msg_id,
                                        f"{msg_id}/{lang} fell through to debug output")
                    self.assertNotIn("=", title.split(":")[0])
                    self.assertTrue(body.strip())


class EveryOtherSurface(unittest.TestCase):
    """The surfaces outside the alert path, all six languages."""

    def test_transactional_email(self):
        en = verification_email("123456", "en")[0]
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                subject, html = verification_email("123456", lang)
                self.assertIn("123456", html)
                if lang != "en":
                    self.assertNotEqual(subject, en, f"{lang} subject not localized")

    def test_api_error_catalogue(self):
        probe = "Agent not found"
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                out = translate(probe, lang)
                if lang == "en":
                    self.assertEqual(out, probe)
                else:
                    self.assertNotEqual(out, probe, f"{lang} error not localized")

    def test_regime_reasons(self):
        probe = "F&G 29 in fear band"
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                out = translate(probe, lang)
                self.assertIn("29", out)
                if lang != "en":
                    self.assertNotEqual(out, probe)

    def test_region_names(self):
        for code in regions.supported_regions():
            for lang in LANG_NAMES:
                with self.subTest(region=code, lang=lang):
                    opts = {o["region"]: o["name"] for o in regions.options(lang)}
                    self.assertTrue(opts.get(code))

    def test_normalize_lang_accepts_every_registered_code(self):
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                self.assertEqual(normalize_lang(lang), lang)
                self.assertEqual(normalize_lang(lang.upper()), lang)
                self.assertEqual(normalize_lang(f"{lang}-XX"), lang)


class NoLookupSilentlySwallowsAWrongTable(unittest.TestCase):
    """The class of bug, not the instance.

    A `except Exception: return <default>` around a SQL read turns a
    permanently wrong table or column name into a silent, uniform default
    that no output test can distinguish from correct behaviour. Every such
    handler in the localization path must at least log.
    """

    def test_language_lookups_log_before_falling_back(self):
        import ast
        offenders = []
        for name in ("hot_issue_daemon.py", "notifications.py", "alerts.py"):
            path = SERVER_DIR / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                if "lang" not in fn.name:
                    continue
                for h in [x for x in ast.walk(fn) if isinstance(x, ast.ExceptHandler)]:
                    # Only handlers that SWALLOW AND SUBSTITUTE — i.e. return a
                    # value. An `except: pass` around conn.close() hides
                    # nothing a member could read, and flagging it would just
                    # train the next person to silence this test.
                    returns_default = any(
                        isinstance(x, ast.Return) and x.value is not None
                        for x in ast.walk(h))
                    if not returns_default:
                        continue
                    has_log = any(
                        isinstance(c, ast.Call)
                        and getattr(getattr(c.func, "value", None), "id", "") == "logger"
                        for c in ast.walk(h))
                    if not has_log:
                        offenders.append(f"{name}:{fn.name}:{h.lineno}")
        self.assertFalse(offenders,
                         "silent except in a language lookup — a wrong table name "
                         "would vanish: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
