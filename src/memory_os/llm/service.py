from __future__ import annotations

import asyncio

import structlog

from memory_os.config import Provider
from memory_os.config.models import SystemConfig
from memory_os.llm.anthropic_adapter import AnthropicChatAdapter
from memory_os.llm.base import BaseChatAdapter, BaseEmbeddingAdapter
from memory_os.llm.embedding import build_embedding_adapter
from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse
from memory_os.llm.openai_adapter import OpenAIChatAdapter

logger = structlog.get_logger(__name__)


def _iter_chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class LLMService:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.chat_adapter = self._build_chat_adapter(config.llm.chat)
        self.fallback_adapter = (
            self._build_chat_adapter(config.llm.fallback) if config.llm.fallback else None
        )
        self.embedding_adapter = build_embedding_adapter(config.llm.embedding)

    def _build_chat_adapter(self, cfg) -> BaseChatAdapter:
        if cfg.provider in (Provider.OPENAI, Provider.OPENAI_COMPATIBLE):
            return OpenAIChatAdapter(cfg)
        if cfg.provider == Provider.ANTHROPIC:
            return AnthropicChatAdapter(cfg)
        raise ValueError(f"不支持的 provider: {cfg.provider}")

    def _apply_override(self, req: UnifiedChatRequest, agent_name: str) -> UnifiedChatRequest:
        overrides = self.config.llm.agent_overrides
        agent_override = getattr(overrides, agent_name, None)
        if agent_override is None:
            return req
        return UnifiedChatRequest(
            system=req.system,
            messages=req.messages,
            temperature=agent_override.temperature if agent_override.temperature is not None else req.temperature,
            max_tokens=agent_override.max_tokens if agent_override.max_tokens is not None else req.max_tokens,
            response_format=req.response_format,
        )

    async def chat(
        self, request: UnifiedChatRequest, *, agent_name: str | None = None
    ) -> UnifiedChatResponse:
        if agent_name:
            request = self._apply_override(request, agent_name)

        last_error = None
        for attempt in range(self.config.llm.chat.retry_max + 1):
            try:
                return await self.chat_adapter.chat(request)
            except Exception as exc:
                last_error = exc
                logger.warning("llm_chat_retry", attempt=attempt, error=str(exc))
                if attempt < self.config.llm.chat.retry_max:
                    await asyncio.sleep(2**attempt)

        if self.fallback_adapter:
            logger.info("llm_fallback_used")
            return await self.fallback_adapter.chat(request)

        raise last_error or RuntimeError("LLM chat failed with no fallback")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        batch_size = self.config.llm.embedding.batch_size
        results = []
        for batch in _iter_chunks(texts, batch_size):
            results.extend(await self.embedding_adapter.embed(batch))
        return results
