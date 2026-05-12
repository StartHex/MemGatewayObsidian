from __future__ import annotations

import pytest

from memory_os.agents.consolidation import ConsolidationAgent
from memory_os.llm.models import UnifiedChatRequest, UnifiedChatResponse
from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryNode, MemoryStatus, MemoryType


class ConsolidationMockLLM:
    """Mock LLM that returns different responses based on prompt content."""

    def __init__(self):
        self.calls: list[dict] = []
        self.last_system = ""
        self.last_prompt = ""

    async def chat(self, request: UnifiedChatRequest, agent_name=None) -> UnifiedChatResponse:
        self.last_system = request.system
        self.last_prompt = request.messages[-1]["content"] if request.messages else ""
        self.calls.append({"system": request.system, "prompt": self.last_prompt})
        content = self.last_prompt

        if "摘要以下内容" in content or "请提炼核心结论" in content:
            return UnifiedChatResponse(
                content="提取的核心结论：这是测试摘要内容。\n\n详细说明部分。",
                model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
            )
        elif "是否包含步骤流程" in content:
            return UnifiedChatResponse(
                content='{"steps": true, "title": "测试步骤", "content": "1. 第一步\\n2. 第二步\\n3. 第三步"}',
                model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
            )
        return UnifiedChatResponse(
            content="默认响应",
            model="mock", input_tokens=5, output_tokens=3, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


class ConsolidationMockLLMNoProcedural:
    """Mock LLM that never triggers procedural creation."""

    def __init__(self):
        self.calls: list[dict] = []

    async def chat(self, request: UnifiedChatRequest, agent_name=None) -> UnifiedChatResponse:
        content = request.messages[-1]["content"] if request.messages else ""
        self.calls.append({"system": request.system, "prompt": content})

        if "摘要以下内容" in content or "请提炼核心结论" in content:
            return UnifiedChatResponse(
                content="提取的核心结论：这是测试摘要内容。\n\n详细说明部分。",
                model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
            )
        elif "是否包含步骤流程" in content:
            return UnifiedChatResponse(
                content='{"steps": false}',
                model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
            )
        return UnifiedChatResponse(
            content="默认响应",
            model="mock", input_tokens=5, output_tokens=3, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def consolidation_agent(test_vault_path, test_config):
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    return agent, memory, llm


@pytest.mark.asyncio
async def test_process_one_without_output(test_vault_path, test_config):
    """Test 1: 纯 input 向后兼容 — 使用 _summarize 不走 pair 路径"""
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)

    # Create a raw input node (no raw_output)
    raw_node = await memory.create(
        content="用户问了一个关于 LanceDB 配置的问题",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        importance=60.0,
    )

    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    stats = await agent._process_one(raw_node)

    assert stats.summaries_generated == 1
    assert "摘要以下内容" in llm.last_prompt
    assert "请提炼核心结论" not in llm.last_prompt


@pytest.mark.asyncio
async def test_process_one_with_output(test_vault_path, test_config):
    """Test 2: input+output 走 pair 路径"""
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)

    raw_node = await memory.create(
        content="LanceDB 怎么配置 dim？",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        importance=60.0,
        raw_output="需要跟 embedding model 一致，nomic-embed-text 用 768",
    )

    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    stats = await agent._process_one(raw_node)

    assert stats.summaries_generated == 1
    # Verify pair path was taken — check calls for summarize_pair prompt
    assert any("请提炼核心结论" in c["prompt"] for c in llm.calls), (
        "Expected summarize_pair prompt in LLM calls"
    )
    # Verify procedural detection was also called (confirms has_output branch)
    assert any("是否包含步骤流程" in c["prompt"] for c in llm.calls), (
        "Expected procedural detection prompt in LLM calls"
    )

    # Verify semantic node was created
    nodes = await memory.list_by_type(MemoryType.SEMANTIC)
    assert len(nodes) == 1
    assert nodes[0].raw_input_ref is not None


@pytest.mark.asyncio
async def test_procedural_created_when_steps(consolidation_agent):
    """Test 3: procedural 检测触发 — LLM 返回 steps: true"""
    agent, memory, llm = consolidation_agent

    raw_node = await memory.create(
        content="怎么用 uv 安装依赖？",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        importance=50.0,
        raw_output="运行 uv sync 即可",
    )

    # Run full process to trigger procedural creation
    stats = await agent._process_one(raw_node)
    assert stats.summaries_generated == 1

    # Check procedural node was created
    pro_nodes = await memory.list_by_type(MemoryType.PROCEDURAL)
    assert len(pro_nodes) == 1, f"Expected 1 procedural node, got {len(pro_nodes)}"
    assert pro_nodes[0].type == MemoryType.PROCEDURAL
    assert "测试步骤" in (pro_nodes[0].title or "")


@pytest.mark.asyncio
async def test_procedural_not_created_when_no_steps(test_vault_path, test_config):
    """Test 4: procedural 不触发 — LLM 返回 steps: false"""
    llm = ConsolidationMockLLMNoProcedural()
    memory = MemoryService(test_vault_path, test_config)

    raw_node = await memory.create(
        content="这是关于一个概念的简单解释",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        importance=30.0,
        raw_output="这个概念是这样的...",
    )

    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    stats = await agent._process_one(raw_node)
    assert stats.summaries_generated == 1

    pro_nodes = await memory.list_by_type(MemoryType.PROCEDURAL)
    assert len(pro_nodes) == 0


@pytest.mark.asyncio
async def test_episodic_log_rich_with_output(test_vault_path, test_config):
    """Test 5: 丰富 episodic log 包含 Q: 和 A: 片段"""
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)

    raw_node = await memory.create(
        content="如何配置 embedding？",
        type_=MemoryType.RAW_INPUT,
        tags=["config", "embedding"],
        importance=50.0,
        raw_output="设置 dimension: 768",
    )

    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    await agent._process_one(raw_node)

    # Check episodic log file exists and contains Q/A
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    epi_path = test_vault_path / "_memory" / "episodic" / f"{today}.md"
    assert epi_path.exists()

    content = epi_path.read_text(encoding="utf-8")
    assert "Q:" in content
    assert "A:" in content
    assert "如何配置" in content


@pytest.mark.asyncio
async def test_episodic_log_without_output(test_vault_path, test_config):
    """Test 5b: 纯 input 时 episodic log 不包含 Q/A"""
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)

    raw_node = await memory.create(
        content="纯输入测试",
        type_=MemoryType.RAW_INPUT,
        tags=["test"],
        importance=30.0,
    )

    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)
    await agent._process_one(raw_node)

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    epi_path = test_vault_path / "_memory" / "episodic" / f"{today}.md"
    assert epi_path.exists()

    content = epi_path.read_text(encoding="utf-8")
    assert "Q:" not in content
    assert "A:" not in content


@pytest.mark.asyncio
async def test_raw_output_serialization(test_vault_path):
    """Test 6: MemoryNode raw_output 序列化轮转"""
    from memory_os.vault.frontmatter import parse_memory, write_memory

    node = MemoryNode(
        id="mem-raw-test-output-001",
        type=MemoryType.RAW_INPUT,
        status=MemoryStatus.RAW,
        content="测试问题",
        raw_output="测试回答",
        tags=["test"],
    )
    file_path = test_vault_path / "_inbox" / "mem-raw-test-output-001.md"
    await write_memory(file_path, node)

    parsed = await parse_memory(file_path)
    assert parsed.raw_output == "测试回答"
    assert parsed.content == "测试问题"


@pytest.mark.asyncio
async def test_summarize_pair_method(test_vault_path, test_config):
    """Test _summarize_pair returns summary based on input+output"""
    llm = ConsolidationMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ConsolidationAgent(memory, llm, test_vault_path, test_config)

    result = await agent._summarize_pair("问题内容", "回答内容")
    assert result is not None
    assert len(llm.last_prompt) > 0
    assert "问题内容" in llm.last_prompt or "回答内容" in llm.last_prompt
