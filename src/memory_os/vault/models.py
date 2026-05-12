from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    RAW_INPUT = "raw_input"
    WORKING_SLOT = "working_slot"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryStatus(str, Enum):
    RAW = "raw"
    PROCESSING = "processing"
    ACTIVE = "active"
    FADING = "fading"
    ARCHIVED = "archived"


def slugify(text: str, max_len: int = 50) -> str:
    """将文本转为文件名安全的 slug，保留中文。"""
    import re
    slug = re.sub(r"[^\w一-鿿\s-]", "", text)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-")


class MemoryNode(BaseModel):
    id: str
    type: MemoryType
    status: MemoryStatus = MemoryStatus.RAW
    title: str | None = None
    strength: float = Field(default=50.0, ge=0.0, le=100.0)
    strength_initial: float | None = None
    decay_rate: float = Field(default=0.03, ge=0.001, le=0.5)
    last_review: datetime | None = None
    next_review: datetime | None = None
    retrieval_count: int = 0
    retrieval_ease: float = Field(default=0.5, ge=0.0, le=1.0)
    last_retrieved: datetime | None = None
    source: str | None = None
    source_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    links_to: list[str] = Field(default_factory=list)
    links_from: list[str] = Field(default_factory=list)
    moc: str | None = None
    embedding_id: str | None = None
    vector_status: MemoryStatus | None = None
    vector_model: str | None = None
    vector_dim: int | None = None
    context: str | None = None
    raw_output: str | None = None
    emotional_tag: str | None = None
    importance: float = Field(default=50.0, ge=0.0, le=100.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    content: str = ""


def generate_memory_id(type_: MemoryType) -> str:
    from datetime import datetime as dt
    prefix = {
        MemoryType.RAW_INPUT: "raw",
        MemoryType.WORKING_SLOT: "slot",
        MemoryType.EPISODIC: "epi",
        MemoryType.SEMANTIC: "sem",
        MemoryType.PROCEDURAL: "pro",
    }[type_]
    ts = dt.now().strftime("%Y%m%d-%H%M%S")
    return f"mem-{prefix}-{ts}"
