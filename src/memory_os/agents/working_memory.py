from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from memory_os.config.models import SystemConfig
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory, write_memory
from memory_os.vault.models import MemoryNode, MemoryType, generate_memory_id

logger = structlog.get_logger(__name__)


class WorkingMemorySlot(BaseModel):
    slot_id: int
    memory_id: str
    slot_name: str
    pinned: bool = False
    importance: float = 50.0
    retrieval_count: int = 0
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decay_rate: float = 0.03


class EvictionResult(BaseModel):
    evicted_slot: WorkingMemorySlot | None = None
    reason: str = ""


class WorkingMemoryManager:
    def __init__(self, memory: MemoryService, config: SystemConfig, vault_path: Path):
        self.memory = memory
        self.config = config
        self.vault_path = vault_path
        self.working_dir = vault_path / "_working"

    @property
    def max_slots(self) -> int:
        return self.config.memory.max_slots

    async def promote_to_slot(self, memory_id: str, slot_name: str) -> int:
        active = await self._get_active_slots()

        if len(active) >= self.max_slots:
            victim = self._select_victim(active)
            if victim is None:
                raise RuntimeError("所有槽位已 pin，无法分配新槽位")
            await self._evict(victim)
            active = [s for s in active if s.slot_id != victim.slot_id]

        slot_id = self._next_slot_id(active)
        slot = WorkingMemorySlot(
            slot_id=slot_id,
            memory_id=memory_id,
            slot_name=slot_name,
        )
        await self._write_slot_file(slot)
        logger.info("slot_promoted", slot_id=slot_id, memory_id=memory_id)
        return slot_id

    async def get_slot(self, slot_id: int) -> WorkingMemorySlot | None:
        slot_path = self.working_dir / f"slot-{slot_id}-{slot_id}.md"
        if not slot_path.exists():
            files = await list_directory(self.working_dir, f"slot-{slot_id}-*.md")
            if files:
                slot_path = files[0]
            else:
                return None
        node = await parse_memory(slot_path)
        return WorkingMemorySlot(
            slot_id=slot_id,
            memory_id=node.id,
            slot_name=node.content.split("\n")[0].replace("# ", "") if node.content else "",
            pinned=node.importance > 90,
            importance=node.importance,
            retrieval_count=node.retrieval_count,
            last_accessed=node.last_retrieved or datetime.now(timezone.utc),
        )

    async def _get_active_slots(self) -> list[WorkingMemorySlot]:
        files = await list_directory(self.working_dir, "slot-*.md")
        slots = []
        for f in files:
            try:
                node = await parse_memory(f)
                slots.append(WorkingMemorySlot(
                    slot_id=int(f.stem.split("-")[1]) if "-" in f.stem else 0,
                    memory_id=node.id,
                    slot_name=node.content.split("\n")[0].replace("# ", "") if node.content else f.stem,
                    pinned=node.importance > 90,
                    importance=node.importance,
                    retrieval_count=node.retrieval_count,
                    last_accessed=node.last_retrieved or datetime.now(timezone.utc),
                ))
            except Exception:
                continue
        return slots

    def _select_victim(self, slots: list[WorkingMemorySlot]) -> WorkingMemorySlot | None:
        now = datetime.now(timezone.utc)
        candidates = []
        for s in slots:
            if s.pinned:
                continue
            age_seconds = (now - s.last_accessed).total_seconds()
            score = (age_seconds * s.decay_rate * (100 - s.importance)) / (s.retrieval_count + 1)
            candidates.append((score, s))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def _evict(self, slot: WorkingMemorySlot) -> None:
        slot_path = self._slot_path(slot)
        if slot_path.exists():
            cooldown = self.config.memory.eviction_cooldown_minutes
            from datetime import timedelta
            await self.memory.create(
                content=f"# Evicted Slot: {slot.slot_name}\n\nMemory: {slot.memory_id}",
                type_=MemoryType.RAW_INPUT,
                tags=["evicted-slot"],
                importance=slot.importance,
                source="working-memory-eviction",
            )
            slot_path.unlink(missing_ok=True)
            logger.info("slot_evicted", slot_id=slot.slot_id, memory_id=slot.memory_id)

    async def _write_slot_file(self, slot: WorkingMemorySlot) -> None:
        node = MemoryNode(
            id=f"mem-slot-{slot.slot_id}",
            type=MemoryType.WORKING_SLOT,
            status=MemoryStatus.ACTIVE,
            importance=slot.importance,
            retrieval_count=slot.retrieval_count,
            last_retrieved=slot.last_accessed,
            content=f"# {slot.slot_name}\n\nMemory: {slot.memory_id}",
        )
        await write_memory(self._slot_path(slot), node)

    def _slot_path(self, slot: WorkingMemorySlot) -> Path:
        return self.working_dir / f"slot-{slot.slot_id}-{slot.slot_name[:30]}.md"

    def _next_slot_id(self, existing: list[WorkingMemorySlot]) -> int:
        taken = {s.slot_id for s in existing}
        for i in range(1, self.max_slots + 1):
            if i not in taken:
                return i
        raise RuntimeError("槽位已满")
