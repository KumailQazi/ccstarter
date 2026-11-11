"""Run SQL over the URL index with DuckDB -- locally, for free.

The URL index is plain Parquet, partitioned by crawl and subset. DuckDB reads
Parquet over HTTPS and only pulls the columns and row groups your query needs,
so a filtered query touches a few MB of a 300 GB index.

Rule of thumb: DuckDB for a sample and for iteration, Athena for the exact
number over a full crawl (Athena bills $5/TiB scanned; a full monthly index is
~300 GB, so worst case about $1.50).
"""
from __future__ import annotations

from typing import List, Sequence

from .discovery import shards as _shards


class QueryError(RuntimeError):
    pass


def lit(value) -> str:
    """Render a Python value as a SQL literal, safely.

    DuckDB accepts `?` parameters, but students debugging a query want to see
    the SQL they actually ran. This keeps that possible without string
    concatenation bugs -- note the doubled quotes for strings containing '.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _literal_list(urls: Sequence[str]) -> str:
    return ", ".join("'" + u.replace("'", "''") + "'" for u in urls)


def _connect():
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover
        raise QueryError("pip install duckdb   (or run the same SQL in Athena)") from exc
    con = duckdb.connect()
    for statement in ("LOAD httpfs;", "INSTALL httpfs; LOAD httpfs;"):
        try:
            con.execute(statement)
            break
        except Exception:
            continue
    return con


def register_index(con, urls: Sequence[str], view: str = "ccindex") -> None:
    """Expose the shards as a view named `ccindex`, so SQL looks like Athena's.

    hive_partitioning=true  -> the crawl=.../subset=... folders become columns
    union_by_name=true      -> newer shards with extra columns still work
    """
    if not urls:
        raise QueryError("no shards given")
    sql = (
        f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet("
        f"[{_literal_list(urls)}], hive_partitioning=true, union_by_name=true)"
    )
    con.execute(sql)


def run_sql(
    sql: str,
    crawl: str,
    *,
    max_files: int = 8,
    subset: str = "warc",
    urls: List[str] | None = None,
    params: Sequence | None = None,
):
    """Execute `sql` (which should select FROM ccindex) and return a DataFrame."""
    shard_urls = urls if urls is not None else _shards(crawl, subset=subset, max_files=max_files)
    con = _connect()
    register_index(con, shard_urls)
    try:
        return con.execute(sql, params).df() if params else con.execute(sql).df()
    finally:
        con.close()
