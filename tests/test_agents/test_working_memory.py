from __future__ import annotations

import pytest

from memory_os.agents.working_memory import (
    EvictionResult,
    SlotOperation,
    WorkingMemoryManager,
    WorkingMemorySlot,
)
from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryType


class WMMockLLM:
    """Mock LLM that returns reasoning chain detected."""

    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content='{"is_reasoning": true, "title": "Docker 部署分析", '
                   '"steps": ["分析需求", "对比方案", "选择多阶段构建"], '
                   '"conclusion": "推荐使用多阶段构建缩减镜像体积"}',
            model="mock", input_tokens=20, output_tokens=10, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


class WMMockLLMNoReasoning:
    """Mock LLM that returns no reasoning chain."""

    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content='{"is_reasoning": false}',
            model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def wm_agent(test_vault_path, test_config):
    llm = WMMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)
    return wm, memory, test_vault_path


@pytest.mark.asyncio
async def test_promote_writes_operation_log(test_vault_path, test_config):
    """promote 写入操作日志"""
    llm = WMMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)

    memory_id = "mem-test-001"
    slot_id = await wm.promote_to_slot(memory_id, "test slot")

    ops_path = wm._ops_path(slot_id)
    assert ops_path.exists()
    ops = wm._read_ops(slot_id)
    assert len(ops) == 1
    assert ops[0].op_type == "promote"


@pytest.mark.asyncio
async def test_update_slot_logs_operation(test_vault_path, test_config):
    """update_slot 更新内容并记录操作"""
    llm = WMMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)

    memory_id = "mem-test-002"
    slot_id = await wm.promote_to_slot(memory_id, "analysis")

    ok = await wm.update_slot(slot_id, "# 新分析\n\n分析问题→拆解→得出结论")
    assert ok

    ops = wm._read_ops(slot_id)
    assert len(ops) == 2
    assert ops[1].op_type == "update"


@pytest.mark.asyncio
async def test_conclude_detects_reasoning_and_saves_trace(test_vault_path, test_config):
    """conclude 检测推理链并保存 trace"""
    llm = WMMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)

    memory_id = "mem-test-003"
    slot_id = await wm.promote_to_slot(memory_id, "problem analysis")
    await wm.update_slot(slot_id, "# 分析\n\n步骤1: 分析 → 步骤2: 对比 → 步骤3: 结论")

    trace = await wm.conclude_slot(slot_id)
    assert trace is not None
    assert "Docker" in trace.title
    assert len(trace.steps) == 3

    # check trace file exists
    trace_dir = test_vault_path / "_memory" / "procedural"
    trace_files = list(trace_dir.glob("trace-*.md"))
    assert len(trace_files) == 1


@pytest.mark.asyncio
async def test_conclude_no_reasoning_no_trace(test_vault_path, test_config):
    """无推理链时 conclude 不保存 trace"""
    llm = WMMockLLMNoReasoning()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)

    memory_id = "mem-test-004"
    slot_id = await wm.promote_to_slot(memory_id, "simple note")
    await wm.update_slot(slot_id, "just a note with no reasoning")

    trace = await wm.conclude_slot(slot_id)
    assert trace is None

    trace_dir = test_vault_path / "_memory" / "procedural"
    trace_files = list(trace_dir.glob("trace-*.md"))
    assert len(trace_files) == 0


@pytest.mark.asyncio
async def test_slot_operation_log_multi_step(test_vault_path, test_config):
    """操作日志多步记录完整"""
    llm = WMMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    wm = WorkingMemoryManager(memory, test_config, test_vault_path, llm)

    memory_id = "mem-test-005"
    slot_id = await wm.promote_to_slot(memory_id, "multi-step")
    await wm.update_slot(slot_id, "step 1 content")
    await wm.update_slot(slot_id, "step 2 content")

    ops = wm._read_ops(slot_id)
    assert len(ops) == 3
    assert ops[0].op_type == "promote"
    assert ops[1].op_type == "update"
    assert ops[2].op_type == "update"
