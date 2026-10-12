"""'Test AI' button: one real request with the tools, reporting exactly what went wrong."""

import time
from urllib.parse import urlparse

from ..config import get_settings
from .llm import LLMError, get_llm_client
from .tools import TOOL_DEFINITIONS

TEST_MESSAGES = [
    {"role": "system", "content": "You are a travel agent. Always use the search_packages tool to find trips."},
    {"role": "user", "content": "Do you have a beach holiday?"},
]


def check_ai() -> dict:
    s = get_settings()
    client = get_llm_client()
    result: dict = {
        "provider": s.llm_provider,
        "model": s.llm_model,
        "fallback_models": [m.strip() for m in s.llm_fallback_models.split(",") if m.strip()],
        "server": urlparse(s.llm_base_url).netloc or s.llm_base_url,
        "api_key_set": bool(s.llm_api_key.strip()),
    }
    started = time.monotonic()
    try:
        resp = client.chat(TEST_MESSAGES, TOOL_DEFINITIONS)
        result["ok"] = True
        result["uses_tools"] = bool(resp.tool_calls)
        result["answered_by"] = getattr(client, "last_model", None) or s.llm_model
        result["message"] = (
            "The AI is working and can search your packages."
            if resp.tool_calls
            else "The AI answers, but did not use the package search tool. Choose a model with tool calling."
        )
    except LLMError as exc:
        result["ok"] = False
        result["uses_tools"] = False
        result["message"] = str(exc)
    result["seconds"] = round(time.monotonic() - started, 2)
    if s.llm_provider == "mock":
        result.update(ok=False, uses_tools=False,
                      message="Demo mode (LLM_PROVIDER=mock): no real AI is connected.")
    return result
