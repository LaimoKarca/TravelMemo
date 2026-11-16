import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_selected_model_and_secrets_not_in_repr():
    settings = Settings(
        _env_file=None,
        session_secret="s" * 40,
        openai_api_key="private-key",
        cloudflare_tunnel_token="private-token",
    )
    assert settings.openai_model == "gpt-6-luna"
    assert "private-key" not in repr(settings)
    assert "private-token" not in repr(settings)


@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4.1", "gpt-3.5-turbo"])
def test_old_models_rejected(model):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_secret="s" * 40, openai_model=model)


@pytest.mark.parametrize("trusted", ["*", "not-an-ip", "172.30.80.0/24"])
def test_proxy_trust_requires_explicit_ips(trusted):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_secret="s" * 40, trusted_proxy_ips=trusted)


def test_production_cookie_origin_and_schema():
    from fastapi.testclient import TestClient

    from backend.app import create_app
    from backend.store import MemoryStore

    settings = Settings(
        _env_file=None,
        session_secret="s" * 40,
        app_env="production",
        public_url="https://travel.example.com",
        cookie_secure=True,
        allowed_emails="friend@example.com",
        smtp_host="smtp.example.com",
        trusted_proxy_ips="172.30.80.10",
    )
    sent = []
    with TestClient(
        create_app(settings, MemoryStore(), lambda email, code: sent.append(code)),
        base_url="https://travel.example.com",
    ) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/api/docs").status_code == 404
        assert (
            client.post(
                "/api/v1/auth/request-code",
                json={"email": "friend@example.com"},
                headers={"Origin": "https://wrong.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/auth/request-code",
                json={"email": "friend@example.com"},
                headers={"Origin": settings.public_url},
            ).status_code
            == 202
        )
        result = client.post(
            "/api/v1/auth/verify-code", json={"email": "friend@example.com", "code": sent[-1]}
        )
        assert result.status_code == 200
        assert "secure" in result.headers["set-cookie"].lower()
        assert client.get("/api/v1/auth/me").status_code == 200
