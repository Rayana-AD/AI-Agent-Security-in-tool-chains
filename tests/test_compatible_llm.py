from types import SimpleNamespace

from eval.agentdojo.compatible_llm import (
    _is_empty_completion,
    parse_tool_arguments,
    safe_openai_to_assistant_message,
    safe_openai_to_tool_call,
)


def test_empty_completion_detects_blank_response():
    msg = SimpleNamespace(content=None, tool_calls=None)
    assert _is_empty_completion(msg) is True


def test_empty_completion_allows_tool_calls_only():
    msg = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(function="search_calendar_events")])
    assert _is_empty_completion(msg) is False


def test_empty_completion_allows_text_only():
    msg = SimpleNamespace(content="Done.", tool_calls=None)
    assert _is_empty_completion(msg) is False


def test_parse_tool_arguments_valid_json():
    assert parse_tool_arguments('{"query": "meetings"}') == {"query": "meetings"}


def test_parse_tool_arguments_repairs_truncated_string():
    raw = '{"query": "find my next meeting'
    assert parse_tool_arguments(raw) == {"query": "find my next meeting"}


def test_parse_tool_arguments_returns_empty_on_garbage():
    assert parse_tool_arguments("not json at all") == {}


def test_safe_openai_to_tool_call_skips_malformed_without_crashing():
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="search_emails", arguments='{"q": "hello'),
    )
    out = safe_openai_to_tool_call(tc)
    assert out is not None
    assert out.function == "search_emails"
    assert out.args == {"q": "hello"}


def test_safe_openai_to_assistant_message_empty_gets_fallback_text():
    msg = SimpleNamespace(content=None, tool_calls=None)
    out = safe_openai_to_assistant_message(msg)
    assert out["tool_calls"] in (None, [])
    assert out["content"] is not None
    assert "empty response" in str(out["content"]).lower()
