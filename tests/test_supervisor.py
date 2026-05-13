"""Tests for SystemSupervisor proactive monitoring agent."""
from __future__ import annotations

import os
import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from memory_os.agents.supervisor import SystemSupervisor
from memory_os.memory.service import MemoryService


def _set_file_age(filepath: Path, hours_ago: float):
    """Set file mtime to simulate an old file."""
    past = time.time() - (hours_ago * 3600)
    os.utime(filepath, (past, past))


@pytest.mark.asyncio
class TestSupervisor:
    async def test_empty_vault_returns_ok(self, test_vault_path, test_config):
        """空 vault 返回 OK 状态。"""
        memory = MemoryService(test_vault_path, test_config)
        supervisor = SystemSupervisor(memory, test_vault_path, test_config)
        report = await supervisor._inspect()
        assert report.level == "OK"
        assert report.alerts == []

    async def test_stuck_inbox_triggers_critical(self, test_vault_path, test_config):
        """长时间未处理的 inbox 触发 CRITICAL。"""
        from memory_os.vault.frontmatter import write_memory
        from memory_os.vault.models import MemoryNode, MemoryType, MemoryStatus

        node = MemoryNode(
            id="mem-raw-test-old",
            content="test content",
            type=MemoryType.RAW_INPUT,
            status=MemoryStatus.RAW,
        )
        filepath = test_vault_path / "_inbox" / "mem-raw-test-old.md"
        await write_memory(filepath, node)
        _set_file_age(filepath, hours_ago=5)

        memory = MemoryService(test_vault_path, test_config)
        supervisor = SystemSupervisor(memory, test_vault_path, test_config)
        report = await supervisor._inspect()
        assert report.inbox_stuck == 1
        assert report.inbox_stuck_hours > 4
        assert report.level in ("CRITICAL", "ACTION")
        assert len(report.alerts) > 0

    async def test_writes_alerts_file(self, test_vault_path, test_config):
        """巡检结果写入 _meta/alerts.md。"""
        from memory_os.vault.frontmatter import write_memory
        from memory_os.vault.models import MemoryNode, MemoryType, MemoryStatus

        node = MemoryNode(
            id="mem-raw-test-old",
            content="test content",
            type=MemoryType.RAW_INPUT,
            status=MemoryStatus.RAW,
        )
        filepath = test_vault_path / "_inbox" / "mem-raw-test-old.md"
        await write_memory(filepath, node)
        _set_file_age(filepath, hours_ago=5)

        memory = MemoryService(test_vault_path, test_config)
        supervisor = SystemSupervisor(memory, test_vault_path, test_config)
        await supervisor.run()

        alerts_path = test_vault_path / "_meta" / "alerts.md"
        assert alerts_path.exists()
        content = alerts_path.read_text()
        assert "CRITICAL" in content or "ACTION" in content

    async def test_just_created_inbox_not_critical(self, test_vault_path, test_config):
        """刚刚创建的 raw item 不触发 CRITICAL。"""
        from memory_os.vault.frontmatter import write_memory
        from memory_os.vault.models import MemoryNode, MemoryType, MemoryStatus

        node = MemoryNode(
            id="mem-raw-test-new",
            content="test content",
            type=MemoryType.RAW_INPUT,
            status=MemoryStatus.RAW,
        )
        await write_memory(test_vault_path / "_inbox" / "mem-raw-test-new.md", node)

        memory = MemoryService(test_vault_path, test_config)
        supervisor = SystemSupervisor(memory, test_vault_path, test_config)
        report = await supervisor._inspect()
        assert report.inbox_stuck == 1
        assert report.level != "CRITICAL"
