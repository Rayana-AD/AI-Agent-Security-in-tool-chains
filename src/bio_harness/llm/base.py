"""LLM backend protocol shared by local and API providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class GenerationStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0


@runtime_checkable
class LLMBackend(Protocol):
    total_stats: GenerationStats

    def generate(self, prompt: str, temperature: float | None = None) -> tuple[str, GenerationStats]: ...

    def generate_json(self, prompt: str) -> tuple[dict[str, Any], GenerationStats]: ...

    def judge_harmful(self, user_goal: str, agent_output: str) -> tuple[bool, str, GenerationStats]: ...

    def judge_shuffle_deception(
        self, original: str, shuffled: str, user_goal: str = ""
    ) -> tuple[bool, str, GenerationStats]: ...
