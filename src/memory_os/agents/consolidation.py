from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel

from memory_os.config.loader import embedding_config_hash
from memory_os.config.models import SystemConfig
from memory_os.llm.models import UnifiedChatRequest
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory, update_fields
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType, slugify

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

        has_output = bool(raw_node.raw_output)

        if has_output:
            summary = await self._summarize_pair(raw_node.content, raw_node.raw_output)
        else:
            summary = await self._summarize(raw_node.content)
        stats.summaries_generated += 1

        title = self._extract_title(summary)

        sem_node = await self.memory.create(
            content=summary,
            type_=MemoryType.SEMANTIC,
            tags=raw_node.tags,
            importance=raw_node.importance,
            context=raw_node.context,
            title=title,
        )
        sem_node.raw_input_ref = f"[[{raw_node.id}]]"

        links, conflicts = await self._discover_links_and_conflicts(summary, sem_node.id)
        sem_node.links_to = links
        stats.links_discovered += len(links)

        if conflicts:
            await self._apply_conflicts(sem_node, conflicts)

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
                "file_path": str(self._semantic_path(sem_node).relative_to(self.vault_path)),
                "last_retrieved": datetime.now(timezone.utc).isoformat(),
                "next_review": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            }])
            stats.embeddings_generated += 1
        except Exception as e:
            logger.warning("embedding_failed", error=str(e))

        if has_output:
            pro_node = await self._maybe_create_procedural(raw_node.content, raw_node.raw_output, sem_node)
            if pro_node:
                stats.embeddings_generated += 1

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

    async def _summarize_pair(self, input_text: str, output_text: str) -> str:
        resp = await self.llm.chat(
            UnifiedChatRequest(
                system="你是知识提炼助手。基于以下问答对，提取核心知识点和结论。忽略提问的细节，聚焦可复用的知识。输出纯文本，不要 JSON。",
                messages=[{"role": "user", "content": f"问题：{input_text[:2000]}\n\n回答：{output_text[:3000]}\n\n请提炼核心结论（不超过 500 字）"}],
                temperature=0.2,
                max_tokens=1024,
            ),
            agent_name="consolidation",
        )
        return resp.content

    async def _maybe_create_procedural(
        self, input_text: str, output_text: str, sem_node: MemoryNode,
    ) -> MemoryNode | None:
        try:
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system="判断以下内容是否包含可重复使用的步骤、流程或操作方法。仅返回 JSON。",
                    messages=[{"role": "user", "content": f"问题：{input_text[:2000]}\n回答：{output_text[:3000]}\n\n是否包含步骤流程？{'{'} \"steps\": true/false, \"title\": \"简短标题\", \"content\": \"提炼的操作步骤或流程\" {'}'}"}],
                    temperature=0.1,
                    max_tokens=1024,
                    response_format="json_object",
                ),
                agent_name="consolidation",
            )
            import json
            data = json.loads(resp.content)
            if not data.get("steps"):
                return None

            pro_title = data.get("title", sem_node.title or "")
            pro_content = data.get("content", "")

            pro_node = await self.memory.create(
                content=pro_content,
                type_=MemoryType.PROCEDURAL,
                tags=sem_node.tags + ["procedure"],
                importance=sem_node.importance,
                context=sem_node.context,
                title=pro_title,
            )
            pro_node.raw_input_ref = sem_node.raw_input_ref
            pro_node.links_to = [f"[[{self._semantic_path(sem_node).relative_to(self.vault_path)}]]"]

            try:
                embedding = (await self.llm.embed([pro_content]))[0]
                pro_node.embedding_id = f"emb-pro-{pro_node.id}"
                pro_node.vector_status = MemoryStatus.ACTIVE
                pro_node.vector_model = self.config.llm.embedding.model
                pro_node.vector_dim = self.config.llm.embedding.dimension

                await self._vector_store().upsert("procedural", [{
                    "memory_id": pro_node.id,
                    "vector": embedding,
                    "strength": float(pro_node.strength),
                    "importance": float(pro_node.importance),
                    "status": "active",
                    "tags": pro_node.tags,
                    "file_path": str(self._procedural_path(pro_node).relative_to(self.vault_path)),
                    "last_retrieved": datetime.now(timezone.utc).isoformat(),
                    "next_review": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                }])
            except Exception as e:
                logger.warning("procedural_embedding_failed", error=str(e))

            pro_node.strength_initial = self._calc_initial_strength_procedural()
            pro_node.next_review = datetime.now(timezone.utc) + timedelta(days=1)
            await self.memory.update(pro_node.id, **pro_node.model_dump(exclude={"id", "type"}))

            logger.info("procedural_created", id=pro_node.id, title=pro_title)
            return pro_node
        except Exception as e:
            logger.warning("procedural_creation_failed", error=str(e))
            return None

    async def _discover_links(self, summary: str) -> list[str]:
        try:
            embedding = (await self.llm.embed([summary]))[0]
            results = await self._vector_store().search("semantic", embedding, top_k=5)
            links = []
            for r in results:
                if r.get("strength", 0) > 30:
                    links.append(f"[[{r.get('file_path', '')}]]")
            return links
        except Exception:
            return []

    async def _discover_links_and_conflicts(
        self, summary: str, new_node_id: str | None,
    ) -> tuple[list[str], list[dict]]:
        try:
            embedding = (await self.llm.embed([summary]))[0]
            results = await self._vector_store().search("semantic", embedding, top_k=5)
        except Exception:
            return [], []

        links = []
        conflicts = []
        high_conf_candidates = []

        for r in results:
            if r.get("strength", 0) > 30:
                links.append(f"[[{r.get('file_path', '')}]]")
            if r.get("importance", 0) > 70 and new_node_id:
                high_conf_candidates.append(r)

        if high_conf_candidates and new_node_id:
            for cand in high_conf_candidates[:3]:
                conflict = await self._check_conflict(summary, cand)
                if conflict:
                    conflicts.append(conflict)

        return links, conflicts

    async def _check_conflict(self, new_summary: str, existing: dict) -> dict | None:
        existing_id = existing.get("memory_id", "")
        try:
            existing_node = await self.memory.get(existing_id)
        except Exception:
            return None

        existing_content = existing_node.content[:800]
        prompt = f"""判断以下两条知识是否存在事实矛盾（如互相否定、结论相反、前提冲突）。

新知识:
{new_summary[:500]}

已有知识 (高置信度):
{existing_content}

仅返回 JSON:
{{"conflict": true/false, "note": "矛盾点简述（若冲突）"}}"""

        try:
            from memory_os.llm.models import UnifiedChatRequest
            import json
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system="你是知识一致性校验助手。仅返回 JSON。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=256,
                    response_format="json_object",
                ),
                agent_name="consolidation",
            )
            data = json.loads(resp.content)
            if data.get("conflict"):
                return {
                    "existing_id": existing_id,
                    "new_summary": new_summary[:100],
                    "existing_title": existing_node.title or existing_id,
                    "note": data.get("note", "知识矛盾"),
                }
        except Exception:
            pass

        return None

    @staticmethod
    def _extract_title(summary: str) -> str:
        for line in summary.strip().split("\n"):
            line = line.strip().lstrip("#").strip()
            if line:
                return line
        return ""

    def _semantic_path(self, node: MemoryNode) -> Path:
        slug = slugify(node.title) if node.title else ""
        filename = f"{node.id}-{slug}.md" if slug else f"{node.id}.md"
        return self.vault_path / "_memory" / "semantic" / filename

    def _procedural_path(self, node: MemoryNode) -> Path:
        slug = slugify(node.title) if node.title else ""
        filename = f"{node.id}-{slug}.md" if slug else f"{node.id}.md"
        return self.vault_path / "_memory" / "procedural" / filename

    async def _apply_conflicts(self, new_node: MemoryNode, conflicts: list[dict]) -> None:
        for c in conflicts:
            existing_id = c["existing_id"]
            try:
                existing_node = await self.memory.get(existing_id)
            except Exception:
                continue

            new_node.conflict = True
            new_node.conflicting_with = list(set(new_node.conflicting_with + [existing_id]))
            new_node.conflict_note = c.get("note", "知识矛盾")

            existing_node.conflict = True
            existing_node.conflicting_with = list(set(existing_node.conflicting_with + [new_node.id]))
            existing_node.conflict_note = c.get("note", "知识矛盾")

            await self.memory.update(new_node.id, conflict=True, conflicting_with=new_node.conflicting_with, conflict_note=new_node.conflict_note)
            await self.memory.update(existing_id, conflict=True, conflicting_with=existing_node.conflicting_with, conflict_note=existing_node.conflict_note)

            self._write_conflict_report(new_node.id, existing_id, c.get("note", ""))

    def _write_conflict_report(self, new_id: str, existing_id: str, note: str) -> None:
        meta_dir = self.vault_path / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        conflict_path = meta_dir / "cognitive-conflicts.md"

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        new_entry = f"- [{now}] [[{new_id}]] ↔ [[{existing_id}]]: {note}\n  ⚠️ 待解决\n"

        if conflict_path.exists():
            content = conflict_path.read_text(encoding="utf-8")
            if "## 待解决" in content:
                content = content.replace("## 待解决\n", f"## 待解决\n{new_entry}")
            else:
                content = f"# 认知冲突日志\n\n## 待解决\n{new_entry}\n" + content
            conflict_path.write_text(content, encoding="utf-8")
        else:
            conflict_path.write_text(f"# 认知冲突日志\n\n## 待解决\n{new_entry}\n", encoding="utf-8")
        logger.info("conflict_recorded", new_id=new_id, existing_id=existing_id)

    def _calc_initial_strength(self, raw: MemoryNode) -> float:
        return raw.importance * 0.3 + raw.source_confidence * 20 + 25

    @staticmethod
    def _calc_initial_strength_procedural() -> float:
        return 40.0

    async def _append_episodic_log(self, raw_node: MemoryNode, sem_node: MemoryNode):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        epi_path = self.vault_path / "_memory" / "episodic" / f"{today}.md"
        sem_filename = self._semantic_path(sem_node).stem
        tag = raw_node.tags[0] if raw_node.tags else "memory"
        has_output = bool(raw_node.raw_output)

        entry_parts = [f"- [{datetime.now(timezone.utc).strftime('%H:%M')}] **{tag}** — [[{sem_filename}]] (from {raw_node.source or 'unknown'})"]
        if has_output:
            q_preview = raw_node.content[:60].replace("\n", " ")
            a_preview = raw_node.raw_output[:60].replace("\n", " ") if raw_node.raw_output else ""
            entry_parts.append(f"  - Q: {q_preview}...")
            entry_parts.append(f"  - A: {a_preview}...")
        entry_parts.append("")

        try:
            existing = epi_path.read_text(encoding="utf-8") if epi_path.exists() else f"# {today}\n\n"
            epi_path.write_text(existing + "\n".join(entry_parts), encoding="utf-8")
        except Exception:
            pass

    def _vector_store(self):
        from memory_os.vault.vector_client import VectorStore
        return VectorStore(self.vault_path)
