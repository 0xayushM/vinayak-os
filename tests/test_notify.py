"""
send_email carries an optional html part alongside the text — never instead of
it — and a caller that passes only text sends exactly what it sent before.
"""
from email.message import EmailMessage

from vinayak import notify


class _Resp:
    status_code = 200
    content = b'{"id": "re_1"}'
    text = ""

    def json(self): return {"id": "re_1"}


def _resend(monkeypatch):
    import requests
    calls = []
    monkeypatch.setenv("RESEND_API_KEY", "k")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append(kw) or _Resp())
    return calls


def test_resend_payload_is_unchanged_for_text_only_callers(monkeypatch):
    calls = _resend(monkeypatch)
    r = notify.send_email("a@x.com", "Hi", "plain body")
    assert r["sent"] is True and r["provider"] == "resend"
    assert calls[0]["json"]["text"] == "plain body"
    assert "html" not in calls[0]["json"]


def test_resend_sends_html_alongside_the_text(monkeypatch):
    calls = _resend(monkeypatch)
    notify.send_email("a@x.com", "Hi", "plain body", html="<p>rich</p>")
    payload = calls[0]["json"]
    assert payload["text"] == "plain body" and payload["html"] == "<p>rich</p>"
    assert payload["to"] == ["a@x.com"]


class _SMTP:
    sent: list[EmailMessage] = []

    def __init__(self, host, port, timeout=None): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): pass
    def login(self, u, p): pass
    def send_message(self, msg): _SMTP.sent.append(msg)


def _smtp(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", _SMTP)
    _SMTP.sent = []


def test_smtp_text_only_stays_a_single_part_message(monkeypatch):
    _smtp(monkeypatch)
    assert notify.send_email("a@x.com", "Hi", "plain body")["sent"] is True
    msg = _SMTP.sent[0]
    assert not msg.is_multipart() and msg.get_content().strip() == "plain body"


def test_smtp_with_html_is_multipart_alternative_text_first(monkeypatch):
    """Clients show the LAST part they can render, so the text must come first
    or a client that handles html would never be offered it."""
    _smtp(monkeypatch)
    notify.send_email("a@x.com", "Hi", "plain body", html="<p>rich</p>")
    msg = _SMTP.sent[0]
    assert msg.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]
    assert "<p>rich</p>" in msg.get_body(("html",)).get_content()


def test_no_provider_still_returns_cleanly_with_html(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert notify.send_email("a@x.com", "Hi", "b", html="<p>x</p>") == {
        "sent": False, "error": "email provider not configured"}
