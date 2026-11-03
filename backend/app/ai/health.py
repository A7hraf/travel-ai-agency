"""'Test AI' button: one real request with the tools, reporting exactly what went wrong."""

import time
from urllib.parse import urlparse

from ..platform_settings import LLMConfig, llm_config
from .llm import LLMError, get_llm_client
from .tools import TOOL_DEFINITIONS

TEST_MESSAGES = [
    {"role": "system", "content": "You are a travel agent. Always use the search_packages tool to find trips."},
    {"role": "user", "content": "Do you have a beach holiday?"},
]


def check_ai(config: LLMConfig | None = None) -> dict:
    """Tests the AI settings in effect, or ``config`` (values typed on the Platform settings page)."""
    cfg = config or llm_config()
    client = get_llm_client(cfg)
    result: dict = {
        "provider": cfg.provider,
        "model": cfg.model,
        "fallback_models": list(cfg.fallback_models),
        "server": urlparse(cfg.base_url).netloc or cfg.base_url,
        "api_key_set": bool((cfg.api_key or "").strip()),
    }
    started = time.monotonic()
    try:
        resp = client.chat(TEST_MESSAGES, TOOL_DEFINITIONS)
        result["ok"] = True
        result["uses_tools"] = bool(resp.tool_calls)
        result["answered_by"] = getattr(client, "last_model", None) or cfg.model
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
    if cfg.provider == "mock":
        result.update(ok=False, uses_tools=False,
                      message="Demo mode (LLM_PROVIDER=mock): no real AI is connected.")
    return result


def for_company(result: dict) -> dict:
    """The Test AI result for a travel company: whether its AI works, without the platform's
    AI server, model or provider error (those are for the platform owner only)."""
    out = {**result, "server": "", "model": "", "fallback_models": [], "answered_by": None}
    if not result.get("ok") and result.get("provider") != "mock":
        out["message"] = "The AI is not working right now. Please tell the platform owner: the details are on the platform console."
    return out
