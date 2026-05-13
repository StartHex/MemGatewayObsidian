from __future__ import annotations

from pydantic import BaseModel, Field

from memory_os.config import EmbeddingProvider, Provider


class ChatConfig(BaseModel):
    provider: Provider
    model: str
    api_key: str
    base_url: str | None = None
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    retry_max: int = Field(default=3, ge=0, le=10)
    retry_backoff: str = "exponential"


class EmbeddingConfig(BaseModel):
    provider: EmbeddingProvider
    model: str
    base_url: str | None = None
    api_key: str | None = None
    dimension: int = Field(ge=128, le=8192)
    batch_size: int = Field(default=32, ge=1, le=256)


class AgentOverride(BaseModel):
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


class AgentOverrides(BaseModel):
    sensory_gateway: AgentOverride = Field(default_factory=AgentOverride)
    consolidation: AgentOverride = Field(default_factory=AgentOverride)
    meta_cognition: AgentOverride = Field(default_factory=AgentOverride)


class LLMConfig(BaseModel):
    chat: ChatConfig
    fallback: ChatConfig | None = None
    embedding: EmbeddingConfig
    agent_overrides: AgentOverrides = Field(default_factory=AgentOverrides)


class AgentSchedule(BaseModel):
    consolidation_cron: str = "0 */4 * * *"
    forgetting_cron: str = "0 3 * * *"
    meta_cognition_cron: str = "0 9 * * 1"
    review_cron: str = "57 8 * * *"


class MemoryParams(BaseModel):
    max_slots: int = Field(default=7, ge=3, le=15)
    eviction_cooldown_minutes: int = 10
    initial_strength: int = Field(default=50, ge=0, le=100)
    decay_rate_default: float = Field(default=0.03, ge=0.001, le=0.5)
    review_boost: float = Field(default=1.2, ge=1.0, le=3.0)
    archive_threshold: int = Field(default=15, ge=0, le=50)
    fading_threshold: int = Field(default=40, ge=0, le=80)
    cascade_max_depth: int = Field(default=2, ge=1, le=5)


class SystemConfig(BaseModel):
    llm: LLMConfig
    agents: AgentSchedule = Field(default_factory=AgentSchedule)
    memory: MemoryParams = Field(default_factory=MemoryParams)
