"""OpenAI-compatible LLM with system role (DeepSeek / HF router compatibility)."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence

from agentdojo.agent_pipeline.llms.openai_llm import (
    OpenAILLM,
    _assistant_message_to_content,
    _function_to_openai,
    _message_to_openai,
    chat_completion_request,
)
from agentdojo.functions_runtime import EmptyEnv, Env, Function, FunctionCall, FunctionsRuntime
from agentdojo.types import ChatAssistantMessage, ChatMessage, ChatUserMessage, get_text_content_as_str, text_content_block_from_string
from openai._types import NOT_GIVEN
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall

logger = logging.getLogger(__name__)

# OpenRouter / Llama sometimes returns finish_reason=None with no content or tool_calls.
_EMPTY_COMPLETION_RETRIES = 8
_EMPTY_RETRY_BACKOFF_SECONDS = 1.5
_EMPTY_FALLBACK_TEXT = (
    "(The model returned an empty response. Continue the user task using available tools.)"
)


def _normalize_openai_roles(messages: list) -> None:
    for msg in messages:
        if msg.get("role") == "developer":
            msg["role"] = "system"  # type: ignore[typeddict-unknown-key]


def _is_empty_completion(message) -> bool:
    has_content = bool(message.content and str(message.content).strip())
    has_tools = bool(message.tool_calls)
    return not has_content and not has_tools


def _json_repair_candidates(raw: str) -> list[str]:
    """Heuristic fixes for truncated Llama tool-call JSON."""
    s = raw.strip()
    candidates = [s]
    if not s:
        return candidates

    if s.count("{") > s.count("}"):
        candidates.append(s + "}" * (s.count("{") - s.count("}")))

    if s.count('"') % 2 == 1:
        candidates.append(s + '"')

    combined = s
    if s.count('"') % 2 == 1:
        combined += '"'
    if combined.count("{") > combined.count("}"):
        combined += "}" * (combined.count("{") - combined.count("}"))
    candidates.append(combined)

    # Strip trailing incomplete key/value fragment after last comma.
    trimmed = re.sub(r",\s*[^,{}\[\]]*$", "", s)
    if trimmed != s:
        candidates.append(trimmed)
        if trimmed.count("{") > trimmed.count("}"):
            candidates.append(trimmed + "}" * (trimmed.count("{") - trimmed.count("}")))

    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def parse_tool_arguments(raw: str | None) -> dict:
    """Parse tool-call JSON; repair common Llama truncation instead of crashing the suite."""
    if raw is None:
        return {}
    s = str(raw).strip()
    if not s:
        return {}

    for candidate in _json_repair_candidates(s):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if candidate != s:
                logger.warning("Repaired malformed tool arguments JSON")
            return parsed

    logger.warning("Malformed tool arguments, using {}: %r", s[:240])
    return {}


def safe_openai_to_tool_call(tool_call: ChatCompletionMessageToolCall) -> FunctionCall | None:
    fn = tool_call.function
    if fn is None or not fn.name:
        logger.warning("Skipping tool call with missing function name")
        return None
    return FunctionCall(
        function=fn.name,
        args=parse_tool_arguments(fn.arguments),
        id=tool_call.id,
    )


def safe_openai_to_assistant_message(message) -> ChatAssistantMessage:
    tool_calls: list[FunctionCall] | None = None
    if message.tool_calls:
        parsed = [tc for tc in (safe_openai_to_tool_call(t) for t in message.tool_calls) if tc is not None]
        tool_calls = parsed or None

    content = _assistant_message_to_content(message)
    if not tool_calls and not content:
        content = [text_content_block_from_string(_EMPTY_FALLBACK_TEXT)]

    return ChatAssistantMessage(role="assistant", content=content, tool_calls=tool_calls)


def _completion_with_empty_retry(
    client,
    model: str,
    messages: list,
    tools: list,
    reasoning_effort,
    temperature: float | None,
    *,
    max_retries: int = _EMPTY_COMPLETION_RETRIES,
    tool_choice=NOT_GIVEN,
) -> ChatCompletion:
    last: ChatCompletion | None = None
    for attempt in range(max_retries):
        if tool_choice is NOT_GIVEN:
            completion = chat_completion_request(
                client, model, messages, tools, reasoning_effort, temperature
            )
        else:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools or NOT_GIVEN,
                tool_choice=tool_choice,
                temperature=temperature if temperature is not None else NOT_GIVEN,
            )
        last = completion
        message = completion.choices[0].message
        if not _is_empty_completion(message):
            return completion
        logger.warning(
            "Empty LLM completion (attempt %s/%s, model=%s, finish=%s)",
            attempt + 1,
            max_retries,
            model,
            completion.choices[0].finish_reason,
        )
        if attempt + 1 < max_retries:
            time.sleep(_EMPTY_RETRY_BACKOFF_SECONDS * (attempt + 1))
    assert last is not None
    return last


class CompatibleOpenAILLM(OpenAILLM):
    """Map AgentDojo's `developer` role → `system` for non-OpenAI APIs."""

    def __init__(self, client, model: str, *, display_name: str | None = None, **kwargs) -> None:
        super().__init__(client, model, **kwargs)
        self.name = display_name or model

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        openai_messages = [_message_to_openai(message, self.model) for message in messages]
        _normalize_openai_roles(openai_messages)
        openai_tools = [_function_to_openai(tool) for tool in runtime.functions.values()]
        completion = _completion_with_empty_retry(
            self.client,
            self.model,
            openai_messages,
            openai_tools,
            self.reasoning_effort,
            self.temperature,
        )
        output = safe_openai_to_assistant_message(completion.choices[0].message)
        return query, runtime, env, [*messages, output], extra_args


class CompatibleOpenAILLMToolFilter(OpenAILLM):
    """Tool filter step with developer→system mapping for DeepSeek / HF APIs."""

    def __init__(self, prompt: str, client, model: str, temperature: float | None = 0.0) -> None:
        super().__init__(client, model, temperature=temperature)
        self.prompt = prompt

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        messages = [*messages, ChatUserMessage(role="user", content=[text_content_block_from_string(self.prompt)])]
        openai_messages = [_message_to_openai(message, self.model) for message in messages]
        _normalize_openai_roles(openai_messages)
        openai_tools = [_function_to_openai(tool) for tool in runtime.functions.values()]
        completion = _completion_with_empty_retry(
            self.client,
            self.model,
            openai_messages,
            openai_tools,
            self.reasoning_effort,
            self.temperature,
            tool_choice="none",
        )
        message = completion.choices[0].message
        if _is_empty_completion(message):
            logger.warning("Tool filter empty after retries; keeping full tool allowlist")
            return query, runtime, env, messages, extra_args

        output = safe_openai_to_assistant_message(message)
        content_text = get_text_content_as_str(output.get("content")) or ""

        new_tools: dict[str, Function] = {}
        for tool_name, tool in runtime.functions.items():
            if content_text and tool_name in content_text:
                new_tools[tool_name] = tool

        runtime.update_functions(new_tools)
        return query, runtime, env, [*messages, output], extra_args
