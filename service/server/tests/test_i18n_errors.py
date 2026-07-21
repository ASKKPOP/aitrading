"""Guards for the localized API error layer.

The catalogue is keyed by the raised English string, which makes it silently
fragile in two directions: reword an error and its key stops matching, or get
a placeholder count wrong and the message renders with the wrong values (or
falls back to English without anybody noticing). Both are caught here.
"""

import ast
import pathlib
import re

import pytest

from i18n_errors import _parse_accept_language, translate
from i18n_errors_data import MESSAGES

SERVER = pathlib.Path(__file__).resolve().parent.parent
LANGS = ("ko", "ja", "th", "vi")

# A bare "{}" or an indexed "{0}"; anything else in the string is literal.
_SLOT = re.compile(r"\{(\d*)\}")


def _slots(text: str) -> list[str]:
    return _SLOT.findall(text)


def _raised_strings() -> set[str]:
    """Every literal error message the backend raises, f-strings collapsed to
    the same "{}" form the catalogue keys use."""
    found: set[str] = set()

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(
                v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
                else "{}"
                for v in node.values
            )
        return None

    raisers = {"HTTPException", "ValueError", "StartConflict",
               "EntitlementDenied", "LookupError", "PermissionError",
               "FleetConflict"}
    for path in SERVER.rglob("*.py"):
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
            if name not in raisers:
                continue
            if name == "HTTPException":
                for kw in node.keywords:
                    if kw.arg == "detail" and (text := literal(kw.value)):
                        found.add(text)
            elif node.args and (text := literal(node.args[0])):
                found.add(text)
    return found


@pytest.mark.parametrize("lang", LANGS)
def test_placeholder_counts_match_english(lang):
    """A translation must consume exactly the values the English does."""
    for english, variants in MESSAGES.items():
        translated = variants.get(lang)
        if not translated:
            continue
        expected = len(_slots(english))
        actual = len(_slots(translated))
        assert actual == expected, (
            f"{lang}: {expected} placeholder(s) in English, {actual} in "
            f"translation\n  en: {english!r}\n  {lang}: {translated!r}"
        )


@pytest.mark.parametrize("lang", LANGS)
def test_multi_placeholder_messages_are_indexed(lang):
    """Two or more values means the order has to be explicit.

    Bare "{}" fills left to right, so a language that reorders the sentence
    would attach the right words to the wrong values — and nothing at runtime
    would flag it. Indexing makes the mapping reviewable.
    """
    for english, variants in MESSAGES.items():
        if len(_slots(english)) < 2:
            continue
        translated = variants.get(lang)
        if not translated:
            continue
        assert all(s != "" for s in _slots(translated)), (
            f"{lang}: multi-value message must use indexed placeholders "
            f"({{0}}, {{1}}, ...)\n  en: {english!r}\n  {lang}: {translated!r}"
        )


@pytest.mark.parametrize("lang", LANGS)
def test_indexed_placeholders_are_in_range(lang):
    """An index past the end of the captured values renders as English."""
    for english, variants in MESSAGES.items():
        translated = variants.get(lang)
        if not translated:
            continue
        available = len(_slots(english))
        for index in _slots(translated):
            if index:
                assert int(index) < available, (
                    f"{lang}: {{{index}}} but only {available} value(s) exist\n"
                    f"  en: {english!r}\n  {lang}: {translated!r}"
                )


def test_every_catalogue_key_is_actually_raised():
    """Catches the reworded-error case: the key drifts, the lookup silently
    stops matching, and the user quietly gets English again."""
    stale = sorted(set(MESSAGES) - _raised_strings())
    assert not stale, (
        "catalogue keys no longer raised anywhere (reworded or removed?):\n  "
        + "\n  ".join(repr(s) for s in stale)
    )


def test_translate_round_trips_placeholder_values():
    """The whole point of the pattern path: values survive into the output."""
    for english, variants in MESSAGES.items():
        slots = len(_slots(english))
        if slots == 0:
            continue
        probes = [f"VALUE{i}" for i in range(slots)]
        rendered_en = english.format(*probes)
        for lang in LANGS:
            if not variants.get(lang):
                continue
            out = translate(rendered_en, lang)
            for probe in probes:
                assert probe in out, (
                    f"{lang}: {probe} lost while rendering {english!r} -> {out!r}"
                )


def test_translate_leaves_unknown_and_english_alone():
    assert translate("not in the catalogue", "ko") == "not in the catalogue"
    assert translate("", "ko") == ""
    for english in MESSAGES:
        assert translate(english, "en") == english


def test_structured_detail_translates_message_and_keeps_the_rest():
    """The run-start conflict ships {"message", "conflicts"} so the UI can
    offer to resolve them. Translating the payload alongside the sentence
    would break the client; not translating the sentence would strand the
    most-hit error in English."""
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    english = "run not found"
    app = FastAPI()

    from routes import create_app  # installs the handler under test
    handler = None
    for exc_type, fn in create_app().exception_handlers.items():
        if exc_type is HTTPException:
            handler = fn
    assert handler is not None, "HTTPException handler not registered"
    app.add_exception_handler(HTTPException, handler)

    @app.get("/plain")
    def _plain():
        raise HTTPException(status_code=404, detail=english)

    @app.get("/structured")
    def _structured():
        raise HTTPException(status_code=409,
                            detail={"message": english, "conflicts": {"rule_ids": [7]}})

    client = TestClient(app)
    ko = MESSAGES[english]["ko"]

    assert client.get("/plain", headers={"Accept-Language": "ko"}).json()["detail"] == ko
    assert client.get("/plain").json()["detail"] == english

    body = client.get("/structured", headers={"Accept-Language": "ko"}).json()["detail"]
    assert body["message"] == ko
    assert body["conflicts"] == {"rule_ids": [7]}, "payload must survive untouched"


@pytest.mark.parametrize("header,expected", [
    ("ko", "ko"),
    ("ja", "ja"),
    (None, "en"),
    ("", "en"),
    ("en-US,en;q=0.9", "en"),
    ("ko-KR,ko;q=0.9,en;q=0.8", "ko"),
    # An unsupported first choice must not shadow a supported later one —
    # normalize_lang() maps zh to "en", which would otherwise win here.
    ("zh-CN,vi;q=0.8", "vi"),
    ("de,fr", "en"),
    ("*", "en"),
    # Lower q loses regardless of position.
    ("en;q=0.2,th;q=0.9", "th"),
])
def test_accept_language_parsing(header, expected):
    assert _parse_accept_language(header) == expected
