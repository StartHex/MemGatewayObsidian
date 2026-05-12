from enum import Enum


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"


class EmbeddingProvider(str, Enum):
    LOCAL = "local"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
