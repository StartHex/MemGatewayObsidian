"""Agent 定时调度引擎 — 按 cron 表达式自动运行后台 Agent。

用法:
- 作为后台服务:  memory-os scheduler --vault ~/memory-vault
- 嵌入 API 服务:  await scheduler.start()
"""

from __future__ import annotations

import asyncio
import calendar
import re
from datetime import datetime, timezone
from typing import Callable, Awaitable

import structlog

from memory_os.agents.consolidation import ConsolidationAgent
from memory_os.agents.forgetting import ForgettingAgent
from memory_os.agents.meta_cognition import MetaCognitionAgent
from memory_os.config.loader import load_config
from memory_os.config.models import SystemConfig
from memory_os.llm.service import LLMService
from memory_os.memory.service import MemoryService

logger = structlog.get_logger(__name__)

Job = tuple[str, str, Callable[[], Awaitable[None]]]  # (name, cron, callback)


class CronField:
    """解析单个 cron 字段为允许值的位图 (0-59 或 0-23 等)."""

    _RANGES = {
        "minute": (0, 59), "hour": (0, 23), "dom": (1, 31),
        "month": (1, 12), "dow": (0, 6),
    }

    def __init__(self, spec: str, field: str):
        lo, hi = self._RANGES[field]
        self.allowed = set()
        for part in spec.split(","):
            if part == "*":
                self.allowed.update(range(lo, hi + 1))
            elif "/" in part:
                base, step = part.split("/")
                base_range = range(lo, hi + 1) if base == "*" else self._parse_range(base, lo, hi)
                self.allowed.update(n for n in base_range if (n - lo) % int(step) == 0)
            elif "-" in part:
                a, b = part.split("-")
                self.allowed.update(range(int(a), int(b) + 1))
            else:
                self.allowed.add(int(part))

    @staticmethod
    def _parse_range(s: str, lo: int, hi: int) -> range:
        if "-" in s:
            a, b = s.split("-")
            return range(max(int(a), lo), min(int(b), hi) + 1)
        return range(int(s), int(s) + 1)

    def matches(self, value: int) -> bool:
        return value in self.allowed


class Cron:
    """5 字段 cron 表达式: minute hour dom month dow"""

    _FIELDS = ("minute", "hour", "dom", "month", "dow")

    def __init__(self, expr: str):
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"cron 表达式需要 5 个字段，收到 {len(parts)}: {expr}")
        self.fields = {
            name: CronField(part, name)
            for name, part in zip(self._FIELDS, parts)
        }

    def matches(self, dt: datetime) -> bool:
        return (
            self.fields["minute"].matches(dt.minute) and
            self.fields["hour"].matches(dt.hour) and
            self.fields["dom"].matches(dt.day) and
            self.fields["month"].matches(dt.month) and
            self.fields["dow"].matches(dt.weekday())
        )

    def next_after(self, dt: datetime) -> datetime:
        """返回 dt 之后下一个匹配的时间点。"""
        from datetime import timedelta
        candidate = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # 最多搜索 2 年 (crontab 粒度)
        for _ in range(60 * 24 * 366 * 2):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"cron 表达式无匹配: {self}")

    def __repr__(self):
        return " ".join(str(sorted(f.allowed)[:5]) for f in self.fields.values())


class AgentScheduler:
    """轻量级 cron 调度器，在 asyncio 事件循环中运行。"""

    def __init__(self, vault_path, config: SystemConfig, memory: MemoryService, llm: LLMService):
        self.vault_path = vault_path
        self.config = config
        self.memory = memory
        self.llm = llm
        self._jobs: list[Job] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def setup_default_jobs(self):
        agents = self.config.agents
        vault = self.vault_path
        mem = self.memory
        llm = self.llm
        cfg = self.config

        self._jobs = [
            (
                "consolidation",
                agents.consolidation_cron,
                lambda: ConsolidationAgent(mem, llm, vault, cfg).run(),
            ),
            (
                "forgetting",
                agents.forgetting_cron,
                lambda: ForgettingAgent(mem, cfg, vault).run(),
            ),
            (
                "meta_cognition",
                agents.meta_cognition_cron,
                lambda: MetaCognitionAgent(mem, llm, cfg, vault).run(),
            ),
        ]

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("scheduler_started", jobs=len(self._jobs))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scheduler_stopped")

    async def run_once(self, agent_name: str):
        """手动触发单次执行。"""
        for name, _, callback in self._jobs:
            if name == agent_name:
                logger.info("scheduler_manual_run", agent=name)
                await callback()
                return
        raise ValueError(f"未知 Agent: {agent_name}")

    async def _loop(self):
        last_run: dict[str, datetime] = {}
        tick_seconds = 30

        while self._running:
            now = datetime.now(timezone.utc)
            for name, cron_expr, callback in self._jobs:
                try:
                    cron = Cron(cron_expr)
                except ValueError:
                    logger.error("invalid_cron", agent=name, cron=cron_expr)
                    continue

                if cron.matches(now):
                    last = last_run.get(name)
                    if last is not None and (now - last).total_seconds() < 120:
                        continue  # 避免同一分钟重复触发

                    last_run[name] = now
                    logger.info("scheduler_trigger", agent=name, cron=cron_expr)
                    try:
                        await callback()
                        logger.info("scheduler_done", agent=name)
                    except Exception as exc:
                        logger.error("scheduler_failed", agent=name, error=str(exc))

            await asyncio.sleep(tick_seconds)


async def run_forever(scheduler: AgentScheduler):
    """阻塞当前协程直到收到 SIGTERM/SIGINT，然后优雅停止调度器。"""
    import signal

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows 不支持 add_signal_handler

    logger.info("scheduler_running", vault=str(scheduler.vault_path))
    await stop_event.wait()
    await scheduler.stop()


async def main():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "memory-vault"))
    args = parser.parse_args()

    vault_path = Path(args.vault)
    config = load_config(vault_path)
    memory = MemoryService(vault_path, config)
    llm = LLMService(config)

    scheduler = AgentScheduler(vault_path, config, memory, llm)
    scheduler.setup_default_jobs()
    await scheduler.start()
    await run_forever(scheduler)


if __name__ == "__main__":
    asyncio.run(main())
