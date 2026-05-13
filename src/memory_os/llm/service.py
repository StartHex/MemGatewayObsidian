from __future__ import annotations

import asyncio

import structlog

from pathlib import Path

from memory_os.config import Provider
from memory_os.config.models import SystemConfig
from memory_os.llm.anthropic_adapter import AnthropicChatAdapter
from memory_os.llm.base import BaseChatAdapter, BaseEmbeddingAdapter
from memory_os.llm.embedding import build_embedding_adapter
from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse
from memory_os.llm.openai_adapter import OpenAIChatAdapter
from memory_os.llm.token_tracker import TokenRecord, TokenTracker

logger = structlog.get_logger(__name__)


def _iter_chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class LLMService:
    def __init__(self, config: SystemConfig, vault_path: Path | None = None):
        self.config = config
        self.chat_adapter = self._build_chat_adapter(config.llm.chat)
        self.fallback_adapter = (
            self._build_chat_adapter(config.llm.fallback) if config.llm.fallback else None
        )
        try:
            self.embedding_adapter = build_embedding_adapter(config.llm.embedding) if config.llm.embedding else None
        except Exception:
            logger.warning("embedding_adapter_init_failed", error=str(Exception))
            self.embedding_adapter = None
        self.token_tracker = TokenTracker(vault_path) if vault_path else None

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
                resp = await self.chat_adapter.chat(request)
                self._log_tokens(resp, agent_name or "unknown")
                return resp
            except Exception as exc:
                last_error = exc
                logger.warning("llm_chat_retry", attempt=attempt, error=str(exc))
                if attempt < self.config.llm.chat.retry_max:
                    await asyncio.sleep(2**attempt)

        if self.fallback_adapter:
            logger.info("llm_fallback_used")
            resp = await self.fallback_adapter.chat(request)
            self._log_tokens(resp, agent_name or "unknown")
            return resp

        raise last_error or RuntimeError("LLM chat failed with no fallback")

    def _log_tokens(self, resp: UnifiedChatResponse, agent_name: str) -> None:
        if self.token_tracker is None:
            return
        from datetime import datetime, timezone
        self.token_tracker.log(TokenRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_name=agent_name,
            model=resp.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
        ))

    @property
    def has_embedding(self) -> bool:
        return self.embedding_adapter is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embedding_adapter:
            return []
        batch_size = self.config.llm.embedding.batch_size
        results = []
        for batch in _iter_chunks(texts, batch_size):
            results.extend(await self.embedding_adapter.embed(batch))
        return results
