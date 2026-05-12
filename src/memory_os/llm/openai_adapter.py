from __future__ import annotations

import httpx
import structlog

from memory_os.config.models import ChatConfig
from memory_os.llm.base import BaseChatAdapter, BaseEmbeddingAdapter
from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse

logger = structlog.get_logger(__name__)


class OpenAIChatAdapter(BaseChatAdapter):
    def __init__(self, config: ChatConfig):
        self.base_url = (config.base_url or "https://api.openai.com").rstrip("/")
        self.model = config.model
        self.api_key = config.api_key
        self.timeout = config.timeout_seconds

    async def chat(self, req: UnifiedChatRequest) -> UnifiedChatResponse:
        messages = [{"role": "system", "content": req.system}] + req.messages

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        return UnifiedChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.model),
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(self, config):
        self.base_url = (config.base_url or "https://api.openai.com").rstrip("/")
        self.model = config.model
        self.api_key = config.api_key or ""
        self.dimension = config.dimension
        self.timeout = 120

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        data_list = sorted(data["data"], key=lambda x: x["index"])
        return [d["embedding"] for d in data_list]
