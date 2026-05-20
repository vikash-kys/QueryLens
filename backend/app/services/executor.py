"""
Query Executor
==============
Executes validated SQL in a read-only transaction.
Returns results as columns + rows with execution metadata.
"""
import time
import pandas as pd
from sqlalchemy import text
from app.core.database import readonly_session
from app.config import settings
import structlog

log = structlog.get_logger()


class ExecutionResult:
    def __init__(
        self,
        columns: list[str],
        rows: list[list],
        row_count: int,
        total_rows_available: int,
        execution_time_ms: float,
        explain_plan: str | None = None,
    ):
        self.columns = columns
        self.rows = rows
        self.row_count = row_count
        self.total_rows_available = total_rows_available
        self.execution_time_ms = execution_time_ms
        self.explain_plan = explain_plan


def execute_query(sql: str, max_rows: int = None) -> ExecutionResult:
    """Execute SQL and return structured results."""
    limit = max_rows or settings.max_rows

    # Get explain plan first (for audit / row estimate)
    explain_plan = None
    try:
        with readonly_session() as conn:
            plan_result = conn.execute(text(f"EXPLAIN {sql}"))
            explain_plan = "\n".join(row[0] for row in plan_result.fetchall())
    except Exception as e:
        log.warning("explain_failed", error=str(e))

    # Execute actual query
    with readonly_session() as conn:
        start = time.perf_counter()

        result = conn.execute(text(sql))
        all_rows = result.fetchall()

        elapsed_ms = (time.perf_counter() - start) * 1000

        columns = list(result.keys())
        total = len(all_rows)
        capped_rows = all_rows[:limit]

        # Serialize to JSON-safe format
        def _serialize(val):
            if val is None:
                return None
            if hasattr(val, "isoformat"):
                return val.isoformat()
            if isinstance(val, (int, float, str, bool)):
                return val
            return str(val)

        serialized = [[_serialize(cell) for cell in row] for row in capped_rows]

        log.info(
            "query_executed",
            rows_total=total,
            rows_returned=len(serialized),
            elapsed_ms=round(elapsed_ms, 2),
        )

        return ExecutionResult(
            columns=columns,
            rows=serialized,
            row_count=len(serialized),
            total_rows_available=total,
            execution_time_ms=round(elapsed_ms, 2),
            explain_plan=explain_plan,
        )
