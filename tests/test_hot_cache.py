"""Tests for Hot Cache: generation, API endpoints, and validation."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def hot_client(test_vault_path, test_config, monkeypatch):
    """FastAPI test client for hot cache / validation endpoints."""
    monkeypatch.setenv("MEMORY_OS_VAULT", str(test_vault_path))
    from memory_os.api.routes import app
    from fastapi.testclient import TestClient
    return TestClient(app), test_vault_path


# ── Hot Cache Generation ──────────────────────────────────────────

class TestHotGenerate:
    async def test_generate_empty_vault(self, test_vault_path):
        """空 vault 生成 minimal hot.md。"""
        from memory_os.api.hot_cache import HotCacheManager
        manager = HotCacheManager(test_vault_path)
        content = await manager.generate()
        assert "# Hot Context" in content
        assert "Active Memories" in content
        assert "No active memories yet" in content
        assert "Pending (0)" in content

    async def test_generate_with_memories(self, test_vault_path):
        """有记忆时 hot.md 含正确统计。"""
        import frontmatter as fm
        from datetime import datetime, timezone

        sem_dir = test_vault_path / "_memory" / "semantic"
        sem_dir.mkdir(parents=True, exist_ok=True)

        post = fm.Post(
            "核心记忆内容：Memory OS 架构设计完成。",
            id="mem-sem-20260513-120000000",
            type="semantic",
            status="active",
            title="Memory OS 架构",
            strength=90.0,
            importance=85.0,
            last_retrieved=datetime.now(timezone.utc).isoformat(),
        )
        fm.dump(post, str(sem_dir / "mem-sem-20260513-120000000.md"))

        from memory_os.api.hot_cache import HotCacheManager
        manager = HotCacheManager(test_vault_path)
        content = await manager.generate()
        assert "# Hot Context" in content
        assert "Memory OS 架构" in content
        assert "strength: 90" in content

    async def test_generate_with_pending(self, test_vault_path):
        """有 inbox items 时显示 pending 数。"""
        inbox = test_vault_path / "_inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "item1.md").write_text("---\nid: test-1\ntype: raw_input\n---\nTest content", encoding="utf-8")
        (inbox / "item2.md").write_text("---\nid: test-2\ntype: raw_input\n---\nTest content 2", encoding="utf-8")

        from memory_os.api.hot_cache import HotCacheManager
        manager = HotCacheManager(test_vault_path)
        content = await manager.generate()
        assert "2 inbox items" in content

    async def test_generate_with_conflicts(self, test_vault_path):
        """有冲突时显示冲突数。"""
        meta = test_vault_path / "_meta"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "cognitive-conflicts.md").write_text(
            "# Cognitive Conflicts\n## Conflict 1\n...\n## Conflict 2\n...", encoding="utf-8")

        from memory_os.api.hot_cache import HotCacheManager
        manager = HotCacheManager(test_vault_path)
        content = await manager.generate()
        assert "conflicts" in content.lower()


# ── Hot Cache API Endpoints ───────────────────────────────────────

class TestHotEndpoints:
    def test_get_hot_auto_generates(self, hot_client, test_vault_path):
        """GET /api/v1/system/hot 在无 hot.md 时自动生成。"""
        client, vault = hot_client
        hot_path = vault / "_meta" / "hot.md"
        if hot_path.exists():
            hot_path.unlink()

        resp = client.get("/api/v1/system/hot")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "content" in data
        assert data["generated"] is True
        assert "# Hot Context" in data["content"]

    def test_get_hot_returns_existing(self, hot_client, test_vault_path):
        """GET /api/v1/system/hot 返回已有 hot.md 内容。"""
        client, vault = hot_client
        hot_dir = vault / "_meta"
        hot_dir.mkdir(parents=True, exist_ok=True)
        (hot_dir / "hot.md").write_text("# Existing Hot Context\nTest content", encoding="utf-8")

        resp = client.get("/api/v1/system/hot")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["content"] == "# Existing Hot Context\nTest content"
        assert data["generated"] is False

    def test_update_hot_endpoint(self, hot_client, test_vault_path):
        """POST /api/v1/system/hot/update 重新生成 hot.md。"""
        client, vault = hot_client
        resp = client.post("/api/v1/system/hot/update")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["updated"] is True
        assert "# Hot Context" in data["content"]

    def test_transcript_save_endpoint(self, hot_client, test_vault_path):
        """POST /api/v1/system/transcript/save 保存转录。"""
        client, vault = hot_client
        resp = client.post("/api/v1/system/transcript/save", json={
            "content": "测试对话转录内容",
            "metadata": {"session_id": "test-session-1", "message_count": 42},
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["saved"] is True
        assert data["file"].startswith("_agent-logs/session-")
        log_path = vault / data["file"]
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "测试对话转录内容" in content


# ── Validation ────────────────────────────────────────────────────

class TestValidation:
    def test_validate_valid_file(self, hot_client, test_vault_path):
        """完整 frontmatter → valid=true。"""
        client, vault = hot_client
        import frontmatter as fm
        sem_dir = vault / "_memory" / "semantic"
        sem_dir.mkdir(parents=True, exist_ok=True)
        post = fm.Post("完整记忆内容。", id="mem-sem-001", type="semantic", status="active", importance=75)
        fm.dump(post, str(sem_dir / "mem-sem-001.md"))

        resp = client.post("/api/v1/system/validate", json={
            "file_path": "_memory/semantic/mem-sem-001.md",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["valid"] is True
        assert data["fields_ok"] is True

    def test_validate_missing_fields(self, hot_client, test_vault_path):
        """缺少必需字段 → issues reported。"""
        client, vault = hot_client
        sem_dir = vault / "_memory" / "semantic"
        sem_dir.mkdir(parents=True, exist_ok=True)
        import frontmatter as fm
        post = fm.Post("内容缺少 importance 和 status 字段。", id="mem-sem-002", type="semantic")
        fm.dump(post, str(sem_dir / "mem-sem-002.md"))

        resp = client.post("/api/v1/system/validate", json={
            "file_path": "_memory/semantic/mem-sem-002.md",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["valid"] is False
        assert data["fields_ok"] is False
        assert any("importance" in issue.lower() or "status" in issue.lower() for issue in data["issues"])

    def test_validate_broken_wikilinks(self, hot_client, test_vault_path):
        """死链 → issues reported。"""
        client, vault = hot_client
        sem_dir = vault / "_memory" / "semantic"
        sem_dir.mkdir(parents=True, exist_ok=True)
        import frontmatter as fm
        post = fm.Post(
            "这是一个引用 [[nonexistent-file]] 的记忆。",
            id="mem-sem-003", type="semantic", status="active", importance=60,
        )
        fm.dump(post, str(sem_dir / "mem-sem-003.md"))

        resp = client.post("/api/v1/system/validate", json={
            "file_path": "_memory/semantic/mem-sem-003.md",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["links_ok"] is False
        assert any("nonexistent" in issue.lower() for issue in data["issues"])

    def test_validate_nonexistent_file(self, hot_client):
        """不存在的文件返回 valid=false。"""
        client, vault = hot_client
        resp = client.post("/api/v1/system/validate", json={
            "file_path": "_memory/semantic/does-not-exist.md",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["valid"] is False
        assert any("not found" in issue.lower() for issue in data["issues"])
