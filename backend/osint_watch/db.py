from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import settings


def required_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("Expected database row was not returned")
    return row


@contextmanager
def connection() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with psycopg.connect(settings().database_url, row_factory=dict_row) as conn:
        yield conn


def migrate() -> None:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(701924)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if not conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,)
            ).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.name,))


if __name__ == "__main__":
    migrate()
