"""Platform-wide settings the owner can change on the Platform settings page.

Every value here also exists as an environment variable (see config.py). A value saved in the
database wins; when it is cleared, the environment variable is used again. Secrets (API key,
WhatsApp app secret and access token) are encrypted in the database and never sent to the browser.

Values are cached for a few seconds so the AI and the webhooks do not query the database on every
message; saving clears the cache of this process right away.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings

log = logging.getLogger(__name__)

CACHE_SECONDS = 10.0


@dataclass(frozen=True)
class SettingDef:
    key: str  # same name as the attribute in config.Settings (and the environment variable)
    group: str  # "ai" or "whatsapp"
    secret: bool = False
    kind: str = "str"  # "str" or "bool"


DEFINITIONS: dict[str, SettingDef] = {d.key: d for d in [
    SettingDef("llm_provider", "ai"),
    SettingDef("llm_base_url", "ai"),
    SettingDef("llm_model", "ai"),
    SettingDef("llm_fallback_models", "ai"),
    SettingDef("llm_reasoning_effort", "ai"),
    SettingDef("llm_api_key", "ai", secret=True),
    SettingDef("whatsapp_app_secret", "whatsapp", secret=True),
    SettingDef("whatsapp_default_access_token", "whatsapp", secret=True),
    SettingDef("whatsapp_verify_token", "whatsapp"),
    SettingDef("whatsapp_api_version", "whatsapp"),
    SettingDef("whatsapp_share_default_token", "whatsapp", kind="bool"),
]}

_lock = threading.Lock()
_cache: dict[str, str] | None = None
_loaded_at = 0.0


def _load() -> dict[str, str]:
    from .database import SessionLocal  # noqa: PLC0415
    from .models import PlatformSetting  # noqa: PLC0415

    try:
        with SessionLocal() as db:
            rows = db.scalars(select(PlatformSetting)).all()
    except SQLAlchemyError as exc:  # table not created yet (first start) or database unavailable
        log.debug("Platform settings not readable, using the environment: %s", exc)
        return {}
    out: dict[str, str] = {}
    for row in rows:
        d = DEFINITIONS.get(row.key)
        if d is None:
            continue
        value = row.secret_value if d.secret else row.value
        if value is not None and value != "":
            out[row.key] = value
    return out


def overrides() -> dict[str, str]:
    """The values saved in the database (decrypted), cached briefly."""
    global _cache, _loaded_at
    with _lock:
        if _cache is None or time.monotonic() - _loaded_at > CACHE_SECONDS:
            _cache = _load()
            _loaded_at = time.monotonic()
        return _cache


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None


def env_value(key: str):
    return getattr(get_settings(), key)


def _typed(d: SettingDef, raw: str):
    if d.kind == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return raw


def get_effective(key: str):
    """The database value when the owner saved one, otherwise the environment variable."""
    d = DEFINITIONS[key]
    saved = overrides().get(key)
    return _typed(d, saved) if saved is not None else env_value(key)


def source(key: str) -> str:
    return "database" if key in overrides() else "environment"


def split_models(text: str) -> list[str]:
    return [m.strip() for m in (text or "").split(",") if m.strip()]


# --- AI brain -------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    fallback_models: list[str]
    reasoning_effort: str


def llm_config(**changes) -> LLMConfig:
    """The AI settings in effect; keyword arguments replace single values (e.g. unsaved form values)."""
    values = {
        "provider": get_effective("llm_provider"),
        "base_url": get_effective("llm_base_url"),
        "api_key": get_effective("llm_api_key"),
        "model": get_effective("llm_model"),
        "fallback_models": split_models(get_effective("llm_fallback_models")),
        "reasoning_effort": get_effective("llm_reasoning_effort"),
    }
    values.update({k: v for k, v in changes.items() if v is not None})
    if isinstance(values["fallback_models"], str):
        values["fallback_models"] = split_models(values["fallback_models"])
    return LLMConfig(**values)


# --- WhatsApp (the platform's shared Meta app) ---------------------------------------


def effective_whatsapp_app_secret() -> str:
    return get_effective("whatsapp_app_secret") or ""


def effective_default_access_token() -> str:
    """The platform's shared access token itself (whether companies may use it: see below)."""
    return get_effective("whatsapp_default_access_token") or ""


def effective_share_default_token() -> bool:
    return bool(get_effective("whatsapp_share_default_token"))


def effective_shared_access_token() -> str | None:
    """The token for companies without their own, or None when the platform does not share it."""
    return (effective_default_access_token() or None) if effective_share_default_token() else None


def effective_verify_token() -> str:
    return get_effective("whatsapp_verify_token") or ""


def effective_api_version() -> str:
    return get_effective("whatsapp_api_version") or "v21.0"


# --- Saving -----------------------------------------------------------------------


def save(db: Session, changes: dict, updated_by: str | None) -> None:
    """Saves the given values. None or "" removes the saved value (the environment is used again)."""
    from .models import PlatformSetting, utcnow  # noqa: PLC0415

    for key, value in changes.items():
        d = DEFINITIONS[key]
        row = db.get(PlatformSetting, key)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            if row is not None:
                db.delete(row)
            continue
        if d.kind == "bool":
            text = "true" if value else "false"
        else:
            text = str(value).strip()
        if row is None:
            row = PlatformSetting(key=key)
            db.add(row)
        if d.secret:
            row.secret_value, row.value = text, None
        else:
            row.value, row.secret_value = text, None
        row.updated_at = utcnow()
        row.updated_by = updated_by
    db.commit()
    invalidate()
