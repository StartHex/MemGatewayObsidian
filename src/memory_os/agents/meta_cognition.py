from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel

from memory_os.config.models import SystemConfig
from memory_os.llm.models import UnifiedChatRequest
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory
from memory_os.vault.index import get_all_active_ids, get_orphan_nodes
from memory_os.vault.vector_client import VectorStore

logger = structlog.get_logger(__name__)


class HealthReport(BaseModel):
    generated_at: datetime
    inbox_pending: int = 0
    active_count: int = 0
    fading_count: int = 0
    archived_count: int = 0
    strength_distribution: dict[str, int] = {}
    orphan_count: int = 0
    vector_inconsistencies: int = 0
    conflict_count: int = 0
    knowledge_gaps: list[str] = []
    recommendations: list[str] = []


class MetaCognitionAgent:
    def __init__(self, memory: MemoryService, llm: LLMService, config: SystemConfig, vault_path):
        self.memory = memory
        self.llm = llm
        self.config = config
        self.vault_path = vault_path
        self.vector = VectorStore(vault_path)

    async def run(self) -> HealthReport:
        (
            inbox_pending,
            strength_dist,
            orphans,
            vec_inconsistencies,
            gaps,
            conflicts,
        ) = await asyncio.gather(
            self._check_inbox(),
            self._calc_strength_distribution(),
            self._find_orphans(),
            self._verify_vector_consistency(),
            self._detect_gaps(),
            self._count_conflicts(),
        )

        report = HealthReport(
            generated_at=datetime.now(timezone.utc),
            inbox_pending=inbox_pending,
            active_count=sum(strength_dist.values()),
            strength_distribution=strength_dist,
            orphan_count=orphans,
            vector_inconsistencies=vec_inconsistencies,
            conflict_count=conflicts,
            knowledge_gaps=gaps,
        )
        report.recommendations = self._generate_recommendations(report)
        return report

    async def _check_inbox(self) -> int:
        files = await list_directory(self.vault_path / "_inbox", "*.md")
        return len(files)

    async def _calc_strength_distribution(self) -> dict[str, int]:
        dist = {"strong": 0, "healthy": 0, "fading": 0, "critical": 0}
        active_ids = await get_all_active_ids(self.vault_path / "_meta" / "index.md")
        for mid in list(active_ids)[:500]:
            try:
                node = await self.memory.get(mid)
                s = node.strength
                if s >= 70:
                    dist["strong"] += 1
                elif s >= 40:
                    dist["healthy"] += 1
                elif s >= 15:
                    dist["fading"] += 1
                else:
                    dist["critical"] += 1
            except Exception:
                continue
        return dist

    async def _find_orphans(self) -> int:
        orphans = await get_orphan_nodes(
            self.vault_path / "_meta" / "index.md", self.vault_path
        )
        return len(orphans)

    async def _verify_vector_consistency(self) -> int:
        file_ids = await get_all_active_ids(self.vault_path / "_meta" / "index.md")
        db_ids: set[str] = set()
        for table in ["semantic", "episodic", "procedural"]:
            try:
                db_ids.update(await self.vector.list_ids(table))
            except Exception:
                continue
        return len(file_ids.symmetric_difference(db_ids))

    async def _detect_gaps(self) -> list[str]:
        gaps = []
        strength_dist = await self._calc_strength_distribution()
        total = sum(strength_dist.values()) or 1
        if strength_dist.get("fading", 0) / total > 0.3:
            gaps.append("超过 30% 的记忆处于 fading 状态，知识可能正在流失")
        if strength_dist.get("critical", 0) / total > 0.1:
            gaps.append("超过 10% 的记忆处于 critical 状态，即将被归档")
        return gaps

    async def _count_conflicts(self) -> int:
        count = 0
        dirs = [
            self.vault_path / "_memory" / "semantic",
            self.vault_path / "_memory" / "episodic",
            self.vault_path / "_memory" / "procedural",
        ]
        for d in dirs:
            files = await list_directory(d, "*.md")
            for f in files[:500]:
                try:
                    node = await parse_memory(f)
                    if node.conflict:
                        count += 1
                except Exception:
                    continue
        return count

    def _generate_recommendations(self, report: HealthReport) -> list[str]:
        recs = []
        if report.inbox_pending > 20:
            recs.append(f"inbox 堆积 {report.inbox_pending} 条，建议增加 Consolidation Agent 运行频率")
        if report.strength_distribution.get("fading", 0) > report.strength_distribution.get("strong", 1) * 0.5:
            recs.append("fading 比例偏高，建议降低全局 decay_rate 或增加复习频率")
        if report.orphan_count > report.active_count * 0.2:
            recs.append(f"孤岛笔记 {report.orphan_count} 条，建议加强 Consolidation 阶段的链接化")
        if report.vector_inconsistencies > 0:
            recs.append(f"向量与文件有 {report.vector_inconsistencies} 处不一致，建议运行 rebuild-vector-index")
        if report.conflict_count > 0:
            recs.append(f"检测到 {report.conflict_count} 个认知冲突，建议审查 _meta/cognitive-conflicts.md 并解决矛盾")
        return recs

    async def generate_narrative_report(self) -> str:
        report = await self.run()
        prompt = f"""基于以下系统健康数据生成一份简短报告（300 字以内）：

- 待处理输入: {report.inbox_pending}
- 活跃记忆: {report.active_count}
- 强度分布: {report.strength_distribution}
- 孤岛笔记: {report.orphant_count}
- 向量不一致: {report.vector_inconsistencies}
- 知识缺口: {report.knowledge_gaps}
- 推荐: {report.recommendations}"""

        try:
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system="你是系统健康报告生成器。简洁、数据驱动。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                ),
                agent_name="meta_cognition",
            )
            return resp.content
        except Exception:
            return f"健康报告 ({report.generated_at.isoformat()}): 活跃 {report.active_count} 条记忆, {report.inbox_pending} 条待处理。"
