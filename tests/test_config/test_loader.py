from __future__ import annotations

import pytest

from memory_os.config.loader import load_config


def test_load_valid_config(test_vault_path):
    config = load_config(test_vault_path)
    assert config.llm.chat.provider.value == "openai-compatible"
    assert config.llm.embedding.dimension == 1024
    assert config.memory.max_slots == 7


def test_config_defaults(test_vault_path):
    config = load_config(test_vault_path)
    assert config.memory.initial_strength == 50
    assert config.memory.decay_rate_default == 0.03
    assert config.memory.cascade_max_depth == 2
