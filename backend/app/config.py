from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-only-secret-change-me-in-production-0000"


class Settings(BaseSettings):
    """All settings come from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Travel AI Agency"
    environment: str = "development"

    # Database: PostgreSQL in production, SQLite works for local development.
    database_url: str = "sqlite:///./travel_ai.db"

    # Auth
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_minutes: int = 60 * 12
    bcrypt_rounds: int = 12
    # Key for encrypting secrets in the database (Fernet, urlsafe base64 of 32 bytes).
    # Empty: derived from SECRET_KEY.
    encryption_key: str = ""

    # The platform owner account, created on first start if it does not exist.
    system_admin_email: str = "owner@example.com"
    system_admin_password: str = "ChangeMe123!"
    system_admin_name: str = "Platform Owner"

    # Creates a demo travel company with packages and staff accounts on first start.
    seed_demo_data: bool = True

    # Folder with the built web app. When set, the API also serves the website
    # (single-container hosting such as Render). Empty: the website is served by nginx.
    frontend_dist: str = ""

    # CORS origins for the dashboard / storefront (comma separated).
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # --- AI brain -------------------------------------------------------------
    # "openai_compatible": any OpenAI-compatible server running an open-source model
    #   (Ollama, vLLM, llama.cpp server, LocalAI, or hosted Llama/Qwen on Groq/Together/OpenRouter).
    # "mock": a small rule-based stand-in so the app can be demoed without a model.
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "travel-agent"
    # Tried in order when the main model has been retired by the provider (comma separated).
    llm_fallback_models: str = ""
    # For reasoning models such as gpt-oss on Groq: "low" keeps replies fast and cheap.
    llm_reasoning_effort: str = ""
    llm_temperature: float = 0.3
    llm_timeout_seconds: float = 120.0
    llm_max_history_messages: int = 24
    llm_max_tool_rounds: int = 6

    # --- WhatsApp Cloud API (Meta) --------------------------------------------
    whatsapp_verify_token: str = "travel-ai-verify"
    # App secret used to verify the X-Hub-Signature-256 header. Leave empty to skip
    # verification (development only).
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_graph_url: str = "https://graph.facebook.com"
    # Fallback access token when a company has not stored its own.
    whatsapp_default_access_token: str = ""

    # Abuse protection (also protects your AI provider quota)
    public_chat_max_messages_per_minute: int = 12
    public_chat_max_messages_per_ip_per_minute: int = 30
    ai_max_replies_per_company_per_hour: int = 300
    public_chat_max_message_length: int = 2000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
