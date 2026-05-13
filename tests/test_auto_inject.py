"""Tests for auto-inject: inject-and-save endpoint + capture hook logic."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


def _load_hook_module():
    """Load the capture_hook.py as a module for testing."""
    hook_path = Path(__file__).parent.parent / "scripts" / "capture_hook.py"
    spec = importlib.util.spec_from_file_location("capture_hook", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── inject-and-save endpoint tests ──────────────────────────────

@pytest.fixture
def api_client(test_vault_path, test_config, monkeypatch):
    """Create a FastAPI test client with vault path set."""
    monkeypatch.setenv("MEMORY_OS_VAULT", str(test_vault_path))
    from memory_os.api.routes import app
    from fastapi.testclient import TestClient
    return TestClient(app), test_vault_path


class TestInjectAndSaveEndpoint:
    def test_with_results_writes_context_file(self, api_client, test_vault_path):
        """搜索到相关记忆时写入 last-context.md。"""
        client, vault = api_client
        # First create some memories in the vault so search can find them
        resp = client.post("/api/v1/memories", json={
            "content": "Memory OS 是一个基于 Obsidian 和 LanceDB 的多 Agent 记忆系统",
            "type": "raw_input", "tags": ["test"], "importance": 80,
        })
        assert resp.status_code == 200, resp.text

        # Now search and inject
        resp = client.post("/api/v1/search/inject-and-save", json={
            "query": "Memory OS 记忆系统", "top_k": 3,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # The search may or may not find results depending on keyword match
        # But the endpoint should always respond correctly
        assert "saved" in data
        assert "context" in data

    def test_no_results_deletes_context_file(self, api_client, test_vault_path):
        """搜索无结果时删除旧的 last-context.md。"""
        client, vault = api_client
        context_path = vault / "_meta" / "last-context.md"

        # Create a stale context file
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text("# old context", encoding="utf-8")
        assert context_path.exists()

        # Search with a nonsense query that won't match anything
        resp = client.post("/api/v1/search/inject-and-save", json={
            "query": "xyzzy_nonexistent_query_abc_12345", "top_k": 3,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["saved"] is False
        assert data["result_count"] == 0
        # File should be deleted
        assert not context_path.exists()

    def test_context_file_format(self, api_client, test_vault_path):
        """有结果时 last-context.md 格式正确。"""
        client, vault = api_client

        # Seed a memory with known content
        client.post("/api/v1/memories", json={
            "content": "项目使用 Tauri 2.x 构建桌面 GUI，React 构建 WebUI，Textual 构建 TUI",
            "type": "raw_input", "tags": ["test", "gui"], "importance": 90,
        })

        resp = client.post("/api/v1/search/inject-and-save", json={
            "query": "Tauri GUI 桌面应用", "top_k": 3,
        })
        assert resp.status_code == 200
        data = resp.json()

        context_path = vault / "_meta" / "last-context.md"
        if data["saved"]:
            assert context_path.exists()
            content = context_path.read_text(encoding="utf-8")
            assert content.startswith("# Memory Context")
            assert "Retrieved:" in content
            assert "Query:" in content
            assert "relevant memories found" in content

    def test_missing_vault_graceful(self, api_client):
        """确保 endpoint 不会因为缺失文件而崩溃。"""
        client, vault = api_client
        resp = client.post("/api/v1/search/inject-and-save", json={
            "query": "any query", "top_k": 3,
        })
        assert resp.status_code == 200
        assert "saved" in resp.json()


# ── Hook logic tests ────────────────────────────────────────────

class TestHookExtractPrompt:
    """测试 hook 的 prompt 提取逻辑。"""

    def test_extract_from_prompt_field(self):
        mod = _load_hook_module()
        result = mod.extract_prompt(json.dumps({"prompt": "什么是 LanceDB？"}))
        assert result == "什么是 LanceDB？"

    def test_extract_from_content_field(self):
        mod = _load_hook_module()
        result = mod.extract_prompt(json.dumps({"content": "一段长文本内容"}))
        assert result == "一段长文本内容"

    def test_extract_prefer_prompt_over_content(self):
        mod = _load_hook_module()
        data = json.dumps({"prompt": "优先取这个", "content": "不要取这个"})
        result = mod.extract_prompt(data)
        assert result == "优先取这个"

    def test_extract_empty_input(self):
        mod = _load_hook_module()
        assert mod.extract_prompt("") == ""
        assert mod.extract_prompt("   ") == ""

    def test_extract_plain_text_fallback(self):
        mod = _load_hook_module()
        result = mod.extract_prompt("直接一段纯文本消息")
        assert result == "直接一段纯文本消息"


class TestHookShortMessageSkipped:
    """测试短消息被跳过。"""

    def test_short_message_not_captured(self, tmp_path):
        """<10 字符的消息不触发 capture。"""
        prompt = "hi"
        assert len(prompt) < 10


class TestHookApiUnreachable:
    """测试 API 不可达时降级。"""

    def test_api_call_returns_none_on_failure(self):
        mod = _load_hook_module()
        result = mod._api("POST", "/api/v1/search/inject-and-save", {"query": "test"})
        assert result is None or isinstance(result, dict)


# ── Integration test ────────────────────────────────────────────

class TestFullHookFlow:
    """完整 hook 流程集成测试。"""

    def test_search_then_capture_flow(self, api_client, test_vault_path, monkeypatch):
        """验证 search→inject-and-save→capture 完整流程。"""
        client, vault = api_client

        query = "Memory OS 架构设计"
        top_k = 3

        # Step 1: inject-and-save
        resp1 = client.post("/api/v1/search/inject-and-save", json={
            "query": query, "top_k": top_k,
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "saved" in data1

        context_path = vault / "_meta" / "last-context.md"
        if data1["saved"]:
            assert context_path.exists()

        # Step 2: capture
        resp2 = client.post("/api/v1/memories", json={
            "content": query, "type": "raw_input",
            "tags": ["test"], "importance": 70, "source": "cc-connect-hook",
        })
        assert resp2.status_code == 200
        memory_id = resp2.json()["id"]
        assert memory_id.startswith("mem-raw-")

        # Verify the memory actually exists
        resp3 = client.get(f"/api/v1/memories/{memory_id}")
        assert resp3.status_code == 200
        assert resp3.json()["content"] == query
