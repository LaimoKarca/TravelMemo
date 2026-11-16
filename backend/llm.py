"""OpenAI Responses structured outputs and LLM interface for conversation."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class AssistantStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "insufficient_evidence", "needs_clarification"]
    content: str = Field(description="對話回答內容")
    cited_event_ids: list[str] = Field(
        default_factory=list,
        description="本次回答所引用的事件 ID 清單（僅能從提供的證據中選取）",
    )


class LLMResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "insufficient_evidence", "needs_clarification", "unavailable"]
    content: str
    cited_event_ids: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, instructions: str, input_text: str) -> LLMResult:
        """Generates structured response based on instructions and input text."""


class OpenAILLM(BaseLLM):
    """Official OpenAI Python Responses structured outputs implementation.

    Uses client.responses.parse(text_format=AssistantStructuredOutput, store=False)
    preserving gpt-6-luna.
    Configures max_retries=0 to bound timeouts and closes the client in a context manager.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-6-luna",
        timeout: float = 45.0,
        max_output_tokens: int = 2000,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens

    def generate(self, instructions: str, input_text: str) -> LLMResult:
        if not self.api_key:
            return LLMResult(
                status="unavailable",
                content="AI 服務尚未設定，請先設定 API 金鑰。",
                cited_event_ids=[],
                input_tokens=0,
                output_tokens=0,
            )

        try:
            from openai import OpenAI

            with OpenAI(
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=0,
            ) as client:
                response = client.responses.parse(
                    model=self.model,
                    instructions=instructions,
                    input=input_text,
                    text_format=AssistantStructuredOutput,
                    store=False,
                    timeout=self.timeout,
                    max_output_tokens=self.max_output_tokens,
                )
                parsed: AssistantStructuredOutput | None = response.output_parsed
                in_tokens = response.usage.input_tokens if response.usage else 0
                out_tokens = response.usage.output_tokens if response.usage else 0

                if parsed is None:
                    return LLMResult(
                        status="unavailable",
                        content="AI 服務回傳格式異常，請稍後再試。",
                        cited_event_ids=[],
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                    )

                return LLMResult(
                    status=parsed.status,
                    content=parsed.content,
                    cited_event_ids=parsed.cited_event_ids,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                )
        except Exception as exc:  # noqa: BLE001
            # 錯誤不可記私密內容：僅記錄例外類別，不記錄輸入內容或私密資訊
            logger.error("LLM generation error: %s", type(exc).__name__)
            return LLMResult(
                status="unavailable",
                content="AI 服務暫時無法使用，請稍後再試。",
                cited_event_ids=[],
                input_tokens=0,
                output_tokens=0,
            )


class MockLLM(BaseLLM):
    """Injectable mock LLM for non-paid testing and offline development."""

    def __init__(
        self,
        default_status: Literal[
            "answered", "insufficient_evidence", "needs_clarification", "unavailable"
        ] = "answered",
        default_content: str = "這是測試回答。",
        default_cited_event_ids: list[str] | None = None,
        input_tokens: int = 15,
        output_tokens: int = 25,
        handler: Callable[[str, str], LLMResult] | None = None,
    ):
        self.default_status = default_status
        self.default_content = default_content
        self.default_cited_event_ids = default_cited_event_ids or []
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.handler = handler
        self.calls: list[dict[str, str]] = []

    def generate(self, instructions: str, input_text: str) -> LLMResult:
        self.calls.append({"instructions": instructions, "input_text": input_text})
        if self.handler:
            return self.handler(instructions, input_text)
        return LLMResult(
            status=self.default_status,
            content=self.default_content,
            cited_event_ids=list(self.default_cited_event_ids),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )
