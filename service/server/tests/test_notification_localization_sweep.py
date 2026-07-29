"""Second localization sweep (2026-07-28), after PR #109.

#109 fixed the three causes behind the reported Korean rows. A full pass over
every producer that reaches a member found four more, of a different shape:

  D. `fleet_profit_target` was emitted as a msg_id that was never added to the
     catalogue, so the one good-news alert in the product rendered as the
     literal 'fleet_profit_target' / 'fleet_id=12, gain_pct=15.0' — in EVERY
     language, English included. Not a translation bug; a broken alert.
  E. The sentence-shaped params (exc / why / detail / filled_txt) were treated
     as untranslatable free text. Most of what lands in them is a sentence we
     wrote ourselves — 'marks stale beyond 900s — …', 'manual halt', 'an
     unknown amount' — so they now go through the i18n_errors catalogue.
     Genuinely foreign text (a broker rejection) must still pass through.
  F. notify() had no localized path at all, so 'Support replied' headed a
     Korean member's support notification in English.
  G. The Settings "test my notifications" send — whose entire purpose is to
     show the member what a real notification looks like — was hardcoded
     English, and its failure reasons were returned in the response body,
     bypassing the exception handler that localizes everything else.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import alerts
import notifications
import notifications_i18n as n
from i18n_errors_data import MESSAGES as ERROR_MESSAGES

LANGS = ("en", "ko", "ja", "th", "vi")
NON_LATIN = ("ko", "ja", "th")

# Every sentence the engine authors that can land in a free-form alert param,
# with the param it arrives on. Kept explicit: a new one added to the engine
# without a catalogue entry should fail here rather than ship in English.
ENGINE_SENTENCES = [
    ("exc", "marks stale beyond 900s — refusing to evaluate P&L stops on frozen prices"),
    ("why", "no mark price to flatten at"),
    ("why", "manual breaker halt blocks exits"),
    ("why", "no long position to sell"),
    ("why", "no short position to cover"),
    ("why", "short position entry price missing"),
    ("why", "invalid quantity/price"),
    ("why", "duplicate client_order_id (cycle already executed)"),
    ("why", "insufficient cash ($10.00 < $25.00)"),
    ("reason", "manual halt"),
    ("reason", "auto: consecutive real liquidation shocks (panic regime)"),
    ("detail", "gateway session down"),
    ("filled_txt", "an unknown amount"),
]


def _ascii_words(text: str) -> set[str]:
    out = set()
    for w in text.replace("(", " ").replace(")", " ").split():
        core = w.strip(".,:;!?")
        if core and core.isascii() and any(c.isalpha() for c in core):
            out.add(core)
    return out


class MissingCatalogueEntry(unittest.TestCase):
    """Cause D."""

    def test_fleet_profit_target_renders_a_real_sentence(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                title, body = n.render("fleet_profit_target", lang,
                                       fleet_id=12, gain_pct="15.0")
                self.assertNotEqual(title, "fleet_profit_target", lang)
                self.assertNotIn("fleet_id=", body, lang)
                self.assertIn("15.0", body, lang)

    def test_every_emitted_msg_id_exists_in_the_catalogue(self):
        """The bug class, not the instance: a producer naming a msg_id that
        was never written renders as key/value debug output to the member."""
        import ast

        emitted: set[tuple[str, int, str]] = set()
        for path in SERVER_DIR.rglob("*.py"):
            if "tests" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name not in ("send_alert", "notify_i18n", "render"):
                    continue
                # send_alert(agent, kind, msg_id, ...) / notify_i18n(uid, cat, msg_id, ...)
                index = 2 if name in ("send_alert", "notify_i18n") else 0
                if len(node.args) > index:
                    arg = node.args[index]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        emitted.add((path.name, node.lineno, arg.value))

        unknown = sorted(e for e in emitted if e[2] not in n.MESSAGES)
        self.assertFalse(unknown, "msg_id emitted but absent from the catalogue: "
                                  + ", ".join(f"{f}:{ln} {m!r}" for f, ln, m in unknown))

    def test_the_alert_kind_is_registered(self):
        """An unregistered kind is silently rewritten to 'custom', which puts
        the alert in the wrong notification category and the wrong budget."""
        self.assertIn("fleet_profit_target", alerts.ALERT_KINDS)
        self.assertIn("fleet_profit_target", notifications.ALERT_KIND_CATEGORY)

    def test_every_registered_kind_has_a_category(self):
        for kind in alerts.ALERT_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, notifications.ALERT_KIND_CATEGORY)


class EngineSentences(unittest.TestCase):
    """Cause E."""

    def test_the_reported_row_is_now_fully_korean(self):
        _, body = n.render(
            "run_stop_eval_paused", "ko", run_id=811,
            exc="marks stale beyond 900s — refusing to evaluate P&L stops "
                "on frozen prices")
        self.assertNotIn("marks stale", body)
        self.assertNotIn("frozen prices", body)
        self.assertIn("900", body)  # the number survives the pattern path

    def test_every_engine_sentence_has_a_translation(self):
        for param, sentence in ENGINE_SENTENCES:
            with self.subTest(param=param, sentence=sentence):
                self.assertTrue(
                    any(k == sentence or ("{}" in k and _pattern_matches(k, sentence))
                        for k in ERROR_MESSAGES),
                    f"no catalogue entry for {sentence!r}")

    def test_no_english_survives_in_non_latin_renders(self):
        templates = {
            "exc": ("run_stop_eval_paused", {"run_id": 1}),
            "why": ("run_positions_held", {"run_id": 1, "minutes": 30}),
            "reason": ("breaker", {"scope": "agent:6"}),
            "detail": ("gateway_down_ibkr_session", {}),
            "filled_txt": ("order_drift_partial_fill",
                           {"symbol": "BTC", "requested": "2", "side": "buy"}),
        }
        for param, sentence in ENGINE_SENTENCES:
            msg_id, base = templates[param]
            for lang in NON_LATIN:
                with self.subTest(lang=lang, sentence=sentence):
                    _, body = n.render(msg_id, lang, **{**base, param: sentence})
                    # Words carried from the sentence itself. Identifiers and
                    # numbers are expected to survive; prose is not.
                    leaked = {w for w in _ascii_words(sentence)
                              if w in _ascii_words(body) and w.isalpha()
                              and "_" not in w and w not in ("SL", "TP")}
                    self.assertFalse(leaked, f"{lang}: {leaked} left in {body!r}")

    def test_third_party_text_still_passes_through(self):
        """A broker rejection is not ours to translate — mangling or dropping
        it would destroy the only diagnostic the member has."""
        broker = "IBKR: order rejected, insufficient margin in account U1234"
        for lang in LANGS:
            with self.subTest(lang=lang):
                _, body = n.render("gateway_down_live_order_failed", lang,
                                   symbol="AAPL", reason=broker)
                self.assertIn(broker, body)

    def test_enum_reasons_are_not_double_translated(self):
        """`reason` is an enum in run_stop_event and a sentence in breaker.
        The token layer must win where it applies."""
        _, body = n.render("run_stop_event", "ko", run_id=1, symbol="ZEC",
                           market="crypto", reason="stop_event:trailing_lock",
                           outcome="flatten")
        self.assertIn("추적 이익 보호", body)
        self.assertNotIn("trailing_lock", body)

    def test_english_renders_are_unchanged(self):
        """The translate() hop must be a no-op for lang='en'."""
        sentence = "marks stale beyond 900s — refusing to evaluate P&L stops on frozen prices"
        _, body = n.render("run_stop_eval_paused", "en", run_id=1, exc=sentence)
        self.assertIn(sentence, body)


class NotificationCentre(unittest.TestCase):
    """Causes F and G."""

    def test_support_reply_headline_is_localized(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                title, _ = n.render("support_replied", lang)
                if lang in NON_LATIN:
                    self.assertFalse(_ascii_words(title), lang)

    def test_notify_i18n_renders_in_the_members_language(self):
        sent = {}

        def fake_notify(user_id, category, title, body, link=None, external=True):
            sent.update(user_id=user_id, category=category, title=title,
                        body=body, link=link)
            return {"channels": ["inapp"]}

        with patch.object(notifications, "user_lang", return_value="ko"), \
                patch.object(notifications, "notify", fake_notify):
            notifications.notify_i18n(7, "support", "support_replied",
                                      link="/support", body_suffix="원문 답변")

        self.assertEqual(sent["title"], n.render("support_replied", "ko")[0])
        self.assertIn("원문 답변", sent["body"])
        self.assertEqual(sent["link"], "/support")

    def test_the_admins_own_words_are_never_translated_away(self):
        """The reply text itself is untranslatable and must survive intact,
        under a localized headline."""
        reply = "We refunded the 2026-07-20 charge."
        sent = {}
        with patch.object(notifications, "user_lang", return_value="ja"), \
                patch.object(notifications, "notify",
                             lambda uid, cat, title, body, link=None, external=True:
                             sent.update(title=title, body=body) or {"channels": []}):
            notifications.notify_i18n(7, "support", "support_replied",
                                      body_suffix=reply)
        self.assertIn(reply, sent["body"])
        self.assertNotIn("Support replied", sent["title"])
        self.assertEqual(sent["title"], n.render("support_replied", "ja")[0])

    def test_no_producer_passes_an_english_literal_to_notify(self):
        """notify_i18n existing is not the fix — the producers using it is.
        Any remaining notify(...) with a literal headline is a member reading
        English regardless of their language setting. The admin broadcast is
        the one legitimate caller: its title is typed by a human at send time.
        """
        import ast

        offenders = []
        for path in SERVER_DIR.rglob("*.py"):
            if "tests" in path.parts or path.name in ("notifications.py", "alerts.py"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) != "notify":
                    continue
                # notify(user_id, category, title, ...) — a literal title is
                # copy we wrote, so it belongs in the catalogue.
                for arg in node.args[2:3]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        offenders.append(f"{path.name}:{node.lineno} {arg.value!r}")
        self.assertFalse(offenders,
                         "English literal passed to notify(); use notify_i18n: "
                         + ", ".join(offenders))

    def test_the_support_route_uses_the_localized_path(self):
        """Pins the call site itself — reverting it to notify('Support
        replied', ...) must not pass just because notify_i18n still works."""
        source = (SERVER_DIR / "routes_support.py").read_text(encoding="utf-8")
        self.assertIn("notify_i18n", source)
        self.assertIn("support_replied", source)
        self.assertNotIn("'Support replied'", source)

    def test_the_test_send_uses_catalogue_copy(self):
        source = (SERVER_DIR / "routes_support.py").read_text(encoding="utf-8")
        self.assertIn("notification_test", source)
        self.assertNotIn("This is a test of your Sooppiy email", source)
        # the failure reasons must be translated before they leave the route
        self.assertIn("translate(detail", source)

    def test_notify_i18n_survives_an_unknown_user(self):
        with patch.object(notifications, "notify",
                          return_value={"skipped": "no_user", "channels": []}):
            out = notifications.notify_i18n(None, "support", "support_replied")
        self.assertEqual(out.get("channels"), [])

    def test_user_lang_fails_soft(self):
        with patch.object(notifications, "get_db_connection",
                          side_effect=RuntimeError("db down")):
            self.assertEqual(notifications.user_lang(7), "en")

    def test_notification_test_copy_is_localized(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                title, body = n.render("notification_test", lang)
                self.assertTrue(title and body)
                if lang in NON_LATIN:
                    self.assertFalse(_ascii_words(body) - {"Sooppiy"}, lang)

    def test_test_send_failure_reasons_are_in_the_catalogue(self):
        for detail in ("no email on account", "no phone number saved in Settings",
                       "provider not configured or rejected",
                       "SMS is not included in your current plan"):
            with self.subTest(detail=detail):
                self.assertIn(detail, ERROR_MESSAGES)


def _pattern_matches(key: str, text: str) -> bool:
    import re
    rx = "(.*?)".join(re.escape(p) for p in key.split("{}"))
    return re.match(f"^{rx}$", text, re.DOTALL) is not None


if __name__ == "__main__":
    unittest.main()
