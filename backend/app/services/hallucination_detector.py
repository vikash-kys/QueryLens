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
import re
from app.services.llm_client import complete, parse_json_response
from app.models.schemas import ConfidenceBreakdown
from app.services.executor import ExecutionResult
import structlog

log = structlog.get_logger()

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
            temperature=0.0,
            max_tokens=300,
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
            temperature=0.0,
            max_tokens=400,
        )
        result = parse_json_response(raw)
        return result.get("alignment_score", 0.5), result.get("issues", [])
    except Exception as e:
        log.error("alignment_score_error", error=str(e))
        return 0.5, [f"Alignment check failed: {e}"]


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
    revenue_cols = [c for c in result.columns if any(
        kw in c.lower() for kw in ["revenue", "amount", "total", "price", "profit"]
    )]
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
        result_summary = f"Columns: {result.columns}\nFirst rows: {sample_rows}\nTotal rows: {result.total_rows_available}"
        try:
            raw = complete(
                system=_SANITY_SYSTEM,
                user=f"Question: {question}\nSQL: {sql}\nResults: {result_summary}",
                temperature=0.0,
                max_tokens=500,
            )
            sanity = parse_json_response(raw)
            llm_score = sanity.get("score", 1.0)
            llm_flags = sanity.get("flags", [])
            score = (score + llm_score) / 2
            flags.extend(llm_flags)
        except Exception as e:
            log.warning("llm_sanity_check_failed", error=str(e))

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
        return 0.5, "Could not generate alternative query"

    if result_a.columns != result_b.columns:
        return 0.3, f"Queries returned different columns: {result_a.columns} vs {result_b.columns}"

    if result_a.total_rows_available != result_b.total_rows_available:
        diff = abs(result_a.total_rows_available - result_b.total_rows_available)
        pct_diff = diff / max(result_a.total_rows_available, 1)
        if pct_diff < 0.01:
            return 0.95, f"Row counts nearly identical ({result_a.total_rows_available} vs {result_b.total_rows_available})"
        elif pct_diff < 0.05:
            return 0.8, f"Small row count discrepancy: {result_a.total_rows_available} vs {result_b.total_rows_available}"
        else:
            return 0.4, f"Significant row count discrepancy: {result_a.total_rows_available} vs {result_b.total_rows_available}"

    # Compare first row numeric values
    if result_a.rows and result_b.rows:
        row_a = result_a.rows[0]
        row_b = result_b.rows[0]
        try:
            for va, vb in zip(row_a, row_b):
                if va is not None and vb is not None:
                    fa, fb = float(va), float(vb)
                    if abs(fa - fb) / max(abs(fa), 1) > 0.01:
                        return 0.5, f"First row values differ: {va} vs {vb}"
        except (ValueError, TypeError):
            pass

    return 0.95, "Both approaches agree on results"


def compute_confidence(
    sql_valid: bool,
    alignment_score: float,
    sanity_score: float,
    schema_coverage: float,
    multi_query_agreement: float,
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

    overall = sum(scores[k] * weights[k] for k in weights)

    return ConfidenceBreakdown(
        syntax_valid=round(scores["syntax_valid"], 3),
        back_translation_alignment=round(alignment_score, 3),
        result_sanity=round(sanity_score, 3),
        schema_coverage=round(schema_coverage, 3),
        overall=round(overall, 3),
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
