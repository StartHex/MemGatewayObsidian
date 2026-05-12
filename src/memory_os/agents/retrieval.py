from __future__ import annotations

from enum import Enum

import structlog
from pydantic import BaseModel

from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory
from memory_os.vault.models import MemoryNode, MemoryStatus
from memory_os.vault.vector_client import VectorStore

logger = structlog.get_logger(__name__)


class SearchStrategy(str, Enum):
    AUTO = "auto"
    EXACT = "exact"
    KEYWORD = "keyword"
    VECTOR = "vector"
    GRAPH = "graph"
    TIMELINE = "timeline"
    CONTEXT = "context"


class SearchResult(BaseModel):
    memory_id: str
    title: str
    snippet: str
    score: float
    strategy: SearchStrategy
    file_path: str


class RetrievalAgent:
    def __init__(self, memory: MemoryService, llm: LLMService, vault_path):
        self.memory = memory
        self.llm = llm
        self.vault_path = vault_path
        self.vector = VectorStore(vault_path)

    async def search(
        self,
        query: str,
        *,
        strategy: SearchStrategy = SearchStrategy.AUTO,
        top_k: int = 10,
        status_filter: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> list[SearchResult]:
        if strategy == SearchStrategy.AUTO:
            strategy = self._auto_select(query)

        where = f"status = '{status_filter.value}'" if status_filter else None

        if strategy == SearchStrategy.EXACT:
            return await self._search_exact(query)
        if strategy == SearchStrategy.KEYWORD:
            return await self._search_keyword(query, top_k, status_filter)
        if strategy == SearchStrategy.VECTOR:
            return await self._search_vector(query, top_k, where)
        if strategy == SearchStrategy.GRAPH:
            return await self._search_graph(query, 3)
        if strategy == SearchStrategy.TIMELINE:
            return await self._search_timeline(query, top_k)
        if strategy == SearchStrategy.CONTEXT:
            return await self._search_context(query, top_k)

        return await self._search_vector(query, top_k, where)

    def _auto_select(self, query: str) -> SearchStrategy:
        if query.startswith("mem-") and len(query) > 15:
            return SearchStrategy.EXACT
        if len(query) < 3:
            return SearchStrategy.KEYWORD
        return SearchStrategy.VECTOR

    async def _search_exact(self, memory_id: str) -> list[SearchResult]:
        try:
            node = await self.memory.get(memory_id)
            title = node.content.split("\n")[0].replace("# ", "")[:80]
            return [SearchResult(
                memory_id=node.id, title=title,
                snippet=node.content[:200], score=1.0,
                strategy=SearchStrategy.EXACT,
                file_path="",
            )]
        except Exception:
            return []

    async def _search_keyword(
        self, query: str, top_k: int, status_filter: MemoryStatus,
    ) -> list[SearchResult]:
        async def _search_in_dir(directory, max_files=100):
            results = []
            files = await list_directory(directory, "*.md")
            for f in files[:max_files]:
                try:
                    node = await parse_memory(f)
                    if status_filter and node.status != status_filter:
                        continue
                    if query.lower() in node.content.lower() or any(
                        query.lower() in t.lower() for t in node.tags
                    ):
                        title = node.content.split("\n")[0].replace("# ", "")[:80]
                        snippet = self._extract_snippet(node.content, query)
                        score = 0.6 + 0.4 * (len(node.tags) / 10)
                        results.append(SearchResult(
                            memory_id=node.id, title=title, snippet=snippet,
                            score=min(score, 1.0), strategy=SearchStrategy.KEYWORD,
                            file_path=str(f.relative_to(self.vault_path)),
                        ))
                except Exception:
                    continue
            return results

        dirs = [
            self.vault_path / "_memory" / "semantic",
            self.vault_path / "_memory" / "episodic",
            self.vault_path / "_memory" / "procedural",
        ]
        all_results = []
        for d in dirs:
            all_results.extend(await _search_in_dir(d))
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    async def _search_vector(self, query: str, top_k: int, where: str | None) -> list[SearchResult]:
        try:
            q_vec = (await self.llm.embed([query]))[0]
        except Exception:
            return await self._search_keyword(query, top_k, MemoryStatus.ACTIVE)

        queries = [
            ("semantic", q_vec, top_k, where),
            ("episodic", q_vec, max(top_k // 2, 3), where),
            ("procedural", q_vec, max(top_k // 2, 3), where),
        ]
        all_results = []
        for table, vec, k, w in queries:
            try:
                rows = await self.vector.search(table, vec, top_k=k, where=w)
                for r in rows:
                    score = 0.5 * (1 - r.get("_distance", 0)) + 0.3 * (r.get("strength", 50) / 100) + 0.2 * (r.get("importance", 50) / 100)
                    all_results.append(SearchResult(
                        memory_id=r["memory_id"],
                        title=r.get("file_path", ""),
                        snippet="",
                        score=min(score, 1.0),
                        strategy=SearchStrategy.VECTOR,
                        file_path=r.get("file_path", ""),
                    ))
            except Exception:
                continue

        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    async def _search_graph(self, start_id: str, hops: int) -> list[SearchResult]:
        visited: set[str] = set()
        frontier: set[str] = {start_id}
        for _ in range(hops):
            next_frontier: set[str] = set()
            for mid in frontier:
                if mid in visited:
                    continue
                visited.add(mid)
                try:
                    node = await self.memory.get(mid)
                    for link in node.links_to:
                        target = link.replace("[[", "").replace("]]", "").split("/")[-1].replace(".md", "")
                        if target not in visited:
                            next_frontier.add(target)
                except Exception:
                    continue
            frontier = next_frontier

        results = []
        for mid in visited:
            try:
                node = await self.memory.get(mid)
                title = node.content.split("\n")[0].replace("# ", "")[:80]
                results.append(SearchResult(
                    memory_id=mid, title=title, snippet=node.content[:200],
                    score=0.7, strategy=SearchStrategy.GRAPH, file_path="",
                ))
            except Exception:
                continue
        return results

    async def _search_timeline(self, date_str: str, top_k: int) -> list[SearchResult]:
        epi_dir = self.vault_path / "_memory" / "episodic"
        files = await list_directory(epi_dir, f"*{date_str}*.md")
        results = []
        for f in files[:top_k]:
            try:
                node = await parse_memory(f)
                results.append(SearchResult(
                    memory_id=node.id, title=f.stem, snippet=node.content[:200],
                    score=0.8, strategy=SearchStrategy.TIMELINE,
                    file_path=str(f.relative_to(self.vault_path)),
                ))
            except Exception:
                continue
        return results

    async def _search_context(self, context: str, top_k: int) -> list[SearchResult]:
        dirs = [
            self.vault_path / "_memory" / "semantic",
            self.vault_path / "_memory" / "episodic",
        ]
        results = []
        for d in dirs:
            files = await list_directory(d, "*.md")
            for f in files[:100]:
                try:
                    node = await parse_memory(f)
                    if node.context and context.lower() in node.context.lower():
                        results.append(SearchResult(
                            memory_id=node.id,
                            title=node.content.split("\n")[0].replace("# ", "")[:80],
                            snippet=node.content[:200], score=0.7,
                            strategy=SearchStrategy.CONTEXT,
                            file_path=str(f.relative_to(self.vault_path)),
                        ))
                except Exception:
                    continue
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _extract_snippet(self, content: str, query: str, window: int = 100) -> str:
        idx = content.lower().find(query.lower())
        if idx < 0:
            return content[:window]
        start = max(0, idx - window // 2)
        end = min(len(content), idx + len(query) + window // 2)
        return content[start:end]
