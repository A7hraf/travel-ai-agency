"""An older database must always be brought up to date at start, even if an upgrade step was forgotten."""

from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.migrations import upgrade


def test_missing_columns_are_added_at_start(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # As if this database was created before these columns existed.
        conn.execute(text("ALTER TABLE conversations DROP COLUMN ai_started_at"))
        conn.execute(text("ALTER TABLE customers DROP COLUMN notes"))
        conn.execute(text("ALTER TABLE tickets DROP COLUMN internal_notes"))  # not in NEW_COLUMNS
    upgrade(engine)
    upgrade(engine)  # running it again changes nothing
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        assert {c.name for c in table.columns} <= have, table.name


def test_database_from_before_business_accounts(tmp_path):
    """Business accounts: new tables are made by create_all, the new columns of old tables by upgrade."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in ("users", "customers"):
            conn.execute(text(f"DROP INDEX ix_{table}_partner_id"))
            # SQLite can't drop a column that has a foreign key: rebuild the table without it.
            cols = [c["name"] for c in inspect(conn).get_columns(table) if c["name"] != "partner_id"]
            listed = ", ".join(cols)
            conn.execute(text(f"CREATE TABLE {table}_old AS SELECT {listed} FROM {table}"))
            conn.execute(text(f"DROP TABLE {table}"))
            conn.execute(text(f"ALTER TABLE {table}_old RENAME TO {table}"))
        conn.execute(text("ALTER TABLE companies DROP COLUMN b2b"))
        conn.execute(text("DROP TABLE partner_phones"))
        conn.execute(text("DROP TABLE partners"))
    Base.metadata.create_all(engine)  # what the app does at start, before upgrade
    upgrade(engine)
    upgrade(engine)
    insp = inspect(engine)
    assert "partner_id" in {c["name"] for c in insp.get_columns("users")}
    assert "partner_id" in {c["name"] for c in insp.get_columns("customers")}
    assert "b2b" in {c["name"] for c in insp.get_columns("companies")}
    assert "ix_users_partner_id" in {i["name"] for i in insp.get_indexes("users")}
    assert {"partners", "partner_phones"} <= set(insp.get_table_names())
