"""Paid provider modes must not silently route through another API."""

from __future__ import annotations

import pytest

from eval.agentdojo.pipeline_factory import _validate_provider_endpoint


def test_deepseek_uses_native_endpoint_only():
    _validate_provider_endpoint("deepseek", "https://api.deepseek.com/v1")
    with pytest.raises(RuntimeError, match="api.deepseek.com"):
        _validate_provider_endpoint("deepseek", "https://openrouter.ai/api/v1")


def test_llama_openrouter_mode_uses_openrouter_only():
    _validate_provider_endpoint("openrouter_llama70", "https://openrouter.ai/api/v1")
    with pytest.raises(RuntimeError, match="openrouter.ai"):
        _validate_provider_endpoint(
            "openrouter_llama70",
            "https://api.deepseek.com/v1",
        )
