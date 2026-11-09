"""Map AgentDojo chat transcripts to BioHarness plan/review/tool_call nodes."""

from __future__ import annotations

import json
from collections.abc import Sequence

from agentdojo.types import ChatMessage, get_text_content_as_str


def safe_message_text(content) -> str:
    """AgentDojo messages may have content=None after empty Llama completions."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    try:
        return (get_text_content_as_str(content) or "").strip()
    except TypeError:
        return ""


def parse_tool_call(tc) -> tuple[str, dict]:
    """Normalize AgentDojo tool_call objects or probe-style dicts."""
    if isinstance(tc, dict):
        fn = tc.get("function") or tc.get("name") or ""
        args = tc.get("args") or {}
        return str(fn), dict(args) if isinstance(args, dict) else {}
    fn = getattr(tc, "function", None) or getattr(tc, "name", "") or ""
    args = getattr(tc, "args", None) or {}
    return str(fn), dict(args) if isinstance(args, dict) else {}


def has_prior_tool_output(messages: Sequence[ChatMessage]) -> bool:
    """True when the transcript already contains tool results before the latest assistant turn."""
    if not messages or messages[-1]["role"] != "assistant":
        return False
    return any(msg["role"] == "tool" for msg in messages[:-1])


def latest_assistant_text(messages: Sequence[ChatMessage]) -> str:
    """Most recent assistant message text (excludes harness block stubs)."""
    for msg in reversed(messages):
        if msg["role"] != "assistant":
            continue
        text = safe_message_text(msg.get("content"))
        if not text:
            continue
        tl = text.lower()
        if "tool call blocked by bioharness" in tl:
            continue
        return text
    return ""


def build_agentdojo_node_outputs(
    query: str,
    messages: Sequence[ChatMessage],
    *,
    current_tool_text: str,
    up_to_tool_idx: int | None = None,
) -> dict[str, str]:
    """Build cross-turn context for shuffle supplement on AgentDojo tool outputs.

    AgentDojo has no explicit plan/review stages; we approximate:
      plan    — user goal
      review  — assistant reasoning text before the current tool batch
      tool_call — prior tool calls/results + current tool output under check
    """
    end = up_to_tool_idx if up_to_tool_idx is not None else len(messages)
    review_parts: list[str] = []
    tool_parts: list[str] = []
    trusted_tool_results: list[str] = []

    for msg in messages[:end]:
        role = msg["role"]
        if role == "assistant":
            text = safe_message_text(msg.get("content"))
            if text:
                review_parts.append(text)
            raw_tool_calls = msg.get("tool_calls")
            if not raw_tool_calls:
                continue
            for tc in raw_tool_calls:
                fn, args = parse_tool_call(tc)
                if not fn:
                    continue
                tool_parts.append(json.dumps({"tool": fn, "args": args}, ensure_ascii=False))
        elif role == "tool":
            text = safe_message_text(msg.get("content"))
            if text:
                tool_parts.append(f"prior_tool_result:\n{text}")
                trusted_tool_results.append(text)

    if current_tool_text.strip():
        tool_parts.append(f"current_tool_result:\n{current_tool_text.strip()}")

    return {
        "plan": f"user_goal: {query.strip()}",
        "review": "\n\n".join(review_parts),
        "tool_call": "\n\n".join(tool_parts),
        # These are post-ToolGuard messages: IPI envelopes have already been
        # cleaved/stripped. Keep separate so current proposed args cannot
        # self-authorize by appearing in tool_call context.
        "trusted_tool_results": "\n\n".join(trusted_tool_results),
    }
