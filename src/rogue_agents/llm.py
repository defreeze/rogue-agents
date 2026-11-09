"""Model backends.

One real backend speaks the OpenAI-compatible chat completions protocol, which
Ollama, vLLM, llama.cpp, LM Studio and most hosted providers expose. The
scripted backend replays canned responses, for tests and offline rehearsals.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLM(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict] | None, *, agent: str) -> LLMResponse: ...


THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def resolve_base_url(explicit: str | None = None) -> str:
    """ROGUE_BASE_URL if set, otherwise the first Ollama we can reach."""
    configured = explicit or os.getenv("ROGUE_BASE_URL")
    if configured:
        return configured
    candidates = ["http://localhost:11434/v1", "http://172.17.0.1:11434/v1"]
    for url in candidates:
        try:
            if httpx.get(f"{url}/models", timeout=1.5).status_code == 200:
                return url
        except httpx.HTTPError:
            continue
    return candidates[0]


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.6,
        reasoning_effort: str | None = None,
        timeout: float = 180,
    ):
        self.base_url = resolve_base_url(base_url).rstrip("/")
        self.model = model or os.getenv("ROGUE_MODEL", "qwen3:8b")
        self.temperature = temperature
        # Hybrid reasoning models (qwen3, ...) are much faster with thinking off.
        # Set ROGUE_REASONING_EFFORT="" for providers that reject the field.
        self.reasoning_effort = reasoning_effort if reasoning_effort is not None else os.getenv("ROGUE_REASONING_EFFORT", "none")
        self.seed: int | None = None  # set per run; each call gets the next value
        key = api_key or os.getenv("ROGUE_API_KEY", "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.http = httpx.Client(timeout=timeout, headers=headers)

    def _post(self, body: dict, attempts: int = 3) -> dict:
        for attempt in range(attempts):
            try:
                resp = self.http.post(f"{self.base_url}/chat/completions", json=body)
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                retryable = isinstance(e, httpx.TransportError) or e.response.status_code >= 500
                if not retryable or attempt == attempts - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        raise AssertionError("unreachable")

    def chat(self, messages: list[dict], tools: list[dict] | None, *, agent: str) -> LLMResponse:
        body: dict = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            body["tools"] = tools
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.seed is not None:
            body["seed"] = self.seed
            self.seed += 1
        data = self._post(body)
        message = data["choices"][0]["message"]
        calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": fn.get("arguments")}
            if not isinstance(args, dict):
                args = {"__invalid_json__": fn.get("arguments")}
            calls.append(ToolCall(id=call.get("id") or f"call_{i}", name=fn["name"], arguments=args))
        usage = data.get("usage") or {}
        return LLMResponse(
            content=THINK_RE.sub("", message.get("content") or "").strip(),
            tool_calls=calls,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


Step = LLMResponse | Callable[[list[dict]], LLMResponse]


class ScriptedLLM:
    """Plays back a fixed list of responses per agent name."""

    model = "scripted"

    def __init__(self, scripts: dict[str, list[Step]]):
        self.scripts = {name: list(steps) for name, steps in scripts.items()}

    def chat(self, messages: list[dict], tools: list[dict] | None, *, agent: str) -> LLMResponse:
        steps = self.scripts.get(agent)
        if not steps:
            return LLMResponse(content="(script exhausted)")
        step = steps.pop(0)
        return step(messages) if callable(step) else step


def call(name: str, **arguments) -> LLMResponse:
    """Shorthand for a scripted response that makes one tool call."""
    return LLMResponse(tool_calls=[ToolCall(id=f"call_{name}", name=name, arguments=arguments)])


def say(text: str) -> LLMResponse:
    return LLMResponse(content=text)
