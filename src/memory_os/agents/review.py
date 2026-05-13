from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel

from memory_os.config.models import SystemConfig
from memory_os.llm.models import UnifiedChatRequest
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import list_directory
from memory_os.vault.frontmatter import parse_memory

logger = structlog.get_logger(__name__)


class ReviewReport(BaseModel):
    generated_at: str = ""
    target_date: str = ""
    activities_count: int = 0
    new_memories: int = 0
    token_usage: dict = {}
    topics: list[str] = []
    key_decisions: list[str] = []
    knowledge_gaps: list[str] = []
    connections: list[str] = []
    actions: list[str] = []
    narrative: str = ""


class ReviewAgent:
    def __init__(self, memory: MemoryService, llm: LLMService, vault_path, config: SystemConfig):
        self.memory = memory
        self.llm = llm
        self.vault_path = vault_path
        self.config = config
        self.token_tracker = getattr(llm, 'token_tracker', None)

    async def run(self, target_date: str | None = None) -> ReviewReport:
        if target_date is None:
            target = datetime.now(timezone.utc) - timedelta(days=1)
        else:
            target = datetime.fromisoformat(target_date)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)

        date_str = target.strftime("%Y-%m-%d")
        report = ReviewReport(generated_at=datetime.now(timezone.utc).isoformat(), target_date=date_str)

        epi_path = self.vault_path / "_memory" / "episodic" / f"{date_str}.md"
        episodic_log = ""
        if epi_path.exists():
            episodic_log = epi_path.read_text(encoding="utf-8")
            report.activities_count = episodic_log.count("- [")

        new_memories = await self._get_memories_from_date(date_str)
        report.new_memories = len(new_memories)

        if self.token_tracker:
            report.token_usage = self.token_tracker.daily_total(date_str)

        if episodic_log or new_memories:
            report = await self._generate_report(report, episodic_log, new_memories)

        await self._save_report(report, date_str)
        return report

    async def _get_memories_from_date(self, date_str: str) -> list[dict]:
        mems = []
        for sub in ("semantic", "episodic", "procedural"):
            d = self.vault_path / "_memory" / sub
            if not d.exists():
                continue
            for f in await list_directory(d, "*.md"):
                if date_str in f.stem and f.stem.startswith("mem-"):
                    try:
                        n = await parse_memory(f)
                        mems.append({
                            "id": n.id,
                            "title": n.title or n.content.split("\n")[0].replace("# ", "")[:80],
                            "content_snippet": n.content[:300],
                            "tags": n.tags,
                            "importance": n.importance,
                        })
                    except Exception:
                        continue
        return mems

    async def _generate_report(
        self, report: ReviewReport, episodic_log: str, new_memories: list[dict],
    ) -> ReviewReport:
        stats_summary = await self._get_stats_summary()

        mems_text = "\n".join(
            f"- [{m['tags'][0] if m['tags'] else 'memory'}] {m['title']}"
            for m in new_memories[:30]
        ) if new_memories else "（无新记忆）"

        token_text = ""
        if report.token_usage:
            tu = report.token_usage
            token_text = f"\n## 昨日 Token 消耗\n总计: {tu['total_input']} 输入 + {tu['total_output']} 输出 = {tu['total_input'] + tu['total_output']} tokens\n"
            for model, stats in tu.get("by_model", {}).items():
                token_text += f"- {model}: {stats['input_tokens']} 输入 + {stats['output_tokens']} 输出\n"

        prompt = f"""## 昨日时间线
{episodic_log[:3000] or '（无活动记录）'}

## 昨日创建的记忆
{mems_text}

## 当前记忆库状态
{stats_summary}
{token_text}
请生成以下内容（JSON 格式，不要 Markdown）：
{{
  "topics": ["话题1", "话题2"],
  "key_decisions": ["重要结论1", "重要结论2"],
  "knowledge_gaps": ["未解决的问题1"],
  "connections": ["连接建议1"],
  "actions": ["行动建议1"],
  "narrative": "<200字中文复盘叙事>"
}}"""

        try:
            resp = await self.llm.chat(
                UnifiedChatRequest(
                    system="你是记忆复盘助手。回顾昨日记忆活动，识别模式、发现缺口、提出行动建议。仅返回 JSON。",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                    response_format="json_object",
                ),
                agent_name="review",
            )
            import json
            data = json.loads(resp.content)
            report.topics = data.get("topics", [])
            report.key_decisions = data.get("key_decisions", [])
            report.knowledge_gaps = data.get("knowledge_gaps", [])
            report.connections = data.get("connections", [])
            report.actions = data.get("actions", [])
            report.narrative = data.get("narrative", "")
        except Exception as e:
            logger.warning("review_llm_failed", error=str(e))
            report.narrative = "LLM 复盘生成失败，请检查 API 配置。"

        return report

    async def _get_stats_summary(self) -> str:
        dirs = [
            self.vault_path / "_memory" / "semantic",
            self.vault_path / "_memory" / "episodic",
            self.vault_path / "_memory" / "procedural",
        ]
        total = 0
        active = 0
        for d in dirs:
            for f in await list_directory(d, "*.md"):
                total += 1
                try:
                    n = await parse_memory(f)
                    if n.status.value == "active":
                        active += 1
                except Exception:
                    continue
        inbox_files = await list_directory(self.vault_path / "_inbox", "*.md")
        return f"总计: {total} 条记忆, 活跃: {active}, 待处理: {len(inbox_files)}"

    async def _save_report(self, report: ReviewReport, date_str: str):
        report_dir = self.vault_path / "_memory" / "episodic"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"review-{date_str}.md"

        lines = [
            f"# 记忆复盘 — {date_str}",
            f"生成时间: {report.generated_at}",
            "",
            "## 统计",
            f"- 时间线活动: {report.activities_count} 条",
            f"- 新创建记忆: {report.new_memories} 条",
            "",
        ]

        if report.topics:
            lines.append("## 话题总结")
            for t in report.topics:
                lines.append(f"- {t}")
            lines.append("")

        if report.key_decisions:
            lines.append("## 关键决策和结论")
            for d in report.key_decisions:
                lines.append(f"- {d}")
            lines.append("")

        if report.knowledge_gaps:
            lines.append("## 知识缺口")
            for g in report.knowledge_gaps:
                lines.append(f"- {g}")
            lines.append("")

        if report.connections:
            lines.append("## 连接建议")
            for c in report.connections:
                lines.append(f"- {c}")
            lines.append("")

        if report.actions:
            lines.append("## 行动建议")
            for a in report.actions:
                lines.append(f"- {a}")
            lines.append("")

        if report.token_usage:
            tu = report.token_usage
            lines.append("## Token 消耗")
            lines.append(f"- 总输入: {tu['total_input']} tokens")
            lines.append(f"- 总输出: {tu['total_output']} tokens")
            lines.append(f"- 合计: {tu['total_input'] + tu['total_output']} tokens")
            for model, stats in tu.get("by_model", {}).items():
                lines.append(f"  - {model}: {stats['input_tokens']} in + {stats['output_tokens']} out")
            lines.append("")

        if report.narrative:
            lines.append("## 复盘叙事")
            lines.append(report.narrative)
            lines.append("")

        try:
            report_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info("review_report_saved", path=str(report_path))
        except Exception as e:
            logger.warning("review_report_save_failed", error=str(e))
