"""PostgreSQL adapter. Used only when KNOW_DATABASE_URL is set."""

from __future__ import annotations

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent / "db" / "V001__chunks.sql"


def migrate(dsn: str) -> None:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=3) as connection:
        connection.execute(MIGRATION.read_text(encoding="utf-8"))
        connection.commit()
