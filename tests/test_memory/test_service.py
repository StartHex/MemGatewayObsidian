from __future__ import annotations

import pytest

from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryType


@pytest.mark.asyncio
async def test_create_and_get(test_vault_path, test_config):
    service = MemoryService(test_vault_path, test_config)
    node = await service.create(
        content="Test memory content",
        type_=MemoryType.SEMANTIC,
        tags=["test"],
    )
    assert node.id.startswith("mem-sem-")
    assert node.tags == ["test"]

    retrieved = await service.get(node.id)
    assert retrieved.content == "Test memory content"
    assert retrieved.retrieval_count == 1


@pytest.mark.asyncio
async def test_create_with_raw_output(test_vault_path, test_config):
    """Test 7: create 传 raw_output 字段"""
    service = MemoryService(test_vault_path, test_config)
    node = await service.create(
        content="测试问题",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        raw_output="测试回答",
    )
    assert node.raw_output == "测试回答"
    assert node.content == "测试问题"

    # Verify persistence
    retrieved = await service.get(node.id)
    assert retrieved.raw_output == "测试回答"
