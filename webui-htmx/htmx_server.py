"""WebUI 方案 B：HTMX + FastAPI + Jinja2 — 超轻量服务端渲染。

特点:
- 零 Node.js 依赖，纯 Python 生态
- 页面 <100KB，首屏 <500ms
- 适合低配设备、移动端浏览器访问
- Canvas 降级为服务端渲染 SVG

启动: uv run python webui-htmx/htmx_server.py --vault ~/memory-vault --port 9090
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.canvas.adapter import CanvasDataAdapter
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService

app = FastAPI(title="Memory OS — HTMX WebUI")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ---- 复用 Core SDK API ----
from memory_os.api.routes import app as api_app
app.mount("/api", api_app)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    results = []
    if q:
        vault_path = Path(os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault")))
        config = load_config(vault_path)
        memory = MemoryService(vault_path, config)
        llm = LLMService(config)
        agent = RetrievalAgent(memory, llm, vault_path)
        results = await agent.search(q, strategy=SearchStrategy.VECTOR)
    return templates.TemplateResponse("search.html", {"request": request, "query": q, "results": results})


@app.get("/canvas/graph", response_class=HTMLResponse)
async def canvas_graph(request: Request):
    vault_path = Path(os.environ.get("MEMORY_OS_VAULT", str(Path.home() / "memory-vault")))
    canvas = CanvasDataAdapter(vault_path)
    data = await canvas.graph_data()
    return templates.TemplateResponse("graph.html", {"request": request, "nodes": data.nodes[:100], "edges": data.edges[:200]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()
    os.environ["MEMORY_OS_VAULT"] = args.vault

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
