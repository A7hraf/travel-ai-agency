"""Small, idempotent schema upgrades for databases created by an older version.

Runs at every start after create_all (which only creates missing tables). Each step
checks first, so running it twice changes nothing.
"""

import json
import logging

from sqlalchemy import Engine, inspect, or_, select, text
from sqlalchemy.orm import Session

from .crypto import PREFIX, encrypt
from .security import random_token

log = logging.getLogger(__name__)

NEW_COLUMNS = [
    ("companies", "max_services", "INTEGER"),
    ("companies", "ai_welcome_message_ar", "TEXT"),
    ("companies", "whatsapp_app_secret", "TEXT"),
    ("companies", "whatsapp_webhook_key", "VARCHAR(64)"),
    ("companies", "whatsapp_verify_token", "VARCHAR(64)"),
    ("users", "tokens_valid_after", "TIMESTAMP WITH TIME ZONE"),
    ("companies", "branding", "JSON"),
    ("tickets", "seats_held", "INTEGER NOT NULL DEFAULT 0"),
    ("conversations", "was_handed_over", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("conversations", "booking_quote", "JSON"),
    ("tickets", "seats_held_at", "TIMESTAMP WITH TIME ZONE"),
    # Instagram Direct channel
    ("companies", "instagram_account_id", "VARCHAR(64)"),
    ("companies", "instagram_username", "VARCHAR(100)"),
    ("companies", "instagram_access_token", "TEXT"),
    ("companies", "instagram_app_secret", "TEXT"),
    ("companies", "instagram_webhook_key", "VARCHAR(64)"),
    ("companies", "instagram_verify_token", "VARCHAR(64)"),
    ("customers", "instagram_id", "VARCHAR(64)"),
    ("companies", "instagram_token_refreshed_at", "TIMESTAMP WITH TIME ZONE"),
    # Plans: when the AI first answered the chat (monthly AI conversation limit)
    ("conversations", "ai_started_at", "TIMESTAMP WITH TIME ZONE"),
    # Business tools: staff notes and labels on customers
    ("customers", "notes", "TEXT"),
    ("customers", "tags", "JSON"),
    # Business accounts (clients and vendors)
    ("companies", "b2b", "JSON"),
    ("users", "partner_id", "INTEGER REFERENCES partners(id) ON DELETE CASCADE"),
    ("customers", "partner_id", "INTEGER REFERENCES partners(id) ON DELETE SET NULL"),
    # Advanced features and the members community
    ("companies", "addons", "JSON"),
    ("companies", "membership", "JSON"),
    ("customers", "member_level", "VARCHAR(10)"),
    ("customers", "member_since", "TIMESTAMP WITH TIME ZONE"),
    ("customers", "member_note", "VARCHAR(500)"),
    # Private trips page and feedback
    ("customers", "portal_valid_after", "TIMESTAMP WITH TIME ZONE"),
    ("tickets", "feedback_requested_at", "TIMESTAMP WITH TIME ZONE"),
    # Custom trips of individual travellers and the AI planner
    ("trip_requests", "customer_id", "INTEGER REFERENCES customers(id) ON DELETE SET NULL"),
    ("trip_options", "estimate_price", "NUMERIC(12, 3)"),
    ("trip_options", "ai_reason", "TEXT"),
    # One request flow: services, quotation loop, options on client requests
    ("companies", "payment_info", "JSON"),
    ("tickets", "service_id", "INTEGER REFERENCES services(id) ON DELETE SET NULL"),
    ("tickets", "answers", "JSON"),
    ("tickets", "parts", "JSON"),
    ("tickets", "destination", "VARCHAR(120)"),
    ("tickets", "origin", "VARCHAR(120)"),
    ("tickets", "return_date", "VARCHAR(20)"),
    ("tickets", "quote_round", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "client_note", "TEXT"),
    ("tickets", "last_client_at", "TIMESTAMP WITH TIME ZONE"),
    ("tickets", "legacy_ref", "VARCHAR(60)"),
    ("tickets", "checklist", "JSON"),
    ("companies", "quote_settings", "JSON"),
    ("tickets", "cost_price", "NUMERIC(12, 3)"),
    ("tickets", "itinerary", "JSON"),
    ("services", "documents", "JSON"),
    ("services", "workflow", "JSON"),
    ("tickets", "workflow", "JSON"),
    ("conversations", "language", "VARCHAR(5)"),
    ("conversations", "verify_phone", "VARCHAR(20)"),
    ("companies", "sla", "JSON"),
    ("trip_options", "photos", "JSON"),
    ("tickets", "quote_meta", "JSON"),
    ("tickets", "checkin", "JSON"),
    ("companies", "calendar_settings", "JSON"),
    ("trip_requests", "share_client", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("trip_requests", "client_rating", "INTEGER"),
    ("trip_requests", "client_comment", "TEXT"),
    ("partners", "quote_settings", "JSON"),
    ("appointments", "client_remind_minutes", "INTEGER"),
    ("appointments", "remind_owner", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("appointments", "owner_reminded_at", "TIMESTAMP WITH TIME ZONE"),
    ("tickets", "questions", "JSON"),
    ("customers", "preferences", "JSON"),
    ("travel_packages", "price_mode", "VARCHAR(12) NOT NULL DEFAULT 'shown'"),
    ("travel_packages", "kind", "VARCHAR(12) NOT NULL DEFAULT 'trip'"),
    ("conversations", "language_fixed", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("tickets", "cancel_info", "JSON"),
    ("request_files", "requirement", "VARCHAR(40)"),
    ("companies", "reminder_template", "JSON"),
    ("users", "whatsapp_number", "VARCHAR(30)"),
    ("users", "ai_features", "JSON"),
    ("trip_options", "supplier_id", "INTEGER REFERENCES suppliers(id) ON DELETE SET NULL"),
    ("trip_options", "image_url", "VARCHAR(500)"),
    ("tickets", "documents_sent_at", "TIMESTAMP WITH TIME ZONE"),
    ("trip_options", "ticket_id", "INTEGER REFERENCES tickets(id) ON DELETE CASCADE"),
    ("trip_options", "link", "VARCHAR(500)"),
]

# Unique indexes of the Instagram columns (same names create_all gives them on a new database).
INSTAGRAM_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_instagram_account_id ON companies (instagram_account_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_instagram_webhook_key ON companies (instagram_webhook_key)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_company_instagram ON customers (company_id, instagram_id)",
]

# Indexes of the business-account columns (same names create_all gives them on a new database).
PARTNER_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_users_partner_id ON users (partner_id)",
    "CREATE INDEX IF NOT EXISTS ix_customers_partner_id ON customers (partner_id)",
    "CREATE INDEX IF NOT EXISTS ix_customers_member_level ON customers (member_level)",
]

# Filled once, right after the column is added.
BACKFILL = {
    ("tickets", "seats_held"): (
        "UPDATE tickets SET seats_held = adults + children WHERE status = 'confirmed' AND package_id IN "
        "(SELECT id FROM travel_packages WHERE seats_available IS NOT NULL)"
    ),
    # Released together with seats per departure date: seats_available used to be the seats left in one
    # pool for every date (booked seats were taken off it). It is now the seats of each departure, so the
    # booked seats are added back once.
    ("tickets", "seats_held_at"): (
        "UPDATE travel_packages SET seats_available = seats_available + (SELECT COALESCE(SUM(t.seats_held), 0) "
        "FROM tickets t WHERE t.package_id = travel_packages.id) WHERE seats_available IS NOT NULL"
    ),
    # Chats the AI already answered count for the month they started in (plan usage meters).
    ("conversations", "ai_started_at"): (
        "UPDATE conversations SET ai_started_at = created_at WHERE id IN "
        "(SELECT conversation_id FROM messages WHERE sender = 'customer')"
    ),
    ("conversations", "was_handed_over"): (
        "UPDATE conversations SET was_handed_over = TRUE WHERE handover_reason IS NOT NULL "
        "OR status = 'human' OR assigned_to_id IS NOT NULL"
    ),
}

# Omani rial prices need 3 decimals (1 rial = 1000 baisa).
THREE_DECIMALS = [
    ("travel_packages", "price_per_person"),
    ("travel_packages", "child_price"),
    ("tickets", "total_price"),
]


def _add_missing_columns(conn, engine: Engine) -> None:
    """Safety net: a column the code knows but the database lacks (an entry forgotten in NEW_COLUMNS)
    is added as an empty, nullable column, so a release never breaks pages on an older database."""
    from .database import Base  # noqa: PLC0415

    insp = inspect(conn)
    tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue  # create_all makes whole new tables
        have = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            ddl = column.type.compile(dialect=engine.dialect)
            log.warning("Database upgrade: adding missing column %s.%s (%s)", table.name, column.name, ddl)
            conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {ddl}'))


def upgrade(engine: Engine) -> None:
    from .models import Company  # noqa: PLC0415 (models import the database module)

    grant_customers_manage = _customers_permission_is_new(engine)  # business tools
    grant_ai_training = _ai_training_is_new(engine)
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # Several app instances may start together: only one upgrades at a time.
            conn.execute(text("SELECT pg_advisory_xact_lock(724501)"))
        insp = inspect(conn)
        tables = set(insp.get_table_names())
        for table, column, ddl in NEW_COLUMNS:
            if table in tables and column not in {c["name"] for c in insp.get_columns(table)}:
                log.info("Database upgrade: adding %s.%s", table, column)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                if (table, column) in BACKFILL:
                    conn.execute(text(BACKFILL[(table, column)]))
        _add_missing_columns(conn, engine)
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
        if "users" in tables:
            # Emails used to be unique across the whole platform; now once per company.
            for ix in insp.get_indexes("users"):
                if ix["name"] == "ix_users_email" and ix.get("unique"):
                    log.info("Database upgrade: user emails unique per company")
                    conn.execute(text("DROP INDEX ix_users_email"))
                    conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_company_email ON users (company_id, email)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_platform_email ON users (email) "
                              "WHERE company_id IS NULL"))
        if {"companies", "customers"} <= tables:
            for ddl in INSTAGRAM_INDEXES:
                conn.execute(text(ddl))
        if {"users", "customers"} <= tables:
            for ddl in PARTNER_INDEXES:
                conn.execute(text(ddl))
        if "trip_requests" in tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trip_options_ticket_id ON trip_options (ticket_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trip_options_supplier_id ON trip_options (supplier_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tickets_service_id ON tickets (service_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tickets_legacy_ref ON tickets (legacy_ref)"))
            if engine.dialect.name == "postgresql":
                # Options now belong to a business request or to a client's request. (A SQLite development
                # database made before this keeps the old rule: recreate it.)
                conn.execute(text("ALTER TABLE trip_options ALTER COLUMN request_id DROP NOT NULL"))
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

    # Every company gets its own Instagram webhook address and verify token.
    with Session(engine) as db:
        missing = db.scalars(
            select(Company).where(
                or_(Company.instagram_webhook_key.is_(None), Company.instagram_verify_token.is_(None))
            )
        ).all()
        for company in missing:
            company.instagram_webhook_key = company.instagram_webhook_key or random_token(18)
            company.instagram_verify_token = company.instagram_verify_token or random_token(18)
        db.commit()
    if grant_customers_manage:
        _grant_customers_manage(engine)
    if grant_ai_training:
        _grant_ai_training(engine)
    _upgrade_plans(engine)


# --- Business tools: the new "customers.manage" permission -------------------------------------

def _customers_permission_is_new(engine: Engine) -> bool:
    """True on the first start with the Customers page: customers has no notes column yet."""
    insp = inspect(engine)
    if not {"customers", "users"} <= set(insp.get_table_names()):
        return False
    return "notes" not in {c["name"] for c in insp.get_columns("customers")}


def _ai_training_is_new(engine: Engine) -> bool:
    """True on the first start where editing the AI's training is a feature (companies has no max_services yet)."""
    insp = inspect(engine)
    if "companies" not in insp.get_table_names():
        return False
    return "max_services" not in {c["name"] for c in insp.get_columns("companies")}


def _grant_ai_training(engine: Engine) -> None:
    """Editing the AI's training became a feature the platform owner gives: the companies that could already
    do it keep it (once; the owner can take it back), new companies start without it."""
    with engine.begin() as conn:
        for cid, raw in conn.execute(text("SELECT id, addons FROM companies")).all():
            addons = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if not isinstance(addons, dict) or "ai_training" in addons:
                continue
            addons["ai_training"] = {"on": True}
            value = "CAST(:a AS JSON)" if engine.dialect.name == "postgresql" else ":a"
            conn.execute(text(f"UPDATE companies SET addons = {value} WHERE id = :id"), {"a": json.dumps(addons), "id": cid})


def _grant_customers_manage(engine: Engine) -> None:
    """Existing support employees who see conversations get "customers.manage", like new support
    accounts (company admins always have every permission). Runs once, when the column is added, so
    an admin who later takes the permission away keeps it that way."""
    from .models import Role, User  # noqa: PLC0415
    from .permissions import clean_permissions  # noqa: PLC0415

    with Session(engine) as db:
        for user in db.scalars(select(User).where(User.role == Role.SUPPORT)).all():
            perms = list(user.permissions or [])
            if "conversations.view" in perms and "customers.manage" not in perms:
                user.permissions = clean_permissions([*perms, "customers.manage"])
        db.commit()



def _upgrade_plans(engine: Engine) -> None:
    """Subscription plans: the default catalogue on first start, and a subscription for every company
    that existed before plans (status active for a year, on a plan that allows what it already uses,
    so the upgrade never locks a company out). See services/plans.py."""
    from .services.plans import backfill_subscriptions, ensure_default_plans  # noqa: PLC0415

    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if "conversations" in tables and "ai_started_at" in {c["name"] for c in inspect(conn).get_columns("conversations")}:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conversations_company_ai_started "
                              "ON conversations (company_id, ai_started_at)"))
        if not {"plans", "subscriptions", "companies"} <= tables:
            return
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(724502)"))
        db = Session(bind=conn)
        ensure_default_plans(db)
        backfill_subscriptions(db)
        db.flush()
        db.close()
