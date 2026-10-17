"""One provider-neutral LLM interface (ADR D-53) and its adapters.

The agent speaks only this module's types: `Message` (user / assistant / tool turns), `ToolSpec`,
`ToolCall`, `LLMResponse` with token counts. Each adapter maps them to its provider's wire format:

    GeminiLLM     Gemini API generateContent with function calling (free tier; the default)
    AnthropicLLM  Claude through the Messages API with tool use (the upgrade, D-53)
    FakeLLM       scripted, for every test: never touches the network

A provider failure of any kind (network, quota, timeout, a malformed answer) is an `LLMError`, which
the agent turns into guided mode. Keys travel only in request headers: they are never logged,
never put in a message, never returned.
"""

import copy
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

from app.core.settings import Settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Gemini default: the free tier allows only 20 requests a day on gemini-3.8-flash (measured);
# the lite model has its own, larger allowance and passed every live scenario (ASSUMED 29).
DEFAULT_MODELS = {"gemini": "gemini-3.1-flash-lite", "anthropic": "claude-sonnet-5-5"}


class LLMError(Exception):
    """The provider could not give a usable answer. The message never contains a key."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (Pydantic's); adapters flatten it as they need


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: dict[str, Any]


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None  # the provider's own form of an assistant turn, echoed back unchanged


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    raw: Any = None


class LLM(Protocol):
    provider: str
    model: str

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        max_output_tokens: int,
        timeout: float,
    ) -> LLMResponse: ...


# ------------------------------------------------------------------ schemas
# The schema keywords function declarations accept (Gemini's OpenAPI subset; Anthropic accepts a
# superset of it). Anything else is dropped after the conversions below.
SCHEMA_KEYS = frozenset(
    {"type", "format", "description", "nullable", "enum", "items", "properties", "required",
     "minItems", "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum"}
)  # fmt: skip


def flatten_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic JSON schema -> the OpenAPI subset function declarations accept: `$ref`s inlined,
    `anyOf [X, null]` folded to X (nullable), exclusive bounds turned into inclusive ones, and
    every other keyword (titles, defaults, `additionalProperties`) dropped."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            return walk({**target, **{k: v for k, v in node.items() if k != "$ref"}})
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            nullable = len(options) < len(node["anyOf"])
            if len(options) == 1:
                out = walk({**options[0], **{k: v for k, v in node.items() if k != "anyOf"}})
                if nullable:
                    out["nullable"] = True
                return out
        node = dict(node)
        step = 1 if node.get("type") == "integer" else 0
        if "exclusiveMinimum" in node:
            node["minimum"] = node.pop("exclusiveMinimum") + step
        if "exclusiveMaximum" in node:
            node["maximum"] = node.pop("exclusiveMaximum") - step
        out = {}
        for key, value in node.items():
            if key not in SCHEMA_KEYS:
                continue
            if key == "properties":
                out[key] = {name: walk(sub) for name, sub in value.items()}
            else:
                out[key] = walk(value)
        return out

    flat = walk(copy.deepcopy(schema))
    flat.setdefault("type", "object")
    flat.setdefault("properties", {})
    return flat


def _redact(text: str, headers: dict[str, str]) -> str:
    """Provider error text, with every credential that was sent removed (a provider may echo it)."""
    for name, value in headers.items():
        if name.lower() in ("x-goog-api-key", "x-api-key", "authorization") and value:
            text = text.replace(value, "[redacted]")
    return " ".join(text.split())


def _post(client: httpx.Client, url: str, *, headers: dict[str, str], body: dict[str, Any],
          timeout: float) -> dict[str, Any]:  # fmt: skip
    try:
        response = client.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException as err:
        raise LLMError("the model did not answer in time") from err
    except httpx.HTTPError as err:
        raise LLMError(f"the model could not be reached ({type(err).__name__})") from err
    if response.status_code == 429:
        raise LLMError("the model's provider is rate limiting requests (HTTP 429)")
    if response.status_code >= 400:
        raise LLMError(
            f"the model's provider answered HTTP {response.status_code}: "
            + _redact(response.text[:300], headers)
        )
    try:
        return response.json()
    except ValueError as err:
        raise LLMError("the model's provider sent something that is not JSON") from err


# ------------------------------------------------------------------ Gemini
class GeminiLLM:
    provider = "gemini"

    def __init__(self, api_key: str, model: str | None = None, client: httpx.Client | None = None):
        self._key = api_key
        self.model = model or DEFAULT_MODELS["gemini"]
        self._client = client or httpx.Client()

    def _contents(self, messages: Sequence[Message]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                contents.append({"role": "user", "parts": [{"text": m.text}]})
            elif m.role == "assistant":
                if m.raw is not None:  # keeps each call's id and thoughtSignature
                    contents.append(m.raw)
                    continue
                parts: list[dict[str, Any]] = [{"text": m.text}] if m.text else []
                parts += [
                    {"functionCall": {"name": c.name, "args": c.arguments, "id": c.id}}
                    for c in m.tool_calls
                ]
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": r.name,
                                    "id": r.call_id,
                                    "response": r.content,
                                }
                            }  # fmt: skip
                            for r in m.tool_results
                        ],
                    }
                )
        return contents

    def complete(self, system, messages, tools, *, max_output_tokens, timeout) -> LLMResponse:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._contents(messages),
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": flatten_schema(t.parameters),
                        }  # fmt: skip
                        for t in tools
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.2},
        }
        data = _post(
            self._client,
            GEMINI_URL.format(model=self.model),
            headers={"x-goog-api-key": self._key, "content-type": "application/json"},
            body=body,
            timeout=timeout,
        )
        try:
            candidate = data["candidates"][0]
            content = candidate.get("content") or {"role": "model", "parts": []}
            parts = content.get("parts", [])
        except (KeyError, IndexError, TypeError) as err:
            raise LLMError("the model's answer had no content") from err
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        calls = [
            ToolCall(
                id=str(p["functionCall"].get("id") or f"call_{i}"),
                name=str(p["functionCall"].get("name", "")),
                arguments=dict(p["functionCall"].get("args") or {}),
            )
            for i, p in enumerate(parts)
            if "functionCall" in p
        ]
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text.strip(),
            tool_calls=calls,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0))
            + int(usage.get("thoughtsTokenCount", 0)),
            raw={"role": "model", "parts": parts},
        )


# ------------------------------------------------------------------ Anthropic
class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str | None = None, client: httpx.Client | None = None):
        self._key = api_key
        self.model = model or DEFAULT_MODELS["anthropic"]
        self._client = client or httpx.Client()

    @staticmethod
    def _messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.text})
            elif m.role == "assistant":
                blocks: list[dict[str, Any]] = [{"type": "text", "text": m.text}] if m.text else []
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in m.tool_calls
                ]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": r.call_id,
                                "content": json.dumps(r.content, default=str),
                            }  # fmt: skip
                            for r in m.tool_results
                        ],
                    }
                )
        return out

    def complete(self, system, messages, tools, *, max_output_tokens, timeout) -> LLMResponse:
        body = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "system": system,
            "messages": self._messages(messages),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": flatten_schema(t.parameters),
                }  # fmt: skip
                for t in tools
            ],
        }
        data = _post(
            self._client,
            ANTHROPIC_URL,
            headers={
                "x-api-key": self._key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            body=body,
            timeout=timeout,
        )
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise LLMError("the model's answer had no content")
        usage = data.get("usage", {})
        return LLMResponse(
            text="".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip(),
            tool_calls=[
                ToolCall(id=str(b["id"]), name=str(b["name"]), arguments=dict(b.get("input") or {}))
                for b in blocks
                if b.get("type") == "tool_use"
            ],
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


# ------------------------------------------------------------------ fake (tests)
Script = Callable[[str, Sequence[Message], Sequence[ToolSpec]], LLMResponse]


class FakeLLM:
    """A scripted model. Each entry is an `LLMResponse`, an exception to raise, or a function of
    (system, messages, tools). Records every call so tests can check what the model was shown."""

    provider = "fake"

    def __init__(self, script: Sequence[Any], model: str = "fake-1") -> None:
        self.model = model
        self._script = list(script)
        self.calls: list[tuple[str, list[Message], list[ToolSpec]]] = []

    def complete(self, system, messages, tools, *, max_output_tokens, timeout) -> LLMResponse:
        self.calls.append((system, [copy.deepcopy(m) for m in messages], list(tools)))
        if not self._script:
            raise LLMError("the fake model has no more answers")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(system, messages, tools)
        return step


def say(text: str, tokens: int = 10) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], input_tokens=tokens, output_tokens=tokens)


def call(name: str, arguments: dict[str, Any] | None = None, call_id: str = "c1") -> LLMResponse:
    return LLMResponse(
        text="", tool_calls=[ToolCall(call_id, name, arguments or {})],
        input_tokens=10, output_tokens=5,
    )  # fmt: skip


# ------------------------------------------------------------------ factory
def build_llm(settings: Settings, client: httpx.Client | None = None) -> LLM | None:
    """The configured provider, or None (guided mode) when switched off or without a key."""
    if not settings.assistant_enabled or settings.llm_provider == "none":
        return None
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiLLM(
            settings.gemini_api_key.get_secret_value(), settings.assistant_model, client
        )
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicLLM(
            settings.anthropic_api_key.get_secret_value(), settings.assistant_model, client
        )
    return None


def guided_reason(settings: Settings) -> str | None:
    """Why there is no model (for the status route), or None when one is configured."""
    if not settings.assistant_enabled:
        return "The assistant's model is switched off."
    if settings.llm_provider == "none":
        return "No model provider is configured."
    key = (
        settings.gemini_api_key if settings.llm_provider == "gemini" else settings.anthropic_api_key
    )
    if not key:
        return f"No API key is set for {settings.llm_provider}."
    return None
