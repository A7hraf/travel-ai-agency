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
