import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders

from .config import DEFAULT_SECRET_KEY, get_settings
from .database import SessionLocal, init_db
from .routers import (
    auth,
    company,
    conversations,
    media,
    packages,
    public,
    system_admin,
    tickets,
    training,
    users,
    whatsapp,
)
from .seed import DEFAULT_ADMIN_PASSWORD, ensure_system_admin, protect_demo_accounts, seed_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travel_ai")

settings = get_settings()
PRODUCTION = settings.environment == "production"


def check_production_settings() -> None:
    if settings.secret_key == DEFAULT_SECRET_KEY or len(settings.secret_key) < 32:
        raise RuntimeError("Set SECRET_KEY to a long random string (32+ characters) before running in production")
    if settings.system_admin_password == DEFAULT_ADMIN_PASSWORD:
        raise RuntimeError("Set SYSTEM_ADMIN_PASSWORD to your own password before running in production")
    if not settings.whatsapp_app_secret:
        log.warning("WHATSAPP_APP_SECRET is empty: the shared WhatsApp webhook is disabled until it is set")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if PRODUCTION:
        check_production_settings()
    init_db()
    with SessionLocal() as db:
        ensure_system_admin(db)
        if settings.seed_demo_data:
            seed_demo(db, production=PRODUCTION)
        if PRODUCTION:
            protect_demo_accounts(db)
    log.info("AI brain: provider=%s model=%s", settings.llm_provider, settings.llm_model)
    yield


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
    "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeaders:
    """Browser security headers on every response; API answers are never cached."""

    def __init__(self, app, hsts: bool):
        self.app = app
        self.headers = [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
            ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
        ]
        if hsts:
            self.headers.append(("Strict-Transport-Security", "max-age=31536000"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_api = scope.get("path", "").startswith("/api/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in self.headers:
                    headers.setdefault(key, value)
                if is_api:
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)


# The interactive API docs describe every endpoint: handy in development, hidden in production.
app = FastAPI(
    title="Travel AI Agency",
    version="1.1.0",
    lifespan=lifespan,
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if PRODUCTION else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeaders, hsts=PRODUCTION)

for r in (auth, system_admin, users, company, packages, conversations, tickets, training, media, public, whatsapp):
    app.include_router(r.router)


@app.get("/api/health", tags=["health"])
def health():
    # Deliberately minimal: nothing about the AI provider, model or versions is public.
    return {"status": "ok", "demo": settings.seed_demo_data and not PRODUCTION}


def mount_frontend(application: FastAPI, dist: Path) -> None:
    """Serve the built React app: real files when they exist, index.html for app routes."""
    index = dist / "index.html"
    if not index.is_file():
        log.warning("FRONTEND_DIST=%s has no index.html; the website is not served", dist)
        return
    root = dist.resolve()
    if (dist / "assets").is_dir():
        application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


if settings.frontend_dist:
    mount_frontend(app, Path(settings.frontend_dist))
