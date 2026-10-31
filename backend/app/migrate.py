"""Lightweight schema upgrade for the SQLite database.

`Base.metadata.create_all()` creates missing tables but never adds columns to
tables that already exist. Existing `certichain.db` files therefore need the
new certificate columns added in place. This runs safely on every start-up.
"""

from sqlalchemy import inspect, text

from app.database import Base
from app import models  # noqa: F401  (registers the tables on Base)

# table -> {column: SQL type}. Names are constants defined here, not user input.
NEW_COLUMNS = {
    "certificates": {
        "issued_by": "VARCHAR",
        "revoked_at": "DATETIME",
        "revoked_by": "VARCHAR",
        "revoke_reason": "VARCHAR",
    },
}


def ensure_schema(engine) -> list[str]:
    """Create missing tables and add missing columns. Returns what was added."""
    Base.metadata.create_all(bind=engine)

    added = []
    inspector = inspect(engine)

    with engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            existing = {col["name"] for col in inspector.get_columns(table)}

            for name, sql_type in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                    )
                    added.append(f"{table}.{name}")

    return added
