from __future__ import annotations

import math
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel

from memory_os.config.models import SystemConfig
from memory_os.memory.service import MemoryService
from memory_os.vault.frontmatter import parse_memory, update_fields
from memory_os.vault.index import get_all_active_ids
from memory_os.vault.models import MemoryNode, MemoryStatus
from memory_os.vault.vector_client import VectorStore

logger = structlog.get_logger(__name__)


class ForgettingReport(BaseModel):
    scanned: int = 0
    retained: int = 0
    fading_count: int = 0
    archived_count: int = 0
    cascade_count: int = 0


class ForgettingAgent:
    def __init__(self, memory: MemoryService, config: SystemConfig, vault_path):
        self.memory = memory
        self.config = config
        self.vault_path = vault_path
        self.vector = VectorStore(vault_path)

    async def run(self) -> ForgettingReport:
        report = ForgettingReport()
        active_ids = await get_all_active_ids(self.vault_path / "_meta" / "index.md")

        for mid in list(active_ids)[:1000]:
            try:
                node = await self.memory.get(mid)
                report.scanned += 1

                new_strength = self._calc_strength(node)
                action = self._decide(new_strength)

                if action == "retain":
                    await self.memory.update(mid, strength=new_strength)
                    report.retained += 1
                elif action == "fading":
                    await self.memory.update(mid, strength=new_strength, status=MemoryStatus.FADING)
                    report.fading_count += 1
                elif action == "archive":
                    cascaded = await self._execute_archive(node)
                    report.archived_count += 1
                    report.cascade_count += cascaded

            except Exception as e:
                logger.error("forgetting_scan_failed", memory_id=mid, error=str(e))

        return report

    def _calc_strength(self, node: MemoryNode) -> float:
        ref_time = node.last_review or node.last_retrieved
        if ref_time is None:
            return node.strength

        days = (datetime.now(timezone.utc) - ref_time).days
        initial = node.strength_initial if node.strength_initial is not None else node.strength
        return initial * math.exp(-node.decay_rate * max(days, 0))

    def _decide(self, strength: float) -> str:
        if strength >= self.config.memory.fading_threshold:
            return "retain"
        if strength >= self.config.memory.archive_threshold:
            return "fading"
        return "archive"

    async def _execute_archive(self, node: MemoryNode) -> int:
        """归档一个节点，返回级联归档数量。"""
        cascaded = 0
        await self.memory.archive(node.id)

        try:
            await self.vector.delete(node.type.value, [node.id])
        except Exception as e:
            logger.warning("vector_delete_failed", memory_id=node.id, error=str(e))

        cascaded += await self._cascade_cleanup(node, depth=0)
        return cascaded

    async def _cascade_cleanup(self, archived_node: MemoryNode, depth: int) -> int:
        """清理关联节点，返回级联归档数量。"""
        if depth >= self.config.memory.cascade_max_depth:
            return 0

        cascaded = 0
        affected_ids: set[str] = set()
        for wikilink in archived_node.links_to + archived_node.links_from:
            target = wikilink.replace("[[", "").replace("]]", "").split("/")[-1].replace(".md", "")
            if target:
                affected_ids.add(target)

        for mid in affected_ids:
            try:
                node = await self.memory.get(mid)
            except Exception:
                continue

            link_count = len(node.links_to) + len(node.links_from)
            if link_count > 0:
                node.retrieval_ease = max(0.1, node.retrieval_ease - (1.0 / link_count))

            node.strength = self._calc_strength(node)
            node.strength *= (0.8 + 0.2 * node.retrieval_ease)

            node.links_to = [l for l in node.links_to if archived_node.id not in l]
            node.links_from = [l for l in node.links_from if archived_node.id not in l]

            await self.memory.update(node.id,
                retrieval_ease=node.retrieval_ease,
                strength=node.strength,
                links_to=node.links_to,
                links_from=node.links_from,
            )

            if node.strength < self.config.memory.archive_threshold:
                cascaded += 1
                cascaded += await self._execute_archive(node)
                cascaded += await self._cascade_cleanup(node, depth + 1)
        return cascaded
