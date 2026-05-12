from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog

from memory_os.config.models import SystemConfig
from memory_os.vault.file_io import list_directory, move_file
from memory_os.vault.frontmatter import parse_memory, update_fields, write_memory
from memory_os.vault.index import (
    get_all_active_ids,
    register_node,
    unregister_node,
)
from memory_os.vault.models import (
    MemoryNode,
    MemoryStatus,
    MemoryType,
    generate_memory_id,
    slugify,
)

logger = structlog.get_logger(__name__)


def _file_path_for(vault_path: Path, node: MemoryNode, title: str | None = None) -> Path:
    type_dir = {
        MemoryType.RAW_INPUT: "_inbox",
        MemoryType.WORKING_SLOT: "_working",
        MemoryType.EPISODIC: "_memory/episodic",
        MemoryType.SEMANTIC: "_memory/semantic",
        MemoryType.PROCEDURAL: "_memory/procedural",
    }[node.type]
    filename = node.id
    slug_src = node.title or title
    if slug_src:
        slug = slugify(slug_src)
        if slug:
            filename = f"{node.id}-{slug}"
    return vault_path / type_dir / f"{filename}.md"


class MemoryService:
    def __init__(self, vault_path: Path, config: SystemConfig):
        self.vault_path = vault_path
        self.config = config
        self._index_path = vault_path / "_meta" / "index.md"

    async def create(
        self,
        content: str,
        type_: MemoryType,
        *,
        tags: list[str] | None = None,
        importance: float = 50.0,
        context: str | None = None,
        source: str | None = None,
        title: str | None = None,
    ) -> MemoryNode:
        node = MemoryNode(
            id=generate_memory_id(type_),
            type=type_,
            status=MemoryStatus.RAW if type_ == MemoryType.RAW_INPUT else MemoryStatus.ACTIVE,
            tags=tags or [],
            importance=importance,
            context=context,
            source=source,
            content=content,
            title=title,
            strength=float(self.config.memory.initial_strength),
            strength_initial=float(self.config.memory.initial_strength),
            decay_rate=self.config.memory.decay_rate_default,
        )

        file_path = _file_path_for(self.vault_path, node, title=title)
        await write_memory(file_path, node)
        await register_node(self._index_path, node.id, node.type.value, str(file_path.relative_to(self.vault_path)))

        logger.info("memory_created", id=node.id, type=type_.value)
        return node

    async def get(self, memory_id: str) -> MemoryNode:
        file_path = await self._resolve_path(memory_id)
        if file_path is None or not file_path.exists():
            raise FileNotFoundError(f"记忆不存在: {memory_id}")

        node = await parse_memory(file_path)
        node.retrieval_count += 1
        node.last_retrieved = datetime.now(timezone.utc)
        node.last_review = datetime.now(timezone.utc)
        await write_memory(file_path, node)
        return node

    async def update(self, memory_id: str, **fields) -> MemoryNode:
        file_path = await self._resolve_path(memory_id)
        if file_path is None or not file_path.exists():
            raise FileNotFoundError(f"记忆不存在: {memory_id}")
        return await update_fields(file_path, **fields)

    async def update_status(self, memory_id: str, status: MemoryStatus) -> None:
        await self.update(memory_id, status=status)

    async def archive(self, memory_id: str) -> None:
        file_path = await self._resolve_path(memory_id)
        if file_path is None or not file_path.exists():
            raise FileNotFoundError(f"记忆不存在: {memory_id}")

        archive_dir = self.vault_path / "_memory" / "archive"
        new_path = await move_file(file_path, archive_dir / file_path.name)

        await update_fields(new_path, status=MemoryStatus.ARCHIVED)
        await unregister_node(self._index_path, memory_id)
        logger.info("memory_archived", id=memory_id)

    async def list_by_status(self, status: MemoryStatus | None = None) -> list[MemoryNode]:
        active_ids = await get_all_active_ids(self._index_path)
        nodes = []
        for mid in list(active_ids)[:500]:
            try:
                node = await self.get(mid)
                if status is None or node.status == status:
                    nodes.append(node)
            except Exception:
                continue
        return nodes

    async def list_by_type(self, type_: MemoryType) -> list[MemoryNode]:
        all_search_dirs = {
            MemoryType.RAW_INPUT: self.vault_path / "_inbox",
            MemoryType.EPISODIC: self.vault_path / "_memory" / "episodic",
            MemoryType.SEMANTIC: self.vault_path / "_memory" / "semantic",
            MemoryType.PROCEDURAL: self.vault_path / "_memory" / "procedural",
        }
        dir_path = all_search_dirs.get(type_)
        if dir_path is None:
            return []
        files = await list_directory(dir_path, "*.md")
        nodes = []
        for f in files[:500]:
            try:
                nodes.append(await parse_memory(f))
            except Exception:
                continue
        return nodes

    async def list_fading(self) -> list[MemoryNode]:
        active_ids = await get_all_active_ids(self._index_path)
        nodes = []
        for mid in list(active_ids)[:500]:
            try:
                node = await self.get(mid)
                if node.status == MemoryStatus.FADING:
                    nodes.append(node)
            except Exception:
                continue
        return nodes

    async def _resolve_path(self, memory_id: str) -> Path | None:
        from memory_os.vault.index import _resolve_path as resolve
        return await resolve(self.vault_path, memory_id)
