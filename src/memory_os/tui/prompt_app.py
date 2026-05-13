"""TUI 方案 B：prompt_toolkit — 轻量 CLI 交互，低依赖，适合 SSH 管道。

启动: uv run python -m memory_os.tui.prompt_app --vault ~/memory-vault
依赖: pip install prompt_toolkit (约 2MB)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.agents.sensory_gateway import SensoryGateway
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService

STYLE = Style.from_dict({
    "prompt": "bold green",
    "result": "italic",
})

COMMANDS = WordCompleter([
    "search", "capture", "stats", "health", "help", "exit", "quit",
], ignore_case=True)


async def cmd_search(memory, llm, vault_path, query: str):
    agent = RetrievalAgent(memory, llm, vault_path)
    results = await agent.search(query, strategy=SearchStrategy.VECTOR)
    if not results:
        print("  无结果。")
        return
    for i, r in enumerate(results[:10], 1):
        print(f"  {i}. [{r.score:.2f}] {r.title[:60]}")
        if r.snippet:
            print(f"     {r.snippet[:100]}")


async def cmd_capture(memory, llm, vault_path, text: str):
    gateway = SensoryGateway(memory, llm, vault_path)
    node = await gateway.ingest(text, "cli-capture")
    if node:
        print(f"  已记录: {node.id} — {node.tags}")
    else:
        print("  跳过（空内容或重复）")


async def cmd_stats(memory, llm, vault_path):
    config = load_config(vault_path)
    from memory_os.agents.meta_cognition import MetaCognitionAgent
    agent = MetaCognitionAgent(memory, llm, config, vault_path)
    report = await agent.run()
    print(f"  活跃记忆: {report.active_count}")
    print(f"  待处理:   {report.inbox_pending}")
    print(f"  孤岛:     {report.orphant_count}")
    print(f"  向量差异: {report.vector_inconsistencies}")


async def main_loop(vault_path: str):
    vault = Path(vault_path)
    config = load_config(vault)
    memory = MemoryService(vault, config)
    llm = LLMService(config, vault_path=vault)

    session = PromptSession(style=STYLE, completer=COMMANDS)

    print("=" * 50)
    print("Mem-Gateway-Obsidian CLI (prompt_toolkit 方案)")
    print("命令: search <query> | capture <text> | stats | help | exit")
    print("=" * 50)

    while True:
        try:
            line = await session.prompt_async("memory> ")
        except (EOFError, KeyboardInterrupt):
            break

        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            break
        elif cmd == "search" and arg:
            await cmd_search(memory, llm, vault, arg)
        elif cmd == "capture" and arg:
            await cmd_capture(memory, llm, vault, arg)
        elif cmd == "stats":
            await cmd_stats(memory, llm, vault)
        elif cmd == "help":
            print("  search <query>  检索记忆（语义搜索）")
            print("  capture <text>  快速记录想法")
            print("  stats           系统统计")
            print("  exit            退出")
        else:
            print(f"  未知命令: {cmd} (输入 help 查看帮助)")

    print("再见。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    args = parser.parse_args()
    import asyncio
    asyncio.run(main_loop(args.vault))


if __name__ == "__main__":
    main()
