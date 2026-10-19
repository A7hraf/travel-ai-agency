"""Platform settings page (platform owner only): the AI brain and the shared WhatsApp app.

Values saved here override the environment variables (see app/platform_settings.py).
Secrets are write-only: the API only says whether they are set.
"""

import os
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import platform_settings as ps
from ..ai.health import check_ai
from ..config import get_settings
from ..database import engine, get_db
from ..deps import require_system_admin
from ..models import Company, PlatformSetting, User
from ..ratelimit import limiter
from ..schemas import AICheckOut
from ..security import random_token

router = APIRouter(prefix="/api/system/platform-settings", tags=["platform settings"])

# The shared webhook of the platform's Meta app (routers/whatsapp.py).
PLATFORM_WEBHOOK_PATH = "/api/webhooks/whatsapp"

_URL_RE = re.compile(r"^https?://[^\s/]+(/\S*)?$", re.IGNORECASE)
_API_VERSION_RE = re.compile(r"^v\d{1,3}\.\d{1,3}$")
_VERIFY_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~-]{8,64}$")


# --- Schemas ----------------------------------------------------------------------


class SettingOut(BaseModel):
    """One setting. For secrets ``value``, ``effective`` and ``env_value`` are always empty."""

    key: str
    secret: bool
    # Saved on the settings page (None: not saved here, the environment variable is used).
    value: str | bool | None = None
    saved: bool
    env_value: str | bool | None = None
    env_set: bool
    effective: str | bool | None = None
    effective_set: bool
    source: Literal["database", "environment"]
    updated_at: datetime | None = None
    updated_by: str | None = None


class PlatformInfo(BaseModel):
    version: str
    commit: str | None
    database: str
    environment: str
    demo_data: bool
    companies: int


class PlatformSettingsOut(BaseModel):
    ai: dict[str, SettingOut]
    whatsapp: dict[str, SettingOut]
    webhook_path: str
    info: PlatformInfo


def _clean_url(v: str | None) -> str | None:
    if v is None or not v.strip():
        return v
    v = v.strip().rstrip("/")
    if not _URL_RE.match(v):
        raise ValueError("The server address must start with http:// or https://")
    return v


def _clean_models(v: str | None) -> str | None:
    if v is None:
        return v
    return ", ".join(ps.split_models(v))


class AIFields(BaseModel):
    llm_provider: Literal["openai_compatible", "mock"] | None = None
    llm_base_url: str | None = Field(default=None, max_length=500)
    llm_model: str | None = Field(default=None, max_length=200)
    llm_fallback_models: str | None = Field(default=None, max_length=1000)
    llm_reasoning_effort: Literal["", "low", "medium", "high"] | None = None
    llm_api_key: str | None = Field(default=None, max_length=1000)

    _url = field_validator("llm_base_url")(_clean_url)
    _models = field_validator("llm_fallback_models")(_clean_models)

    @field_validator("llm_model", "llm_api_key")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class WhatsAppFields(BaseModel):
    whatsapp_app_secret: str | None = Field(default=None, max_length=500)
    whatsapp_default_access_token: str | None = Field(default=None, max_length=2000)
    whatsapp_verify_token: str | None = Field(default=None, max_length=64)
    whatsapp_api_version: str | None = Field(default=None, max_length=10)
    whatsapp_share_default_token: bool | None = None

    @field_validator("whatsapp_app_secret", "whatsapp_default_access_token")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("whatsapp_verify_token")
    @classmethod
    def _verify_token(cls, v: str | None) -> str | None:
        if v and v.strip() and not _VERIFY_TOKEN_RE.match(v.strip()):
            raise ValueError("The verify token must be 8 to 64 letters, numbers, dots, dashes or underscores")
        return v.strip() if v else v

    @field_validator("whatsapp_api_version")
    @classmethod
    def _version(cls, v: str | None) -> str | None:
        if v and v.strip() and not _API_VERSION_RE.match(v.strip()):
            raise ValueError("The API version looks like v21.0")
        return v.strip() if v else v


class PlatformSettingsUpdate(BaseModel):
    """Only the fields sent are changed. null or "" removes the saved value (the environment is used)."""

    ai: AIFields | None = None
    whatsapp: WhatsAppFields | None = None


class VerifyTokenOut(BaseModel):
    whatsapp_verify_token: str


# --- Helpers ----------------------------------------------------------------------


def _is_set(value) -> bool:
    if isinstance(value, bool):
        return True
    return bool(value and str(value).strip())


def _setting_out(d: ps.SettingDef, rows: dict[str, PlatformSetting]) -> SettingOut:
    row = rows.get(d.key)
    saved_raw = (row.secret_value if d.secret else row.value) if row is not None else None
    saved = _is_set(saved_raw)
    env = ps.env_value(d.key)
    effective = ps._typed(d, saved_raw) if saved else env
    hide = d.secret
    return SettingOut(
        key=d.key,
        secret=d.secret,
        value=None if hide or not saved else ps._typed(d, saved_raw),
        saved=saved,
        env_value=None if hide else env,
        env_set=_is_set(env),
        effective=None if hide else effective,
        effective_set=_is_set(effective),
        source="database" if saved else "environment",
        updated_at=row.updated_at if row is not None and saved else None,
        updated_by=row.updated_by if row is not None and saved else None,
    )


def _settings_out(request: Request, db: Session) -> PlatformSettingsOut:
    rows = {r.key: r for r in db.scalars(select(PlatformSetting)).all()}
    s = get_settings()
    groups: dict[str, dict[str, SettingOut]] = {"ai": {}, "whatsapp": {}}
    for d in ps.DEFINITIONS.values():
        groups[d.group][d.key] = _setting_out(d, rows)
    commit = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or os.environ.get("SOURCE_COMMIT")
    info = PlatformInfo(
        version=str(getattr(request.app, "version", "") or ""),
        commit=commit[:12] if commit else None,
        database="PostgreSQL" if engine.dialect.name == "postgresql" else
                 "SQLite" if engine.dialect.name == "sqlite" else engine.dialect.name,
        environment=s.environment,
        demo_data=bool(s.seed_demo_data),
        companies=db.scalar(select(func.count(Company.id))) or 0,
    )
    return PlatformSettingsOut(ai=groups["ai"], whatsapp=groups["whatsapp"],
                               webhook_path=PLATFORM_WEBHOOK_PATH, info=info)


# --- Endpoints ----------------------------------------------------------------------


@router.get("", response_model=PlatformSettingsOut)
def read_settings(request: Request, db: Session = Depends(get_db), _: User = Depends(require_system_admin)):
    return _settings_out(request, db)


@router.put("", response_model=PlatformSettingsOut)
def update_settings(body: PlatformSettingsUpdate, request: Request, db: Session = Depends(get_db),
                    me: User = Depends(require_system_admin)):
    changes: dict = {}
    for group in (body.ai, body.whatsapp):
        if group is not None:
            changes.update(group.model_dump(exclude_unset=True))
    ps.save(db, changes, me.email)
    return _settings_out(request, db)


@router.post("/whatsapp/verify-token", response_model=VerifyTokenOut)
def regenerate_verify_token(db: Session = Depends(get_db), me: User = Depends(require_system_admin)):
    """A new random verify token. Meta must then be given the new one (Verify and save)."""
    token = random_token(18)
    ps.save(db, {"whatsapp_verify_token": token}, me.email)
    return VerifyTokenOut(whatsapp_verify_token=token)


@router.post("/ai-check", response_model=AICheckOut)
def test_ai(body: AIFields | None = None, me: User = Depends(require_system_admin)):
    """Tests the AI with the values on the form (unsaved ones too); empty fields use the saved values."""
    limiter.check(f"ai-check:{me.id}", 6, "Please wait a minute before testing again")
    changes: dict = {}
    if body is not None:
        data = body.model_dump(exclude_unset=True)
        mapping = {"llm_provider": "provider", "llm_base_url": "base_url", "llm_model": "model",
                   "llm_fallback_models": "fallback_models", "llm_reasoning_effort": "reasoning_effort",
                   "llm_api_key": "api_key"}
        for key, name in mapping.items():
            value = data.get(key)
            # A blank field means "the value in effect" (saved, or from the environment).
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            changes[name] = value
    return check_ai(ps.llm_config(**changes))
