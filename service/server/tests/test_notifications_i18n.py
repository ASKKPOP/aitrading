"""Invariants for the 5-language system-alert catalogue.

These lock in the properties that must hold for every message regardless of the
specific (machine-generated, pending native review) translations: full language
coverage, placeholder parity across languages, clean formatting, safe fallback,
never-raise, and token (enum) localization.
"""
import re

import pytest

from notifications_i18n import MESSAGES, TOKENS, TOKEN_PARAMS, render

LANGS = {"en", "ko", "ja", "th", "vi"}
_PH = re.compile(r"{(\w+)}")


def _placeholders(msg_variant):
    title, body = msg_variant
    return set(_PH.findall(title)) | set(_PH.findall(body))


def _dummy_params(msg_id):
    """A params dict covering every placeholder in the English template.

    Token params get a real token key so their localization path is exercised;
    everything else gets a plain string.
    """
    en = MESSAGES[msg_id]["en"]
    params = {}
    for name in _placeholders(en):
        if name in TOKEN_PARAMS:
            params[name] = next(iter(TOKENS[name]["en"]))  # a valid enum key
        else:
            params[name] = f"<{name}>"
    return params


def test_all_msg_ids_have_all_five_langs():
    for mid, variants in MESSAGES.items():
        assert set(variants.keys()) == LANGS, f"{mid} langs={set(variants)}"


def test_placeholder_parity_across_langs():
    """Every language's title+body must reference exactly the English placeholder
    set — a dropped/renamed placeholder would crash formatting or lose data."""
    for mid, variants in MESSAGES.items():
        want = _placeholders(variants["en"])
        for lang in LANGS:
            got = _placeholders(variants[lang])
            assert got == want, f"{mid}/{lang}: {got} != {want}"


def test_every_message_renders_cleanly_in_every_lang():
    """With all placeholders supplied, no template leaves an unformatted brace."""
    for mid in MESSAGES:
        params = _dummy_params(mid)
        for lang in LANGS:
            title, body = render(mid, lang, **params)
            assert isinstance(title, str) and isinstance(body, str)
            assert "{" not in title and "}" not in title, f"{mid}/{lang} title"
            assert "{" not in body and "}" not in body, f"{mid}/{lang} body"


def test_render_never_raises_on_missing_params():
    """Missing params must fall back (English/raw), never raise, in every lang."""
    for mid in MESSAGES:
        for lang in LANGS:
            title, body = render(mid, lang)  # no params at all
            assert isinstance(title, str) and isinstance(body, str)


def test_unknown_lang_falls_back_to_english():
    a = render("breaker", "xx", scope="account", reason="cap")
    b = render("breaker", "en", scope="account", reason="cap")
    assert a == b


def test_unknown_msg_id_returns_id_and_param_dump():
    title, body = render("does_not_exist", "ko", x=1)
    assert title == "does_not_exist"
    assert "x=1" in body


def test_token_param_is_localized_per_language():
    """A tokenized enum value renders as the language's phrase, not the raw key."""
    # 'watch' body uses {comparator}; 'above' must localize away from the raw key.
    for lang in ("ko", "ja", "th", "vi"):
        params = _dummy_params("watch")
        params["comparator"] = "above"
        _, body = render("watch", lang, **params)
        expected = TOKENS["comparator"][lang]["above"]
        assert expected in body, f"{lang}: {expected!r} not in {body!r}"


def test_unknown_token_key_passes_through():
    """An enum value with no token entry is passed through verbatim (never crashes)."""
    params = _dummy_params("watch")
    params["comparator"] = "sideways"  # not a known comparator key
    _, body = render("watch", "ko", **params)
    assert "sideways" in body


def test_token_families_cover_all_langs():
    for fam, langs in TOKENS.items():
        assert set(langs.keys()) == LANGS, f"token family {fam} langs={set(langs)}"
        keys = set(langs["en"].keys())
        for lang in LANGS:
            assert set(langs[lang].keys()) == keys, f"{fam}/{lang} keys differ"


@pytest.mark.parametrize("mid", sorted(MESSAGES))
def test_ko_differs_from_en_where_there_is_translatable_text(mid):
    """Sanity that ko isn't a silent copy of en — unless the template is pure
    placeholders (nothing to translate)."""
    en = MESSAGES[mid]["en"]
    ko = MESSAGES[mid]["ko"]
    en_text = re.sub(_PH, "", en[0] + en[1]).strip()
    # Only assert when the English has actual words (not just placeholders/punct).
    if re.search(r"[A-Za-z]{3,}", en_text):
        assert ko != en, f"{mid}: ko identical to en despite translatable text"
