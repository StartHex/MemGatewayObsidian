from __future__ import annotations

import hashlib
import json

import structlog

from memory_os.llm.models import UnifiedChatRequest
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.models import MemoryNode, MemoryType

logger = structlog.get_logger(__name__)


class ClassificationResult:
    def __init__(self, tags: list[str], importance: float, context: str, modality: str):
        self.tags = tags
        self.importance = importance
        self.context = context
        self.modality = modality


class SensoryGateway:
    def __init__(self, memory: MemoryService, llm: LLMService, vault_path):
        self.memory = memory
        self.llm = llm
        self.vault_path = vault_path

    async def ingest(self, content: str, source: str) -> MemoryNode | None:
        if not content.strip():
            logger.warning("empty_content_skipped")
            return None

        if await self._is_duplicate(content):
            logger.info("duplicate_content_skipped")
            return None

        metadata = await self._classify(content)

        node = await self.memory.create(
            content=content,
            type_=MemoryType.RAW_INPUT,
            tags=metadata.tags,
            importance=metadata.importance,
            context=metadata.context,
            source=source,
        )
        logger.info("ingested", id=node.id, tags=metadata.tags, modality=metadata.modality)
        return node

    async def _classify(self, content: str) -> ClassificationResult:
        system = "你是内容分类助手。分析输入内容，仅返回 JSON，不要其他文字。"
        prompt = f"""分析以下内容并返回 JSON：
{{
  "tags": ["标签1", "标签2", "标签3"],
  "importance": <0-100 整数>,
  "context": "<一句话上下文>",
  "modality": "chat|code|doc|url|idea"
}}

内容:
{content[:3000]}"""

        try:
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=512,
                    response_format="json_object",
                ),
                agent_name="sensory_gateway",
            )
            data = json.loads(resp.content)
            return ClassificationResult(
                tags=data.get("tags", ["uncategorized"]),
                importance=float(data.get("importance", 50)),
                context=data.get("context", ""),
                modality=data.get("modality", "chat"),
            )
        except Exception:
            logger.warning("classification_failed_using_defaults")
            return ClassificationResult(
                tags=["uncategorized"],
                importance=50,
                context="",
                modality="chat",
            )

    async def _is_duplicate(self, content: str) -> bool:
        inbox_dir = self.vault_path / "_inbox"
        recent_files = await list_directory(inbox_dir, "*.md")
        content_hash = hashlib.md5(content[:200].encode()).hexdigest()
        for f in recent_files[:50]:
            try:
                text = f.read_text(encoding="utf-8")
                if hashlib.md5(text[:200].encode()).hexdigest() == content_hash:
                    return True
            except Exception:
                continue
        return False
