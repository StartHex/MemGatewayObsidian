from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import yaml

from memory_os.config.models import SystemConfig

_ENV_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    def _replacer(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            raise KeyError(f"环境变量 {var} 未设置")
        return val

    return _ENV_RE.sub(_replacer, value)


def load_config(vault_path: Path) -> SystemConfig:
    config_path = vault_path / "_meta" / "system-config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    raw = config_path.read_text(encoding="utf-8")
    resolved = _ENV_RE.sub(lambda m: _resolve_env(m.group(0)), raw)
    data = yaml.safe_load(resolved)
    return SystemConfig.model_validate(data)


def embedding_config_hash(config) -> str:
    if config is None:
        return "none"
    payload = f"{config.provider}:{config.model}:{config.dimension}:{config.base_url or ''}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
