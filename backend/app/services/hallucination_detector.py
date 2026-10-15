"""
Hallucination Detection System
================================
Multi-signal system to detect when generated SQL doesn't actually answer the question.

Signals:
1. Back-translation alignment  — does the SQL answer the original question?
2. Result sanity checks        — are values within plausible ranges?
3. Multi-query validation      — do two independent approaches agree?
4. Schema coverage             — did the query use expected tables?
"""

from collections import Counter
from pydantic import BaseModel, Field
from app.services.llm_client import complete, parse_json_response
from app.models.schemas import ConfidenceBreakdown
from app.services.executor import ExecutionResult
import structlog

log = structlog.get_logger()


class Alignment(BaseModel):
    alignment_score: float = Field(ge=0, le=1)
    issues: list[str] = []


class Sanity(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = []


_BACK_TRANSLATE_SYSTEM = """You are an expert SQL analyst.
Given a SQL query, describe in ONE sentence what question it answers.
Be specific: mention the exact columns aggregated, any filters applied, and the tables involved.
Return ONLY a JSON object: {"question": "...", "confidence": 0.0-1.0}
"""

_ALIGNMENT_SYSTEM = """You are an expert evaluator.
Given an original question and a back-translated interpretation of a SQL query,
rate how well the SQL addresses the original question.
Return ONLY JSON: {"alignment_score": 0.0-1.0, "issues": ["list of discrepancies"]}

Scoring guide:
1.0 = SQL perfectly answers the question
0.8 = SQL answers the main intent with minor differences
0.6 = SQL partially answers (missing a filter, wrong aggregation)
0.4 = SQL answers a related but different question
0.2 = SQL barely relates to the question
0.0 = SQL answers a completely different question
"""

_SANITY_SYSTEM = """You are a data sanity checker.
Given a question, SQL query, and query results (first few rows + stats),
identify any suspicious results that might indicate a bug or wrong query.
Return ONLY JSON: {
  "is_sane": true/false,
  "score": 0.0-1.0,
  "flags": ["list of specific anomalies found"]
}

Common anomalies to check:
- Revenue/count values that are implausibly large or zero
- Date ranges that seem wrong
- Unexpected NULL-heavy columns
- Results that contradict the question (e.g., "top 5" but 50 rows returned)
- Numeric results with wrong sign or scale
"""


def back_translate(sql: str) -> tuple[str, float]:
    """Ask the LLM what question this SQL answers."""
    try:
        raw = complete(
            system=_BACK_TRANSLATE_SYSTEM,
            user=f"SQL:\n{sql}",
        )
        result = parse_json_response(raw)
        return result.get("question", ""), result.get("confidence", 0.5)
    except Exception as e:
        log.error("back_translate_error", error=str(e))
        return "", 0.0


def score_alignment(original_question: str, back_translated: str) -> tuple[float, list[str]]:
    """Score how well the back-translation aligns with the original question."""
    if not back_translated:
        return 0.0, ["Could not back-translate SQL"]

    try:
        raw = complete(
            system=_ALIGNMENT_SYSTEM,
            user=f"Original question: {original_question}\nSQL interprets as: {back_translated}",
        )
        result = parse_json_response(raw)
        validated = Alignment.model_validate(result)
        return validated.alignment_score, validated.issues
    except Exception as e:
        log.error("alignment_score_error", error=str(e))
        return 0.0, ["Alignment check unavailable; review the SQL manually."]


def check_result_sanity(
    question: str,
    sql: str,
    result: ExecutionResult,
) -> tuple[float, list[str]]:
    """Sanity-check execution results for plausibility."""
    flags = []
    score = 1.0

    # Zero results for non-aggregate query
    if result.row_count == 0 and "COUNT" not in sql.upper():
        flags.append("Query returned 0 rows — possible bad JOIN or over-restrictive filter")
        score -= 0.3

    # NULL-heavy check
    if result.row_count > 0 and result.columns:
        for col_idx, col_name in enumerate(result.columns):
            null_count = sum(1 for row in result.rows if row[col_idx] is None)
            null_pct = null_count / result.row_count
            if null_pct > 0.8:
                flags.append(f"Column '{col_name}' is {null_pct:.0%} NULL — possible JOIN issue")
                score -= 0.1

    # Numeric plausibility for revenue-type columns
    revenue_cols = [
        c
        for c in result.columns
        if any(kw in c.lower() for kw in ["revenue", "amount", "total", "price", "profit"])
    ]
    for col_name in revenue_cols:
        col_idx = result.columns.index(col_name)
        values = [row[col_idx] for row in result.rows if row[col_idx] is not None]
        if values:
            try:
                floats = [float(v) for v in values]
                if any(v < 0 for v in floats):
                    flags.append(f"Negative values in '{col_name}' — check calculation")
                    score -= 0.15
                if max(floats) > 1e12:
                    flags.append(f"Implausibly large value in '{col_name}' ({max(floats):,.0f})")
                    score -= 0.2
            except (ValueError, TypeError):
                pass

    # LLM-based sanity check for complex cases
    if result.row_count > 0:
        sample_rows = result.rows[:5]
        result_summary = (
            f"Columns: {result.columns}\nFirst rows: {sample_rows}\nTotal rows: {result.total_rows_available}"
        )
        try:
            raw = complete(
                system=_SANITY_SYSTEM,
                user=f"Question: {question}\nSQL: {sql}\nResults: {result_summary}",
            )
            sanity = parse_json_response(raw)
            validated = Sanity.model_validate(sanity)
            llm_score = validated.score
            llm_flags = validated.flags
            score = (score + llm_score) / 2
            flags.extend(llm_flags)
        except Exception as e:
            log.warning("llm_sanity_check_failed", error_type=type(e).__name__)
            flags.append("Model-based result sanity check unavailable; only local heuristics ran.")
            score = min(score, 0.5)

    return max(0.0, min(1.0, score)), flags


def validate_multi_query(
    result_a: ExecutionResult,
    result_b: ExecutionResult,
) -> tuple[float, str]:
    """
    Compare results from two independent SQL approaches.
    Returns agreement score (0-1) and explanation.
    """
    if result_b is None:
        return 0.0, "Alternative query unavailable"
    if result_a.columns != result_b.columns:
        return 0.0, "Column names differ; agreement cannot be established"
    # Compare every returned row, preserving duplicate multiplicity and ignoring order.
    # Capped results can only establish agreement on the returned sample.
    rows_a = Counter(tuple(row) for row in result_a.rows)
    rows_b = Counter(tuple(row) for row in result_b.rows)
    if rows_a != rows_b:
        return 0.0, "Returned row values differ"
    return 1.0, "Returned rows agree (not a proof of semantic correctness)"


def compute_confidence(
    sql_valid: bool,
    alignment_score: float,
    sanity_score: float,
    schema_coverage: float,
    multi_query_agreement: float | None,
) -> ConfidenceBreakdown:
    """Weighted combination of all confidence signals."""
    weights = {
        "syntax_valid": 0.15,
        "back_translation_alignment": 0.35,
        "result_sanity": 0.25,
        "schema_coverage": 0.10,
        "multi_query_agreement": 0.15,
    }

    syntax_score = 1.0 if sql_valid else 0.0
    scores = {
        "syntax_valid": syntax_score,
        "back_translation_alignment": alignment_score,
        "result_sanity": sanity_score,
        "schema_coverage": schema_coverage,
        "multi_query_agreement": multi_query_agreement,
    }

    measured = {k: v for k, v in scores.items() if v is not None}
    overall = sum(max(0.0, min(1.0, v)) * weights[k] for k, v in measured.items()) / sum(
        weights[k] for k in measured
    )

    return ConfidenceBreakdown(
        syntax_valid=round(scores["syntax_valid"], 3),
        back_translation_alignment=round(alignment_score, 3),
        result_sanity=round(sanity_score, 3),
        schema_coverage=round(schema_coverage, 3),
        overall=round(overall, 3),
        multi_query_agreement=multi_query_agreement,
    )


def compute_schema_coverage(tables_used: list[str], schema_tables: list[str], question: str) -> float:
    """
    Heuristic: do the tables used make sense for the question?
    Cross-reference keywords in the question with table names.
    """
    if not tables_used:
        return 0.3

    question_lower = question.lower()
    # Keyword-to-table hints
    hints = {
        "customer": ["customers"],
        "product": ["products", "order_items"],
        "order": ["orders", "order_items"],
        "return": ["returns"],
        "campaign": ["marketing_campaigns"],
        "revenue": ["orders", "order_items"],
        "sales": ["orders", "order_items"],
        "inventory": ["products"],
    }

    expected_tables = set()
    for keyword, tables in hints.items():
        if keyword in question_lower:
            expected_tables.update(tables)

    if not expected_tables:
        return 0.8  # No hints → neutral score

    overlap = len(set(tables_used) & expected_tables)
    return min(1.0, overlap / len(expected_tables))
