from __future__ import annotations

import pytest

from memory_os.vault.frontmatter import parse_memory, write_memory
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType


@pytest.mark.asyncio
async def test_roundtrip(test_vault_path):
    node = MemoryNode(
        id="mem-test-001",
        type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        tags=["test", "memory"],
        importance=75.0,
        content="# Hello\n\nWorld.",
    )
    file_path = test_vault_path / "_memory" / "semantic" / "mem-test-001.md"
    await write_memory(file_path, node)

    parsed = await parse_memory(file_path)
    assert parsed.id == "mem-test-001"
    assert parsed.type == MemoryType.SEMANTIC
    assert parsed.tags == ["test", "memory"]
    assert parsed.content == "# Hello\n\nWorld."
    assert parsed.status == MemoryStatus.ACTIVE


@pytest.mark.asyncio
async def test_minimal_frontmatter(test_vault_path):
    node = MemoryNode(id="mem-minimal", type=MemoryType.RAW_INPUT, content="minimal content")
    file_path = test_vault_path / "_inbox" / "mem-minimal.md"
    await write_memory(file_path, node)

    parsed = await parse_memory(file_path)
    assert parsed.id == "mem-minimal"
    assert parsed.content == "minimal content"
    assert parsed.strength == 50.0  # default


@pytest.mark.asyncio
async def test_update_fields(test_vault_path):
    from memory_os.vault.frontmatter import update_fields

    node = MemoryNode(id="mem-update", type=MemoryType.SEMANTIC, content="old", tags=["a"])
    fp = test_vault_path / "_memory" / "semantic" / "mem-update.md"
    await write_memory(fp, node)

    updated = await update_fields(fp, tags=["b", "c"], importance=90.0)
    assert updated.tags == ["b", "c"]
    assert updated.importance == 90.0
    assert updated.content == "old"  # unchanged
