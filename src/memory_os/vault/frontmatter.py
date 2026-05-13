from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import frontmatter as fm
import structlog

from memory_os.vault.file_io import atomic_write, safe_read
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType

logger = structlog.get_logger(__name__)

_FRONTMATTER_FIELDS = {
    "id", "type", "status", "title", "strength", "strength_initial", "decay_rate",
    "last_review", "next_review", "retrieval_count", "retrieval_ease",
    "last_retrieved", "source", "source_confidence", "raw_input_ref", "raw_output",
    "tags", "links_to", "links_from", "moc", "embedding_id", "vector_status",
    "vector_model", "vector_dim", "context", "emotional_tag", "importance", "confidence",
    "conflict", "conflicting_with", "conflict_note",
}


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, MemoryType):
        return value.value
    if isinstance(value, MemoryStatus):
        return value.value
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _deserialize_value(key: str, value):
    if value is None:
        return None
    if key in ("last_review", "next_review", "last_retrieved"):
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if key == "type":
        return MemoryType(value) if isinstance(value, str) else value
    if key in ("status", "vector_status"):
        return MemoryStatus(value) if isinstance(value, str) else value
    return value


async def parse_memory(file_path: Path) -> MemoryNode:
    loop = asyncio.get_running_loop()

    def _parse():
        post = fm.load(str(file_path))
        meta = dict(post.metadata)
        model_kwargs = {}
        for key in _FRONTMATTER_FIELDS:
            if key in meta:
                model_kwargs[key] = _deserialize_value(key, meta[key])
        model_kwargs["content"] = post.content.strip()
        if "id" not in model_kwargs:
            model_kwargs["id"] = file_path.stem
        if "type" not in model_kwargs:
            model_kwargs["type"] = MemoryType.SEMANTIC
        return MemoryNode(**model_kwargs)

    return await loop.run_in_executor(None, _parse)


async def write_memory(file_path: Path, node: MemoryNode) -> None:
    meta = {}
    for key in _FRONTMATTER_FIELDS:
        val = getattr(node, key, None)
        if val is not None and val != [] and val != "" and val != 0:
            meta[key] = _serialize_value(val)

    post = fm.Post(node.content, **meta)
    loop = asyncio.get_running_loop()

    def _serialize() -> str:
        return fm.dumps(post) + "\n"

    text = await loop.run_in_executor(None, _serialize)
    await atomic_write(file_path, text)


async def update_fields(file_path: Path, **kwargs) -> MemoryNode:
    node = await parse_memory(file_path)
    for key, value in kwargs.items():
        if key in _FRONTMATTER_FIELDS or key == "content":
            setattr(node, key, value)
    await write_memory(file_path, node)
    return node
