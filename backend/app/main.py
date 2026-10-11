import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import DEFAULT_SECRET_KEY, get_settings
from .database import SessionLocal, init_db
from .routers import auth, company, conversations, packages, public, system_admin, tickets, users, whatsapp
from .seed import ensure_system_admin, seed_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travel_ai")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment == "production":
        if settings.secret_key == DEFAULT_SECRET_KEY or len(settings.secret_key) < 32:
            raise RuntimeError("Set SECRET_KEY to a long random string (32+ characters) before running in production")
        if not settings.whatsapp_app_secret:
            log.warning("WHATSAPP_APP_SECRET is empty: WhatsApp webhook signatures are NOT verified")
        if settings.system_admin_password == "ChangeMe123!":
            log.warning("The system admin uses the default password. Log in and change it now.")
    init_db()
    with SessionLocal() as db:
        ensure_system_admin(db)
        if settings.seed_demo_data:
            seed_demo(db)
    log.info("AI brain: provider=%s model=%s url=%s", settings.llm_provider, settings.llm_model, settings.llm_base_url)
    yield


app = FastAPI(title="Travel AI Agency", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, system_admin, users, company, packages, conversations, tickets, public, whatsapp):
    app.include_router(r.router)


@app.get("/api/health", tags=["health"])
def health():
    s = get_settings()
    return {"status": "ok", "llm_provider": s.llm_provider, "llm_model": s.llm_model, "demo": s.seed_demo_data}
