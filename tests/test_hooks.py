"""Tests for hook scripts: session_start, stop, precompact, posttool."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest


def _load_hook_module(name: str):
    """Load a hook script as a Python module for testing."""
    hook_path = Path(__file__).parent.parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── SessionStart Hook ─────────────────────────────────────────────

class TestSessionStartHook:
    def test_prints_hot_content(self, monkeypatch, test_vault_path):
        """SessionStart hook 输出 hot.md 内容。"""
        # Pre-create hot.md
        hot_dir = test_vault_path / "_meta"
        hot_dir.mkdir(parents=True, exist_ok=True)
        (hot_dir / "hot.md").write_text("# Hot Context\n## Active Memories (3)\n- [[mem-1|Test]] (strength: 80)", encoding="utf-8")

        mod = _load_hook_module("session_start_hook")

        # Mock _api to return pre-created content and empty alerts
        calls = []
        def mock_api(method, path):
            calls.append({"method": method, "path": path})
            if "alerts" in path:
                return {"level": "OK", "content": "", "file_exists": False}
            return {"content": "# Hot Context\n## Active Memories (3)\n- [[mem-1|Test]] (strength: 80)", "generated": False}
        monkeypatch.setattr(mod, "_api", mock_api)

        # Capture stdout
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        mod.main()
        output = buf.getvalue()

        assert "MEMORY OS CONTEXT" in output
        assert "Active Memories" in output
        assert calls[0]["path"] == "/api/v1/system/hot"
        assert calls[1]["path"] == "/api/v1/system/alerts"

    def test_handles_empty_vault(self, monkeypatch):
        """空 vault 时不崩溃。"""
        mod = _load_hook_module("session_start_hook")

        def mock_api(method, path):
            return None

        monkeypatch.setattr(mod, "_api", mock_api)
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        mod.main()
        output = buf.getvalue()
        assert "MEMORY OS CONTEXT" in output
        assert "No memories indexed" in output or "memory-vault" in output


# ── Stop Hook ────────────────────────────────────────────────────

class TestStopHook:
    def test_updates_hot_and_prints_summary(self, monkeypatch, test_vault_path):
        """Stop hook 调用 update-hot + 打印统计。"""
        mod = _load_hook_module("stop_hook")

        api_calls = []
        def mock_api(method, path, body=None):
            api_calls.append((method, path, body))
            if "stats" in path:
                return {"active": 15, "fading": 3, "total": 42, "inbox_pending": 5}
            elif "hot" in path:
                return {"content": "# Hot Context\n...", "updated": True}
            return None

        monkeypatch.setattr(mod, "_api", mock_api)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        mod.main()

        # Should have called both endpoints
        methods_paths = [(m, p) for m, p, _ in api_calls]
        assert ("POST", "/api/v1/system/hot/update") in methods_paths
        assert ("GET", "/api/v1/system/stats") in methods_paths


# ── PreCompact Hook ──────────────────────────────────────────────

class TestPreCompactHook:
    def test_saves_transcript(self, monkeypatch, test_vault_path):
        """PreCompact hook 保存转录到 API。"""
        mod = _load_hook_module("pre_compact_hook")

        api_calls = []
        def mock_api(method, path, body):
            api_calls.append((method, path, body))
            return {"saved": True, "file": "_agent-logs/session-test-20260513T120000.md"}

        monkeypatch.setattr(mod, "_api", mock_api)
        hook_data = json.dumps({"message_count": 10, "summary": "测试对话摘要"})
        monkeypatch.setattr(sys, "stdin", io.StringIO(hook_data))
        mod.main()

        assert len(api_calls) == 1
        method, path, body = api_calls[0]
        assert method == "POST"
        assert path == "/api/v1/system/transcript/save"
        assert body["metadata"]["message_count"] == 10

    def test_skips_empty_stdin(self, monkeypatch):
        """空 stdin 时跳过不崩溃。"""
        mod = _load_hook_module("pre_compact_hook")
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        # Should not raise
        mod.main()


# ── PostToolUse Hook ─────────────────────────────────────────────

class TestPostToolUseHook:
    def test_validates_md_files(self, monkeypatch, test_vault_path):
        """PostToolUse 验证写入的 .md 文件。"""
        monkeypatch.setenv("MEMORY_OS_VAULT", str(test_vault_path))
        mod = _load_hook_module("post_tool_hook")

        # Create a test .md file in vault
        sem_dir = test_vault_path / "_memory" / "semantic"
        sem_dir.mkdir(parents=True, exist_ok=True)
        import frontmatter as fm
        post = fm.Post("测试内容。", id="mem-sem-test", type="semantic", status="active", importance=70)
        fm.dump(post, str(sem_dir / "mem-sem-test.md"))

        api_calls = []
        def mock_api(method, path, body=None):
            api_calls.append((method, path, body))
            return {"valid": True, "issues": [], "fields_ok": True, "links_ok": True}

        monkeypatch.setattr(mod, "_api", mock_api)

        # Construct hook data for a Write tool call
        hook_data = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": str(sem_dir / "mem-sem-test.md")},
        })
        monkeypatch.setattr(mod, "VAULT", str(test_vault_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(hook_data))
        mod.main()

        # Should have called validate
        assert len(api_calls) >= 1

    def test_skips_non_md_files(self, monkeypatch, test_vault_path):
        """非 .md 文件跳过验证。"""
        monkeypatch.setenv("MEMORY_OS_VAULT", str(test_vault_path))
        mod = _load_hook_module("post_tool_hook")

        api_calls = []
        def mock_api(method, path, body=None):
            api_calls.append((method, path, body))
            return {}

        monkeypatch.setattr(mod, "_api", mock_api)

        # Write a non-.md file
        hook_data = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": str(test_vault_path / "test.txt")},
        })
        monkeypatch.setattr(sys, "stdin", io.StringIO(hook_data))
        mod.main()

        # Should NOT have called validate (no .md file written in vault)
        assert len(api_calls) == 0
