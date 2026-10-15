"""PostgreSQL-aware, fail-closed validation for every execution path.

The AST policy is defense in depth. PostgreSQL privileges and read-only
transactions remain required; this is not a sandbox for arbitrary functions.
"""

import sqlglot
from sqlglot import exp
from app.config import settings
from app.models.schemas import GuardrailViolation

# Deliberately narrow analytics function surface. Unknown/custom functions fail closed.
SAFE_FUNCTIONS = set(
    "ABS AVG CEIL CEILING COALESCE CONCAT CONCAT_WS COUNT DATE DATE_TRUNC EXTRACT FLOOR GREATEST LEAST LENGTH LOWER LTRIM MAX MIN NULLIF POWER ROUND RTRIM SIGN SQRT STDDEV STDDEV_POP STDDEV_SAMP STRING_AGG SUBSTRING SUM TO_CHAR TRIM UPPER VARIANCE VAR_POP VAR_SAMP ROW_NUMBER RANK DENSE_RANK LAG LEAD FIRST_VALUE LAST_VALUE NTH_VALUE NTILE PERCENT_RANK CUME_DIST PERCENTILE_CONT PERCENTILE_DISC ARRAY_AGG CAST TRY_CAST IF CASE CURRENT_DATE CURRENT_TIMESTAMP CURRENT_TIME NOW TIMESTAMP_TRUNC TIMESTAMP_DIFF TIME_TO_STR STR_POSITION TS_OR_DS_TO_DATE TS_OR_DS_TO_TIMESTAMP".split()
)


def _parse(sql: str):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
        raise ValueError("SQL must contain between 1 and 20,000 characters")
    statements = sqlglot.parse(sql, read="postgres")
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise ValueError("Exactly one SELECT query is permitted")
    return statements[0]


def check_guardrails(sql: str) -> list[GuardrailViolation]:
    violations = []

    def block(rule, detail):
        violations.append(GuardrailViolation(rule=rule, detail=detail, severity="block"))

    try:
        tree = _parse(sql)
    except (ValueError, sqlglot.errors.ParseError) as exc:
        block("SELECT_ONLY", str(exc).splitlines()[0][:200])
        return violations

    for node in tree.walk():
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Drop,
                exp.Alter,
                exp.Command,
                exp.Into,
                exp.Lock,
                exp.Copy,
                exp.Merge,
            ),
        ):
            block("READ_ONLY", "Writes, locking, commands and SELECT INTO are not permitted")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            block("RECURSION", "Recursive queries are not permitted")
        if isinstance(node, exp.Table):
            if (
                node.catalog
                or node.db.lower() not in ("", "public")
                or node.name.lower().startswith(("pg_", "sql_"))
            ):
                block("SYSTEM_TABLE_ACCESS", "Only application tables in public are permitted")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in SAFE_FUNCTIONS or isinstance(node.parent, exp.Dot):
                block("FUNCTION_NOT_ALLOWED", f"Function {name} is outside the analytics allowlist")
        if isinstance(node, exp.Subquery):
            depth = 1
            parent = node.parent
            while parent is not None:
                depth += isinstance(parent, exp.Subquery)
                parent = parent.parent
            if depth > settings.max_subquery_depth:
                block("SUBQUERY_DEPTH", "Query nesting exceeds the configured limit")
    return violations


def inject_limit(sql: str, max_rows: int | None = None) -> str:
    """Cap the outer query, including aggregates, inner LIMITs and LIMIT ALL."""
    cap = min(max_rows or settings.max_rows, settings.max_rows)
    if cap < 1:
        raise ValueError("Row limit must be positive")
    tree = _parse(sql)
    limit = tree.args.get("limit")
    value = limit.expression if limit is not None else None
    if isinstance(value, exp.Literal) and value.is_int:
        cap = min(cap, max(0, int(value.this)))
    tree.set("limit", exp.Limit(expression=exp.Literal.number(cap)))
    return tree.sql(dialect="postgres")


def is_blocked(violations: list[GuardrailViolation]) -> bool:
    return any(v.severity == "block" for v in violations)


def validate_sql_syntax(sql: str) -> tuple[bool, str | None]:
    try:
        _parse(sql)
        return True, None
    except (ValueError, sqlglot.errors.ParseError) as exc:
        return False, str(exc).splitlines()[0][:200]
