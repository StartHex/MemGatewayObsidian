"""Mem-Gateway-Obsidian CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def cmd_init(args):
    vault = Path(args.vault)
    dirs = [
        "_inbox", "_working", "_memory/semantic", "_memory/episodic",
        "_memory/procedural", "_memory/archive", "_vectors",
        "_meta", "_agent-logs", "_canvas", "_ui-config",
    ]
    for d in dirs:
        (vault / d).mkdir(parents=True, exist_ok=True)

    import yaml
    config = {
        "llm": {
            "chat": {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_key": "${ANTHROPIC_API_KEY}"},
            "embedding": {"provider": "local", "model": "bge-m3", "base_url": "http://localhost:8080", "dimension": 1024},
        },
    }
    config_path = vault / "_meta" / "system-config.yaml"
    if not config_path.exists():
        config_path.write_text(yaml.dump(config, default_flow_style=False))

    from memory_os.config.loader import embedding_config_hash
    from memory_os.config.models import EmbeddingConfig
    from memory_os.vault.vector_client import VectorStore

    embedding_raw = config["llm"]["embedding"]
    embed_cfg = EmbeddingConfig(
        provider=embedding_raw["provider"],
        model=embedding_raw["model"],
        base_url=embedding_raw.get("base_url"),
        dimension=embedding_raw.get("dimension", 1024),
    )
    embed_hash = embedding_config_hash(embed_cfg)
    hash_path = vault / "_meta" / "embedding-hash.txt"
    hash_path.write_text(embed_hash)

    VectorStore(vault)
    print(f"Vault 已初始化: {vault}")


async def cmd_ingest(args):
    from memory_os.config.loader import load_config
    from memory_os.llm.service import LLMService
    from memory_os.memory.service import MemoryService
    from memory_os.agents.sensory_gateway import SensoryGateway

    vault = Path(args.vault)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config)
    gateway = SensoryGateway(memory, llm, vault)

    node = await gateway.ingest(args.text, "cli", output=args.output)
    if node:
        print(f"Ingested: {node.id}")


async def cmd_search(args):
    from memory_os.config.loader import load_config
    from memory_os.llm.service import LLMService
    from memory_os.memory.service import MemoryService
    from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy

    vault = Path(args.vault)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config)
    agent = RetrievalAgent(memory, llm, vault)

    results = await agent.search(args.query, strategy=SearchStrategy.VECTOR)
    for r in results:
        print(f"[{r.score:.2f}] {r.title[:60]}")


async def cmd_list(args):
    from memory_os.config.loader import load_config
    from memory_os.llm.service import LLMService
    from memory_os.memory.service import MemoryService
    from memory_os.agents.retrieval import RetrievalAgent

    vault = Path(args.vault)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config)
    agent = RetrievalAgent(memory, llm, vault)

    result = await agent.list_all(
        type_filter=args.type,
        status_filter=args.status,
        limit=args.limit,
        offset=args.offset,
        sort_by=args.sort,
    )
    print(f"总计 {result['total']} 条记忆 (显示 {len(result['items'])} 条):")
    for item in result["items"]:
        print(f"  [{item['type']}] {item['id']} {item['title'][:60]}")
        print(f"    强度:{item['strength']:.0f} 重要:{item['importance']:.0f} 状态:{item['status']}")


async def cmd_similar(args):
    from memory_os.config.loader import load_config
    from memory_os.llm.service import LLMService
    from memory_os.memory.service import MemoryService
    from memory_os.agents.retrieval import RetrievalAgent

    vault = Path(args.vault)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config)
    agent = RetrievalAgent(memory, llm, vault)

    results = await agent.search_by_id(args.memory_id, top_k=args.top_k)
    if not results:
        print(f"未找到与 {args.memory_id} 相似的记忆")
        return
    for r in results:
        print(f"[{r.score:.2f}] {r.title[:60]}  id={r.memory_id}")


async def cmd_review(args):
    from memory_os.config.loader import load_config
    from memory_os.llm.service import LLMService
    from memory_os.memory.service import MemoryService
    from memory_os.agents.review import ReviewAgent

    vault = Path(args.vault)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config)
    agent = ReviewAgent(memory, llm, vault, config)

    report = await agent.run(target_date=args.date)
    print(f"## 记忆复盘 — {report.target_date}")
    print(f"时间线活动: {report.activities_count} 条, 新记忆: {report.new_memories} 条")
    if report.topics:
        print(f"话题: {', '.join(report.topics)}")
    if report.key_decisions:
        print(f"关键结论 ({len(report.key_decisions)} 条)")
    if report.narrative:
        print(f"\n{report.narrative}")


def main():
    parser = argparse.ArgumentParser(description="Mem-Gateway-Obsidian")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="初始化 vault")
    p_init.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_ingest = sub.add_parser("ingest", help="记录内容")
    p_ingest.add_argument("text")
    p_ingest.add_argument("--output", "-o", help="对应的结论或回答，提供后可自动提炼知识点和步骤")
    p_ingest.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_search = sub.add_parser("search", help="检索记忆")
    p_search.add_argument("query")
    p_search.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_list = sub.add_parser("list", help="列出所有记忆")
    p_list.add_argument("--type", "-t", choices=["all", "semantic", "episodic", "procedural"], default="all")
    p_list.add_argument("--status", "-s", choices=["all", "active", "fading", "archived"], default="all")
    p_list.add_argument("--limit", "-n", type=int, default=50)
    p_list.add_argument("--offset", "-o", type=int, default=0)
    p_list.add_argument("--sort", choices=["created", "strength", "importance", "recent"], default="created")
    p_list.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_similar = sub.add_parser("similar", help="查找与指定记忆语义相似的记忆")
    p_similar.add_argument("memory_id")
    p_similar.add_argument("--top-k", "-k", type=int, default=5)
    p_similar.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_review = sub.add_parser("review", help="触发记忆复盘（默认复盘昨日）")
    p_review.add_argument("--date", "-d", help="要复盘的日期 (YYYY-MM-DD)，默认昨日")
    p_review.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_tui = sub.add_parser("tui", help="启动 Textual TUI")
    p_tui.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    p_tui.add_argument("--backend", choices=["textual", "prompt"], default="textual")

    p_web = sub.add_parser("web", help="启动 WebUI")
    p_web.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    p_web.add_argument("--port", type=int, default=9090)

    p_mcp = sub.add_parser("mcp", help="启动 MCP Server (供 Claude Code 等 MCP 客户端调用)")
    p_mcp.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    p_sched = sub.add_parser("scheduler", help="启动 Agent 定时调度引擎")
    p_sched.add_argument("--vault", default=str(Path.home() / "memory-vault"))

    args = parser.parse_args()

    if args.command == "init":
        asyncio.run(cmd_init(args))
    elif args.command == "ingest":
        asyncio.run(cmd_ingest(args))
    elif args.command == "search":
        asyncio.run(cmd_search(args))
    elif args.command == "list":
        asyncio.run(cmd_list(args))
    elif args.command == "similar":
        asyncio.run(cmd_similar(args))
    elif args.command == "review":
        asyncio.run(cmd_review(args))
    elif args.command == "tui":
        if args.backend == "textual":
            from memory_os.tui.textual_app import main as tui_main
            sys.argv = ["tui", "--vault", args.vault]
            tui_main()
        else:
            from memory_os.tui.prompt_app import main as prompt_main
            sys.argv = ["tui", "--vault", args.vault]
            asyncio.run(prompt_main())
    elif args.command == "web":
        import os
        os.environ["MEMORY_OS_VAULT"] = args.vault
        import uvicorn
        from memory_os.api.routes import app
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    elif args.command == "mcp":
        import os
        os.environ["MEMORY_OS_VAULT"] = args.vault
        vault_path = Path(args.vault)
        if not (vault_path / "_meta" / "system-config.yaml").exists():
            print(f"错误: vault 未初始化。先运行: memory-os init --vault {vault_path}", file=sys.stderr)
            sys.exit(1)
        from memory_os.mcp_server import MCPServer
        server = MCPServer(vault_path)
        asyncio.run(server.run())
    elif args.command == "scheduler":
        import os
        os.environ["MEMORY_OS_VAULT"] = args.vault
        vault_path = Path(args.vault)
        if not (vault_path / "_meta" / "system-config.yaml").exists():
            print(f"错误: vault 未初始化。先运行: memory-os init --vault {vault_path}", file=sys.stderr)
            sys.exit(1)
        from memory_os.config.loader import load_config
        from memory_os.llm.service import LLMService
        from memory_os.memory.service import MemoryService
        from memory_os.scheduler import AgentScheduler, run_forever

        config = load_config(vault_path)
        memory = MemoryService(vault_path, config)
        llm = LLMService(config)
        sched = AgentScheduler(vault_path, config, memory, llm)
        sched.setup_default_jobs()
        async def _run():
            await sched.start()
            await run_forever(sched)
        asyncio.run(_run())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
