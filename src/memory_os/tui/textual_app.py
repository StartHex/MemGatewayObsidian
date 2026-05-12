"""TUI 方案 A：Textual — 富终端界面，键盘驱动，vim 键位。

启动: uv run python -m memory_os.tui.textual_app --vault ~/memory-vault
"""

from __future__ import annotations

import argparse
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, ListItem,
    ListView, Static, TabbedContent, TabPane,
)

from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.canvas.adapter import CanvasDataAdapter
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService


class DashboardTab(Static):
    def compose(self):
        yield Label("[bold]Memory OS Dashboard[/bold]")
        yield Label("Active: --  Fading: --  Inbox: --")
        yield Button("Refresh", id="refresh-dash")


class SearchTab(Static):
    def compose(self):
        yield Input(placeholder="搜索记忆... (Enter 检索)", id="search-input")
        yield DataTable(id="search-results")


class CaptureTab(Static):
    def compose(self):
        yield Input(placeholder="快速记录想法... (Enter 提交)", id="capture-input")


class HealthTab(Static):
    def compose(self):
        yield Label("[bold]系统健康[/bold]")
        yield Static(id="health-report")


class MemoryOSTUI(App):
    CSS = """
    Screen { layout: horizontal; }
    #sidebar { width: 20; background: $surface; }
    #content { width: 1fr; }
    ListView { height: 1fr; }
    #search-results { height: 1fr; }
    """

    def __init__(self, vault_path: str):
        super().__init__()
        self.vault_path = Path(vault_path)
        self.config = load_config(self.vault_path)
        self.memory = MemoryService(self.vault_path, self.config)
        self.llm = LLMService(self.config)

    def compose(self):
        yield Header()
        yield Horizontal(
            ListView(
                ListItem(Label("Dashboard")),
                ListItem(Label("Search")),
                ListItem(Label("Quick Capture")),
                ListItem(Label("Health")),
                id="sidebar",
            ),
            Container(
                DashboardTab(),
                SearchTab(),
                CaptureTab(),
                HealthTab(),
                id="content",
            ),
        )
        yield Footer()

    def on_key(self, event):
        if event.key == "ctrl+q":
            self.exit()
        if event.key == "ctrl+f":
            self.query_one("#search-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            await self._do_search(event.value)
        elif event.input.id == "capture-input":
            await self._do_capture(event.value)
            event.input.value = ""

    async def _do_search(self, query: str):
        agent = RetrievalAgent(self.memory, self.llm, self.vault_path)
        results = await agent.search(query, strategy=SearchStrategy.VECTOR)
        table = self.query_one("#search-results", DataTable)
        table.clear()
        table.add_columns("ID", "Title", "Score")
        for r in results:
            table.add_row(r.memory_id[:20], r.title[:50], f"{r.score:.2f}")

    async def _do_capture(self, text: str):
        from memory_os.agents.sensory_gateway import SensoryGateway
        gateway = SensoryGateway(self.memory, self.llm, self.vault_path)
        await gateway.ingest(text, "tui-quick-capture")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    args = parser.parse_args()
    app = MemoryOSTUI(args.vault)
    app.run()


if __name__ == "__main__":
    main()
