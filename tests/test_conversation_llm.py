from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.llm import AssistantStructuredOutput, MockLLM, OpenAILLM


def test_assistant_structured_output_validation():
    valid = AssistantStructuredOutput(
        status="answered",
        content="2026-11-01 造訪了晴空塔。",
        cited_event_ids=["evt-1", "evt-2"],
    )
    assert valid.status == "answered"
    assert valid.content == "2026-11-01 造訪了晴空塔。"
    assert valid.cited_event_ids == ["evt-1", "evt-2"]

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        AssistantStructuredOutput(
            status="answered",
            content="ok",
            extra_field="disallowed",
        )

    # Invalid status forbidden
    with pytest.raises(ValidationError):
        AssistantStructuredOutput(
            status="unknown_status",  # type: ignore
            content="ok",
        )


def test_openai_llm_without_api_key():
    llm = OpenAILLM(api_key="", model="gpt-6-luna")
    res = llm.generate("instructions", "input_text")
    assert res.status == "unavailable"
    assert "尚未設定" in res.content
    assert res.input_tokens == 0
    assert res.output_tokens == 0


def test_openai_llm_responses_parse_success():
    llm = OpenAILLM(api_key="sk-test-key", model="gpt-6-luna", timeout=45.0, max_output_tokens=2000)

    mock_parsed = AssistantStructuredOutput(
        status="answered",
        content="根據紀錄，您在11月1日造訪了東京鐵塔。",
        cited_event_ids=["evt-123"],
    )

    mock_response = MagicMock()
    mock_response.output_parsed = mock_parsed
    mock_response.usage.input_tokens = 42
    mock_response.usage.output_tokens = 68

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value.__enter__.return_value = mock_client
        mock_openai_cls.return_value.__exit__.return_value = None
        mock_client.responses.parse.return_value = mock_response

        result = llm.generate("System instructions", "User evidence and query")

        mock_openai_cls.assert_called_once_with(
            api_key="sk-test-key",
            timeout=45.0,
            max_retries=0,
        )
        mock_client.responses.parse.assert_called_once_with(
            model="gpt-6-luna",
            instructions="System instructions",
            input="User evidence and query",
            text_format=AssistantStructuredOutput,
            store=False,
            timeout=45.0,
            max_output_tokens=2000,
        )

        assert result.status == "answered"
        assert result.content == "根據紀錄，您在11月1日造訪了東京鐵塔。"
        assert result.cited_event_ids == ["evt-123"]
        assert result.input_tokens == 42
        assert result.output_tokens == 68


def test_openai_llm_responses_parse_api_error_no_secret_leak():
    llm = OpenAILLM(api_key="sk-test-key", model="gpt-6-luna")

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value.__enter__.return_value = mock_client
        mock_openai_cls.return_value.__exit__.return_value = None
        mock_client.responses.parse.side_effect = RuntimeError("OpenAI connection timeout")

        with patch("backend.llm.logger") as mock_logger:
            result = llm.generate("secret instructions", "secret query with private token")
            assert result.status == "unavailable"
            assert "無法使用" in result.content

            # Verify logger only records exception class name, never message or secret data
            mock_logger.error.assert_called_once()
            log_args = mock_logger.error.call_args[0]
            assert "secret" not in str(log_args)
            assert log_args[1] == "RuntimeError"


def test_mock_llm():
    mock = MockLLM(
        default_status="insufficient_evidence",
        default_content="證據不足",
        default_cited_event_ids=[],
        input_tokens=10,
        output_tokens=20,
    )
    res = mock.generate("inst", "query")
    assert res.status == "insufficient_evidence"
    assert res.content == "證據不足"
    assert res.input_tokens == 10
    assert res.output_tokens == 20
    assert len(mock.calls) == 1
