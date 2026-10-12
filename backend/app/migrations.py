"""Small, idempotent schema upgrades for databases created by an older version.

Runs at every start after create_all (which only creates missing tables). Each step
checks first, so running it twice changes nothing.
"""

import logging

from sqlalchemy import Engine, inspect, or_, select, text
from sqlalchemy.orm import Session

from .crypto import PREFIX, encrypt
from .security import random_token

log = logging.getLogger(__name__)

NEW_COLUMNS = [
    ("companies", "ai_welcome_message_ar", "TEXT"),
    ("companies", "whatsapp_app_secret", "TEXT"),
    ("companies", "whatsapp_webhook_key", "VARCHAR(64)"),
    ("companies", "whatsapp_verify_token", "VARCHAR(64)"),
    ("users", "tokens_valid_after", "TIMESTAMP WITH TIME ZONE"),
    ("companies", "branding", "JSON"),
]

# Omani rial prices need 3 decimals (1 rial = 1000 baisa).
THREE_DECIMALS = [
    ("travel_packages", "price_per_person"),
    ("travel_packages", "child_price"),
    ("tickets", "total_price"),
]


def upgrade(engine: Engine) -> None:
    from .models import Company  # noqa: PLC0415 (models import the database module)

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in NEW_COLUMNS:
            if table in tables and column not in {c["name"] for c in insp.get_columns(table)}:
                log.info("Database upgrade: adding %s.%s", table, column)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        if engine.dialect.name == "postgresql":
            for table, column in THREE_DECIMALS:
                col = next((c for c in insp.get_columns(table) if c["name"] == column), None)
                if col is not None and getattr(col["type"], "scale", None) != 3:
                    log.info("Database upgrade: %s.%s to 3 decimals", table, column)
                    conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE NUMERIC(12, 3)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_whatsapp_webhook_key "
                "ON companies (whatsapp_webhook_key)"
            )
        )
        # WhatsApp tokens saved before encryption existed are encrypted now.
        rows = conn.execute(
            text("SELECT id, whatsapp_access_token FROM companies WHERE whatsapp_access_token IS NOT NULL")
        ).all()
        for company_id, token in rows:
            if token and not token.startswith(PREFIX):
                conn.execute(
                    text("UPDATE companies SET whatsapp_access_token = :t WHERE id = :id"),
                    {"t": encrypt(token), "id": company_id},
                )

    with Session(engine) as db:
        missing = db.scalars(
            select(Company).where(
                or_(Company.whatsapp_webhook_key.is_(None), Company.whatsapp_verify_token.is_(None))
            )
        ).all()
        for company in missing:
            company.whatsapp_webhook_key = company.whatsapp_webhook_key or random_token(18)
            company.whatsapp_verify_token = company.whatsapp_verify_token or random_token(18)
        db.commit()
