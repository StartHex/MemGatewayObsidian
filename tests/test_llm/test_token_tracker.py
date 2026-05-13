from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from memory_os.llm.token_tracker import TokenRecord, TokenTracker


@pytest.fixture
def tracker(tmp_path):
    return TokenTracker(tmp_path)


class TestTokenTracker:
    def test_log_writes_jsonl(self, tracker):
        """日志写入 jsonl 文件"""
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:00:00",
            agent_name="review",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
        ))
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:05:00",
            agent_name="review",
            model="claude-sonnet-4-6",
            input_tokens=300,
            output_tokens=150,
        ))

        log_path = tracker._log_path
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        r = json.loads(lines[0])
        assert r["input_tokens"] == 500

    def test_daily_stats_aggregates_by_model(self, tracker):
        """daily_stats 按模型聚合"""
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:00:00",
            agent_name="review",
            model="claude-sonnet-4-6",
            input_tokens=400,
            output_tokens=100,
        ))
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:05:00",
            agent_name="consolidation",
            model="qwen2.5:14b",
            input_tokens=600,
            output_tokens=300,
        ))

        stats = tracker.daily_stats("2026-05-13")
        assert stats["total_input"] == 1000
        assert stats["total_output"] == 400
        assert "claude-sonnet-4-6" in stats["models"]
        assert "qwen2.5:14b" in stats["models"]
        assert stats["models"]["claude-sonnet-4-6"]["input_tokens"] == 400
        assert stats["models"]["qwen2.5:14b"]["output_tokens"] == 300

    def test_daily_stats_empty_day_returns_zero(self, tracker):
        """空日统计返回全 0"""
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:00:00",
            agent_name="review",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
        ))

        stats = tracker.daily_stats("2026-05-12")
        assert stats["total_input"] == 0
        assert stats["total_output"] == 0
        assert stats["models"] == {}

    def test_daily_total_returns_summary(self, tracker):
        """daily_total 返回简洁汇总"""
        tracker.log(TokenRecord(
            timestamp="2026-05-13T09:00:00",
            agent_name="review",
            model="claude-opus-4-7",
            input_tokens=800,
            output_tokens=400,
        ))

        total = tracker.daily_total("2026-05-13")
        assert total["total_input"] == 800
        assert total["total_output"] == 400
        assert "claude-opus-4-7" in total["by_model"]
