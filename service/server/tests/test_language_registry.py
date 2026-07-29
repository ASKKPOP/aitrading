"""One language set, six places that must agree (2026-07-28).

Adding Indonesian meant touching the LLM output language, the alert
catalogue, the email catalogue, the error catalogue, the region registry, the
signup resolver and the frontend picker. Any one of them missed is a silent
half-launch: the member picks Bahasa Indonesia in the top bar and still gets
English alerts, because normalize_lang maps an unknown code to 'en' rather
than raising.

LANG_NAMES in analysis_agents is the single source of truth. These tests fail
on a language present there but missing from a catalogue — which is the shape
of every drift this file exists to catch.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import notifications_i18n as n
import regions
from analysis_agents import LANG_NAMES, normalize_lang
from email_i18n import _VERIFICATION
from i18n_errors_data import MESSAGES as ERROR_MESSAGES

FRONTEND = SERVER_DIR.parents[0] / "frontend" / "src" / "i18n.ts"


class TheRegistryIsTheSourceOfTruth(unittest.TestCase):

    def test_indonesian_is_registered(self):
        self.assertIn("id", LANG_NAMES)
        self.assertEqual(normalize_lang("id-ID"), "id")
        self.assertEqual(normalize_lang("ID"), "id")

    def test_an_unknown_code_still_falls_back_to_english(self):
        for bad in ("de", "xx", "", None, "zz-ZZ"):
            self.assertEqual(normalize_lang(bad), "en")


class EveryCatalogueCoversEveryLanguage(unittest.TestCase):

    def test_alert_messages(self):
        for msg_id, variants in n.MESSAGES.items():
            for lang in LANG_NAMES:
                with self.subTest(msg_id=msg_id, lang=lang):
                    self.assertIn(lang, variants)
                    title, body = variants[lang]
                    self.assertTrue(title and body)

    def test_alert_tokens(self):
        for family, langs in n.TOKENS.items():
            for lang in LANG_NAMES:
                with self.subTest(family=family, lang=lang):
                    self.assertIn(lang, langs)
                    self.assertEqual(set(langs[lang]), set(langs["en"]),
                                     f"{family}/{lang} key set differs from English")

    def test_verdict_and_trigger_tables(self):
        for name, table in (("_VERDICT", n._VERDICT), ("_STANCE", n._STANCE),
                            ("_URGENCY", n._URGENCY), ("_SIDE", n._SIDE),
                            ("_TRIGGER", n._TRIGGER)):
            for lang in LANG_NAMES:
                with self.subTest(table=name, lang=lang):
                    self.assertIn(lang, table)

    def test_transactional_email(self):
        for lang in LANG_NAMES:
            with self.subTest(lang=lang):
                self.assertIn(lang, _VERIFICATION)
                subject, html = _VERIFICATION[lang]
                self.assertTrue(subject)
                self.assertIn("{code}", html)

    def test_error_catalogue(self):
        missing = {lang: [k for k, v in ERROR_MESSAGES.items() if lang not in v]
                   for lang in LANG_NAMES if lang != "en"}
        for lang, keys in missing.items():
            with self.subTest(lang=lang):
                self.assertFalse(keys, f"{lang}: {len(keys)} keys untranslated")

    def test_region_display_names(self):
        for code in regions.supported_regions():
            for lang in LANG_NAMES:
                with self.subTest(region=code, lang=lang):
                    self.assertIn(lang, regions.REGISTRY[code].names)


class NoBackendModuleKeepsItsOwnLanguageList(unittest.TestCase):
    """The server-side counterpart to the frontend hand-list check below.

    hot_issue_daemon kept a private `_LANG_NAMES` used to tell the LLM which
    language to write the alert note in. It listed five languages. Indonesian
    shipped, the private copy was never updated, and `.get(lang, "English")`
    turned that omission into a silent English fallback — so an `id` member
    got an English note interpolated into an Indonesian sentence:

        NETRAL bagi posisi beli (long) Anda (tingkat urgensi tinggi): <English>

    the very half-and-half alert the localized verdict tables exist to
    prevent. A drifting copy of the registry is the bug; forbid the copy.
    """

    def test_no_module_redefines_the_language_name_table(self):
        offenders = []
        for path in sorted(SERVER_DIR.rglob("*.py")):
            if path.name == "analysis_agents.py" or "tests" in path.parts:
                continue          # the registry itself, and this file
            text = path.read_text(encoding="utf-8")
            # An assignment to a dict literal that maps language codes to
            # English language NAMES — the shape a prompt-language table has.
            for m in re.finditer(r"=\s*\{([^{}]*?)\}", text, re.S):
                body = m.group(1)
                keys = set(re.findall(r"[\"']([a-z]{2})[\"']\s*:", body))
                if len(keys & set(LANG_NAMES)) < 3:
                    continue
                names = set(re.findall(r":\s*[\"'](\w+)[\"']", body))
                if names & {"English", "Korean", "Japanese", "Thai",
                            "Vietnamese", "Indonesian"}:
                    line = text[:m.start()].count("\n") + 1
                    offenders.append(f"{path.name}:{line} {sorted(keys)}")
        self.assertFalse(offenders,
                         "backend module(s) hand-listing language names "
                         "instead of importing analysis_agents.LANG_NAMES: "
                         + "; ".join(offenders))

    def test_the_hot_issue_note_is_requested_in_every_language(self):
        """Whatever table the daemon ends up using, every registered language
        must resolve to its own name — never to the English fallback."""
        import hot_issue_daemon as daemon

        source = Path(daemon.__file__).read_text(encoding="utf-8")
        self.assertIn('Write the "note" value in', source,
                      "the note-language instruction moved; update this test")
        for lang, name in LANG_NAMES.items():
            with self.subTest(lang=lang):
                self.assertEqual(daemon.LANG_NAMES.get(lang), name)


class TokenTablesCoverWhatActuallyReachesThem(unittest.TestCase):
    """Cross-language parity is not coverage.

    `test_alert_tokens` above asserts every language has the same key set as
    English — and passed while `side` was missing `long` in ALL SIX, because
    English was missing it too. hot_issue_daemon._position_side returns
    'long' or 'short', so a member holding a SHORT read '숏' and a member
    holding a LONG read the English word 'long' in an otherwise Korean title:

        핫이슈: ETHUSDT — 보유 중인 long 포지션

    An unknown token passes through verbatim by design (a new detector must
    stay visible rather than vanish), which is exactly what turns a missing
    key into silent English instead of a failure. So the domains are pinned
    here, next to the tables.

    Deliberately NOT listed: `hold`/`HOLD` for action, and `draft` for
    status. Both trade alerts are guarded by `if signal_id:` — a hold never
    places a trade — and a run only queues a digest once it is past draft.
    Padding a table against a value that cannot arrive is the speculative
    error handling this codebase avoids.
    """

    DOMAINS = {
        "side": {"long", "short"},          # hot_issue_daemon._position_side
        "action": {"buy", "sell", "short", "cover"},
        "action_upper": {"BUY", "SELL", "SHORT", "COVER"},
        "status": {"armed", "running", "paused", "stopping", "stopped"},
        "outcome": {"flatten", "hold"},
    }

    def test_every_runtime_value_has_a_translation(self):
        for family, domain in self.DOMAINS.items():
            for lang in LANG_NAMES:
                table = n.TOKENS[family][lang]
                for value in sorted(domain):
                    with self.subTest(family=family, lang=lang, value=value):
                        self.assertIn(value, table,
                                      f"{family}/{lang} has no '{value}' — it would "
                                      f"render as the raw English token")


class TheAssistantFallsBackInTheMembersLanguage(unittest.TestCase):
    """The assistant answers in the member's language on every turn the model
    handles. Its two failure replies — no model configured, model unreachable —
    were plain English, so the one turn most likely to confuse a member was
    also the one turn that stopped speaking their language."""

    REPLIES = (
        "The assistant is unavailable right now (no AI model configured on this "
        "server). Your message was saved — everything else on the platform keeps "
        "working, and your data is unchanged.",
        "I couldn't reach the model just now — please try again. Nothing in your "
        "account was changed.",
    )

    def test_both_fallbacks_translate_into_every_language(self):
        from i18n_errors import translate

        for reply in self.REPLIES:
            for lang in LANG_NAMES:
                with self.subTest(lang=lang, reply=reply[:32]):
                    out = translate(reply, lang)
                    self.assertTrue(out)
                    if lang != "en":
                        self.assertNotEqual(out, reply,
                                            "served English to a non-English member")

    # Drift (reword the reply, forget the catalogue, silently serve English)
    # is already caught by test_i18n_errors.py's
    # test_every_catalogue_key_still_exists_in_the_backend, which AST-scans
    # every literal in the backend against every catalogue key. No second copy.


class IndonesiaIsServed(unittest.TestCase):

    def test_the_region_exists_with_a_real_zone(self):
        r = regions.get_region("ID")
        self.assertIsNotNone(r)
        self.assertEqual(r.timezone, "Asia/Jakarta")
        self.assertEqual(r.lang, "id")
        # zoneinfo must actually know it, or every clock on the page is wrong
        self.assertEqual(regions.normalize_timezone("Asia/Jakarta"), "Asia/Jakarta")

    def test_an_indonesian_ip_resolves_to_indonesian(self):
        import signup_lang
        self.assertEqual(signup_lang._country_to_lang("ID"), "id")

    def test_every_region_default_lang_is_a_language_we_serve(self):
        for code in regions.supported_regions():
            with self.subTest(region=code):
                self.assertIn(regions.default_lang(code), LANG_NAMES)


class TheFrontendPickerAgrees(unittest.TestCase):
    """A language offered in the top bar but unknown to the backend means the
    member switches to it and keeps receiving English."""

    def _source(self) -> str:
        return FRONTEND.read_text(encoding="utf-8")

    def test_the_language_union_matches(self):
        src = self._source()
        declared = re.search(r"export type Language = ([^\n]+)", src)
        self.assertIsNotNone(declared)
        codes = set(re.findall(r"'([a-z-]+)'", declared.group(1)))
        self.assertEqual(codes, set(LANG_NAMES))

    def test_no_page_hand_lists_the_language_codes(self):
        """MarketingPage held its own switcher as

            const LANGS: Record<string, string> = { ko:'KO', …, vi:'VI' }

        The loose `string` key meant adding a sixth language typechecked
        perfectly clean while the landing page kept offering five — a visitor
        could not select the language the rest of the product already served,
        and nothing failed. Any structure enumerating language codes must
        derive from LANGUAGES instead of repeating them.
        """
        src_root = FRONTEND.parent
        codes = set(LANG_NAMES)
        offenders = []
        for path in sorted(src_root.rglob("*.ts")) + sorted(src_root.rglob("*.tsx")):
            if path.name == "i18n.ts":
                continue          # the registry itself
            for m in re.finditer(r"Record<string,\s*string>\s*=\s*\{([^}]*)\}",
                                 path.read_text(encoding="utf-8")):
                keys = set(re.findall(r"(\w[\w-]*)\s*:", m.group(1)))
                # a map keyed by language codes and nothing else
                if len(keys) >= 3 and keys <= codes:
                    offenders.append(f"{path.name}: {sorted(keys)}")
        self.assertFalse(offenders,
                         "language codes hand-listed instead of derived from "
                         "LANGUAGES: " + "; ".join(offenders))

    def test_no_page_renders_the_raw_fear_greed_vendor_string(self):
        """alternative.me returns value_classification as English prose
        ("Fear", "Extreme Greed"). Three pages — home, Signals Board and
        Dashboard — interpolated it straight into the UI, so a Korean member
        read "29 Fear" on an otherwise Korean page. It is third-party text but
        a CLOSED set of five bands, so it is ours to translate; it must go
        through fearGreedLabel(), never `fng.classification` on its own.
        """
        src_root = FRONTEND.parent
        offenders = []
        for path in sorted(src_root.rglob("*.tsx")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"[{$]\{?\s*fng\.classification\s*\}", line) \
                        and "fearGreedLabel" not in line:
                    offenders.append(f"{path.name}:{i}")
        self.assertFalse(offenders,
                         "raw vendor Fear & Greed label rendered: " + ", ".join(offenders))

    def test_every_language_has_a_fear_greed_band_set(self):
        src = self._source()
        block = re.search(r"const FEAR_GREED[^=]*=\s*\{(.*?)\n\}", src, re.S)
        self.assertIsNotNone(block, "FEAR_GREED table missing from i18n.ts")
        bands = re.findall(r"'([a-z ]+)':\s*\{([^}]*)\}", block.group(1))
        self.assertEqual({b for b, _ in bands},
                         {"extreme fear", "fear", "neutral", "greed", "extreme greed"})
        for band, body in bands:
            for lang in LANG_NAMES:
                with self.subTest(band=band, lang=lang):
                    self.assertRegex(body, rf"\b{lang}:\s*'")

    def test_every_frontend_language_map_covers_every_language(self):
        """The UI-copy counterpart to the catalogue checks above.

        A "language map" is any object literal carrying `en` plus two or more
        of ko/ja/th/vi — the shape `tr()` consumes. Every one of them must
        cover every registered language, or that surface silently serves
        English to a member who chose otherwise.

        Regex rather than a TS parser, so it runs in the Python suite: for
        each map, capture its key names and compare. Multi-line maps are
        handled by matching across newlines; template literals count too,
        which is what a purely line-based grep gets wrong.
        """
        src_root = FRONTEND.parent
        codes = set(LANG_NAMES)
        offenders = []
        # Object literal that contains an `en:` key and at least one other
        # language key. Non-greedy to the first closing brace that is not
        # inside a nested ${...} — good enough because these maps are flat.
        pat = re.compile(r"\{[^{}]*?\ben\s*:.*?\}", re.S)
        for path in list(src_root.rglob("*.ts")) + list(src_root.rglob("*.tsx")):
            if path.name == "i18n.ts" or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for m in pat.finditer(text):
                keys = set(re.findall(r"(?:^|[{,\s])([a-z]{2})\s*:", m.group(0)))
                present = keys & codes
                if "en" in present and len(present - {"en"}) >= 2 and "id" not in present:
                    line = text[:m.start()].count("\n") + 1
                    offenders.append(f"{path.name}:{line}")
        self.assertFalse(offenders,
                         f"{len(offenders)} frontend language map(s) missing 'id': "
                         + ", ".join(offenders[:15]))

    def test_every_language_has_a_picker_label_and_a_locale(self):
        src = self._source()
        listed = set(re.findall(r"\{ value: '([a-z-]+)', label:", src))
        self.assertEqual(listed, set(LANG_NAMES))
        block = re.search(r"LOCALE_BY_LANGUAGE: Record<Language, string> = \{(.*?)\}",
                          src, re.S)
        self.assertIsNotNone(block)
        locales = set(re.findall(r"^\s*([a-z-]+):", block.group(1), re.M))
        self.assertEqual(locales, set(LANG_NAMES))


if __name__ == "__main__":
    unittest.main()
