from __future__ import annotations

from pydantic import BaseModel, Field


class UnifiedChatRequest(BaseModel):
    system: str
    messages: list[dict] = Field(default_factory=list)
    temperature: float = 0.3
    max_tokens: int = 4096
    response_format: str | None = None  # "json_object" or None


class UnifiedChatResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class UnifiedEmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int
