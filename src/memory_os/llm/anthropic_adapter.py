from __future__ import annotations

import httpx
import structlog

from memory_os.config.models import ChatConfig
from memory_os.llm.base import BaseChatAdapter
from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse

logger = structlog.get_logger(__name__)


class AnthropicChatAdapter(BaseChatAdapter):
    def __init__(self, config: ChatConfig):
        self.model = config.model
        self.api_key = config.api_key
        self.timeout = config.timeout_seconds

    async def chat(self, req: UnifiedChatRequest) -> UnifiedChatResponse:
        payload = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": req.messages,
            "temperature": req.temperature,
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return UnifiedChatResponse(
            content=data["content"][0]["text"],
            model=data.get("model", self.model),
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "end_turn"),
        )
