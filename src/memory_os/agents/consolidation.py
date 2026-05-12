from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from pydantic import BaseModel

from memory_os.config.loader import embedding_config_hash
from memory_os.config.models import SystemConfig
from memory_os.llm.models import UnifiedChatRequest
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory, update_fields
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType

logger = structlog.get_logger(__name__)


class ConsolidationStats(BaseModel):
    summaries_generated: int = 0
    links_discovered: int = 0
    embeddings_generated: int = 0


class ConsolidationReport(BaseModel):
    processed: int = 0
    failed: int = 0
    summaries_generated: int = 0
    links_discovered: int = 0
    embeddings_generated: int = 0


class ConsolidationAgent:
    def __init__(self, memory: MemoryService, llm: LLMService, vault_path, config: SystemConfig):
        self.memory = memory
        self.llm = llm
        self.vault_path = vault_path
        self.config = config

    async def run(self) -> ConsolidationReport:
        raw_files = await list_directory(self.vault_path / "_inbox", "*.md")
        pending = []
        for f in raw_files:
            try:
                node = await parse_memory(f)
                if node.status == MemoryStatus.RAW:
                    pending.append(node)
            except Exception:
                continue

        report = ConsolidationReport()
        for item in pending:
            try:
                stats = await self._process_one(item)
                report.processed += 1
                report.summaries_generated += stats.summaries_generated
                report.links_discovered += stats.links_discovered
                report.embeddings_generated += stats.embeddings_generated
            except Exception as e:
                logger.error("consolidation_failed", memory_id=item.id, error=str(e))
                report.failed += 1
        return report

    async def _process_one(self, raw_node: MemoryNode) -> ConsolidationStats:
        stats = ConsolidationStats()
        await self.memory.update_status(raw_node.id, MemoryStatus.PROCESSING)

        summary = await self._summarize(raw_node.content)
        stats.summaries_generated += 1

        sem_node = await self.memory.create(
            content=summary,
            type_=MemoryType.SEMANTIC,
            tags=raw_node.tags,
            importance=raw_node.importance,
            context=raw_node.context,
        )
        sem_node.raw_input_ref = f"[[{raw_node.id}]]"

        links = await self._discover_links(summary)
        sem_node.links_to = links
        stats.links_discovered += len(links)

        try:
            embedding = (await self.llm.embed([summary]))[0]
            emb_id = f"emb-sem-{sem_node.id}"
            sem_node.embedding_id = emb_id
            sem_node.vector_status = MemoryStatus.ACTIVE
            sem_node.vector_model = self.config.llm.embedding.model
            sem_node.vector_dim = self.config.llm.embedding.dimension

            await self._vector_store().upsert("semantic", [{
                "memory_id": sem_node.id,
                "vector": embedding,
                "strength": float(sem_node.strength),
                "importance": float(sem_node.importance),
                "status": "active",
                "tags": sem_node.tags,
                "file_path": f"_memory/semantic/{sem_node.id}.md",
                "last_retrieved": datetime.now(timezone.utc).isoformat(),
                "next_review": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            }])
            stats.embeddings_generated += 1
        except Exception as e:
            logger.warning("embedding_failed", error=str(e))

        sem_node.strength_initial = self._calc_initial_strength(raw_node)
        sem_node.next_review = datetime.now(timezone.utc) + timedelta(days=1)
        await self.memory.update(sem_node.id, **sem_node.model_dump(exclude={"id", "type"}))

        await self.memory.update_status(raw_node.id, MemoryStatus.ACTIVE)
        await self._append_episodic_log(raw_node, sem_node)
        return stats

    async def _summarize(self, raw_content: str) -> str:
        resp = await self.llm.chat(
            UnifiedChatRequest(
                system="你是知识摘要助手。提取核心要点，保留关键细节。输出纯文本，不要 JSON。",
                messages=[{"role": "user", "content": f"摘要以下内容（不超过 500 字）：\n{raw_content[:5000]}"}],
                temperature=0.2,
                max_tokens=1024,
            ),
            agent_name="consolidation",
        )
        return resp.content

    async def _discover_links(self, summary: str) -> list[str]:
        try:
            embedding = (await self.llm.embed([summary]))[0]
            results = self._vector_store().search("semantic", embedding, top_k=5)
            links = []
            for r in results:
                if r.get("strength", 0) > 30:
                    links.append(f"[[{r.get('file_path', '')}]]")
            return links
        except Exception:
            return []

    def _calc_initial_strength(self, raw: MemoryNode) -> float:
        return raw.importance * 0.3 + raw.source_confidence * 20 + 25

    async def _append_episodic_log(self, raw_node: MemoryNode, sem_node: MemoryNode):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        epi_path = self.vault_path / "_memory" / "episodic" / f"{today}.md"
        entry = f"- [{datetime.now(timezone.utc).strftime('%H:%M')}] **{raw_node.tags[0] if raw_node.tags else 'memory'}** — [[{sem_node.id}]] (from {raw_node.source or 'unknown'})\n"
        try:
            existing = epi_path.read_text(encoding="utf-8") if epi_path.exists() else f"# {today}\n\n"
            epi_path.write_text(existing + entry, encoding="utf-8")
        except Exception:
            pass

    def _vector_store(self):
        from memory_os.vault.vector_client import VectorStore
        return VectorStore(self.vault_path)
