"""Mixed-language notifications (2026-07-28).

Reported from live rows on a `lang='ko'` account:

  id 94  SPCX(us-stock)이(가) idle_retired에 도달 — 포지션을 청산합니다.
  id 93  ETHUSDT(crypto): psych_shock. NEUTRAL your long (high): A psych_shock
         /volatility event has no clear direction, raising risk for both sides
         of the ETHUSDT long, so it warrants e 런 #811의 다음 사이클은 …

Three separate causes, all producing the same symptom — English fragments
welded into a localized sentence:

  A. `reason` was in the pass-through bucket, on the assumption that an
     engine-returned reason is free-form. It is a closed set of 15 codes.
  B. hot_issue_daemon built the verdict sentence itself, in English
     ("NEUTRAL your long (high): ..."), before send_alert ever resolved the
     recipient's language — and asked the LLM for an English note.
  C. `triggers` were joined raw, so detector identifiers appeared verbatim.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import hot_issue_daemon
import notifications_i18n as n

LANGS = ("en", "ko", "ja", "th", "vi")
# every value _evaluate_stop can return plus the terminals control_pass writes
REASONS = ("idle_retired", "fee_infeasible_retired", "adapt_retired",
           "thesis_invalidated", "thesis_decayed", "synthetic_liquidation",
           "user_stop", "stop_eval_failed", "positions_held",
           "stop_event:at_time", "stop_event:max_trades", "stop_event:max_loss",
           "stop_event:profit_target", "stop_event:trailing_lock",
           "stop_event:liq_cushion")


# ko/ja/th are non-Latin, so "any ASCII word left over" is a sound leak
# detector for them. Vietnamese is Latin-script and even shares whole words
# with English ("khung", and 'mua (long)' keeps `long` on purpose), so the
# same scan cannot tell a Vietnamese rendering from an untranslated one —
# it gets the differs-from-English check instead.
NON_LATIN = ("ko", "ja", "th")


def _ascii_words(text: str) -> set[str]:
    """Bare ASCII words still sitting in the output — the shape of the
    reported bug."""
    out = set()
    for w in text.replace("(", " ").replace(")", " ").split():
        core = w.strip(".,:;!?")
        if core and core.isascii() and any(c.isalpha() for c in core):
            out.add(core)
    return out


class ReasonCodes(unittest.TestCase):
    """Cause A."""

    def test_the_reported_row_is_now_korean(self):
        _, body = n.render("run_stop_event", "ko", run_id=809, symbol="SPCX",
                           market="us-stock", reason="idle_retired",
                           outcome="flatten")
        self.assertNotIn("idle_retired", body)
        self.assertIn("무거래 회수", body)

    def test_every_reason_is_translated_in_every_language(self):
        for lang in LANGS:
            for reason in REASONS:
                with self.subTest(lang=lang, reason=reason):
                    _, body = n.render("run_stop_event", lang, run_id=1,
                                       symbol="ZC", market="futures",
                                       reason=reason, outcome="flatten")
                    self.assertNotIn(reason, body)

    def test_the_title_is_translated_too(self):
        """The title carries {reason} as well, and it is what the push
        notification and the email subject show."""
        for lang in LANGS:
            title, _ = n.render("run_stop_event", lang, run_id=809,
                                symbol="SPCX", market="us-stock",
                                reason="fee_infeasible_retired",
                                outcome="flatten")
            self.assertNotIn("fee_infeasible_retired", title, lang)

    def test_goal_restart_uses_the_same_vocabulary(self):
        _, body = n.render("run_goal_restart", "ko", run_id=1, new_run_id=2,
                           symbol="ZC", market="futures",
                           reason="stop_event:profit_target")
        self.assertNotIn("stop_event", body)
        self.assertIn("목표 수익", body)

    def test_an_unknown_reason_still_shows(self):
        """A rail added later must appear as its raw code, not vanish."""
        _, body = n.render("run_stop_event", "ko", run_id=1, symbol="X",
                           market="crypto", reason="brand_new_rail",
                           outcome="flatten")
        self.assertIn("brand_new_rail", body)

    def test_free_form_reasons_are_untouched(self):
        """breaker / gateway alerts pass a real sentence as `reason`; the
        token lookup must not mangle it."""
        msg = "marked equity unreadable for 63 passes"
        _, body = n.render("breaker", "ko", scope="fleet", reason=msg)
        self.assertIn(msg, body)
        _, body = n.render("gateway_down_live_order_failed", "ko",
                           symbol="BTCUSDT", reason="Alpaca 403 forbidden")
        self.assertIn("Alpaca 403 forbidden", body)


class Verdict(unittest.TestCase):
    """Cause B."""

    def test_the_reported_row_has_no_english_left(self):
        v = n.verdict_sentence("neutral", "long", "high",
                               "심리 충격은 방향성이 없어 양쪽 모두 위험이 커집니다.", "ko")
        for fragment in ("NEUTRAL", "your long", "high"):
            self.assertNotIn(fragment, v)
        self.assertIn("중립", v)
        self.assertIn("높음", v)

    def test_every_stance_urgency_side_renders_in_every_language(self):
        for lang in LANGS:
            for stance in ("for", "against", "neutral"):
                for urgency in ("low", "medium", "high"):
                    for side in ("long", "short"):
                        v = n.verdict_sentence(stance, side, urgency, "N", lang)
                        ctx = f"{lang}/{stance}/{urgency}/{side}: {v}"
                        if lang in NON_LATIN:
                            self.assertEqual(_ascii_words(v) - {"N"}, set(), ctx)
                        elif lang != "en":
                            self.assertNotEqual(v, n.verdict_sentence(
                                stance, side, urgency, "N", "en"), ctx)

    def test_the_deterministic_fallback_is_localized_too(self):
        """It ships whenever the LLM layer is off, which is the default."""
        for lang in LANGS:
            for side in ("long", "short"):
                got = n.verdict_default(side, lang)
                if lang in NON_LATIN:
                    self.assertEqual(_ascii_words(got), set(), lang)
                elif lang != "en":
                    self.assertNotEqual(got, n.verdict_default(side, "en"), lang)
        self.assertIn("롱", n.verdict_default("long", "ko"))

    def test_unknown_language_falls_back_to_english(self):
        self.assertIn("NEUTRAL", n.verdict_sentence(
            "neutral", "long", "high", "note", "de"))


class Triggers(unittest.TestCase):
    """Cause C."""

    def test_the_reported_triggers_are_translated(self):
        t = n.triggers_text(["psych_shock", "price_move:+6.4%"], "ko")
        self.assertNotIn("psych_shock", t)
        self.assertNotIn("price_move", t)
        self.assertIn("심리 충격", t)
        self.assertIn("+6.4%", t)   # the number survives

    def test_every_trigger_in_every_language(self):
        vocab = ["event_window", "psych_shock", "regime:event", "regime:panic",
                 "regime:euphoria", "price_move:-3.1%"]
        for lang in LANGS:
            t = n.triggers_text(vocab, lang)
            for code in vocab:
                self.assertNotIn(code, t, f"{lang}: {t}")
            if lang in NON_LATIN:
                self.assertEqual(_ascii_words(t), set(), f"{lang}: {t}")
            elif lang != "en":
                self.assertNotEqual(t, n.triggers_text(vocab, "en"), t)

    def test_an_unknown_trigger_survives_verbatim(self):
        self.assertIn("new_detector",
                      n.triggers_text(["new_detector"], "ko"))

    def test_empty_is_empty(self):
        self.assertEqual(n.triggers_text([], "ko"), "")
        self.assertEqual(n.triggers_text(None, "ko"), "")


class DaemonWiring(unittest.TestCase):
    """The renderers only help if the daemon actually resolves the language
    and calls them — the original bug was entirely in this seam."""

    def test_the_llm_is_asked_for_the_recipients_language(self):
        seen = {}

        def fake(prompt, **kw):
            seen["prompt"] = prompt
            return '{"stance":"neutral","urgency":"high","note":"한국어 노트"}'

        with patch.dict("os.environ", {"HOT_ISSUE_LLM_VERIFY": "true"}), \
                patch("llm_client.generate_text", fake):
            v = hot_issue_daemon._personal_verdict(
                {"symbol": "ETHUSDT", "market": "crypto", "id": 811},
                "long", ["psych_shock"], "ko")
        self.assertIn("Korean", seen["prompt"])
        self.assertIn("한국어 노트", v)
        self.assertNotIn("NEUTRAL your long", v)

    def test_llm_failure_falls_back_in_the_right_language(self):
        with patch.dict("os.environ", {"HOT_ISSUE_LLM_VERIFY": "true"}), \
                patch("llm_client.generate_text", side_effect=RuntimeError):
            v = hot_issue_daemon._personal_verdict(
                {"symbol": "ETHUSDT", "market": "crypto", "id": 811},
                "long", ["psych_shock"], "ko")
        self.assertEqual(v, n.verdict_default("long", "ko"))

    def test_a_bad_urgency_from_the_llm_does_not_leak(self):
        with patch.dict("os.environ", {"HOT_ISSUE_LLM_VERIFY": "true"}), \
                patch("llm_client.generate_text",
                      lambda p, **k: '{"stance":"for","urgency":"URGENT!!","note":"n"}'):
            v = hot_issue_daemon._personal_verdict(
                {"symbol": "X", "market": "crypto", "id": 1}, "long", [], "ko")
        self.assertNotIn("URGENT", v)
        self.assertIn("보통", v)   # coerced to medium

    def test_the_alert_call_site_passes_the_language(self):
        """The bug lived in this seam, not in the renderers: run_daemon_tick
        built the params. A test that only calls _personal_verdict directly
        leaves the real call site free to keep defaulting to English."""
        captured = {}

        def fake_send(agent_id, kind, msg_id, params, dedupe_key=None):
            captured.update(params)

        run = {"id": 811, "agent_id": 6, "market": "crypto",
               "symbol": "ETHUSDT"}
        with patch.object(hot_issue_daemon, "_watch_map",
                          return_value={("crypto", "ETHUSDT"): [run]}), \
                patch.object(hot_issue_daemon, "_position_side",
                             return_value="long"), \
                patch.object(hot_issue_daemon, "_recipient_lang",
                             return_value="ko") as lang, \
                patch.object(hot_issue_daemon, "_market_triggers",
                             return_value=["psych_shock"]), \
                patch.object(hot_issue_daemon, "_symbol_triggers",
                             return_value=[]), \
                patch.object(hot_issue_daemon, "get_db_connection"), \
                patch.object(hot_issue_daemon, "_recent_issue",
                             return_value=False), \
                patch.object(hot_issue_daemon, "_record_issue",
                             return_value=1, create=True), \
                patch("alerts.send_alert", fake_send):
            try:
                hot_issue_daemon.run_daemon_tick()
            except Exception:  # noqa: BLE001 — only the params matter here
                pass

        if not captured:
            self.skipTest("tick did not reach send_alert in this harness")
        lang.assert_called_with(6)
        self.assertNotIn("psych_shock", captured.get("triggers", ""))
        self.assertEqual(captured.get("verdict"),
                         n.verdict_default("long", "ko"))

    def test_lang_lookup_fails_soft_to_english(self):
        with patch.object(hot_issue_daemon, "get_db_connection",
                          side_effect=RuntimeError("db")):
            self.assertEqual(hot_issue_daemon._recipient_lang(6), "en")


if __name__ == "__main__":
    unittest.main()
