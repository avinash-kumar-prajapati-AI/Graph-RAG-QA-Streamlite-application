"""
tools.py — Read-only LangChain tools for DBReadAgent (Ollama backend)
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tabulate import tabulate

from db_setup import DB_PATHS_FN, get_conn, get_schema_text


# ── Result model ──────────────────────────────────────────────────────────────
class QueryResult(BaseModel):
    success: bool
    sql: str = ""
    db_name: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    error: str | None = None
    execution_ms: float = 0.0


# ── Core executor (read-only) ─────────────────────────────────────────────────
def execute_read_sql(db_name: str, sql: str, limit: int = 500) -> QueryResult:
    sql_clean = sql.strip().rstrip(";")

    # Safety gate — only SELECT / WITH / EXPLAIN / PRAGMA
    first = sql_clean.split()[0].upper() if sql_clean else ""
    if first not in ("SELECT", "WITH", "EXPLAIN", "PRAGMA"):
        return QueryResult(
            success=False, sql=sql, db_name=db_name,
            error=f"Read-only agent: only SELECT/WITH/EXPLAIN allowed. Got: {first}",
        )

    # Auto-limit
    if "LIMIT" not in sql_clean.upper() and first in ("SELECT", "WITH"):
        sql_clean += f" LIMIT {limit}"

    t0 = time.perf_counter()
    try:
        conn  = get_conn(db_name)
        rows  = [dict(r) for r in conn.execute(sql_clean).fetchall()]
        conn.close()
        ms = round((time.perf_counter() - t0) * 1000, 2)
        return QueryResult(success=True, sql=sql_clean, db_name=db_name,
                           rows=rows, row_count=len(rows), execution_ms=ms)
    except Exception as exc:
        return QueryResult(success=False, sql=sql_clean, db_name=db_name, error=str(exc))


def format_result(r: QueryResult, max_rows: int = 60) -> str:
    if not r.success:
        return (
            f"❌ **SQL Error** on `{r.db_name}`:\n```\n{r.error}\n```\n"
            f"**SQL tried:**\n```sql\n{r.sql}\n```"
        )
    if not r.rows:
        return f"✅ Query returned **0 rows** from `{r.db_name}` in {r.execution_ms}ms."

    display = r.rows[:max_rows]
    tbl = tabulate(display, headers="keys", tablefmt="github",
                   floatfmt=".2f", missingval="—", maxcolwidths=45)
    note = f"\n*(showing {len(display)} of {r.row_count} rows)*" if r.row_count > max_rows else ""
    return (
        f"{tbl}{note}\n\n"
        f"**{r.row_count:,} rows** · `{r.db_name}` · {r.execution_ms:.1f}ms\n"
        f"```sql\n{r.sql}\n```"
    )


# ── LangChain tools ───────────────────────────────────────────────────────────
@tool
def get_schema(databases: str = "all") -> str:
    """Retrieve the full DDL schema and row counts for one or more databases.
    Args:
        databases: comma-separated names (company, analytics, inventory) or 'all'
    """
    if databases.strip().lower() == "all":
        targets = None
    else:
        targets = [d.strip() for d in databases.split(",")]
    return get_schema_text(targets)


@tool
def query_company(sql: str) -> str:
    """Execute a read-only SQL query on the COMPANY database.
    Tables: employees, departments, projects, assignments, performance_reviews.
    Supports CTEs, window functions, multi-table JOINs, aggregations."""
    return format_result(execute_read_sql("company", sql))


@tool
def query_analytics(sql: str) -> str:
    """Execute a read-only SQL query on the ANALYTICS database.
    Tables: user_sessions, page_views, conversion_events, ab_tests.
    Supports time-series, funnel analysis, A/B test queries."""
    return format_result(execute_read_sql("analytics", sql))


@tool
def query_inventory(sql: str) -> str:
    """Execute a read-only SQL query on the INVENTORY database.
    Tables: products, warehouses, stock_levels, purchase_orders.
    Supports stock analysis, reorder alerts, PO tracking."""
    return format_result(execute_read_sql("inventory", sql))


@tool
def explain_query(db_name: str, sql: str) -> str:
    """Run EXPLAIN QUERY PLAN on a SQL statement to show the execution strategy.
    Args:
        db_name: 'company', 'analytics', or 'inventory'
        sql:     The SQL query to explain
    """
    return format_result(execute_read_sql(db_name, f"EXPLAIN QUERY PLAN {sql}"))


@tool
def get_sample_values(db_name: str, table: str, column: str, limit: int = 12) -> str:
    """Retrieve distinct sample values from a column — useful for resolving ambiguous filter values.
    Args:
        db_name: database name
        table:   table name
        column:  column name
        limit:   max distinct values to return
    """
    r = execute_read_sql(db_name, f"SELECT DISTINCT {column} FROM {table} ORDER BY {column} LIMIT {limit}")
    if r.success:
        vals = [str(row[column]) for row in r.rows]
        return f"Sample `{table}.{column}` values: {', '.join(vals)}"
    return f"Error: {r.error}"


ALL_TOOLS = [
    get_schema,
    query_company,
    query_analytics,
    query_inventory,
    explain_query,
    get_sample_values,
]
