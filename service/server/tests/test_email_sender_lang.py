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
    assert captured["subject"] == "Sooppiy 인증 코드"
    assert "654321" in captured["html"]
