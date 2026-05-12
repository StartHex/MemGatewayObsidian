from __future__ import annotations

from memory_os.config import EmbeddingProvider
from memory_os.config.models import EmbeddingConfig
from memory_os.llm.base import BaseEmbeddingAdapter
from memory_os.llm.openai_adapter import OpenAIEmbeddingAdapter


class LocalEmbeddingAdapter(BaseEmbeddingAdapter):
    """本地 embedding 服务适配器（兼容 OpenAI API 格式的本地服务，如 text-embeddings-inference）。"""

    def __init__(self, config: EmbeddingConfig):
        self.base_url = (config.base_url or "http://localhost:8080").rstrip("/")
        self.model = config.model
        self.dimension = config.dimension
        self.timeout = 120

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        url = f"{self.base_url}/embed"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                headers=headers,
                json={"texts": texts, "model": self.model},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]


def build_embedding_adapter(config: EmbeddingConfig) -> BaseEmbeddingAdapter:
    if config.provider in (EmbeddingProvider.OPENAI, EmbeddingProvider.OPENAI_COMPATIBLE):
        return OpenAIEmbeddingAdapter(config)
    if config.provider == EmbeddingProvider.LOCAL:
        return LocalEmbeddingAdapter(config)
    raise ValueError(f"不支持的 embedding provider: {config.provider}")
