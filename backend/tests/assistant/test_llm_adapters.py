"""WP4c / D-53: the Gemini and Anthropic adapters map the neutral types to each wire format.
No test touches the network: every request goes to an httpx.MockTransport."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.assistant.llm import (
    AnthropicLLM,
    GeminiLLM,
    LLMError,
    Message,
    ToolCall,
    ToolResult,
    ToolSpec,
    build_llm,
    flatten_schema,
    guided_reason,
)
from app.assistant.tools import MODEL_TOOLS

KEY = "test-key-not-real-0123456789"
SPEC = ToolSpec("get_forecast", "The forecast.", {"type": "object", "properties": {}})


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_flatten_inlines_refs_and_folds_nullable():
    schema = MODEL_TOOLS["check_purchase_risk"].input_schema()
    flat = flatten_schema(schema)
    text = json.dumps(flat)
    assert "$ref" not in text and "$defs" not in text and "title" not in flat
    assert flat["properties"]["total_price_sen"]["nullable"] is True
    assert flat["properties"]["total_price_sen"]["type"] == "integer"
    assert set(flat["properties"]["provider"]["enum"]) == {
        "spaylater",
        "tiktok_paylater",
        "atome",
        "other",
    }
    for tool in MODEL_TOOLS.values():
        assert "$ref" not in json.dumps(flatten_schema(tool.input_schema())), tool.name


def test_gemini_request_and_response_mapping():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        parts = [
            {"functionCall": {"name": "get_forecast", "args": {}, "id": "call_9"},
             "thoughtSignature": "sig-abc"},
        ]  # fmt: skip
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": parts}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8,
                              "thoughtsTokenCount": 30},
        })  # fmt: skip

    llm = GeminiLLM(KEY, "gemini-test", client(handler))
    history = [
        Message("user", "How am I doing?"),
        Message("assistant", tool_calls=[ToolCall("call_1", "get_budgets", {})],
                raw={"role": "model", "parts": [{"functionCall": {"name": "get_budgets",
                     "args": {}, "id": "call_1"}, "thoughtSignature": "keep-me"}]}),
        Message(
            "tool", tool_results=[ToolResult("call_1", "get_budgets", {"data": {"budgets": []}})]
        ),
    ]  # fmt: skip
    out = llm.complete("system text", history, [SPEC], max_output_tokens=256, timeout=5)
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert seen["key"] == KEY
    body = seen["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "system text"
    assert body["contents"][1]["parts"][0]["thoughtSignature"] == "keep-me"
    response_part = body["contents"][2]["parts"][0]["functionResponse"]
    assert response_part == {"name": "get_budgets", "id": "call_1",
                             "response": {"data": {"budgets": []}}}  # fmt: skip
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "get_forecast"
    assert body["generationConfig"]["maxOutputTokens"] == 256
    assert out.tool_calls == [ToolCall("call_9", "get_forecast", {})]
    assert (out.input_tokens, out.output_tokens) == (120, 38)
    assert out.raw["parts"][0]["thoughtSignature"] == "sig-abc"


def test_gemini_text_answer_skips_thought_parts():
    def handler(request):
        parts = [{"text": "thinking...", "thought": True}, {"text": "You are fine."}]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]})

    llm = GeminiLLM(KEY, client=client(handler))
    out = llm.complete("s", [Message("user", "hi")], [], max_output_tokens=50, timeout=5)
    assert out.text == "You are fine." and out.tool_calls == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "quota"}),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"candidates": []}),
    ],
)
def test_gemini_failures_are_llm_errors_without_the_key(response):
    llm = GeminiLLM(KEY, client=client(lambda request: response))
    with pytest.raises(LLMError) as caught:
        llm.complete("s", [Message("user", "hi")], [], max_output_tokens=10, timeout=5)
    assert KEY not in str(caught.value)


def test_a_network_failure_or_timeout_is_an_llm_error():
    def refuse(request):
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(LLMError, match="in time"):
        GeminiLLM(KEY, client=client(refuse)).complete("s", [], [], max_output_tokens=1, timeout=1)


def test_anthropic_request_and_response_mapping():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "Let me check."},
                        {"type": "tool_use", "id": "tu_1", "name": "get_forecast", "input": {}}],
            "usage": {"input_tokens": 300, "output_tokens": 20},
        })  # fmt: skip

    llm = AnthropicLLM(KEY, client=client(handler))
    history = [
        Message("user", "Can I afford it?"),
        Message("assistant", tool_calls=[ToolCall("tu_0", "get_budgets", {})]),
        Message("tool", tool_results=[ToolResult("tu_0", "get_budgets", {"ok": True})]),
    ]
    out = llm.complete("sys", history, [SPEC], max_output_tokens=500, timeout=5)
    assert seen["headers"]["x-api-key"] == KEY
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    body = seen["body"]
    assert body["model"] == "claude-sonnet-5-5" and body["system"] == "sys"
    assert body["tools"][0]["input_schema"]["type"] == "object"
    assert body["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "tu_0",
                                                 "content": '{"ok": true}'}  # fmt: skip
    assert out.text == "Let me check."
    assert out.tool_calls == [ToolCall("tu_1", "get_forecast", {})]
    assert (out.input_tokens, out.output_tokens) == (300, 20)


def test_build_llm_follows_the_settings(settings):
    assert build_llm(settings) is None  # no key
    assert "No API key" in guided_reason(settings)
    gemini = settings.model_copy(update={"gemini_api_key": SecretStr(KEY)})
    assert isinstance(build_llm(gemini), GeminiLLM) and guided_reason(gemini) is None
    anthropic = settings.model_copy(update={"llm_provider": "anthropic",
                                            "anthropic_api_key": SecretStr(KEY)})  # fmt: skip
    assert isinstance(build_llm(anthropic), AnthropicLLM)
    off = gemini.model_copy(update={"assistant_enabled": False})
    assert build_llm(off) is None and "switched off" in guided_reason(off)
    none = gemini.model_copy(update={"llm_provider": "none"})
    assert build_llm(none) is None
    model = gemini.model_copy(update={"assistant_model": "gemini-3.5-flash"})
    assert build_llm(model).model == "gemini-3.5-flash"
