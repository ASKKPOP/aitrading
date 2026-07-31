import email_sender


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
