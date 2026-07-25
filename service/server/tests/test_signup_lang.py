import httpx
import pytest

import signup_lang
from signup_lang import _client_ip, _country_to_lang, _geo_country, resolve_signup_lang

class FakeReq:
    def __init__(self, headers=None, host="1.2.3.4"):
        self.headers = headers or {}
        class C: pass
        self.client = C(); self.client.host = host

class FakeResp:
    def __init__(self, status_code=200, json_data=None, json_exc=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_exc = json_exc

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._json_data

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


# --- _geo_country: real network path (httpx.get monkeypatched, not _geo_country) ---

def test_geo_country_returns_code_on_200(monkeypatch):
    monkeypatch.setattr(signup_lang.httpx, "get", lambda url, timeout: FakeResp(200, {"countryCode": "KR"}))
    assert _geo_country("8.8.8.8") == "KR"

def test_geo_country_none_when_httpx_raises_timeout(monkeypatch):
    def raise_timeout(url, timeout):
        raise httpx.TimeoutException("timed out")
    monkeypatch.setattr(signup_lang.httpx, "get", raise_timeout)
    assert _geo_country("8.8.8.8") is None

def test_geo_country_none_when_httpx_raises_generic_exception(monkeypatch):
    def raise_generic(url, timeout):
        raise RuntimeError("boom")
    monkeypatch.setattr(signup_lang.httpx, "get", raise_generic)
    assert _geo_country("8.8.8.8") is None

def test_geo_country_none_on_non_200_status(monkeypatch):
    monkeypatch.setattr(signup_lang.httpx, "get", lambda url, timeout: FakeResp(500, {"countryCode": "KR"}))
    assert _geo_country("8.8.8.8") is None

def test_geo_country_none_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        signup_lang.httpx,
        "get",
        lambda url, timeout: FakeResp(200, json_exc=ValueError("malformed")),
    )
    assert _geo_country("8.8.8.8") is None

@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",       # loopback
        "10.0.0.5",        # private
        "192.168.1.1",     # private
        "172.16.0.1",      # private (missed by old prefix check)
        "169.254.1.1",     # link-local
        "::1",             # IPv6 loopback
        "fe80::1",         # IPv6 link-local
    ],
)
def test_geo_country_none_for_private_or_loopback_ip_no_network_call(monkeypatch, ip):
    called = {"hit": False}

    def fake_get(url, timeout):
        called["hit"] = True
        return FakeResp(200, {"countryCode": "KR"})

    monkeypatch.setattr(signup_lang.httpx, "get", fake_get)
    assert _geo_country(ip) is None
    assert called["hit"] is False

def test_geo_country_none_for_unparseable_ip_no_network_call(monkeypatch):
    called = {"hit": False}

    def fake_get(url, timeout):
        called["hit"] = True
        return FakeResp(200, {"countryCode": "KR"})

    monkeypatch.setattr(signup_lang.httpx, "get", fake_get)
    assert _geo_country("not-an-ip") is None
    assert called["hit"] is False


# --- _client_ip: X-Forwarded-For parsing ---

def test_client_ip_uses_first_xff_hop():
    req = FakeReq(headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, host="9.9.9.9")
    assert _client_ip(req) == "203.0.113.7"

def test_client_ip_falls_back_to_request_client_host_when_no_xff():
    req = FakeReq(headers={}, host="9.9.9.9")
    assert _client_ip(req) == "9.9.9.9"
