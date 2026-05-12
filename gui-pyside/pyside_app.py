"""GUI 方案 B：PySide6 — Python 原生桌面应用。

特点:
- 纯 Python，零语言边界，直接调 Core SDK
- 系统托盘 + 菜单栏 + 原生 widget
- 适合快速原型和调试
- ~15MB 依赖（PySide6）

启动: uv run python gui-pyside/pyside_app.py --vault ~/memory-vault
依赖: pip install PySide6
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLineEdit, QListWidget,
    QMainWindow, QPushButton, QSplitter, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu,
)
from PySide6.QtGui import QIcon, QAction

from memory_os.agents.retrieval import RetrievalAgent, SearchStrategy
from memory_os.agents.sensory_gateway import SensoryGateway
from memory_os.config.loader import load_config
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService


class MemoryOSWindow(QMainWindow):
    def __init__(self, vault_path: Path):
        super().__init__()
        self.vault_path = vault_path
        self.config = load_config(vault_path)
        self.memory = MemoryService(vault_path, self.config)
        self.llm = LLMService(self.config)

        self.setWindowTitle("Mem-Gateway-Obsidian (PySide6)")
        self.resize(900, 600)
        self._setup_ui()
        self._setup_tray()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        tabs = QTabWidget()

        # ---- Search Tab ----
        search_tab = QWidget()
        search_layout = QVBoxLayout(search_tab)
        search_input = QLineEdit()
        search_input.setPlaceholderText("搜索记忆...")
        search_results = QListWidget()
        search_layout.addWidget(search_input)
        search_layout.addWidget(search_results)
        tabs.addTab(search_tab, "Search")

        # ---- Capture Tab ----
        capture_tab = QWidget()
        capture_layout = QVBoxLayout(capture_tab)
        capture_input = QTextEdit()
        capture_input.setPlaceholderText("记录想法...")
        capture_btn = QPushButton("Save")
        capture_layout.addWidget(capture_input)
        capture_layout.addWidget(capture_btn)
        tabs.addTab(capture_tab, "Capture")

        # ---- Dashboard Tab ----
        dash_tab = QWidget()
        dash_layout = QVBoxLayout(dash_tab)
        dash_text = QTextEdit()
        dash_text.setReadOnly(True)
        dash_text.setPlainText("Dashboard 加载中...")
        dash_layout.addWidget(dash_text)
        tabs.addTab(dash_tab, "Dashboard")

        layout.addWidget(tabs)

        # ---- Connect signals ----
        search_input.returnPressed.connect(
            lambda: self._on_search(search_input.text(), search_results)
        )
        capture_btn.clicked.connect(
            lambda: self._on_capture(capture_input.toPlainText(), capture_input)
        )
        QTimer.singleShot(500, lambda: self._update_dash(dash_text))

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("Memory OS")
        menu = QMenu()
        menu.addAction("Show", self.show)
        menu.addAction("Quit", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_search(self, query: str, results_widget: QListWidget):
        async def _do():
            agent = RetrievalAgent(self.memory, self.llm, self.vault_path)
            results = await agent.search(query, strategy=SearchStrategy.VECTOR)
            results_widget.clear()
            for r in results:
                results_widget.addItem(f"[{r.score:.2f}] {r.title[:60]}")
        asyncio.run(_do())

    def _on_capture(self, text: str, input_widget: QTextEdit):
        async def _do():
            gateway = SensoryGateway(self.memory, self.llm, self.vault_path)
            await gateway.ingest(text, "pyside-gui")
            input_widget.clear()
        asyncio.run(_do())

    def _update_dash(self, widget: QTextEdit):
        async def _do():
            from memory_os.agents.meta_cognition import MetaCognitionAgent
            agent = MetaCognitionAgent(self.memory, self.llm, self.config, self.vault_path)
            report = await agent.run()
            widget.setPlainText(
                f"活跃记忆: {report.active_count}\n"
                f"待处理: {report.inbox_pending}\n"
                f"孤岛: {report.orphant_count}\n"
                f"向量不一致: {report.vector_inconsistencies}\n"
                f"推荐:\n" + "\n".join(f"  - {r}" for r in report.recommendations)
            )
        asyncio.run(_do())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MemoryOSWindow(Path(args.vault))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
