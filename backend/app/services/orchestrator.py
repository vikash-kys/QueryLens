"""
Query Orchestrator
==================
Coordinates the full text-to-SQL pipeline:
1. Schema extraction and context building
2. SQL generation
3. Guardrail validation
4. Execution (in read-only sandbox)
5. Hallucination detection
6. Confidence scoring
"""

import uuid
from threading import RLock
from app.config import settings
from datetime import datetime, timezone
from app.models.schemas import (
    QueryRequest,
    QueryResponse,
    GuardrailViolation,
    ClarificationOption,
)
from app.services.schema_extractor import get_schema, schema_to_prompt_context
from app.services.sql_generator import generate_sql, generate_alternate_sql
from app.services.guardrails import check_guardrails, inject_limit, is_blocked, validate_sql_syntax
from app.services.executor import execute_query
from app.services.hallucination_detector import (
    back_translate,
    score_alignment,
    check_result_sanity,
    validate_multi_query,
    compute_confidence,
    compute_schema_coverage,
)
import structlog

log = structlog.get_logger()

# In-memory query history (swap for Redis/DB in production)
_query_history: dict[str, QueryResponse] = {}
_feedback: dict[str, dict] = {}
_history_lock = RLock()


def _remember(resp: QueryResponse) -> QueryResponse:
    with _history_lock:
        _query_history[resp.query_id] = resp
        while len(_query_history) > settings.history_limit:
            oldest = next(iter(_query_history))
            _query_history.pop(oldest)
            _feedback.pop(oldest, None)
    return resp


def process_query(request: QueryRequest) -> QueryResponse:
    """Full pipeline: NL question → SQL → results → confidence."""
    query_id = str(uuid.uuid4())
    log.info("query_start", query_id=query_id, mode=request.mode)
    if request.mode == "sql":
        return _process_sql(query_id, request.question)

    # ── Step 1: Load schema ──────────────────────────────────────────
    try:
        schema = get_schema()
        schema_context = schema_to_prompt_context(schema)
    except Exception as e:
        log.error("schema_load_failed", error_type=type(e).__name__)
        return _error_response(
            query_id,
            request.question,
            "Database unavailable. Check the database service and connection settings.",
        )

    # ── Step 2: Generate SQL ─────────────────────────────────────────
    try:
        question = request.question
        if request.clarification_choice:
            question += "\nUser clarification: " + request.clarification_choice
        gen_result = generate_sql(question, schema_context)
    except Exception as e:
        log.error("sql_gen_failed", error_type=type(e).__name__)
        return _error_response(
            query_id,
            request.question,
            "SQL generation failed. Check provider credentials, model name and availability, or use SQL mode.",
        )

    # ── Step 3: Handle clarification needed ──────────────────────────
    if gen_result.get("needs_clarification"):
        options = [ClarificationOption(**opt) for opt in gen_result.get("clarification_options", [])]
        resp = QueryResponse(
            query_id=query_id,
            question=request.question,
            status="clarification_needed",
            clarification_options=options,
        )
        _remember(resp)
        return resp

    sql = gen_result.get("sql")
    if not sql:
        return _error_response(query_id, request.question, gen_result.get("error", "No SQL generated"))

    # ── Step 5: Guardrail check ──────────────────────────────────────
    violations = check_guardrails(sql)
    if is_blocked(violations):
        resp = QueryResponse(
            query_id=query_id,
            question=request.question,
            sql=sql,
            status="blocked",
            guardrail_violations=violations,
            error_message="Query blocked by safety guardrails. "
            + "; ".join(v.detail for v in violations if v.severity == "block"),
        )
        _remember(resp)
        return resp

    syntax_valid, _ = validate_sql_syntax(sql)
    if gen_result.get("confidence", 0) < settings.min_confidence_to_execute:
        return _remember(
            QueryResponse(
                query_id=query_id,
                question=request.question,
                sql=sql,
                status="blocked",
                guardrail_violations=[
                    GuardrailViolation(
                        rule="LOW_CONFIDENCE",
                        detail="The model is too uncertain to execute this query. Refine the question.",
                        severity="block",
                    )
                ],
            )
        )

    # ── Step 6: Auto-inject LIMIT ────────────────────────────────────
    sql_safe = inject_limit(sql)

    # ── Step 7: Execute primary query ────────────────────────────────
    try:
        exec_result = execute_query(sql_safe)
    except Exception as e:
        log.error("execution_failed", error_type=type(e).__name__)
        return _error_response(
            query_id,
            request.question,
            "The database could not execute this query. Check the schema and SQL, or try a more specific question.",
            sql=sql,
        )

    if not settings.enable_ai_review:
        return _remember(
            QueryResponse(
                query_id=query_id,
                question=request.question,
                sql=sql_safe,
                explanation=gen_result.get("explanation"),
                columns=exec_result.columns,
                rows=exec_result.rows,
                row_count=exec_result.row_count,
                total_rows_available=exec_result.total_rows_available,
                execution_time_ms=exec_result.execution_time_ms,
                guardrail_violations=violations,
                tables_used=gen_result.get("tables_used", []),
                status="success",
                hallucination_flags=[
                    "Single-call AI mode: SQL safety checks passed. Additional AI review is disabled to conserve quota; no confidence score is assigned."
                ],
            )
        )

    # ── Step 8: Back-translation ─────────────────────────────────────
    back_translated, _bt_conf = back_translate(sql_safe)
    alignment_score, alignment_issues = score_alignment(question, back_translated)

    # ── Step 9: Result sanity check ──────────────────────────────────
    sanity_score, sanity_flags = check_result_sanity(question, sql_safe, exec_result)

    # ── Step 10: Multi-query validation (for medium-confidence queries) ──
    multi_query_score = None  # Unmeasured signals are excluded from the score
    if alignment_score < 0.85:
        try:
            alt_result = generate_alternate_sql(question, sql_safe, schema_context)
            if alt_result.get("sql"):
                alt_sql_safe = inject_limit(alt_result["sql"])
                try:
                    alt_exec = execute_query(alt_sql_safe)
                    multi_query_score, _mq_reason = validate_multi_query(exec_result, alt_exec)
                except Exception:
                    multi_query_score = None
        except Exception:
            multi_query_score = None

    # ── Step 11: Schema coverage ─────────────────────────────────────
    schema_tables = [t.name for t in schema.tables]
    tables_used = gen_result.get("tables_used", [])
    coverage_score = compute_schema_coverage(tables_used, schema_tables, request.question)

    # ── Step 12: Confidence scoring ───────────────────────────────────
    confidence = compute_confidence(
        sql_valid=syntax_valid,
        alignment_score=alignment_score,
        sanity_score=sanity_score,
        schema_coverage=coverage_score,
        multi_query_agreement=multi_query_score,
    )

    # ── Step 13: Hallucination flags ─────────────────────────────────
    hallucination_flags = []
    if alignment_score < 0.6:
        hallucination_flags.append(
            f"Low back-translation alignment ({alignment_score:.0%}): SQL may not answer the original question"
        )
    for issue in alignment_issues:
        hallucination_flags.append(f"Alignment issue: {issue}")
    for flag in sanity_flags:
        hallucination_flags.append(flag)
    if multi_query_score is not None and multi_query_score < 0.6:
        hallucination_flags.append(f"Multi-query validation discrepancy (score: {multi_query_score:.0%})")

    if multi_query_score is None:
        hallucination_flags.append("Alternative-query agreement was not verified.")
    if confidence.overall < settings.hallucination_flag_threshold:
        hallucination_flags.append("Overall confidence is below the configured review threshold.")

    # ── Step 14: Build response ───────────────────────────────────────
    resp = QueryResponse(
        query_id=query_id,
        question=request.question,
        sql=sql_safe,
        explanation=gen_result.get("explanation"),
        columns=exec_result.columns,
        rows=exec_result.rows,
        row_count=exec_result.row_count,
        total_rows_available=exec_result.total_rows_available,
        execution_time_ms=exec_result.execution_time_ms,
        confidence=confidence,
        guardrail_violations=violations,  # warns only at this point
        hallucination_flags=hallucination_flags,
        back_translation=back_translated,
        tables_used=tables_used,
        status="success",
    )

    _remember(resp)
    log.info(
        "query_complete",
        query_id=query_id,
        confidence=confidence.overall,
        rows=exec_result.row_count,
        flags=len(hallucination_flags),
    )
    return resp


def _error_response(query_id: str, question: str, message: str, sql: str | None = None) -> QueryResponse:
    return _remember(
        QueryResponse(
            query_id=query_id,
            question=question,
            sql=sql,
            status="error",
            error_message=message,
        )
    )


def _process_sql(query_id: str, sql: str) -> QueryResponse:
    violations = check_guardrails(sql)
    if is_blocked(violations):
        return _remember(
            QueryResponse(
                query_id=query_id, question=sql, sql=sql, status="blocked", guardrail_violations=violations
            )
        )
    try:
        safe_sql = inject_limit(sql)
        result = execute_query(safe_sql)
    except Exception as exc:
        log.warning("sql_execution_failed", query_id=query_id, error_type=type(exc).__name__)
        return _error_response(
            query_id,
            sql,
            "The database could not execute this query. Check the schema, SQL and database connection.",
            sql=sql,
        )
    return _remember(
        QueryResponse(
            query_id=query_id,
            question=sql,
            sql=safe_sql,
            status="success",
            explanation="Direct SQL execution · No model used and no AI confidence score assigned.",
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            total_rows_available=result.total_rows_available,
            execution_time_ms=result.execution_time_ms,
        )
    )


def record_feedback(query_id: str, is_correct: bool, comment: str | None = None):
    with _history_lock:
        if query_id not in _query_history:
            raise KeyError(query_id)
        _feedback[query_id] = {
            "is_correct": is_correct,
            "comment": comment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_history(limit: int = 20) -> list[dict]:
    with _history_lock:
        return [
            {
                "query_id": qid,
                "question": resp.question,
                "sql": resp.sql,
                "status": resp.status,
                "confidence": resp.confidence.overall if resp.confidence else None,
                "is_correct": _feedback.get(qid, {}).get("is_correct"),
                "timestamp": resp.timestamp.isoformat(),
            }
            for qid, resp in reversed(list(_query_history.items())[-limit:])
        ]
