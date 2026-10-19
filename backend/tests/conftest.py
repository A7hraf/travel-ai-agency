import os
import tempfile
from datetime import date, timedelta

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["WHATSAPP_APP_SECRET"] = ""
os.environ["SYSTEM_ADMIN_EMAIL"] = "owner@example.com"
os.environ["SYSTEM_ADMIN_PASSWORD"] = "OwnerPass123!"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai.llm import LLMResponse, set_llm_client  # noqa: E402
from app import platform_settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from app.services.whatsapp import set_whatsapp_sender  # noqa: E402


class ScriptedLLM:
    """Returns the scripted responses in order. A step may be a function of the messages."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools):
        self.calls.append([dict(m) for m in messages])
        if not self.steps:
            return LLMResponse("(no more scripted replies)")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step


class FakeWhatsApp:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, str]] = []
        self.read: list[str] = []
        self.fail = fail

    def send_text(self, company, to, text):
        from app.services.whatsapp import WhatsAppError

        if self.fail:
            raise WhatsAppError("boom")
        self.sent.append((company.whatsapp_phone_number_id, to, text))
        return f"wamid.out.{len(self.sent)}"

    def mark_read(self, company, message_id):
        self.read.append(message_id)


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    limiter.reset()
    platform_settings.invalidate()  # values saved by an earlier test must not leak into this one
    set_llm_client(None)
    set_whatsapp_sender(None)
    with TestClient(app) as c:
        yield c
    set_llm_client(None)
    set_whatsapp_sender(None)


def login(client, email, password) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def owner(client):
    return login(client, "owner@example.com", "OwnerPass123!")


def make_company(client, owner, name="Blue Sky Travel", admin_email="admin@bluesky.com", max_users=5, **extra):
    r = client.post(
        "/api/system/companies",
        headers=owner,
        json={
            "name": name,
            "max_users": max_users,
            "admin_email": admin_email,
            "admin_full_name": f"{name} Admin",
            "admin_password": "AdminPass123!",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json(), login(client, admin_email, "AdminPass123!")


def future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def make_package(client, headers, **overrides) -> dict:
    body = {
        "title": "Maldives Honeymoon",
        "destination": "Male",
        "country": "Maldives",
        "description": "Overwater villa",
        "duration_days": 6,
        "price_per_person": 2000,
        "child_price": 1000,
        "departure_dates": [future(30), future(60)],
        "tags": ["honeymoon", "beach"],
        "seats_available": 10,
    }
    body.update(overrides)
    r = client.post("/api/packages", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def company_a(client, owner):
    company, admin = make_company(client, owner)
    return company, admin


@pytest.fixture
def scripted():
    def _make(steps):
        llm = ScriptedLLM(steps)
        set_llm_client(llm)
        return llm

    return _make
