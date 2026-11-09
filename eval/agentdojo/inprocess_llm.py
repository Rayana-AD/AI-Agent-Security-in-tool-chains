"""In-process Qwen LLM for AgentDojo (no vLLM server required)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from agentdojo.agent_pipeline.llms.local_llm import (
    LocalLLM,
    _make_system_prompt,
    _parse_model_output,
)
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import ChatMessage, get_text_content_as_str

if TYPE_CHECKING:
    from bio_harness.llm.qwen_backend import QwenBackend


class InProcessQwenLLM(LocalLLM):
    """AgentDojo LocalLLM-compatible backend backed by transformers Qwen."""

    def __init__(self, backend: QwenBackend, tool_delimiter: str = "tool") -> None:
        self.backend = backend
        self.tool_delimiter = tool_delimiter
        self.model = backend.model_path or "local-qwen"
        self.temperature = backend.temperature
        self.top_p = 0.9
        self.name = f"local-{self.model.split('/')[-1]}"

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        import json

        messages_ = []
        for m in messages:
            role, content = m["role"], m["content"]
            if role == "system" and content is not None:
                content = _make_system_prompt(get_text_content_as_str(content), runtime.functions.values())
            if role == "tool":
                role = self.tool_delimiter
                if m.get("error"):
                    content = json.dumps({"error": m["error"]})
                else:
                    func_result = m["content"]
                    if func_result == "None":
                        func_result = "Success"
                    content = json.dumps({"result": func_result})
            messages_.append({"role": role, "content": content})

        prompt = self._messages_to_prompt(messages_, query)
        completion, _ = self.backend.generate(prompt, temperature=self.temperature)
        output = _parse_model_output(completion)
        return query, runtime, env, [*messages, output], extra_args

    def _messages_to_prompt(self, messages: list[dict], query: str) -> str:
        self.backend.load()
        tokenizer = self.backend._tokenizer
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            chat = [{"role": m["role"], "content": str(m["content"] or "")} for m in messages]
            if not chat:
                chat = [{"role": "user", "content": query}]
            try:
                return tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass
        parts = [f"{m['role'].upper()}: {m['content']}" for m in messages]
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)
