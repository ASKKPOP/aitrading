"""Invariants for the 5-language transactional email catalogue."""
from email_i18n import verification_email

LANGS = ("en", "ko", "ja", "th", "vi")


def test_all_langs_render_code_and_tags():
    for lang in LANGS:
        subj, html = verification_email("654321", lang)
        assert subj.strip(), f"{lang}: empty subject"
        assert "654321" in html, f"{lang}: code missing"
        assert "<strong>" in html and "<p>" in html, f"{lang}: tags missing"
        assert "{code}" not in html, f"{lang}: unformatted placeholder"


def test_english_wording():
    subj, html = verification_email("123456", "en")
    assert "verification code" in subj.lower()


def test_non_english_subjects_are_translated():
    en_subj = verification_email("1", "en")[0]
    for lang in ("ko", "ja", "th", "vi"):
        assert verification_email("1", lang)[0] != en_subj, f"{lang} subject not translated"


def test_unknown_lang_falls_back_to_english():
    assert verification_email("123456", "xx") == verification_email("123456", "en")
