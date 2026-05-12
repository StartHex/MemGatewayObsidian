from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def test_vault_path(tmp_path: Path) -> Path:
    vault = tmp_path / "test-vault"
    dirs = [
        "_inbox", "_working", "_memory/semantic", "_memory/episodic",
        "_memory/procedural", "_memory/archive", "_vectors",
        "_meta", "_agent-logs", "_canvas", "_ui-config",
    ]
    for d in dirs:
        (vault / d).mkdir(parents=True)

    config = {
        "llm": {
            "chat": {
                "provider": "openai-compatible",
                "model": "test-model",
                "api_key": "test-key",
            },
            "embedding": {
                "provider": "local",
                "model": "bge-m3",
                "base_url": "http://localhost:8080",
                "dimension": 1024,
            },
        },
        "agents": {},
        "memory": {},
    }
    (vault / "_meta" / "system-config.yaml").write_text(yaml.dump(config))
    return vault


@pytest.fixture
def test_config(test_vault_path):
    from memory_os.config.loader import load_config
    return load_config(test_vault_path)


class MockLLMService:
    async def chat(self, request, agent_name=None):
        from memory_os.llm.models import UnifiedChatResponse
        return UnifiedChatResponse(
            content='{"tags":["test"],"importance":50,"context":"test","modality":"chat"}',
            model="mock", input_tokens=10, output_tokens=5, finish_reason="stop",
        )

    async def embed(self, texts):
        return [[0.1] * 1024 for _ in texts]


@pytest.fixture
def mock_llm():
    return MockLLMService()
