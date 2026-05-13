from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from memory_os.config.models import SystemConfig
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory, write_memory
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType, generate_memory_id

logger = structlog.get_logger(__name__)


class SlotOperation(BaseModel):
    timestamp: str
    op_type: Literal["promote", "update", "evict", "conclude"]
    content_snippet: str = ""
    description: str = ""


class ReasoningTrace(BaseModel):
    trace_id: str = ""
    slot_id: int = 0
    title: str = ""
    steps: list[str] = []
    conclusion: str = ""
    created_at: str = ""


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
    def __init__(self, memory: MemoryService, config: SystemConfig, vault_path: Path, llm=None):
        self.memory = memory
        self.config = config
        self.vault_path = vault_path
        self.working_dir = vault_path / "_working"
        self.llm = llm

    @property
    def max_slots(self) -> int:
        return self.config.memory.max_slots

    # ── public API ─────────────────────────────────────────

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
        self._log_op(slot_id, SlotOperation(
            timestamp=datetime.now(timezone.utc).isoformat(),
            op_type="promote",
            content_snippet=slot_name[:200],
            description=f"promoted memory {memory_id}",
        ))
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

    async def update_slot(self, slot_id: int, new_content: str) -> bool:
        slot = await self.get_slot(slot_id)
        if slot is None:
            return False

        # Find the actual slot file on disk (slot_name is mutable, so _slot_path
        # may compute a different path after content changed).
        slot_path = self._slot_path(slot)
        if not slot_path.exists():
            files = await list_directory(self.working_dir, f"slot-{slot_id}-*.md")
            if files:
                slot_path = files[0]
            else:
                return False

        node = await parse_memory(slot_path)
        node.content = new_content
        # Write to the new path, then remove old file if the path changed.
        new_path = self.working_dir / f"slot-{slot_id}-{new_content.split(chr(10))[0].replace('# ', '')[:30]}.md"
        await write_memory(new_path if new_path != slot_path else slot_path, node)
        if new_path != slot_path:
            slot_path.unlink(missing_ok=True)

        self._log_op(slot_id, SlotOperation(
            timestamp=datetime.now(timezone.utc).isoformat(),
            op_type="update",
            content_snippet=new_content[:200],
            description="slot content updated",
        ))
        logger.info("slot_updated", slot_id=slot_id)
        return True

    async def conclude_slot(self, slot_id: int) -> ReasoningTrace | None:
        """Analyze the slot's operation log and save a reasoning trace if detected."""
        slot = await self.get_slot(slot_id)
        if slot is None:
            return None

        ops = self._read_ops(slot_id)
        self._log_op(slot_id, SlotOperation(
            timestamp=datetime.now(timezone.utc).isoformat(),
            op_type="conclude",
            description="slot concluded",
        ))

        trace = await self._detect_reasoning_chain(slot, ops)
        if trace:
            await self._save_trace(trace, ops)
            logger.info("reasoning_trace_saved", slot_id=slot_id, trace_id=trace.trace_id)

        return trace

    async def list_slots(self) -> list[dict]:
        slots = await self._get_active_slots()
        result = []
        for s in slots:
            ops = self._read_ops(s.slot_id)
            result.append({
                "slot_id": s.slot_id,
                "slot_name": s.slot_name,
                "memory_id": s.memory_id,
                "pinned": s.pinned,
                "importance": s.importance,
                "operation_count": len(ops),
            })
        return result

    # ── private helpers ────────────────────────────────────

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
        await self._maybe_save_trace(slot)

        self._log_op(slot.slot_id, SlotOperation(
            timestamp=datetime.now(timezone.utc).isoformat(),
            op_type="evict",
            description="slot evicted from working memory",
        ))

        slot_path = self._slot_path(slot)
        if slot_path.exists():
            cooldown = self.config.memory.eviction_cooldown_minutes
            await self.memory.create(
                content=f"# Evicted Slot: {slot.slot_name}\n\nMemory: {slot.memory_id}",
                type_=MemoryType.RAW_INPUT,
                tags=["evicted-slot"],
                importance=slot.importance,
                source="working-memory-eviction",
            )
            slot_path.unlink(missing_ok=True)
            logger.info("slot_evicted", slot_id=slot.slot_id, memory_id=slot.memory_id)

    async def _maybe_save_trace(self, slot: WorkingMemorySlot) -> None:
        ops = self._read_ops(slot.slot_id)
        if len(ops) < 2:  # need at least promote + one update
            return
        trace = await self._detect_reasoning_chain(slot, ops)
        if trace:
            await self._save_trace(trace, ops)

    async def _detect_reasoning_chain(
        self, slot: WorkingMemorySlot, ops: list[SlotOperation],
    ) -> ReasoningTrace | None:
        if self.llm is None:
            return None

        ops_text = "\n".join(
            f"- [{op.timestamp}] {op.op_type}: {op.description}\n  {op.content_snippet[:200]}"
            for op in ops
        )

        prompt = f"""以下是工作记忆槽位 "{slot.slot_name}" 的操作序列。判断这些操作是否构成有意义的推理过程（分析问题→拆解→得出结论）。

操作序列:
{ops_text}

如果是推理链，提取步骤和结论，返回 JSON:
{{"is_reasoning": true, "title": "推理链标题", "steps": ["步骤1", "步骤2"], "conclusion": "最终结论"}}

如果不是推理链（如只是简单记录或查询），返回:
{{"is_reasoning": false}}"""

        try:
            from memory_os.llm.models import UnifiedChatRequest
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system="你是推理链检测助手。仅返回 JSON。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=512,
                    response_format="json_object",
                ),
                agent_name="working_memory",
            )
            data = json.loads(resp.content)
            if data.get("is_reasoning"):
                return ReasoningTrace(
                    slot_id=slot.slot_id,
                    title=data.get("title", f"推理链 - {slot.slot_name}"),
                    steps=data.get("steps", []),
                    conclusion=data.get("conclusion", ""),
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as e:
            logger.warning("reasoning_detect_failed", error=str(e))

        return None

    async def _save_trace(self, trace: ReasoningTrace, ops: list[SlotOperation]) -> None:
        trace_dir = self.vault_path / "_memory" / "procedural"
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace.trace_id = generate_memory_id(MemoryType.PROCEDURAL)
        trace_path = trace_dir / f"trace-{trace.trace_id}.md"

        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(trace.steps))
        ops_text = "\n".join(
            f"- [{op.timestamp}] {op.op_type}: {op.content_snippet[:100]}"
            for op in ops
        )

        content = f"""# 推理链: {trace.title}

## 步骤
{steps_text}

## 结论
{trace.conclusion}

## 操作记录
{ops_text}
"""
        node = MemoryNode(
            id=trace.trace_id,
            type=MemoryType.PROCEDURAL,
            status=MemoryStatus.ACTIVE,
            title=f"推理链: {trace.title}",
            tags=["reasoning-trace", f"slot-{trace.slot_id}"],
            importance=75,
            content=content,
        )
        await write_memory(trace_path, node)

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

    def _ops_path(self, slot_id: int) -> Path:
        # find the actual slot file to get the name
        return self.working_dir / f"slot-ops-{slot_id}.jsonl"

    def _log_op(self, slot_id: int, op: SlotOperation) -> None:
        self.working_dir.mkdir(parents=True, exist_ok=True)
        with open(self._ops_path(slot_id), "a", encoding="utf-8") as f:
            f.write(op.model_dump_json() + "\n")

    def _read_ops(self, slot_id: int) -> list[SlotOperation]:
        ops_path = self._ops_path(slot_id)
        if not ops_path.exists():
            return []
        ops = []
        with open(ops_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ops.append(SlotOperation.model_validate_json(line))
                except Exception:
                    continue
        return ops

    def _next_slot_id(self, existing: list[WorkingMemorySlot]) -> int:
        taken = {s.slot_id for s in existing}
        for i in range(1, self.max_slots + 1):
            if i not in taken:
                return i
        raise RuntimeError("槽位已满")
