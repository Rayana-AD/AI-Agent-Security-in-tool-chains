"""Tests for LLM factory."""

from __future__ import annotations

from bio_harness.llm.factory import build_llm
from bio_harness.llm.openai_backend import OpenAICompatibleBackend
from bio_harness.llm.qwen_backend import QwenBackend


def test_build_local_backend():
    llm = build_llm({"backend": "local", "path": "/tmp/fake"}, backend="local")
    assert isinstance(llm, QwenBackend)


def test_build_openai_backend():
    llm = build_llm({"backend": "openai", "api_model": "gpt-4o-mini"}, backend="openai")
    assert isinstance(llm, OpenAICompatibleBackend)
    assert llm.model == "gpt-4o-mini"


def test_build_huggingface_backend():
    llm = build_llm(
        {
            "backend": "huggingface",
            "api_model": "Qwen/Qwen3-32B-Instruct",
            "api_key": "hf_test",
            "base_url": "https://router.huggingface.co/v1",
        },
        backend="huggingface",
    )
    assert isinstance(llm, OpenAICompatibleBackend)
    assert llm.model == "Qwen/Qwen3-32B-Instruct"
    assert llm.api_key == "hf_test"
