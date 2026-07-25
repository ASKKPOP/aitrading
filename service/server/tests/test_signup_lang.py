from signup_lang import _country_to_lang, resolve_signup_lang

class FakeReq:
    def __init__(self, headers=None, host="1.2.3.4"):
        self.headers = headers or {}
        class C: pass
        self.client = C(); self.client.host = host

def test_country_maps_to_lang():
    assert _country_to_lang("KR") == "ko"
    assert _country_to_lang("JP") == "ja"
    assert _country_to_lang("TH") == "th"
    assert _country_to_lang("VN") == "vi"
    assert _country_to_lang("US") == "en"
    assert _country_to_lang(None) is None

def test_falls_back_to_accept_language_when_geo_unknown(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: None)
    req = FakeReq(headers={"accept-language": "ja,en;q=0.8"})
    assert resolve_signup_lang(req) == "ja"

def test_falls_back_to_english_when_nothing_known(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: None)
    req = FakeReq(headers={})
    assert resolve_signup_lang(req) == "en"

def test_geo_country_wins_over_header(monkeypatch):
    monkeypatch.setattr("signup_lang._geo_country", lambda ip: "KR")
    req = FakeReq(headers={"accept-language": "ja"})
    assert resolve_signup_lang(req) == "ko"
