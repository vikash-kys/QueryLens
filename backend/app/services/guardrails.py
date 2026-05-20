"""
SQL Guardrail Middleware
========================
Blocks destructive or dangerous SQL before execution.
Every rule is configurable and logs violations for audit.
"""
import re
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DDL, DML
from app.models.schemas import GuardrailViolation
from app.config import settings
import structlog

log = structlog.get_logger()

# DDL keywords that must never execute
_DDL_KEYWORDS = {
    "CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME",
    "COMMENT", "GRANT", "REVOKE",
}

# DML write keywords
_WRITE_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE"}

# Dangerous patterns (regex)
_DANGEROUS_PATTERNS = [
    (r"\bDROP\s+TABLE\b", "DROP TABLE detected"),
    (r"\bDROP\s+DATABASE\b", "DROP DATABASE detected"),
    (r"\bTRUNCATE\b", "TRUNCATE detected"),
    (r"\bEXEC\b|\bEXECUTE\b", "EXEC/EXECUTE detected — possible injection"),
    (r";\s*\w", "Multiple statement execution (semicolon injection)"),
    (r"--.*?(DROP|DELETE|INSERT|UPDATE)", "Comment masking write operation"),
    (r"xp_cmdshell", "xp_cmdshell syscall attempt"),
    (r"\bpg_sleep\b", "pg_sleep DoS attempt"),
    (r"\bpg_read_file\b|\bpg_ls_dir\b", "Filesystem access attempt"),
    (r"\bcopy\s+\w+\s+(from|to)\b", "COPY TO/FROM filesystem detected"),
]


def _count_subquery_depth(sql: str) -> int:
    """Count maximum nesting depth of SELECT subqueries."""
    depth = 0
    max_depth = 0
    for char in sql:
        if char == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ")":
            depth = max(0, depth - 1)
    return max_depth


def check_guardrails(sql: str) -> list[GuardrailViolation]:
    """
    Run all guardrail checks against the SQL string.
    Returns list of violations. Empty list = safe to execute.
    """
    violations: list[GuardrailViolation] = []
    sql_upper = sql.upper().strip()
    sql_normalized = " ".join(sql.split())  # collapse whitespace

    # ── Rule 1: DDL check ───────────────────────────────────────────
    parsed = sqlparse.parse(sql)
    for statement in parsed:
        for token in statement.flatten():
            if token.ttype in (DDL,) or (token.ttype is Keyword and token.value.upper() in _DDL_KEYWORDS):
                violations.append(GuardrailViolation(
                    rule="NO_DDL",
                    detail=f"DDL operation '{token.value.upper()}' is not permitted. Only SELECT queries are allowed.",
                    severity="block",
                ))
                break

    # ── Rule 2: DML write check ─────────────────────────────────────
    for keyword in _WRITE_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, sql_upper):
            violations.append(GuardrailViolation(
                rule="NO_WRITE_DML",
                detail=f"Write operation '{keyword}' is not permitted. Only SELECT queries are allowed.",
                severity="block",
            ))

    # ── Rule 3: Dangerous pattern detection ─────────────────────────
    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            violations.append(GuardrailViolation(
                rule="DANGEROUS_PATTERN",
                detail=description,
                severity="block",
            ))

    # ── Rule 4: Subquery depth ──────────────────────────────────────
    depth = _count_subquery_depth(sql)
    if depth > settings.max_subquery_depth * 2:  # *2 because parens include non-subqueries
        violations.append(GuardrailViolation(
            rule="SUBQUERY_DEPTH",
            detail=f"Query nesting depth ({depth}) exceeds limit ({settings.max_subquery_depth}). Simplify the query.",
            severity="warn",
        ))

    # ── Rule 5: Missing LIMIT enforcement ───────────────────────────
    # (Note: we auto-inject LIMIT if missing, so this is a warning only)
    if "LIMIT" not in sql_upper and "COUNT(" not in sql_upper:
        violations.append(GuardrailViolation(
            rule="NO_LIMIT",
            detail=f"Query has no LIMIT clause. A LIMIT of {settings.max_rows} will be auto-applied.",
            severity="warn",
        ))

    # ── Rule 6: System catalog access ───────────────────────────────
    system_tables = ["pg_catalog", "information_schema", "pg_stat", "pg_shadow", "pg_user"]
    for tbl in system_tables:
        if tbl in sql.lower():
            violations.append(GuardrailViolation(
                rule="SYSTEM_TABLE_ACCESS",
                detail=f"Access to system table/schema '{tbl}' is not permitted.",
                severity="block",
            ))

    log.info(
        "guardrail_check",
        sql_preview=sql[:100],
        violations=len(violations),
        blocked=any(v.severity == "block" for v in violations),
    )

    return violations


def inject_limit(sql: str, max_rows: int = None) -> str:
    """Auto-inject LIMIT if query lacks one and isn't an aggregate."""
    limit = max_rows or settings.max_rows
    sql_upper = sql.upper()
    if "LIMIT" in sql_upper or "COUNT(" in sql_upper or "SUM(" in sql_upper:
        return sql
    # Strip trailing semicolon, add limit
    sql = sql.rstrip().rstrip(";")
    return f"{sql}\nLIMIT {limit}"


def is_blocked(violations: list[GuardrailViolation]) -> bool:
    return any(v.severity == "block" for v in violations)


def validate_sql_syntax(sql: str) -> tuple[bool, str | None]:
    """Basic syntax validation using sqlparse."""
    try:
        parsed = sqlparse.parse(sql)
        if not parsed or not parsed[0].tokens:
            return False, "Empty or unparseable SQL"
        # Must start with SELECT
        for token in parsed[0].flatten():
            if token.ttype is DML:
                if token.value.upper() == "SELECT":
                    return True, None
                else:
                    return False, f"Query must start with SELECT, got {token.value.upper()}"
        return False, "Could not identify query type"
    except Exception as e:
        return False, str(e)
