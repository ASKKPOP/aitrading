import json

import email_sender


class _FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_uses_localized_subject(monkeypatch):
    captured = {}

    class FakeEmails:
        @staticmethod
        def send(payload):
            captured.update(payload)
            return {"id": "x"}

    monkeypatch.setattr(email_sender, "_RESEND_AVAILABLE", True)
    monkeypatch.setattr(email_sender, "_resend_lib", type("L", (), {"Emails": FakeEmails}))
    email_sender.send_verification_code_email("a@b.com", "654321", "ko")
    # Assert against the catalogue itself, not a pinned translation string.
    from email_i18n import verification_email
    assert captured["subject"] == verification_email("654321", "ko")[0]
    assert captured["subject"] != verification_email("654321", "en")[0]
    assert "654321" in captured["html"]


def test_sendgrid_fallback_when_resend_unconfigured(monkeypatch):
    """Prod has no RESEND_API_KEY — the code must go out via SendGrid,
    the rail that already delivers alert email."""
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(email_sender, "_RESEND_AVAILABLE", False)
    monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
    monkeypatch.setenv("ALERT_FROM_EMAIL", "cs@example.com")
    monkeypatch.setattr(email_sender.urllib.request, "urlopen", fake_urlopen)

    ok = email_sender.send_verification_code_email(
        "a@b.com", "654321", "ko", purpose="invite")

    assert ok is True
    assert captured["url"] == "https://api.sendgrid.com/v3/mail/send"
    assert captured["auth"] == "Bearer sg-test-key"
    payload = captured["payload"]
    from email_i18n import verification_email
    assert payload["subject"] == verification_email("654321", "ko", "invite")[0]
    assert payload["from"]["email"] == "cs@example.com"
    assert payload["personalizations"][0]["to"][0]["email"] == "a@b.com"
    # SendGrid requires text/plain before text/html, and both carry the code.
    content = payload["content"]
    assert [c["type"] for c in content] == ["text/plain", "text/html"]
    assert all("654321" in c["value"] for c in content)


def test_sendgrid_fallback_after_resend_error(monkeypatch):
    """A Resend failure should fall through to SendGrid, not give up."""

    class BrokenEmails:
        @staticmethod
        def send(payload):
            raise RuntimeError("resend down")

    sent = {}

    def fake_urlopen(req, timeout=0):
        sent["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(email_sender, "_RESEND_AVAILABLE", True)
    monkeypatch.setattr(email_sender, "_resend_lib",
                        type("L", (), {"Emails": BrokenEmails}))
    monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
    monkeypatch.setenv("ALERT_FROM_EMAIL", "cs@example.com")
    monkeypatch.setattr(email_sender.urllib.request, "urlopen", fake_urlopen)

    assert email_sender.send_verification_code_email("a@b.com", "111222") is True
    assert "111222" in sent["payload"]["content"][0]["value"]


def test_no_provider_configured_returns_false(monkeypatch):
    """Neither rail configured → False, so callers log the code fallback."""
    monkeypatch.setattr(email_sender, "_RESEND_AVAILABLE", False)
    monkeypatch.setenv("SENDGRID_API_KEY", "")
    monkeypatch.setenv("ALERT_FROM_EMAIL", "")
    assert email_sender.send_verification_code_email("a@b.com", "999000") is False
