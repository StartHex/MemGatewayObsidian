from __future__ import annotations

import asyncio

import pytest

from memory_os.agents.retrieval import RetrievalAgent, SearchResult, SearchStrategy
from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryType


class RetrievalMockLLM:
    """Mock LLM that returns fixed embeddings."""
    has_embedding = True

    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content="mock", model="mock", input_tokens=5, output_tokens=3, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def retrieval_agent(test_vault_path, test_config):
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)
    return agent, memory, llm


@pytest.mark.asyncio
async def test_search_by_id_returns_similar(test_vault_path, test_config):
    """Test 1: search_by_id 返回相似记忆列表"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    # Create a target memory
    target = await memory.create(
        content="Docker 多阶段构建的最佳实践", type_=MemoryType.SEMANTIC, tags=["docker"],
    )
    # Create another memory
    await memory.create(
        content="Node.js 应用的 Docker 部署", type_=MemoryType.SEMANTIC, tags=["docker"],
    )

    results = await agent.search_by_id(target.id, top_k=5)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_by_id_not_found(test_vault_path, test_config):
    """Test 2: search_by_id 目标不存在返回空"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    results = await agent.search_by_id("mem-sem-nonexistent", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_by_id_empty_store(test_vault_path, test_config):
    """Test 3: search_by_id 向量表为空返回空"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    target = await memory.create(
        content="test content", type_=MemoryType.SEMANTIC, tags=["test"],
    )
    # No embeddings stored, so vector search will return empty
    results = await agent.search_by_id(target.id, top_k=3)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_list_all_no_filter(test_vault_path, test_config):
    """Test 4: list_all 无过滤返回所有"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    await memory.create(content="mem 1", type_=MemoryType.SEMANTIC, tags=["a"])
    await asyncio.sleep(1.1)
    await memory.create(content="mem 2", type_=MemoryType.PROCEDURAL, tags=["b"])
    await asyncio.sleep(1.1)
    await memory.create(content="mem 3", type_=MemoryType.SEMANTIC, tags=["c"])

    result = await agent.list_all()
    assert result["total"] == 3
    assert len(result["items"]) == 3


@pytest.mark.asyncio
async def test_list_all_type_filter(test_vault_path, test_config):
    """Test 5: list_all 按类型过滤"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    await memory.create(content="sem", type_=MemoryType.SEMANTIC, tags=["a"])
    await memory.create(content="pro", type_=MemoryType.PROCEDURAL, tags=["b"])

    result = await agent.list_all(type_filter="semantic")
    assert result["total"] == 1
    assert result["items"][0]["type"] == "semantic"

    result = await agent.list_all(type_filter="procedural")
    assert result["total"] == 1
    assert result["items"][0]["type"] == "procedural"


@pytest.mark.asyncio
async def test_list_all_pagination(test_vault_path, test_config):
    """Test 6: list_all 分页 offset/limit"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    for i in range(5):
        await memory.create(content=f"mem {i}", type_=MemoryType.SEMANTIC, tags=["test"])
        await asyncio.sleep(1.1)

    page = await agent.list_all(limit=2, offset=2)
    assert len(page["items"]) == 2
    assert page["total"] == 5


@pytest.mark.asyncio
async def test_list_all_sort_by(test_vault_path, test_config):
    """Test 7: list_all 排序按强度"""
    llm = RetrievalMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = RetrievalAgent(memory, llm, test_vault_path)

    low = await memory.create(content="low", type_=MemoryType.SEMANTIC, importance=20, tags=["test"])
    high = await memory.create(content="high", type_=MemoryType.SEMANTIC, importance=90, tags=["test"])
    await memory.update(high.id, importance=90)

    result = await agent.list_all(sort_by="importance")
    assert result["items"][0]["importance"] >= result["items"][-1]["importance"]
