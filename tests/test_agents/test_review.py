from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory_os.agents.review import ReviewAgent, ReviewReport
from memory_os.memory.service import MemoryService
from memory_os.vault.models import MemoryType


class ReviewMockLLM:
    """Mock LLM for review agent tests."""

    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content='{"topics": ["Docker", "记忆系统"], "key_decisions": ["使用多阶段构建"], '
                   '"knowledge_gaps": ["K8s 部署细节"], "connections": ["关联到部署流程"], '
                   '"actions": ["补充 K8s 配置文档"], "narrative": "昨日主要讨论了 Docker 多阶段构建。"}',
            model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


class ReviewMockLLMNoActivity:
    """Mock LLM for review with no activity."""

    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content='{"topics": [], "key_decisions": [], "knowledge_gaps": [], '
                   '"connections": [], "actions": [], "narrative": "昨日无活动。"}',
            model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def review_agent(test_vault_path, test_config):
    llm = ReviewMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ReviewAgent(memory, llm, test_vault_path, test_config)
    return agent, memory, llm, test_vault_path


@pytest.mark.asyncio
async def test_review_reads_episodic_log(test_vault_path, test_config):
    """Test 8: review 读取昨日 episodic 日志"""
    llm = ReviewMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ReviewAgent(memory, llm, test_vault_path, test_config)

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    epi_dir = test_vault_path / "_memory" / "episodic"
    epi_dir.mkdir(parents=True, exist_ok=True)
    (epi_dir / f"{date_str}.md").write_text(
        f"# {date_str}\n\n"
        "- [14:30] **Docker** — [[sem-001]] (from mcp)\n"
        "  - Q: Docker 多阶段构建...\n"
        "  - A: 使用 builder stage...\n",
        encoding="utf-8",
    )

    report = await agent.run()
    assert report.target_date == date_str
    assert report.activities_count >= 1
    assert report.new_memories == 0


@pytest.mark.asyncio
async def test_review_no_activity(test_vault_path, test_config):
    """Test 9: review 无昨日活动时"""
    llm = ReviewMockLLMNoActivity()
    memory = MemoryService(test_vault_path, test_config)
    agent = ReviewAgent(memory, llm, test_vault_path, test_config)

    # No episodic log for yesterday
    report = await agent.run()
    assert report.activities_count == 0
    assert report.new_memories == 0


@pytest.mark.asyncio
async def test_review_saves_report(test_vault_path, test_config):
    """Test 10: review 生成报告保存到正确路径"""
    llm = ReviewMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ReviewAgent(memory, llm, test_vault_path, test_config)

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    epi_dir = test_vault_path / "_memory" / "episodic"
    epi_dir.mkdir(parents=True, exist_ok=True)
    (epi_dir / f"{date_str}.md").write_text(f"# {date_str}\n\n- [14:00] **test** — [[test]]\n", encoding="utf-8")

    report = await agent.run()
    assert len(report.topics) >= 1
    assert len(report.key_decisions) >= 1

    report_path = epi_dir / f"review-{date_str}.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Docker" in content


@pytest.mark.asyncio
async def test_review_report_model():
    """Test 11: ReviewReport model 字段"""
    report = ReviewReport(
        generated_at="2026-05-13T09:00:00",
        target_date="2026-05-12",
        activities_count=5,
        new_memories=3,
        topics=["AI", "DevOps"],
        key_decisions=["使用 Docker 多阶段构建"],
        knowledge_gaps=["K8s 细节"],
        connections=["关联到 CI/CD"],
        actions=["补充文档"],
        narrative="复盘叙事内容",
    )
    assert report.activities_count == 5
    assert len(report.topics) == 2
    assert len(report.key_decisions) == 1
    assert report.target_date == "2026-05-12"


@pytest.mark.asyncio
async def test_review_specific_date(test_vault_path, test_config):
    """Test 12: review 手动指定日期"""
    llm = ReviewMockLLM()
    memory = MemoryService(test_vault_path, test_config)
    agent = ReviewAgent(memory, llm, test_vault_path, test_config)

    target = "2026-05-10"
    epi_dir = test_vault_path / "_memory" / "episodic"
    epi_dir.mkdir(parents=True, exist_ok=True)
    (epi_dir / f"{target}.md").write_text(f"# {target}\n\n- [10:00] **test** — [[t]]\n", encoding="utf-8")

    report = await agent.run(target_date=target)
    assert report.target_date == target
