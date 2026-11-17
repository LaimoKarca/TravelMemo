import smtplib
from types import SimpleNamespace

import pytest

from backend.auth import AuthError
from backend.mail import smtp_sender


class FakeSMTPClient:
    def __init__(self, host, port, timeout=10, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = context
        self.started_tls = False
        self.login_credentials = None
        self.sent_messages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        self.login_credentials = (user, password)

    def send_message(self, message):
        self.sent_messages.append(message)


def test_smtp_captured_message_and_behavior(monkeypatch):
    captured_clients = []
    ssl_captured_clients = []

    def fake_smtp_factory(host, port, **kwargs):
        client = FakeSMTPClient(host, port, **kwargs)
        captured_clients.append(client)
        return client

    def fake_smtp_ssl_factory(host, port, **kwargs):
        client = FakeSMTPClient(host, port, **kwargs)
        ssl_captured_clients.append(client)
        return client

    monkeypatch.setattr(smtplib, "SMTP", fake_smtp_factory)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fake_smtp_ssl_factory)

    # 1. Missing host raises AuthError(503)
    no_host_settings = SimpleNamespace(smtp_host="")
    with pytest.raises(AuthError) as exc_info:
        smtp_sender(no_host_settings)("user@example.com", "123456")
    assert exc_info.value.status == 503
    assert "尚未設定寄信服務" in str(exc_info.value)

    # 2. Main delivery check: MIME multipart/alternative, code, escaping, design tokens, links
    settings = SimpleNamespace(
        smtp_host="mail.example.com",
        smtp_port=587,
        smtp_tls="starttls",
        smtp_user="smtp_user",
        smtp_auth=True,
        smtp_password="smtp_password",
        smtp_from="TravelMemo <noreply@example.com>",
        smtp_timeout=10,
        otp_seconds=600,
        public_url="https://travelmemo.example.com",
    )
    sender = smtp_sender(settings)
    sender("traveler@example.com", "849201")

    assert len(captured_clients) == 1
    client = captured_clients[0]
    assert client.host == "mail.example.com"
    assert client.port == 587
    assert client.timeout == 10
    assert client.started_tls is True
    assert client.login_credentials == ("smtp_user", "smtp_password")
    assert len(client.sent_messages) == 1

    msg = client.sent_messages[0]
    assert msg["Subject"] == "TravelMemo 登入驗證碼"
    assert msg["From"] == "TravelMemo <noreply@example.com>"
    assert msg["To"] == "traveler@example.com"

    # MIME multipart/alternative validation
    assert msg.is_multipart() is True
    assert msg.get_content_type() == "multipart/alternative"

    parts = list(msg.iter_parts())
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"

    plain_body = parts[0].get_content()
    assert "你的 TravelMemo 驗證碼是：849201" in plain_body
    assert "有效時間為 10 分鐘。" in plain_body
    assert "若非本人操作，請忽略此信。" in plain_body

    html_body = parts[1].get_content()
    # Design tokens check
    assert "#FFFFFF" in html_body
    assert "#F5F7FB" in html_body
    assert "#172B4D" in html_body
    assert "#245AE8" in html_body
    assert "#F4C84B" in html_body
    assert "#DCEDE5" in html_body

    # Email-safe table & prominent selectable code
    assert '<table role="presentation"' in html_body
    assert "user-select: all" in html_body
    assert "849201" in html_body

    # Expiry, ignore line, and brand heading
    assert "登入驗證碼" in html_body
    assert "有效時間為 10 分鐘。" in html_body
    assert "若非本人操作，請忽略此信。" in html_body

    # Private URL link
    assert "https://travelmemo.example.com" in html_body
    assert "前往 TravelMemo" in html_body

    # Verify no external assets (scripts, external stylesheets, external image tags)
    assert "<script" not in html_body.lower()
    assert '<link rel="stylesheet"' not in html_body.lower()
    assert "<img" not in html_body.lower()

    # 3. HTML escaping and injection safety check
    sender("traveler@example.com", '<script>alert("hack")</script>')
    escaped_client = captured_clients[-1]
    escaped_msg = escaped_client.sent_messages[0]
    escaped_html = list(escaped_msg.iter_parts())[1].get_content()
    assert '<script>alert("hack")</script>' not in escaped_html
    assert "&lt;script&gt;alert(&quot;hack&quot;)&lt;/script&gt;" in escaped_html

    # Dangerous URL scheme check
    settings_unsafe_url = SimpleNamespace(
        smtp_host="mail.example.com",
        smtp_port=587,
        smtp_tls="starttls",
        smtp_user="u",
        smtp_auth=True,
        smtp_password="p",
        smtp_from="noreply@example.com",
        smtp_timeout=10,
        otp_seconds=300,
        public_url="javascript:alert(1)",
    )
    smtp_sender(settings_unsafe_url)("traveler@example.com", "112233")
    unsafe_client = captured_clients[-1]
    unsafe_html = list(unsafe_client.sent_messages[0].iter_parts())[1].get_content()
    assert "javascript:" not in unsafe_html

    # 4. Existing behavior variations: SSL mode and no-auth mode
    ssl_settings = SimpleNamespace(
        smtp_host="smtp.ssl.example.com",
        smtp_port=465,
        smtp_tls="ssl",
        smtp_user="",
        smtp_auth=False,
        smtp_password="",
        smtp_from="noreply@example.com",
        smtp_timeout=5,
        otp_seconds=600,
        public_url="",
    )
    smtp_sender(ssl_settings)("traveler@example.com", "999888")
    assert len(ssl_captured_clients) == 1
    ssl_client = ssl_captured_clients[0]
    assert ssl_client.host == "smtp.ssl.example.com"
    assert ssl_client.port == 465
    assert ssl_client.timeout == 5
    assert ssl_client.context is not None
    assert ssl_client.login_credentials is None
    assert len(ssl_client.sent_messages) == 1
