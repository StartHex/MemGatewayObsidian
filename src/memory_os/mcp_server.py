"""MCP (Model Context Protocol) Server — 让 Claude Code 直接存取记忆。

协议: JSON-RPC 2.0 over stdio
启动: uv run memory-os mcp --vault ~/memory-vault
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.agents.sensory_gateway import SensoryGateway
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService


def _build_tools() -> list[dict]:
    return [
        {
            "name": "search_memory",
            "description": "语义搜索记忆库，返回最相关的结果。适合在对话中查找之前存储的知识、事实或上下文。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询，可以是自然语言问题或关键词",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 5",
                        "default": 5,
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["auto", "vector", "keyword", "graph"],
                        "description": "搜索策略: auto 自动选择, vector 语义搜索, keyword 关键词, graph 图谱遍历",
                        "default": "auto",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "capture_memory",
            "description": "将重要信息存入记忆库。适合保存用户偏好、决策、项目上下文、学到的知识等，供后续对话检索。同时提供 input 和 output 可让记忆更完整（系统会自动提炼结论和步骤）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "用户的问题、请求或情境",
                    },
                    "output": {
                        "type": "string",
                        "description": "得出的结论、回答或解决方案。与 content 一起提供时，系统会从中提炼核心知识点和步骤",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表，用于分类和检索",
                    },
                    "importance": {
                        "type": "number",
                        "description": "重要性评分 0-100，默认 50。高重要性记忆衰减更慢",
                        "default": 50,
                    },
                },
                "required": ["content"],
            },
        },
        {
            "name": "get_memory",
            "description": "根据记忆 ID 获取完整记忆内容。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "记忆 ID，如 mem-sem-xxx",
                    },
                },
                "required": ["memory_id"],
            },
        },
        {
            "name": "get_context",
            "description": "获取与当前话题相关的记忆上下文。自动语义匹配，适合在对话开始时了解用户背景和偏好。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "当前话题或项目描述",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 10",
                        "default": 10,
                    },
                },
                "required": ["topic"],
            },
        },
        {
            "name": "list_recent",
            "description": "列出最近存储的记忆。适合了解最近的对话主题和项目动态。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 20",
                        "default": 20,
                    },
                    "type": {
                        "type": "string",
                        "enum": ["all", "semantic", "episodic", "procedural"],
                        "description": "记忆类型过滤",
                        "default": "all",
                    },
                },
            },
        },
        {
            "name": "get_stats",
            "description": "获取记忆库统计信息：总数、活跃/衰减/归档分布、强度分布。",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
    ]


class MCPServer:
    """MCP JSON-RPC 2.0 服务端，通过 stdio 与 Claude Code 通信。"""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.config = load_config(vault_path)
        self.memory = MemoryService(vault_path, self.config)
        self.llm = LLMService(self.config)
        self._tools = _build_tools()
        self._initialized = False

    async def _process_line(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
            resp = await self._handle(msg)
            if resp is not None:
                out = json.dumps(resp, ensure_ascii=False, default=str) + "\n"
                sys.stdout.write(out)
                sys.stdout.flush()
        except json.JSONDecodeError:
            pass

    async def run(self):
        loop = asyncio.get_event_loop()
        # Use a thread to read stdin line by line, feed into async queue
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _read_stdin():
            for line in sys.stdin:
                loop.call_soon_threadsafe(queue.put_nowait, line)

        reader_task = loop.run_in_executor(None, _read_stdin)

        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=0.1)
                await self._process_line(line)
            except asyncio.TimeoutError:
                # Check if stdin reader has finished
                if reader_task.done():
                    # Process any remaining items in queue
                    while not queue.empty():
                        line = queue.get_nowait()
                        await self._process_line(line)
                    break

    async def _handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        msg_id = msg.get("id")

        # Notification — no response needed
        if msg_id is None:
            if method == "notifications/initialized":
                self._initialized = True
            return None

        params = msg.get("params", {})

        try:
            if method == "initialize":
                return self._respond(msg_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "memory-os",
                        "version": "0.1.0",
                    },
                })
            elif method == "tools/list":
                return self._respond(msg_id, {"tools": self._tools})
            elif method == "tools/call":
                return await self._call_tool(msg_id, params)
            else:
                return self._error(msg_id, -32601, f"未知方法: {method}")
        except Exception as exc:
            return self._error(msg_id, -32603, str(exc))

    async def _call_tool(self, msg_id: int, params: dict) -> dict:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await self._execute(name, arguments)
        return self._respond(msg_id, {
            "content": [{"type": "text", "text": result}],
        })

    async def _execute(self, name: str, args: dict) -> str:
        if name == "search_memory":
            return await self._search(args)
        elif name == "capture_memory":
            return await self._capture(args)
        elif name == "get_memory":
            return await self._get_item(args)
        elif name == "get_context":
            return await self._get_context(args)
        elif name == "list_recent":
            return await self._list_recent(args)
        elif name == "get_stats":
            return await self._get_stats()
        else:
            return f"未知工具: {name}"

    async def _search(self, args: dict) -> str:
        query = args["query"]
        top_k = args.get("top_k", 5)
        strategy = SearchStrategy(args.get("strategy", "auto"))

        agent = RetrievalAgent(self.memory, self.llm, self.vault_path)
        results = await agent.search(query, strategy=strategy, top_k=top_k)

        if not results:
            return "未找到相关记忆。"

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"**{i}.** [{r.score:.0%}] {r.title}")
            if r.snippet:
                lines.append(f"   {r.snippet[:200]}")
            lines.append(f"   id: `{r.memory_id}`")
        return "\n".join(lines)

    async def _capture(self, args: dict) -> str:
        content = args["content"]
        output = args.get("output")
        tags = args.get("tags", [])
        importance = float(args.get("importance", 50))

        gateway = SensoryGateway(self.memory, self.llm, self.vault_path)
        node = await gateway.ingest(content, source="mcp", output=output)

        if node is None:
            return "内容为空或重复，已跳过。"

        if tags:
            await self.memory.update(node.id, tags=tags)
        if importance != 50:
            await self.memory.update(node.id, importance=importance)

        return f"已存入记忆库。\n- ID: `{node.id}`\n- 标签: {tags or 'auto'}\n- 重要性: {importance:.0f}"

    async def _get_item(self, args: dict) -> str:
        memory_id = args["memory_id"]
        try:
            node = await self.memory.get(memory_id)
        except FileNotFoundError:
            return f"记忆不存在: `{memory_id}`"

        return (
            f"## {node.id}\n"
            f"- 类型: {node.type.value}\n"
            f"- 状态: {node.status.value}\n"
            f"- 强度: {node.strength:.1f}\n"
            f"- 重要性: {node.importance:.0f}\n"
            f"- 标签: {', '.join(node.tags) if node.tags else '无'}\n"
            f"- 关联: {len(node.links_to) + len(node.links_from)} 条\n"
            f"- 创建时间: {node.created_at}\n"
            f"- 最近检索: {node.last_retrieved or '从未'}\n"
            f"\n---\n{node.content}"
        )

    async def _get_context(self, args: dict) -> str:
        topic = args["topic"]
        top_k = args.get("top_k", 10)

        agent = RetrievalAgent(self.memory, self.llm, self.vault_path)
        results = await agent.search(topic, strategy=SearchStrategy.VECTOR, top_k=top_k)

        if not results:
            return "未找到相关上下文。"

        lines = [f"当前话题「{topic}」的相关记忆：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"### {i}. {r.title}")
            if r.snippet:
                lines.append(r.snippet[:300])
            lines.append(f"_id: `{r.memory_id}`, score: {r.score:.0%}_")
            lines.append("")
        return "\n".join(lines)

    async def _list_recent(self, args: dict) -> str:
        limit = args.get("limit", 20)
        mem_type = args.get("type", "all")

        from memory_os.vault.file_io import list_directory
        from memory_os.vault.frontmatter import parse_memory

        dirs = []
        if mem_type in ("all", "semantic"):
            dirs.append(self.vault_path / "_memory" / "semantic")
        if mem_type in ("all", "episodic"):
            dirs.append(self.vault_path / "_memory" / "episodic")
        if mem_type in ("all", "procedural"):
            dirs.append(self.vault_path / "_memory" / "procedural")

        nodes = []
        for d in dirs:
            files = await list_directory(d, "*.md")
            for f in files:
                try:
                    nodes.append(await parse_memory(f))
                except Exception:
                    continue

        nodes.sort(key=lambda n: n.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        nodes = nodes[:limit]

        if not nodes:
            return "记忆库为空。"

        lines = [f"最近 {len(nodes)} 条记忆：\n"]
        for i, n in enumerate(nodes, 1):
            title = n.content.split("\n")[0].replace("# ", "")[:80]
            tags_str = f" [{', '.join(n.tags)}]" if n.tags else ""
            date_str = n.created_at.strftime("%m-%d %H:%M") if n.created_at else "?"
            lines.append(f"{i}. `{n.id}` {date_str} {title}{tags_str}")
        return "\n".join(lines)

    async def _get_stats(self) -> str:
        from memory_os.vault.file_io import list_directory
        from memory_os.vault.frontmatter import parse_memory

        dirs = [
            self.vault_path / "_memory" / "semantic",
            self.vault_path / "_memory" / "episodic",
            self.vault_path / "_memory" / "procedural",
        ]

        total = 0
        active = 0
        fading = 0
        archived = 0
        strength_buckets = {"high": 0, "mid": 0, "low": 0}
        total_strength = 0.0

        for d in dirs:
            files = await list_directory(d, "*.md")
            for f in files:
                try:
                    n = await parse_memory(f)
                    total += 1
                    total_strength += n.strength
                    if n.status.value == "active":
                        active += 1
                    elif n.status.value == "fading":
                        fading += 1
                    elif n.status.value == "archived":
                        archived += 1
                    if n.strength >= 50:
                        strength_buckets["high"] += 1
                    elif n.strength >= 20:
                        strength_buckets["mid"] += 1
                    else:
                        strength_buckets["low"] += 1
                except Exception:
                    continue

        inbox_files = await list_directory(self.vault_path / "_inbox", "*.md")
        avg_strength = total_strength / max(total, 1)

        return (
            f"## 记忆库统计\n"
            f"- 总计: {total} 条记忆\n"
            f"- 活跃: {active} | 衰减中: {fading} | 已归档: {archived}\n"
            f"- 待处理 (inbox): {len(inbox_files)} 条\n"
            f"- 平均强度: {avg_strength:.1f}\n"
            f"- 高强度 (≥50): {strength_buckets['high']} | "
            f"中强度 (20-49): {strength_buckets['mid']} | "
            f"低强度 (<20): {strength_buckets['low']}"
        )

    @staticmethod
    def _respond(msg_id: int, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: int, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    args = parser.parse_args()

    vault_path = Path(args.vault)
    if not (vault_path / "_meta" / "system-config.yaml").exists():
        print(f"错误: vault 未初始化。先运行: memory-os init --vault {vault_path}", file=sys.stderr)
        sys.exit(1)

    server = MCPServer(vault_path)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
