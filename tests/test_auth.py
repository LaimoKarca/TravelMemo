import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.store import MemoryStore


@pytest.fixture
def setup():
    sent = []
    now = [1000.0]
    settings = Settings(
        _env_file=None,
        session_secret="test-secret-" * 4,
        allowed_emails="friend@example.com",
        cookie_secure=False,
    )
    store = MemoryStore()
    app = create_app(
        settings, store, lambda email, code: sent.append((email, code)), clock=lambda: now[0]
    )
    with TestClient(app) as client:
        yield client, sent, now, settings, store


def issue(client):
    return client.post("/api/v1/auth/request-code", json={"email": "friend@example.com"})


def verify(client, code):
    return client.post(
        "/api/v1/auth/verify-code", json={"email": "friend@example.com", "code": code}
    )


def test_login_single_use_session_csrf_logout(setup):
    client, sent, _, _, store = setup
    assert issue(client).status_code == 202
    code = sent[-1][1]
    assert code not in str(store.records)
    response = verify(client, code)
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    token = response.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == "friend@example.com"
    assert verify(client, code).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_allowlist_and_removal(setup):
    client, sent, _, settings, _ = setup
    assert (
        client.post("/api/v1/auth/request-code", json={"email": "stranger@example.com"}).status_code
        == 202
    )
    assert sent == []
    issue(client)
    assert verify(client, sent[-1][1]).status_code == 200
    settings.allowed_emails = ""
    assert client.get("/api/v1/auth/me").status_code == 401


def test_code_expiry_resend_and_attempts(setup):
    client, sent, now, _, _ = setup
    issue(client)
    old = sent[-1][1]
    assert issue(client).status_code == 429
    now[0] += 61
    issue(client)
    assert verify(client, old).status_code == 401
    new = sent[-1][1]
    wrong = "000000" if new != "000000" else "111111"
    for _ in range(4):
        assert verify(client, wrong).status_code == 401
    assert verify(client, new).status_code == 401
    now[0] += 61
    issue(client)
    now[0] += 601
    assert verify(client, sent[-1][1]).status_code == 401


def test_origin_validation_and_input(setup):
    client, _, _, _, _ = setup
    assert (
        client.post(
            "/api/v1/auth/request-code",
            json={"email": "friend@example.com"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert client.post("/api/v1/auth/request-code", json={"email": "bad"}).status_code == 422
    assert verify(client, "123").status_code == 422


def test_resend_does_not_reveal_allowlist(setup):
    client, _, _, _, _ = setup
    for email in ["friend@example.com", "outsider@example.com"]:
        payload = {"email": email}
        assert client.post("/api/v1/auth/request-code", json=payload).status_code == 202
        assert client.post("/api/v1/auth/request-code", json=payload).status_code == 429


def test_smtp_failure_never_leaves_a_usable_code():
    settings = Settings(
        _env_file=None, session_secret="x" * 40, allowed_emails="friend@example.com"
    )
    store = MemoryStore()

    def failed_send(email, code):
        raise OSError("SMTP offline")

    with TestClient(create_app(settings, store, failed_send)) as client:
        response = issue(client)
        assert response.status_code == 503
        assert "SMTP offline" not in response.text
        assert not any(key.startswith("otp:") for key in store.records)


def test_session_expiry(setup):
    client, sent, now, settings, _ = setup
    issue(client)
    assert verify(client, sent[-1][1]).status_code == 200
    now[0] += settings.session_days * 86400 + 1
    assert client.get("/api/v1/auth/me").status_code == 401


def test_production_configuration_requires_https_and_smtp():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_secret="x" * 40, app_env="production")
