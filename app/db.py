"""DuckDB access for the structured 'exact facts' store."""
from __future__ import annotations

from pathlib import Path

import duckdb

from app.settings import SETTINGS, ROOT

_SCHEMA = ROOT / "ingestion" / "schema.sql"


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(SETTINGS["paths"]["duckdb_path"], read_only=read_only)


def init_db() -> None:
    """Create tables if they do not exist."""
    sql = Path(_SCHEMA).read_text(encoding="utf-8")
    con = connect()
    try:
        con.execute(sql)
    finally:
        con.close()


def run_query(sql: str, params: list | None = None) -> list[dict]:
    """Run a read-only SELECT and return rows as dicts.

    Used by the exact-lookup tool. Rejects anything but SELECT/WITH
    so the LLM cannot mutate the store.
    """
    stripped = sql.strip().lower()
    if not (stripped.startswith("select") or stripped.startswith("with")):
        raise ValueError("Only SELECT/WITH queries are permitted.")
    con = connect(read_only=True)
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


if __name__ == "__main__":
    init_db()
    print("Initialized DuckDB at", SETTINGS["paths"]["duckdb_path"])
