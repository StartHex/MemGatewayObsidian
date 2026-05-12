from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from memory_os.vault.file_io import atomic_write, safe_read

logger = structlog.get_logger(__name__)

_ACTIVE_MARKER = "active"
_SEPARATOR = " | "


async def _read_index_lines(index_path: Path) -> list[str]:
    if not index_path.exists():
        return []
    content = await safe_read(index_path)
    lines = content.strip().split("\n")
    if lines == [""]:
        return []
    return lines


async def register_node(index_path: Path, memory_id: str, memory_type: str, file_path: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = await _read_index_lines(index_path)
    entry = f"{memory_id}{_SEPARATOR}{memory_type}{_SEPARATOR}{file_path}{_SEPARATOR}{_ACTIVE_MARKER}"
    existing = {line.split(_SEPARATOR)[0] for line in lines}
    if memory_id in existing:
        lines = [line for line in lines if not line.startswith(memory_id)]
    lines.append(entry)
    await atomic_write(index_path, "\n".join(lines) + "\n")


async def unregister_node(index_path: Path, memory_id: str) -> None:
    lines = await _read_index_lines(index_path)
    lines = [line for line in lines if not line.startswith(memory_id)]
    await atomic_write(index_path, "\n".join(lines) + "\n")


async def get_all_active_ids(index_path: Path) -> set[str]:
    lines = await _read_index_lines(index_path)
    result = set()
    for line in lines:
        parts = line.split(_SEPARATOR)
        if len(parts) >= 4 and parts[3] == _ACTIVE_MARKER:
            result.add(parts[0])
    return result


async def get_orphan_nodes(index_path: Path, vault_path: Path) -> list[str]:
    from memory_os.vault.frontmatter import parse_memory

    active_ids = await get_all_active_ids(index_path)
    orphans = []
    for mid in active_ids:
        node_path = await _resolve_path(vault_path, mid)
        if node_path and node_path.exists():
            node = await parse_memory(node_path)
            if not node.links_to and not node.links_from:
                orphans.append(mid)
    return orphans


async def _resolve_path(vault_path: Path, memory_id: str) -> Path | None:
    index_path = vault_path / "_meta" / "index.md"
    lines = await _read_index_lines(index_path)
    for line in lines:
        parts = line.split(_SEPARATOR)
        if parts[0] == memory_id and len(parts) >= 3:
            return vault_path / parts[2]
    return None
