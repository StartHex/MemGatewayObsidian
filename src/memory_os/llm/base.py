from __future__ import annotations

from abc import ABC, abstractmethod

from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse


class BaseChatAdapter(ABC):
    @abstractmethod
    async def chat(self, request: UnifiedChatRequest) -> UnifiedChatResponse: ...


class BaseEmbeddingAdapter(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
