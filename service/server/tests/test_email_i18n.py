from email_i18n import verification_email


def test_english_default():
    subj, html = verification_email("123456", "en")
    assert "123456" in html and "verification code" in subj.lower()


def test_korean_localized():
    subj, html = verification_email("123456", "ko")
    assert "123456" in html
    assert subj != verification_email("123456", "en")[0]   # actually translated


def test_unknown_falls_back_to_english():
    assert verification_email("123456", "xx") == verification_email("123456", "en")
