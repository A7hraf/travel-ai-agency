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
_OPEN_THINK_RE = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)
_CLOSE_THINK_RE = re.compile(r"\A.*?</think>", re.DOTALL | re.IGNORECASE)

# Set in the arguments when the model sent arguments that are not a JSON object.
INVALID_ARGUMENTS = "__invalid_arguments__"


def clean_content(text: str | None) -> str | None:
    """Remove hidden reasoning blocks some open models (Qwen3, DeepSeek-R1) emit, including a
    block that was never closed or whose opening tag was cut off."""
    if text is None:
        return None
    text = _THINK_RE.sub("", text)
    text = _OPEN_THINK_RE.sub("", text)
    text = _CLOSE_THINK_RE.sub("", text)
    return text.strip()


def _parse_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    value = raw
    # Some models double-encode: the arguments are a JSON string that contains JSON.
    for _ in range(2):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {INVALID_ARGUMENTS: str(raw)[:300]}
    return value if isinstance(value, dict) else {INVALID_ARGUMENTS: str(raw)[:300]}


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
    if isinstance(obj.get("function"), dict):  # OpenAI shape: {"type": "function", "function": {...}}
        obj = obj["function"]
    name = obj.get("name") or obj.get("function") or obj.get("tool")
    if not isinstance(name, str):
        return None
    name = name.removeprefix("functions.")
    if name not in tool_names:
        return None
    args = obj.get("arguments", obj.get("parameters", {}))
    return ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=_parse_arguments(args))


def looks_like_tool_call(content: str) -> bool:
    """A reply that is only a JSON object naming a function must never reach the customer."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return text.startswith("{") and text.endswith("}") and ('"name"' in text or '"function"' in text)


RETRY_DELAY_SECONDS = 2.0
MAX_RETRY_WAIT_SECONDS = 20.0
_MODEL_GONE = ("model_decommissioned", "decommissioned", "model_not_found", "does not exist", "not supported")


def provider_error(resp: httpx.Response) -> str:
    """The provider's own error text, e.g. Groq's {"error": {"message": ...}}."""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict) and err.get("message"):
            return f"{resp.status_code}: {err['message']}"
        if isinstance(err, str):
            return f"{resp.status_code}: {err}"
    except ValueError:
        pass
    return f"{resp.status_code}: {resp.text[:300]}"


def _retry_wait(resp: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when retrying will not help."""
    transient = resp.status_code in (429, 500, 502, 503, 504) or (
        resp.status_code == 400 and "tool_use_failed" in resp.text
    )
    if not transient:
        return None
    try:
        wait = float(resp.headers.get("retry-after", ""))
    except ValueError:
        wait = RETRY_DELAY_SECONDS * (attempt + 1)
    return min(max(wait, 0.0), MAX_RETRY_WAIT_SECONDS)


def _model_gone(resp: httpx.Response) -> bool:
    return resp.status_code in (400, 404) and any(word in resp.text.lower() for word in _MODEL_GONE)


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float, timeout: float,
                 fallback_models: list[str] | None = None, reasoning_effort: str = ""):
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.models = [m for m in [model.strip(), *(fallback_models or [])] if m]
        self.temperature = temperature
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort.strip()
        self.last_model: str | None = None

    @property
    def model(self) -> str:
        return self.models[0]

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        last_error = "no model configured"
        for model in self.models:
            payload: dict = {"model": model, "messages": messages, "temperature": self.temperature}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort
            waited = 0.0
            resp = None
            for attempt in range(3):
                try:
                    resp = httpx.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=self.timeout
                    )
                except httpx.HTTPError as exc:
                    resp = None
                    last_error = f"{model} -> cannot reach the AI server at {self.base_url}: {exc}"
                    break
                if resp.is_success:
                    try:
                        parsed = self._parse(resp.json()["choices"][0]["message"], tools)
                        self.last_model = model
                        return parsed
                    except (KeyError, IndexError, ValueError, TypeError) as exc:
                        raise LLMError(f"Unexpected answer from the AI server: {exc}") from exc
                last_error = f"{model} -> {provider_error(resp)}"
                wait = _retry_wait(resp, attempt)
                if wait is None or attempt == 2 or waited + wait > MAX_RETRY_WAIT_SECONDS:
                    break
                log.info("AI busy (%s), retrying in %.1fs", resp.status_code, wait)
                time.sleep(wait)
                waited += wait
            # Try the next model when this one is retired, busy (rate limit, server error) or unreachable.
            # Other errors (a wrong API key, a bad request) would fail the same way on every model.
            retry_next = resp is None or _model_gone(resp) or _retry_wait(resp, 0) is not None
            if retry_next and model != self.models[-1]:
                log.warning("AI model %s failed, trying the next one: %s", model, last_error)
                continue
            break
        raise LLMError(last_error)

    @staticmethod
    def _parse(message: dict, tools: list[dict]) -> LLMResponse:
        tool_calls = [
            ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=tc["function"]["name"].removeprefix("functions."),
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for tc in (message.get("tool_calls") or [])
            if (tc.get("function") or {}).get("name")
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

    HUMAN_WORDS = re.compile(r"\b(human|agent|employee|staff)\b|موظف|انسان|إنسان", re.IGNORECASE)

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        last = messages[-1]
        if last["role"] == "user":
            text = last.get("content") or ""
            if self.HUMAN_WORDS.search(text):
                return LLMResponse(None, [ToolCall("mock_h", "request_human_agent", {"reason": "Customer asked"})])
            return LLMResponse(None, [ToolCall("mock_s", "search_packages", {"query": text})])
        if last["role"] == "tool":
            data = _parse_arguments(last.get("content"))
            if data.get("handed_over"):
                return LLMResponse("I've asked one of our travel consultants to join. They'll reply here shortly.")
            items = data.get("results") or data.get("alternatives") or []
            if not items:
                return LLMResponse("I couldn't find a matching trip right now. Could you tell me another destination?")
            def price(p: dict) -> str:
                amount = float(p["price_per_person"])
                return f"{p['currency']} {amount:,.3f}" if p["currency"] == "OMR" else f"{amount:,.2f} {p['currency']}"

            lines = [f"• {p['title']} ({p['duration_days']} days) from {price(p)}" for p in items[:5]]
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
        fallback_models=[m.strip() for m in s.llm_fallback_models.split(",") if m.strip()],
        reasoning_effort=s.llm_reasoning_effort,
    )
