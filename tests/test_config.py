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
