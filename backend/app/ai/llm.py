"""Clients for the AI brain.

The production brain is any open-source model served behind an OpenAI-compatible
``/chat/completions`` endpoint with tool (function) calling: Ollama, vLLM,
llama.cpp server, LocalAI, or a hosted provider running Llama / Qwen.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    def to_openai(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments, ensure_ascii=False)},
        }


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def clean_content(text: str | None) -> str | None:
    """Remove hidden reasoning blocks some open models (Qwen3, DeepSeek-R1) emit."""
    if text is None:
        return None
    return _THINK_RE.sub("", text).strip()


def _parse_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _tool_call_from_text(content: str, tool_names: set[str]) -> ToolCall | None:
    """Small models sometimes write the tool call as JSON text instead of using the
    tool-calling channel. Recover it when the whole reply is such a JSON object."""
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name") or obj.get("function") or obj.get("tool")
    if name not in tool_names:
        return None
    args = obj.get("arguments", obj.get("parameters", {}))
    return ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=_parse_arguments(args))


RETRY_DELAY_SECONDS = 2.0


def _worth_retrying(resp: httpx.Response) -> bool:
    """Rate limits, temporary server errors, and Groq's occasional malformed tool call."""
    if resp.status_code in (429, 500, 502, 503, 504):
        return True
    return resp.status_code == 400 and "tool_use_failed" in resp.text


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        payload: dict = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        for attempt in range(2):
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout
                )
                if attempt == 0 and _worth_retrying(resp):
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                resp.raise_for_status()
                message = resp.json()["choices"][0]["message"]
                break
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                raise LLMError(f"LLM request failed: {exc}") from exc

        tool_calls = [
            ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=tc["function"]["name"],
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for tc in (message.get("tool_calls") or [])
            if tc.get("function", {}).get("name")
        ]
        content = clean_content(message.get("content"))
        if not tool_calls and content:
            names = {t["function"]["name"] for t in tools}
            recovered = _tool_call_from_text(content, names)
            if recovered:
                return LLMResponse(content=None, tool_calls=[recovered])
        return LLMResponse(content=content, tool_calls=tool_calls)


class MockTravelLLM:
    """Rule-based stand-in for demos and UI work without a model server.

    It searches the catalog with the customer's words and lists what it finds,
    and hands over to a human when asked. It does not take bookings.
    """

    HUMAN_WORDS = ("human", "agent", "employee", "person", "موظف", "شخص")

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        last = messages[-1]
        if last["role"] == "user":
            text = last.get("content") or ""
            if any(w in text.lower() for w in self.HUMAN_WORDS):
                return LLMResponse(None, [ToolCall("mock_h", "request_human_agent", {"reason": "Customer asked"})])
            return LLMResponse(None, [ToolCall("mock_s", "search_packages", {"query": text})])
        if last["role"] == "tool":
            data = _parse_arguments(last.get("content"))
            if data.get("handed_over"):
                return LLMResponse("I've asked one of our travel consultants to join. They'll reply here shortly.")
            items = data.get("results") or data.get("alternatives") or []
            if not items:
                return LLMResponse("I couldn't find a matching trip right now. Could you tell me another destination?")
            lines = [
                f"• {p['title']} ({p['duration_days']} days) from {p['price_per_person']} {p['currency']}"
                for p in items[:5]
            ]
            intro = "Here are some trips you may like:" if data.get("results") else "No exact match, but you may like:"
            return LLMResponse(intro + "\n" + "\n".join(lines) + "\nWhich one interests you?")
        return LLMResponse("How can I help you plan your trip?")


_client_override: LLMClient | None = None


def set_llm_client(client: LLMClient | None) -> None:
    """Used by tests to plug in a scripted model."""
    global _client_override
    _client_override = client


def get_llm_client() -> LLMClient:
    if _client_override is not None:
        return _client_override
    s = get_settings()
    if s.llm_provider == "mock":
        return MockTravelLLM()
    return OpenAICompatibleClient(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        timeout=s.llm_timeout_seconds,
    )
