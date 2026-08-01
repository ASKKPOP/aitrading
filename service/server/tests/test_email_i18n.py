"""Invariants for the 5-language transactional email catalogue."""
from analysis_agents import LANG_NAMES
from email_i18n import _COPY, verification_email

LANGS = tuple(LANG_NAMES)
PURPOSES = tuple(_COPY)


def test_every_purpose_covers_every_language():
    # verification_email falls back to the signup copy for an unknown purpose
    # and to English for an unknown lang — both silent. Parity is the only
    # thing that stops a new purpose shipping half-translated.
    for purpose, langs in _COPY.items():
        assert set(langs) == set(LANGS), f"{purpose}: {set(LANGS) ^ set(langs)}"
        for lang, copy in langs.items():
            assert set(copy) == {"subject", "heading", "intro", "note"}, f"{purpose}/{lang}"


def test_all_langs_render_code_and_branding():
    for lang in LANGS:
        for purpose in PURPOSES:
            subj, html = verification_email("654321", lang, purpose)
            assert subj.strip(), f"{lang}/{purpose}: empty subject"
            assert "654321" in html, f"{lang}/{purpose}: code missing"
            assert "Sooppiy" in html, f"{lang}/{purpose}: branding missing"
            assert "{code}" not in html, f"{lang}/{purpose}: unformatted placeholder"


def test_english_wording():
    signup_subj, _ = verification_email("123456", "en")
    assert "confirm your email" in signup_subj.lower()
    reset_subj, _ = verification_email("123456", "en", "reset")
    assert "password" in reset_subj.lower()


def test_non_english_subjects_are_translated():
    en_subj = verification_email("1", "en")[0]
    for lang in tuple(l for l in LANG_NAMES if l != "en"):
        assert verification_email("1", lang)[0] != en_subj, f"{lang} subject not translated"


def test_unknown_lang_falls_back_to_english():
    assert verification_email("123456", "xx") == verification_email("123456", "en")
