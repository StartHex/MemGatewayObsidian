from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class TokenRecord(BaseModel):
    timestamp: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int


class TokenTracker:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self._meta_dir = vault_path / "_meta"
        self._log_path = self._meta_dir / "token-usage.jsonl"

    def log(self, record: TokenRecord) -> None:
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def daily_stats(self, date_str: str) -> dict:
        """Return per-model token stats for a given date, and per-agent breakdown."""
        if not self._log_path.exists():
            return {"models": {}, "agents": {}, "total_input": 0, "total_output": 0}

        models: dict[str, dict] = {}
        agents: dict[str, dict] = {}
        total_input = 0
        total_output = 0

        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = TokenRecord.model_validate_json(line)
                except Exception:
                    continue
                if not r.timestamp.startswith(date_str):
                    continue

                total_input += r.input_tokens
                total_output += r.output_tokens

                if r.model not in models:
                    models[r.model] = {"input_tokens": 0, "output_tokens": 0}
                models[r.model]["input_tokens"] += r.input_tokens
                models[r.model]["output_tokens"] += r.output_tokens

                if r.agent_name not in agents:
                    agents[r.agent_name] = {"input_tokens": 0, "output_tokens": 0}
                agents[r.agent_name]["input_tokens"] += r.input_tokens
                agents[r.agent_name]["output_tokens"] += r.output_tokens

        return {
            "models": models,
            "agents": agents,
            "total_input": total_input,
            "total_output": total_output,
        }

    def daily_total(self, date_str: str) -> dict:
        """Return total token usage for a given date."""
        stats = self.daily_stats(date_str)
        return {
            "total_input": stats["total_input"],
            "total_output": stats["total_output"],
            "by_model": stats["models"],
        }
