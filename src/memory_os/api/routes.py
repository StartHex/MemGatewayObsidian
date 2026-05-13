"""Core SDK Public API — FastAPI routes.

所有 UI（GUI/TUI/WebUI）通过此 API 与系统交互。
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from memory_os.agents.consolidation import ConsolidationAgent
from memory_os.agents.forgetting import ForgettingAgent
from memory_os.agents.meta_cognition import MetaCognitionAgent
from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.agents.sensory_gateway import SensoryGateway
from memory_os.canvas.adapter import CanvasDataAdapter
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryType


_scheduler = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _scheduler
    vault_path = Path(os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault")))
    try:
        config = load_config(vault_path)
        memory = MemoryService(vault_path, config)
        llm = LLMService(config, vault_path=vault_path)
        from memory_os.scheduler import AgentScheduler
        _scheduler = AgentScheduler(vault_path, config, memory, llm)
        _scheduler.setup_default_jobs()
        await _scheduler.start()
    except Exception:
        pass  # 调度器启动失败不影响 API 服务
    yield
    if _scheduler:
        await _scheduler.stop()


app = FastAPI(title="Memory OS API", version="0.1.0", lifespan=_lifespan)


class CreateMemoryRequest(BaseModel):
    content: str
    type: str = "raw_input"
    tags: list[str] = []
    importance: float = 50.0
    context: str | None = None
    source: str | None = None
    output: str | None = None


class SearchRequest(BaseModel):
    query: str
    strategy: str = "auto"
    top_k: int = 10


class TriggerAgentRequest(BaseModel):
    agent: str  # consolidation | forgetting | meta_cognition


def _get_services():
    vault_path = Path(os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault")))
    config = load_config(vault_path)
    memory = MemoryService(vault_path, config)
    llm = LLMService(config, vault_path=vault_path)
    return vault_path, config, memory, llm



@app.get("/api/v1/system/health")
async def get_health():
    _, config, memory, llm = _get_services()
    agent = MetaCognitionAgent(memory, llm, config, _get_services()[0])
    return await agent.run()


@app.get("/api/v1/system/stats")
async def get_stats():
    vault_path, config, memory, _ = _get_services()
    canvas = CanvasDataAdapter(vault_path)
    heatmap = await canvas.heatmap_data()
    active = sum(1 for c in heatmap.cells if c.status == "active")
    fading = sum(1 for c in heatmap.cells if c.status == "fading")
    return {"active": active, "fading": fading, "total": len(heatmap.cells)}


@app.post("/api/v1/memories")
async def create_memory(req: CreateMemoryRequest):
    _, config, memory, llm = _get_services()
    gateway = SensoryGateway(memory, llm, _get_services()[0])
    type_ = MemoryType(req.type) if req.type in [t.value for t in MemoryType] else MemoryType.RAW_INPUT
    if req.source:
        node = await gateway.ingest(req.content, req.source, output=req.output)
        return node
    node = await memory.create(
        content=req.content, type_=type_,
        tags=req.tags, importance=req.importance, context=req.context,
        raw_output=req.output,
    )
    return node


@app.get("/api/v1/memories/{memory_id}")
async def get_memory(memory_id: str):
    _, config, memory, _ = _get_services()
    try:
        return await memory.get(memory_id)
    except FileNotFoundError:
        raise HTTPException(404, f"记忆不存在: {memory_id}")


@app.post("/api/v1/search")
async def search(req: SearchRequest):
    _, config, memory, llm = _get_services()
    vault_path = _get_services()[0]
    agent = RetrievalAgent(memory, llm, vault_path)
    strategy = SearchStrategy(req.strategy) if req.strategy in [s.value for s in SearchStrategy] else SearchStrategy.AUTO
    return await agent.search(req.query, strategy=strategy, top_k=req.top_k)


@app.post("/api/v1/search/semantic")
async def semantic_search(query: str = Query(...), top_k: int = 10):
    _, config, memory, llm = _get_services()
    vault_path = _get_services()[0]
    agent = RetrievalAgent(memory, llm, vault_path)
    return await agent.search(query, strategy=SearchStrategy.VECTOR, top_k=top_k)


@app.get("/api/v1/canvas/graph")
async def get_canvas_graph(status: str | None = None):
    vault_path = _get_services()[0]
    canvas = CanvasDataAdapter(vault_path)
    status_list = [status] if status else None
    return await canvas.graph_data(status_list)


@app.get("/api/v1/canvas/heatmap")
async def get_canvas_heatmap():
    vault_path = _get_services()[0]
    canvas = CanvasDataAdapter(vault_path)
    return await canvas.heatmap_data()


@app.get("/api/v1/canvas/timeline")
async def get_canvas_timeline(start: str | None = None, end: str | None = None):
    vault_path = _get_services()[0]
    canvas = CanvasDataAdapter(vault_path)
    today = date.today()
    s = date.fromisoformat(start) if start else today.replace(day=1)
    e = date.fromisoformat(end) if end else today
    return await canvas.timeline_data(s, e)


@app.get("/api/v1/canvas/projection")
async def get_canvas_projection(type: str = "semantic"):
    vault_path = _get_services()[0]
    canvas = CanvasDataAdapter(vault_path)
    return await canvas.vector_projection(type)


@app.post("/api/v1/system/agents/run")
async def trigger_agent(req: TriggerAgentRequest):
    vault_path, config, memory, llm = _get_services()
    if req.agent == "consolidation":
        agent = ConsolidationAgent(memory, llm, vault_path, config)
    elif req.agent == "forgetting":
        agent = ForgettingAgent(memory, config, vault_path)
    elif req.agent == "meta_cognition":
        agent = MetaCognitionAgent(memory, llm, config, vault_path)
    elif req.agent == "review":
        from memory_os.agents.review import ReviewAgent
        agent = ReviewAgent(memory, llm, vault_path, config)
    else:
        raise HTTPException(400, f"未知 Agent: {req.agent}")
    return await agent.run()


@app.get("/api/v1/memories")
async def list_memories(
    type: str = "all",
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "created",
):
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    return await agent.list_all(
        type_filter=type, status_filter=status,
        limit=limit, offset=offset, sort_by=sort_by,
    )


@app.get("/api/v1/memories/{memory_id}/similar")
async def find_similar(memory_id: str, top_k: int = 5):
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    return await agent.search_by_id(memory_id, top_k=top_k)


@app.post("/api/v1/system/review")
async def trigger_review(date: str | None = None):
    from memory_os.agents.review import ReviewAgent
    vault_path, config, memory, llm = _get_services()
    agent = ReviewAgent(memory, llm, vault_path, config)
    return await agent.run(target_date=date)


@app.post("/api/v1/working-memory/{action}")
async def working_memory_action(action: str, request: dict | None = None):
    from memory_os.agents.working_memory import WorkingMemoryManager
    vault_path, config, memory, llm = _get_services()
    wm = WorkingMemoryManager(memory, config, vault_path, llm)
    args = request or {}

    if action == "list":
        return await wm.list_slots()
    elif action == "promote":
        return {"slot_id": await wm.promote_to_slot(args.get("memory_id", ""), args.get("slot_name", "untitled"))}
    elif action == "update":
        return {"ok": await wm.update_slot(int(args.get("slot_id", 0)), args.get("content", ""))}
    elif action == "evict":
        slot = await wm.get_slot(int(args.get("slot_id", 0)))
        if slot is None:
            raise HTTPException(404, "槽位不存在")
        await wm._evict(slot)
        return {"ok": True}
    elif action == "conclude":
        trace = await wm.conclude_slot(int(args.get("slot_id", 0)))
        return trace.model_dump() if trace else {"trace": None}
    raise HTTPException(400, f"未知 action: {action}")
