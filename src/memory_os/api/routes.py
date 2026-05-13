"""Core SDK Public API — FastAPI routes.

All UIs (GUI/TUI/WebUI) interact with the system through this API.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from memory_os.agents.consolidation import ConsolidationAgent
from memory_os.agents.forgetting import ForgettingAgent
from memory_os.agents.meta_cognition import MetaCognitionAgent
from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.agents.sensory_gateway import SensoryGateway
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.models import MemoryType


_scheduler = None
_services_cache: dict = {}


def _get_services():
    """Get or create services for the configured vault."""
    vault_path_str = os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault"))
    key = f"svc-{vault_path_str}"
    if key not in _services_cache:
        vault_path = Path(vault_path_str)
        config = load_config(vault_path)
        memory = MemoryService(vault_path, config)
        llm = LLMService(config, vault_path=vault_path)
        _services_cache[key] = (vault_path, config, memory, llm)
    return _services_cache[key]


def _invalidate_services():
    _services_cache.clear()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _scheduler
    vault_path_str = os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault"))
    try:
        vault_path = Path(vault_path_str)
        config = load_config(vault_path)
        memory = MemoryService(vault_path, config)
        llm = LLMService(config, vault_path=vault_path)
        from memory_os.scheduler import AgentScheduler
        _scheduler = AgentScheduler(vault_path, config, memory, llm)
        _scheduler.setup_default_jobs()
        await _scheduler.start()
    except Exception:
        pass
    yield
    if _scheduler:
        await _scheduler.stop()


app = FastAPI(title="Memory OS API", version="0.1.0", lifespan=_lifespan)

# Allow LAN access from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket for real-time events ─────────────────────────────

_ws_clients: list[WebSocket] = []


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        _ws_clients.remove(ws)


# ── Request models ─────────────────────────────────────────────

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


class InjectRequest(BaseModel):
    query: str
    top_k: int = 5


class TriggerAgentRequest(BaseModel):
    agent: str  # consolidation | forgetting | meta_cognition | review


class WorkingMemoryRequest(BaseModel):
    action: str | None = None
    slot_id: int | None = None
    memory_id: str | None = None
    name: str | None = None
    content: str | None = None


# ── System endpoints ───────────────────────────────────────────

@app.get("/api/v1/system/health")
async def get_health():
    vault_path, config, memory, llm = _get_services()
    agent = MetaCognitionAgent(memory, llm, config, vault_path)
    return await agent.run()


@app.get("/api/v1/system/stats")
async def get_stats():
    vault_path, config, memory, llm = _get_services()
    from memory_os.vault.frontmatter import parse_memory

    active = 0
    fading = 0
    total = 0
    for mem_dir in ["_memory/semantic", "_memory/episodic", "_memory/procedural"]:
        dir_path = vault_path / mem_dir
        if not dir_path.exists():
            continue
        for f in await list_directory(dir_path, "*.md"):
            try:
                node = await parse_memory(f)
                total += 1
                if node.status.value == "active":
                    active += 1
                elif node.status.value == "fading":
                    fading += 1
            except Exception:
                continue
    # Count inbox items (raw=unprocessed pending, active=already consolidated)
    inbox_pending = 0
    inbox_dir = vault_path / "_inbox"
    if inbox_dir.exists():
        for f in await list_directory(inbox_dir, "*.md"):
            try:
                node = await parse_memory(f)
                total += 1
                if node.status.value == "raw":
                    inbox_pending += 1
            except Exception:
                continue
    return {
        "active": active, "fading": fading, "total": total,
        "inbox_pending": inbox_pending,
    }


@app.get("/api/v1/system/review/latest")
async def get_latest_review():
    vault_path = _get_services()[0]
    epi_dir = vault_path / "_memory" / "episodic"
    if not epi_dir.exists():
        return {"found": False}
    review_files = sorted(
        [f for f in epi_dir.glob("review-*.md")],
        key=lambda f: f.stat().st_mtime, reverse=True,
    )
    if not review_files:
        return {"found": False}
    content = review_files[0].read_text(encoding="utf-8")
    return {"found": True, "date": review_files[0].stem.replace("review-", ""), "content": content}


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
    elif req.agent == "supervisor":
        from memory_os.agents.supervisor import SystemSupervisor
        agent = SystemSupervisor(memory, vault_path, config)
    else:
        raise HTTPException(400, f"Unknown agent: {req.agent}")
    return await agent.run()


@app.post("/api/v1/system/review")
async def trigger_review(date: str | None = None):
    from memory_os.agents.review import ReviewAgent
    vault_path, config, memory, llm = _get_services()
    agent = ReviewAgent(memory, llm, vault_path, config)
    return await agent.run(target_date=date)


# ── Memory CRUD ─────────────────────────────────────────────────

@app.post("/api/v1/memories")
async def create_memory(req: CreateMemoryRequest):
    vault_path, config, memory, llm = _get_services()
    gateway = SensoryGateway(memory, llm, vault_path)
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


@app.get("/api/v1/memories/{memory_id}")
async def get_memory(memory_id: str):
    vault_path, config, memory, llm = _get_services()
    try:
        return await memory.get(memory_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Memory not found: {memory_id}")


@app.get("/api/v1/memories/{memory_id}/similar")
async def find_similar(memory_id: str, top_k: int = 5):
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    return await agent.search_by_id(memory_id, top_k=top_k)


# ── Search ──────────────────────────────────────────────────────

@app.post("/api/v1/search")
async def search(req: SearchRequest):
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    strategy = SearchStrategy(req.strategy) if req.strategy in [s.value for s in SearchStrategy] else SearchStrategy.AUTO
    return await agent.search(req.query, strategy=strategy, top_k=req.top_k)


@app.post("/api/v1/search/inject")
async def search_and_inject(req: InjectRequest):
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    ctx = await agent.search_and_inject(req.query, top_k=req.top_k)
    return {"query": req.query, "context": ctx, "result_count": ctx.count("[记忆")}


@app.post("/api/v1/search/inject-and-save")
async def search_inject_and_save(req: InjectRequest):
    """搜索相关记忆并写入 _meta/last-context.md，无结果时删除旧文件。"""
    vault_path, config, memory, llm = _get_services()
    agent = RetrievalAgent(memory, llm, vault_path)
    ctx = await agent.search_and_inject(req.query, top_k=req.top_k, min_score=0.40)

    context_path = vault_path / "_meta" / "last-context.md"
    result_count = ctx.count("[记忆") if ctx else 0

    if ctx and result_count > 0:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        content = (
            f"# Memory Context\n"
            f"> Retrieved: {now} | Query: \"{req.query[:120]}\"\n"
            f"> {result_count} relevant memories found\n\n"
            f"{ctx}\n"
        )
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(content, encoding="utf-8")
        return {"query": req.query, "context": ctx, "result_count": result_count, "saved": True}
    else:
        if context_path.exists():
            context_path.unlink()
        return {"query": req.query, "context": "", "result_count": 0, "saved": False}


# ── Working Memory ──────────────────────────────────────────────

@app.post("/api/v1/working-memory/{action}")
async def working_memory_action(action: str, request: dict | None = None):
    from memory_os.agents.working_memory import WorkingMemoryManager
    _, config, memory, llm = _get_services()
    vault_path = _get_services()[0]
    wm = WorkingMemoryManager(memory, config, vault_path, llm)
    args = request or {}

    if action == "list":
        return await wm.list_slots()
    elif action == "promote":
        return {"slot_id": await wm.promote_to_slot(args.get("memory_id", ""), args.get("name", "untitled"))}
    elif action == "update":
        return {"ok": await wm.update_slot(int(args.get("slot_id", 0)), args.get("content", ""))}
    elif action == "evict":
        slot = await wm.get_slot(int(args.get("slot_id", 0)))
        if slot is None:
            raise HTTPException(404, "Slot not found")
        await wm._evict(slot)
        return {"ok": True}
    elif action == "conclude":
        trace = await wm.conclude_slot(int(args.get("slot_id", 0)))
        return trace.model_dump() if trace else {"trace": None}
    raise HTTPException(400, f"Unknown action: {action}")


# ── System Supervisor ───────────────────────────────────────────

@app.get("/api/v1/system/alerts")
async def get_alerts():
    """Return latest alerts.md content with parsed severity level."""
    vault_path = _get_services()[0]
    alerts_path = vault_path / "_meta" / "alerts.md"
    if not alerts_path.exists():
        return {"level": "OK", "content": "", "file_exists": False}

    content = alerts_path.read_text(encoding="utf-8")
    # Parse severity from content
    level = "OK"
    if "CRITICAL" in content:
        level = "CRITICAL"
    elif "ACTION" in content:
        level = "ACTION"
    elif "WARNING" in content:
        level = "WARNING"
    return {"level": level, "content": content, "file_exists": True}


# ── Hot Cache ────────────────────────────────────────────────────

class TranscriptSaveRequest(BaseModel):
    content: str
    metadata: dict = {}


class ValidateRequest(BaseModel):
    file_path: str


@app.get("/api/v1/system/hot")
async def get_hot():
    """Return hot.md content for session injection."""
    from memory_os.api.hot_cache import HotCacheManager
    vault_path = _get_services()[0]
    manager = HotCacheManager(vault_path)
    content = await manager.get()
    if content:
        return {"content": content, "generated": False}
    # Auto-generate if missing
    content = await manager.generate(session_count=1)
    return {"content": content, "generated": True}


@app.post("/api/v1/system/hot/update")
async def update_hot(session_count: int = 0):
    """Regenerate hot.md from current vault state."""
    from memory_os.api.hot_cache import HotCacheManager
    vault_path = _get_services()[0]
    manager = HotCacheManager(vault_path)
    content = await manager.generate(session_count=session_count)
    return {"content": content, "updated": True}


@app.post("/api/v1/system/transcript/save")
async def save_transcript(req: TranscriptSaveRequest):
    """Save session transcript to _agent-logs/."""
    vault_path = _get_services()[0]
    from datetime import datetime, timezone
    from memory_os.vault.file_io import atomic_write

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    session_id = req.metadata.get("session_id", "unknown")[:20]
    filename = f"session-{session_id}-{ts}.md"
    log_dir = vault_path / "_agent-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_content = (
        f"# Session Transcript\n"
        f"> Saved: {ts} | Messages: {req.metadata.get('message_count', 0)}\n\n"
        f"```json\n{req.content}\n```\n"
    )
    await atomic_write(log_dir / filename, log_content)

    return {"saved": True, "file": f"_agent-logs/{filename}"}


@app.post("/api/v1/system/validate")
async def validate_file(req: ValidateRequest):
    """Validate a markdown file: frontmatter fields + wikilinks."""
    from memory_os.api.hot_cache import validate_md_file
    vault_path = _get_services()[0]
    return await validate_md_file(vault_path, req.file_path)


# ── Static file serving (WebUI production build) ───────────────

_webui_dist = Path(__file__).resolve().parent.parent.parent.parent / "webui-react" / "dist"


@app.get("/{full_path:path}")
async def serve_webui(full_path: str):
    """Serve WebUI static files. Falls through to API routes first."""
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    file_path = _webui_dist / full_path if full_path else _webui_dist / "index.html"
    if file_path.is_file() and file_path.exists():
        return FileResponse(str(file_path))
    # SPA fallback
    index_path = _webui_dist / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(404, "WebUI not built. Run: cd webui-react && npm run build")
