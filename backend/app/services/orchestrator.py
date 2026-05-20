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
from datetime import datetime
from app.models.schemas import (
    QueryRequest, QueryResponse, GuardrailViolation,
    ClarificationOption, ConfidenceBreakdown,
)
from app.services.schema_extractor import get_schema, schema_to_prompt_context
from app.services.sql_generator import generate_sql, generate_alternate_sql
from app.services.guardrails import check_guardrails, inject_limit, is_blocked, validate_sql_syntax
from app.services.executor import execute_query
from app.services.hallucination_detector import (
    back_translate, score_alignment, check_result_sanity,
    validate_multi_query, compute_confidence, compute_schema_coverage,
)
import structlog

log = structlog.get_logger()

# In-memory query history (swap for Redis/DB in production)
_query_history: dict[str, QueryResponse] = {}
_feedback: dict[str, dict] = {}


def process_query(request: QueryRequest) -> QueryResponse:
    """Full pipeline: NL question → SQL → results → confidence."""
    query_id = str(uuid.uuid4())
    log.info("query_start", query_id=query_id, question=request.question[:100])

    # ── Step 1: Load schema ──────────────────────────────────────────
    try:
        schema = get_schema()
        schema_context = schema_to_prompt_context(schema)
    except Exception as e:
        log.error("schema_load_failed", error=str(e))
        return _error_response(query_id, request.question, f"Failed to load database schema: {e}")

    # ── Step 2: Generate SQL ─────────────────────────────────────────
    try:
        gen_result = generate_sql(request.question, schema_context)
    except Exception as e:
        log.error("sql_gen_failed", error=str(e))
        return _error_response(query_id, request.question, f"SQL generation failed: {e}")

    # ── Step 3: Handle clarification needed ──────────────────────────
    if gen_result.get("needs_clarification"):
        options = [
            ClarificationOption(**opt)
            for opt in gen_result.get("clarification_options", [])
        ]
        resp = QueryResponse(
            query_id=query_id,
            question=request.question,
            status="clarification_needed",
            clarification_options=options,
        )
        _query_history[query_id] = resp
        return resp

    sql = gen_result.get("sql")
    if not sql:
        return _error_response(query_id, request.question, gen_result.get("error", "No SQL generated"))

    # ── Step 4: Syntax validation ────────────────────────────────────
    syntax_valid, syntax_error = validate_sql_syntax(sql)
    if not syntax_valid:
        return QueryResponse(
            query_id=query_id,
            question=request.question,
            sql=sql,
            status="error",
            error_message=f"Generated SQL failed syntax validation: {syntax_error}",
            guardrail_violations=[],
        )

    # ── Step 5: Guardrail check ──────────────────────────────────────
    violations = check_guardrails(sql)
    if is_blocked(violations):
        resp = QueryResponse(
            query_id=query_id,
            question=request.question,
            sql=sql,
            status="blocked",
            guardrail_violations=violations,
            error_message="Query blocked by safety guardrails. " +
                          "; ".join(v.detail for v in violations if v.severity == "block"),
        )
        _query_history[query_id] = resp
        return resp

    # ── Step 6: Auto-inject LIMIT ────────────────────────────────────
    sql_safe = inject_limit(sql)

    # ── Step 7: Execute primary query ────────────────────────────────
    try:
        exec_result = execute_query(sql_safe)
    except Exception as e:
        log.error("execution_failed", error=str(e))
        return _error_response(query_id, request.question, f"Query execution failed: {e}", sql=sql)

    # ── Step 8: Back-translation ─────────────────────────────────────
    back_translated, _bt_conf = back_translate(sql)
    alignment_score, alignment_issues = score_alignment(request.question, back_translated)

    # ── Step 9: Result sanity check ──────────────────────────────────
    sanity_score, sanity_flags = check_result_sanity(
        request.question, sql, exec_result
    )

    # ── Step 10: Multi-query validation (for medium-confidence queries) ──
    multi_query_score = 0.9  # default: assume good
    if alignment_score < 0.85:
        try:
            alt_result = generate_alternate_sql(request.question, sql, schema_context)
            if alt_result.get("sql"):
                alt_sql_safe = inject_limit(alt_result["sql"])
                try:
                    alt_exec = execute_query(alt_sql_safe)
                    multi_query_score, _mq_reason = validate_multi_query(exec_result, alt_exec)
                except Exception:
                    multi_query_score = 0.5
        except Exception:
            multi_query_score = 0.5

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
    if multi_query_score < 0.6:
        hallucination_flags.append(
            f"Multi-query validation discrepancy (score: {multi_query_score:.0%})"
        )

    # ── Step 14: Build response ───────────────────────────────────────
    resp = QueryResponse(
        query_id=query_id,
        question=request.question,
        sql=sql,
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

    _query_history[query_id] = resp
    log.info(
        "query_complete",
        query_id=query_id,
        confidence=confidence.overall,
        rows=exec_result.row_count,
        flags=len(hallucination_flags),
    )
    return resp


def _error_response(query_id: str, question: str, message: str, sql: str | None = None) -> QueryResponse:
    return QueryResponse(
        query_id=query_id,
        question=question,
        sql=sql,
        status="error",
        error_message=message,
    )


def record_feedback(query_id: str, is_correct: bool, comment: str | None = None):
    _feedback[query_id] = {
        "is_correct": is_correct,
        "comment": comment,
        "timestamp": datetime.utcnow().isoformat(),
    }
    log.info("feedback_recorded", query_id=query_id, is_correct=is_correct)


def get_history(limit: int = 20) -> list[dict]:
    items = []
    for qid, resp in list(_query_history.items())[-limit:]:
        fb = _feedback.get(qid, {})
        items.append({
            "query_id": qid,
            "question": resp.question,
            "sql": resp.sql,
            "status": resp.status,
            "confidence": resp.confidence.overall if resp.confidence else None,
            "is_correct": fb.get("is_correct"),
            "timestamp": resp.timestamp.isoformat(),
        })
    return list(reversed(items))
