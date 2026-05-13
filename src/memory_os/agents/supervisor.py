"""SystemSupervisor — 主动巡检 Agent，发现问题及时写 _meta/alerts.md。

SessionStart hook 会在新会话时注入 alerts.md，实现问题自动汇报。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel

from memory_os.config.models import SystemConfig
from memory_os.memory.service import MemoryService
from memory_os.vault.file_io import atomic_write, list_directory
from memory_os.vault.frontmatter import parse_memory
from memory_os.vault.models import MemoryStatus

logger = structlog.get_logger(__name__)

INBOX_STUCK_HOURS = 2          # inbox 未处理超过此时间视为滞留
CONSOLIDATION_GAP_HOURS = 6    # 超过此时间没巩固视为异常
ORPHAN_WARN = 5                # 孤岛数量警告线
VECTOR_INCONSISTENCY_WARN = 10 # 向量不一致警告线


class SupervisorReport(BaseModel):
    level: str = "OK"             # OK | WARNING | ACTION | CRITICAL
    inbox_stuck: int = 0          # 滞留 inbox 数量
    inbox_stuck_hours: float = 0  # 最长滞留时间
    orphans: int = 0
    vector_inconsistencies: int = 0
    hours_since_consolidation: float | None = None
    alerts: list[str] = []


class SystemSupervisor:
    """巡检 Agent：每 30 分钟检查系统健康，写入 _meta/alerts.md。"""

    def __init__(
        self,
        memory: MemoryService,
        vault_path: Path,
        config: SystemConfig,
    ):
        self.memory = memory
        self.vault_path = vault_path
        self.config = config

    async def run(self) -> SupervisorReport:
        report = await self._inspect()
        await self._write_alerts(report)
        return report

    async def _inspect(self) -> SupervisorReport:
        report = SupervisorReport()
        now = datetime.now(timezone.utc)

        # 1. 检查 inbox 是否滞留
        inbox_dir = self.vault_path / "_inbox"
        if inbox_dir.exists():
            oldest = None
            for f in await list_directory(inbox_dir, "*.md"):
                try:
                    node = await parse_memory(f)
                    if node.status == MemoryStatus.RAW:
                        report.inbox_stuck += 1
                        created = datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        )
                        if oldest is None or created < oldest:
                            oldest = created
                except Exception:
                    continue
            if oldest:
                report.inbox_stuck_hours = (now - oldest).total_seconds() / 3600

        # 2. 检查上次巩固时间
        episodic_dir = self.vault_path / "_memory" / "episodic"
        last_consolidation = None
        if episodic_dir.exists():
            ep_files = sorted(
                [f for f in episodic_dir.glob("mem-epi-*.md")],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if ep_files:
                last_consolidation = datetime.fromtimestamp(
                    ep_files[0].stat().st_mtime, tz=timezone.utc
                )
            if last_consolidation:
                report.hours_since_consolidation = (
                    now - last_consolidation
                ).total_seconds() / 3600

        # 3. 检查孤岛和向量不一致（reuse MetaCognition if available）
        try:
            from memory_os.agents.meta_cognition import MetaCognitionAgent
            # Use a simple internal check for faster results
            meta_dir = self.vault_path / "_meta"
            health_file = meta_dir / "health-report.md"
            if health_file.exists():
                content = health_file.read_text(encoding="utf-8")
                # Parse orphan count from health report
                for line in content.split("\n"):
                    if "orphan" in line.lower() and ":" in line:
                        try:
                            report.orphans = int(line.split(":")[-1].strip())
                        except ValueError:
                            pass
                    if "inconsisten" in line.lower() and ":" in line:
                        try:
                            report.vector_inconsistencies = int(
                                line.split(":")[-1].strip()
                            )
                        except ValueError:
                            pass
        except Exception:
            pass

        # 4. 计算严重级别
        alerts = []
        critical = False
        action = False
        warning = False

        if report.inbox_stuck > 0 and report.inbox_stuck_hours > INBOX_STUCK_HOURS:
            alerts.append(
                f"🔴 {report.inbox_stuck} 条对话滞留 inbox 超过 "
                f"{report.inbox_stuck_hours:.1f} 小时未处理，请手动触发巩固"
            )
            critical = True

        if report.hours_since_consolidation is not None:
            if report.hours_since_consolidation > CONSOLIDATION_GAP_HOURS:
                alerts.append(
                    f"🟠 巩固 Agent 已 {report.hours_since_consolidation:.1f} 小时未运行，"
                    f"建议检查 scheduler 状态"
                )
                action = True

        if report.orphans > ORPHAN_WARN:
            alerts.append(
                f"🟠 {report.orphans} 条孤岛笔记，建议运行巩固增强链接"
            )
            action = True

        if report.vector_inconsistencies > VECTOR_INCONSISTENCY_WARN:
            alerts.append(
                f"🟠 {report.vector_inconsistencies} 处向量不一致，"
                f"建议运行 rebuild-vector-index"
            )
            action = True

        if report.inbox_stuck > 0 and report.inbox_stuck_hours <= INBOX_STUCK_HOURS:
            alerts.append(
                f"🟡 {report.inbox_stuck} 条新对话等待处理（"
                f"最长 {report.inbox_stuck_hours:.1f} 小时）"
            )
            warning = True

        report.alerts = alerts
        if critical:
            report.level = "CRITICAL"
        elif action:
            report.level = "ACTION"
        elif warning:
            report.level = "WARNING"

        return report

    async def _write_alerts(self, report: SupervisorReport):
        alerts_path = self.vault_path / "_meta" / "alerts.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if report.level == "OK":
            content = (
                f"# System Alerts\n"
                f"> Checked: {now} | Status: ✅ All Clear\n\n"
                f"系统运行正常，无异常告警。\n"
            )
        else:
            consolidation_h = (
                f"{report.hours_since_consolidation:.1f}h"
                if report.hours_since_consolidation is not None
                else "N/A"
            )
            consolidation_warn = (
                "⚠️"
                if report.hours_since_consolidation is not None
                and report.hours_since_consolidation > CONSOLIDATION_GAP_HOURS
                else "✅"
            )
            content = (
                f"# System Alerts\n"
                f"> Checked: {now} | Severity: {report.level}\n\n"
                f"| 指标 | 值 | 状态 |\n"
                f"|------|----|------|\n"
                f"| 待处理对话 | {report.inbox_stuck} 条 | "
                f"{'⚠️' if report.inbox_stuck > 0 else '✅'} |\n"
                f"| 最长滞留 | {report.inbox_stuck_hours:.1f}h | "
                f"{'⚠️' if report.inbox_stuck_hours > 1 else '✅'} |\n"
                f"| 孤岛笔记 | {report.orphans} | "
                f"{'⚠️' if report.orphans > ORPHAN_WARN else '✅'} |\n"
                f"| 向量不一致 | {report.vector_inconsistencies} | "
                f"{'⚠️' if report.vector_inconsistencies > VECTOR_INCONSISTENCY_WARN else '✅'} |\n"
                f"| 距上次巩固 | {consolidation_h} | "
                f"{consolidation_warn} |\n\n"
                + "".join(f"- {a}\n" for a in report.alerts)
            )

        alerts_path.parent.mkdir(parents=True, exist_ok=True)
        await atomic_write(alerts_path, content)
        logger.info("supervisor_alerts_written", level=report.level, alert_count=len(report.alerts))
