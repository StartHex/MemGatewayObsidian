"""TUI — Textual terminal UI for Memory OS.

Launch: memory-os tui --vault ~/memory-vault
Or:     uv run python -m memory_os.tui.textual_app --vault ~/memory-vault

Requires the API server running: memory-os serve --vault ~/memory-vault
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label,
    ListItem, ListView, RichLog, Static, Switch, TabbedContent,
    TabPane, TextArea,
)
from textual.binding import Binding

API_BASE = os.environ.get("MEMORY_OS_API", "http://127.0.0.1:9090")


async def api_get(path: str) -> dict | list:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{API_BASE}{path}")
        resp.raise_for_status()
        return resp.json()


async def api_post(path: str, body: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API_BASE}{path}", json=body or {})
        resp.raise_for_status()
        return resp.json()


class DashboardPane(Static):
    """Live stats + recent memories."""

    async def on_mount(self):
        self.set_interval(30, self.refresh_data)
        await self.refresh_data()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="dash-stats")
            yield Static("Recent Memories:", id="dash-recent-label")
            yield DataTable(id="dash-recent-table", cursor_type="row")

    @work(exclusive=True)
    async def refresh_data(self):
        try:
            stats = await api_get("/api/v1/system/stats")
            self.query_one("#dash-stats", Static).update(
                f"[bold green]{stats.get('active', 0)}[/] active  "
                f"[bold yellow]{stats.get('fading', 0)}[/] fading  "
                f"[bold]{stats.get('total', 0)}[/] total  "
                f"[bold magenta]{stats.get('inbox_pending', 0)}[/] inbox pending"
            )
            mems = await api_get("/api/v1/memories?limit=10&sort_by=recent")
            table = self.query_one("#dash-recent-table", DataTable)
            table.clear(columns=True)
            table.add_columns("ID", "Type", "Title", "Strength")
            for m in mems.get("items", [])[:10]:
                table.add_row(
                    m["id"][-16:], m["type"],
                    m["title"][:50],
                    f"{m['strength']:.0f}",
                )
        except Exception:
            pass


class SearchPane(Static):
    """Search with strategy selector and results table."""

    strategies = ["auto", "vector", "keyword", "exact", "graph", "timeline", "traceback"]

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="search-bar"):
                yield Input(placeholder="Search memories...", id="search-input")
                yield Button("Search", id="search-btn", variant="primary")
            with Horizontal(id="search-options"):
                yield Label("Strategy:")
                for s in self.strategies:
                    yield Button(s, id=f"strat-{s}", classes="strat-btn")
                yield Label("  Top-K:")
                yield Input(value="10", id="topk-input", type="integer")
            yield DataTable(id="search-results", cursor_type="row")

    def on_mount(self):
        self._strat = "vector"
        self._highlight_strat()

    def _highlight_strat(self):
        for s in self.strategies:
            btn = self.query_one(f"#strat-{s}", Button)
            btn.variant = "primary" if s == self._strat else "default"

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("strat-"):
            self._strat = event.button.id.replace("strat-", "")
            self._highlight_strat()
        elif event.button.id == "search-btn":
            self._do_search()

    async def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self._do_search()

    @work(exclusive=True)
    async def _do_search(self):
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            return
        try:
            top_k = int(self.query_one("#topk-input", Input).value or "10")
        except ValueError:
            top_k = 10
        try:
            results = await api_post("/api/v1/search", {
                "query": query, "strategy": self._strat, "top_k": top_k,
            })
            table = self.query_one("#search-results", DataTable)
            table.clear(columns=True)
            table.add_columns("Score", "Strategy", "Title", "ID")
            for r in results:
                table.add_row(
                    f"{r['score']:.2f}", r['strategy'],
                    r['title'][:60], r['memory_id'][:24],
                )
        except Exception as e:
            self.query_one("#search-results", DataTable).clear(columns=True)
            self.query_one("#search-results", DataTable).add_columns("Error")
            self.query_one("#search-results", DataTable).add_row(str(e))


class CapturePane(Static):
    """Quick capture with optional output."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Quick Capture[/bold]")
            yield Label("Input (question / thought):")
            yield TextArea(id="capture-input", text="")
            yield Label("Output / answer (optional):")
            yield TextArea(id="capture-output", text="")
            yield Input(placeholder="tags: comma separated", id="capture-tags")
            with Horizontal():
                yield Button("Submit", id="capture-submit", variant="primary")
                yield Label("", id="capture-status")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "capture-submit":
            self._do_capture()

    @work(exclusive=True)
    async def _do_capture(self):
        content = self.query_one("#capture-input", TextArea).text.strip()
        if not content:
            return
        output = self.query_one("#capture-output", TextArea).text.strip() or None
        tags_str = self.query_one("#capture-tags", Input).value.strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        try:
            await api_post("/api/v1/memories", {
                "content": content, "type": "raw_input", "tags": tags,
                "importance": 60, "source": "tui", "output": output,
            })
            self.query_one("#capture-status", Label).update("[green]Saved![/]")
            self.query_one("#capture-input", TextArea).text = ""
            self.query_one("#capture-output", TextArea).text = ""
        except Exception as e:
            self.query_one("#capture-status", Label).update(f"[red]{e}[/]")


class WorkingMemoryPane(Static):
    """Working memory slots management."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Working Memory Slots[/bold]")
            yield DataTable(id="wm-table", cursor_type="row")
            with Horizontal(id="wm-actions"):
                yield Button("Refresh", id="wm-refresh")
                yield Button("Promote", id="wm-promote", variant="primary")
                yield Button("Update", id="wm-update")
                yield Button("Evict", id="wm-evict")
                yield Button("Conclude", id="wm-conclude", variant="warning")
            yield Static(id="wm-status")

    async def on_mount(self):
        await self._refresh()

    def on_button_pressed(self, event: Button.Pressed):
        bid = event.button.id
        if bid == "wm-refresh":
            self._refresh()
        elif bid == "wm-promote":
            self._promote()
        elif bid == "wm-update":
            self._update()
        elif bid == "wm-evict":
            self._evict()
        elif bid == "wm-conclude":
            self._conclude()

    @work(exclusive=True)
    async def _refresh(self):
        try:
            slots = await api_post("/api/v1/working-memory/list", {"action": "list"})
            table = self.query_one("#wm-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Slot", "Name", "Pinned", "Ops")
            for s in slots:
                table.add_row(
                    str(s["slot_id"]), s["slot_name"],
                    "[green]Y[/]" if s.get("pinned") else "N",
                    str(s.get("operation_count", 0)),
                )
        except Exception as e:
            self.query_one("#wm-status", Static).update(f"[red]{e}[/]")

    @work(exclusive=True)
    async def _promote(self):
        # Placeholder — real impl would show a dialog
        try:
            result = await api_post("/api/v1/working-memory/promote", {
                "memory_id": "mem-test-001", "name": "manual-promote",
            })
            self.query_one("#wm-status", Static).update(f"[green]Promoted slot {result.get('slot_id')}[/]")
            await self._refresh()
        except Exception as e:
            self.query_one("#wm-status", Static).update(f"[red]{e}[/]")

    @work(exclusive=True)
    async def _update(self):
        table = self.query_one("#wm-table", DataTable)
        if table.row_count == 0:
            return
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_row, 0)
            slot_id = int(table.get_cell(row_key))
            result = await api_post("/api/v1/working-memory/update", {
                "slot_id": slot_id, "content": "# Updated from TUI\n\nManual update",
            })
            self.query_one("#wm-status", Static).update(f"[green]Slot {slot_id} updated[/]")
            await self._refresh()
        except Exception as e:
            self.query_one("#wm-status", Static).update(f"[red]{e}[/]")

    @work(exclusive=True)
    async def _evict(self):
        table = self.query_one("#wm-table", DataTable)
        if table.row_count == 0:
            return
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_row, 0)
            slot_id = int(table.get_cell(row_key))
            await api_post("/api/v1/working-memory/evict", {"slot_id": slot_id})
            self.query_one("#wm-status", Static).update(f"[green]Slot {slot_id} evicted[/]")
            await self._refresh()
        except Exception as e:
            self.query_one("#wm-status", Static).update(f"[red]{e}[/]")

    @work(exclusive=True)
    async def _conclude(self):
        table = self.query_one("#wm-table", DataTable)
        if table.row_count == 0:
            return
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_row, 0)
            slot_id = int(table.get_cell(row_key))
            result = await api_post("/api/v1/working-memory/conclude", {"slot_id": slot_id})
            trace = result.get("trace") if isinstance(result, dict) else None
            if trace:
                self.query_one("#wm-status", Static).update(
                    f"[green]Trace saved: {result.get('title', '')}[/]"
                )
            else:
                self.query_one("#wm-status", Static).update("No reasoning chain detected")
            await self._refresh()
        except Exception as e:
            self.query_one("#wm-status", Static).update(f"[red]{e}[/]")


class HealthPane(Static):
    """System health report from Meta-Cognition Agent."""

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Button("Refresh Health Report", id="health-refresh", variant="primary")
            yield Static(id="health-content")

    async def on_mount(self):
        await self._refresh()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "health-refresh":
            self._refresh()

    @work(exclusive=True)
    async def _refresh(self):
        try:
            report = await api_get("/api/v1/system/health")
            lines = [
                "[bold]System Health Report[/bold]",
                f"Generated: {report.get('generated_at', '')}",
                "",
                f"[bold]Inbox Pending:[/] {report.get('inbox_pending', 0)}",
                f"[bold]Active Count:[/] {report.get('active_count', 0)}",
                f"[bold]Fading Count:[/] {report.get('fading_count', 0)}",
                f"[bold]Archived:[/] {report.get('archived_count', 0)}",
                f"[bold]Orphan Nodes:[/] {report.get('orphan_count', 0)}",
                f"[bold]Vector Inconsistencies:[/] {report.get('vector_inconsistencies', 0)}",
                f"[bold]Conflicts:[/] [red]{report.get('conflict_count', 0)}[/]",
                "",
            ]
            dist = report.get("strength_distribution", {})
            if dist:
                lines.append("[bold]Strength Distribution:[/]")
                for k, v in dist.items():
                    lines.append(f"  {k}: {v}")
                lines.append("")

            gaps = report.get("knowledge_gaps", [])
            if gaps:
                lines.append("[bold yellow]Knowledge Gaps:[/]")
                for g in gaps:
                    lines.append(f"  - {g}")
                lines.append("")

            recs = report.get("recommendations", [])
            if recs:
                lines.append("[bold cyan]Recommendations:[/]")
                for r in recs:
                    lines.append(f"  - {r}")

            self.query_one("#health-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#health-content", Static).update(f"[red]Failed: {e}[/]")


class CanvasPane(Static):
    """Canvas data overview."""

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="canvas-tabs"):
                for name in ["graph", "heatmap", "timeline", "projection"]:
                    yield Button(name, id=f"canvas-{name}", classes="canvas-btn")
            yield Static(id="canvas-content")

    def on_mount(self):
        self._active = "graph"
        self._do_load()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id and event.button.id.startswith("canvas-"):
            self._active = event.button.id.replace("canvas-", "")
            self._do_load()

    @work(exclusive=True)
    async def _do_load(self):
        try:
            data = await api_get(f"/api/v1/canvas/{self._active}")
            if self._active == "graph":
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])
                self.query_one("#canvas-content", Static).update(
                    f"[bold]Memory Graph[/bold]\n"
                    f"Nodes: {len(nodes)}  Edges: {len(edges)}\n"
                    f"Status distribution: " + ", ".join(
                        f"{s}: {sum(1 for n in nodes if n.get('status') == s)}"
                        for s in ["active", "fading", "archived"]
                    )
                )
            elif self._active == "heatmap":
                cells = data.get("cells", [])
                self.query_one("#canvas-content", Static).update(
                    f"[bold]Strength Heatmap[/bold]\n"
                    f"Cells: {len(cells)}\n"
                    f"Avg strength: {sum(c.get('strength', 0) for c in cells) / max(len(cells), 1):.1f}"
                )
            elif self._active == "timeline":
                entries = data.get("entries", [])
                self.query_one("#canvas-content", Static).update(
                    f"[bold]Timeline[/bold]\nEntries: {len(entries)}"
                )
            else:
                points = data.get("points", [])
                self.query_one("#canvas-content", Static).update(
                    f"[bold]Vector Projection[/bold]\nPoints: {len(points)}"
                )
        except Exception as e:
            self.query_one("#canvas-content", Static).update(f"[red]Failed to load: {e}[/]")


class ReviewPane(Static):
    """Memory review / daily recap."""

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            with Horizontal():
                yield Button("Generate Review", id="review-generate", variant="primary")
                yield Button("Load Latest", id="review-latest")
                yield Input(placeholder="Date (YYYY-MM-DD, empty=yesterday)", id="review-date")
            yield Static(id="review-content")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "review-generate":
            self._generate()
        elif event.button.id == "review-latest":
            self._load_latest()

    @work(exclusive=True)
    async def _generate(self):
        date_str = self.query_one("#review-date", Input).value.strip() or None
        body = {"date": date_str} if date_str else {}
        try:
            report = await api_post("/api/v1/system/review", body)
            self._display_report(report)
        except Exception as e:
            self.query_one("#review-content", Static).update(f"[red]Failed: {e}[/]")

    @work(exclusive=True)
    async def _load_latest(self):
        try:
            result = await api_get("/api/v1/system/review/latest")
            if result.get("found"):
                self.query_one("#review-content", Static).update(result["content"])
            else:
                self.query_one("#review-content", Static).update("No review reports found.")
        except Exception as e:
            self.query_one("#review-content", Static).update(f"[red]{e}[/]")

    def _display_report(self, report: dict):
        lines = [
            f"[bold]Memory Review — {report.get('target_date', '')}[/bold]",
            f"Activities: {report.get('activities_count', 0)}  New: {report.get('new_memories', 0)}",
            "",
        ]
        for section, label in [
            ("topics", "Topics"), ("key_decisions", "Key Decisions"),
            ("knowledge_gaps", "Knowledge Gaps"), ("connections", "Connections"),
            ("actions", "Actions"),
        ]:
            items = report.get(section, [])
            if items:
                lines.append(f"[bold]{label}:[/]")
                for item in items:
                    lines.append(f"  - {item}")
                lines.append("")
        if report.get("narrative"):
            lines.append(f"[bold italic]{report['narrative']}[/]")
        self.query_one("#review-content", Static).update("\n".join(lines))


class MemoryOSTUI(App):
    CSS = """
    Screen { layout: horizontal; }
    #sidebar {
        width: 18;
        background: $surface;
        border-right: solid $primary;
    }
    #sidebar ListView { height: 1fr; }
    #content { width: 1fr; padding: 1; }
    #dash-stats { padding: 1; background: $surface-darken-1; margin-bottom: 1; }
    #search-bar { height: 3; margin-bottom: 1; }
    #search-bar Input { width: 1fr; }
    #search-options { height: 3; margin-bottom: 1; }
    .strat-btn { min-width: 8; }
    #search-results { height: 1fr; }
    #wm-actions { height: 3; }
    #wm-table { height: 1fr; }
    #wm-status { height: 1; }
    #canvas-tabs { height: 3; }
    .canvas-btn { min-width: 12; }
    #canvas-content { height: 1fr; }
    #health-content { height: 1fr; }
    #review-content { height: 1fr; }
    TextArea { height: 5; margin-bottom: 1; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+f", "focus_search", "Search", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
        Binding("ctrl+n", "focus_capture", "Capture", show=True),
    ]

    def __init__(self, vault_path: str):
        super().__init__()
        self.vault_path = vault_path

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(
                ListItem(Label("  Dashboard")),
                ListItem(Label("  Search")),
                ListItem(Label("  Quick Capture")),
                ListItem(Label("  Working Memory")),
                ListItem(Label("  Review")),
                ListItem(Label("  Health")),
                ListItem(Label("  Canvas")),
                id="sidebar",
            )
            with Container(id="content"):
                yield DashboardPane(id="screen-dashboard")
                yield SearchPane(id="screen-search")
                yield CapturePane(id="screen-capture")
                yield WorkingMemoryPane(id="screen-wm")
                yield ReviewPane(id="screen-review")
                yield HealthPane(id="screen-health")
                yield CanvasPane(id="screen-canvas")
        yield Footer()

    def on_mount(self):
        self._show_screen("screen-dashboard")

    def on_list_view_selected(self, event: ListView.Selected):
        if event.item is None:
            return
        label = event.item.query_one(Label).renderable.plain.strip()
        screen_map = {
            "Dashboard": "screen-dashboard",
            "Search": "screen-search",
            "Quick Capture": "screen-capture",
            "Working Memory": "screen-wm",
            "Review": "screen-review",
            "Health": "screen-health",
            "Canvas": "screen-canvas",
        }
        screen_id = screen_map.get(label)
        if screen_id:
            self._show_screen(screen_id)

    def _show_screen(self, screen_id: str):
        all_screens = [
            "screen-dashboard", "screen-search", "screen-capture",
            "screen-wm", "screen-review", "screen-health", "screen-canvas",
        ]
        for sid in all_screens:
            self.query_one(f"#{sid}").display = (sid == screen_id)

    def action_focus_search(self):
        self._show_screen("screen-search")
        self.query_one("#search-input", Input).focus()

    def action_focus_capture(self):
        self._show_screen("screen-capture")
        self.query_one("#capture-input", TextArea).focus()

    def action_refresh(self):
        # Trigger refresh on visible screen
        for sid, cls in [
            ("screen-dashboard", DashboardPane),
            ("screen-health", HealthPane),
            ("screen-wm", WorkingMemoryPane),
        ]:
            w = self.query_one(f"#{sid}")
            if w.display and hasattr(w, "refresh_data"):
                w.refresh_data()
            elif w.display and hasattr(w, "_refresh"):
                w._refresh()


def main():
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    parser.add_argument("--api", default="http://127.0.0.1:9090", help="API server URL")
    args = parser.parse_args()

    global API_BASE
    API_BASE = args.api.rstrip("/")
    os.environ.setdefault("MEMORY_OS_API", API_BASE)

    app = MemoryOSTUI(args.vault)
    app.run()


if __name__ == "__main__":
    main()
