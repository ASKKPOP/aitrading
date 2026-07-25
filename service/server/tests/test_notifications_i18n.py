from notifications_i18n import render, MESSAGES


def test_english_render():
    title, body = render("breaker", "en", scope="account", reason="daily loss cap")
    assert title == "Circuit breaker HALT (account)"
    assert "daily loss cap" in body


def test_korean_title_differs_when_translated():
    en = render("run_stopped", "en", run_id=7, reason="loss")
    ko = render("run_stopped", "ko", run_id=7, reason="loss")
    assert ko[0] != en[0]         # ko title is localized
    assert "7" in ko[1] or "7" in ko[0]


def test_unknown_lang_falls_back_to_english():
    assert render("trade_executed", "xx", side="BUY", qty=1, symbol="BTC", price=100) == \
           render("trade_executed", "en", side="BUY", qty=1, symbol="BTC", price=100)


def test_every_msg_id_has_english():
    for mid, variants in MESSAGES.items():
        assert "en" in variants, f"{mid} missing en"


def test_missing_param_falls_back_not_raises():
    # A template referencing an unpassed param must return English, never raise.
    title, body = render("breaker", "ko")   # no scope/reason
    assert isinstance(title, str) and isinstance(body, str)
