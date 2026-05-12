"""MemoryOS SDK Client — 对 Core SDK HTTP API 的 Python 封装。

用法:
    async with MemoryOSClient("http://localhost:9090") as client:
        memories = await client.search("Python 异步编程")
        memory = await client.get_memory("mem-sem-abc123")
"""

from __future__ import annotations

from typing import Any

import httpx


class MemoryOSError(Exception):
    pass


class MemoryOSClient:
    """异步 HTTP 客户端，封装 Memory OS API。"""

    def __init__(self, base_url: str = "http://localhost:9090", timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    async def _get(self, path: str, **params) -> dict:
        resp = await self._client.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json_data: dict | None = None) -> dict:
        resp = await self._client.post(f"{self.base_url}{path}", json=json_data or {})
        resp.raise_for_status()
        return resp.json()

    # ── Memories ────────────────────────────────────────────

    async def create_memory(
        self,
        content: str,
        *,
        type: str = "raw_input",
        tags: list[str] | None = None,
        importance: float = 50.0,
        context: str | None = None,
        source: str | None = None,
        output: str | None = None,
    ) -> dict:
        """录入新记忆。提供 output 可让系统自动提炼结论和步骤。"""
        body = {
            "content": content,
            "type": type,
            "tags": tags or [],
            "importance": importance,
            "context": context,
            "source": source,
        }
        if output is not None:
            body["output"] = output
        return await self._post("/api/v1/memories", body)

    async def get_memory(self, memory_id: str) -> dict:
        """获取指定记忆。"""
        return await self._get(f"/api/v1/memories/{memory_id}")

    # ── Search ──────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        strategy: str = "auto",
        top_k: int = 10,
    ) -> list[dict]:
        """通用搜索。strategy: auto/exact/keyword/vector/graph/timeline/context"""
        return await self._post("/api/v1/search", {
            "query": query,
            "strategy": strategy,
            "top_k": top_k,
        })

    async def semantic_search(self, query: str, top_k: int = 10) -> list[dict]:
        """语义搜索。"""
        return await self._post("/api/v1/search/semantic", {
            "query": query,
            "top_k": top_k,
        })

    # ── Canvas ──────────────────────────────────────────────

    async def get_canvas_graph(self, status: str | None = None) -> dict:
        """获取记忆图谱数据。"""
        params = {"status": status} if status else {}
        return await self._get("/api/v1/canvas/graph", **params)

    async def get_canvas_heatmap(self) -> dict:
        """获取强度热力图数据。"""
        return await self._get("/api/v1/canvas/heatmap")

    async def get_canvas_timeline(self, start: str | None = None, end: str | None = None) -> dict:
        """获取情景时间轴数据。start/end 格式: YYYY-MM-DD"""
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._get("/api/v1/canvas/timeline", **params)

    async def get_canvas_projection(self, type: str = "semantic") -> dict:
        """获取向量空间 2D 投影数据。"""
        return await self._get("/api/v1/canvas/projection", type=type)

    # ── System ──────────────────────────────────────────────

    async def get_health(self) -> dict:
        """系统健康报告。"""
        return await self._get("/api/v1/system/health")

    async def get_stats(self) -> dict:
        """记忆库统计。"""
        return await self._get("/api/v1/system/stats")

    async def trigger_agent(self, agent_name: str) -> dict:
        """手动触发 Agent 运行。agent_name: consolidation/forgetting/meta_cognition"""
        return await self._post("/api/v1/system/agents/run", {"agent": agent_name})


class SyncMemoryOSClient:
    """同步 HTTP 客户端（适合非异步场景）。"""

    def __init__(self, base_url: str = "http://localhost:9090", timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _get(self, path: str, **params) -> dict:
        resp = self._client.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_data: dict | None = None) -> dict:
        resp = self._client.post(f"{self.base_url}{path}", json=json_data or {})
        resp.raise_for_status()
        return resp.json()

    def create_memory(self, content: str, **kwargs) -> dict:
        body = {
            "content": content,
            "type": kwargs.get("type", "raw_input"),
            "tags": kwargs.get("tags", []),
            "importance": kwargs.get("importance", 50.0),
            "context": kwargs.get("context"),
            "source": kwargs.get("source"),
        }
        output = kwargs.get("output")
        if output is not None:
            body["output"] = output
        return self._post("/api/v1/memories", body)

    def get_memory(self, memory_id: str) -> dict:
        return self._get(f"/api/v1/memories/{memory_id}")

    def search(self, query: str, *, strategy: str = "auto", top_k: int = 10) -> list[dict]:
        return self._post("/api/v1/search", {
            "query": query, "strategy": strategy, "top_k": top_k,
        })

    def semantic_search(self, query: str, top_k: int = 10) -> list[dict]:
        return self._post("/api/v1/search/semantic", {"query": query, "top_k": top_k})

    def get_canvas_graph(self, status: str | None = None) -> dict:
        params = {"status": status} if status else {}
        return self._get("/api/v1/canvas/graph", **params)

    def get_canvas_heatmap(self) -> dict:
        return self._get("/api/v1/canvas/heatmap")

    def get_canvas_timeline(self, start: str | None = None, end: str | None = None) -> dict:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self._get("/api/v1/canvas/timeline", **params)

    def get_canvas_projection(self, type: str = "semantic") -> dict:
        return self._get("/api/v1/canvas/projection", type=type)

    def get_health(self) -> dict:
        return self._get("/api/v1/system/health")

    def get_stats(self) -> dict:
        return self._get("/api/v1/system/stats")

    def trigger_agent(self, agent_name: str) -> dict:
        return self._post("/api/v1/system/agents/run", {"agent": agent_name})
