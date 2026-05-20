"""
SQL Generator
=============
Translates natural language questions to SQL using a schema-aware prompt.
Returns structured output with SQL, explanation, confidence, and tables used.
"""
from app.services.llm_client import complete, parse_json_response
from app.services.schema_extractor import schema_to_prompt_context, get_schema
from app.models.schemas import ClarificationOption
import structlog

log = structlog.get_logger()

_FEW_SHOT_EXAMPLES = """
EXAMPLES (question → SQL):

Q: How many customers are from the USA?
A: {"sql":"SELECT COUNT(*) AS customer_count FROM customers WHERE country = 'USA'","explanation":"Counts all customers whose country is USA.","tables_used":["customers"],"confidence":0.95,"needs_clarification":false}

Q: What are the top 5 best-selling products by revenue?
A: {"sql":"SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue FROM products p JOIN order_items oi ON oi.product_id = p.product_id JOIN orders o ON o.order_id = oi.order_id WHERE o.status NOT IN ('cancelled','refunded') GROUP BY p.product_id, p.name ORDER BY revenue DESC LIMIT 5","explanation":"Joins products, order_items, and orders to sum revenue per product, excluding cancelled/refunded orders.","tables_used":["products","order_items","orders"],"confidence":0.92,"needs_clarification":false}

Q: Show me monthly revenue for 2024
A: {"sql":"SELECT DATE_TRUNC('month', o.created_at) AS month, SUM(oi.quantity * oi.unit_price) AS revenue FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE o.status NOT IN ('cancelled','refunded') AND EXTRACT(YEAR FROM o.created_at) = 2024 GROUP BY 1 ORDER BY 1","explanation":"Truncates order dates to month, sums revenue from order items, filters to 2024 only.","tables_used":["orders","order_items"],"confidence":0.93,"needs_clarification":false}

Q: Which customers have never placed an order?
A: {"sql":"SELECT c.customer_id, c.full_name, c.email FROM customers c LEFT JOIN orders o ON o.customer_id = c.customer_id WHERE o.order_id IS NULL","explanation":"Left join customers to orders; rows with NULL order_id have never ordered.","tables_used":["customers","orders"],"confidence":0.95,"needs_clarification":false}

Q: What is our revenue?
A: {"sql":null,"explanation":null,"tables_used":[],"confidence":0.0,"needs_clarification":true,"clarification_options":[{"label":"Gross revenue (all completed orders)","description":"Total revenue from all non-cancelled/refunded orders","example_sql":"SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE o.status NOT IN ('cancelled','refunded')"},{"label":"Net revenue (after discounts)","description":"Revenue accounting for discount percentages","example_sql":"SELECT SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100)) FROM order_items oi JOIN orders o ON o.order_id=oi.order_id WHERE o.status NOT IN ('cancelled','refunded')"}]}
"""

_SYSTEM_PROMPT = """You are a precise SQL generation assistant. Your job is to convert natural language questions into correct PostgreSQL queries.

RULES:
1. Only generate SELECT queries. Never INSERT, UPDATE, DELETE, DROP, or any DDL.
2. Always use explicit table aliases and qualify column names when joining.
3. Exclude cancelled/refunded orders unless the user explicitly asks about them.
4. Use DATE_TRUNC for time groupings. Use EXTRACT for year/month/day filters.
5. If a question is ambiguous, set needs_clarification=true and provide options.
6. Set confidence between 0.0 (uncertain) and 1.0 (certain).
7. Only reference columns and tables that exist in the schema provided.
8. Return ONLY valid JSON matching the specified format.

RESPONSE FORMAT (JSON only, no markdown):
{
  "sql": "SELECT ...",
  "explanation": "Plain English description of what the query does",
  "tables_used": ["table1", "table2"],
  "confidence": 0.85,
  "needs_clarification": false,
  "clarification_options": []
}

If needs_clarification is true:
{
  "sql": null,
  "explanation": null,
  "tables_used": [],
  "confidence": 0.0,
  "needs_clarification": true,
  "clarification_options": [
    {"label": "...", "description": "...", "example_sql": "..."}
  ]
}
"""


def generate_sql(question: str, schema_context: str) -> dict:
    """
    Generate SQL for a natural language question.
    Returns a dict with: sql, explanation, tables_used, confidence, needs_clarification, clarification_options
    """
    user_prompt = f"""{schema_context}

{_FEW_SHOT_EXAMPLES}

Now answer this question:
Q: {question}
A:"""

    log.info("generating_sql", question=question[:100])

    raw = complete(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.0,
        max_tokens=1500,
    )

    try:
        result = parse_json_response(raw)
    except Exception as e:
        log.error("sql_parse_error", error=str(e), raw=raw[:300])
        return {
            "sql": None,
            "explanation": None,
            "tables_used": [],
            "confidence": 0.0,
            "needs_clarification": False,
            "clarification_options": [],
            "error": f"Failed to parse LLM response: {e}",
        }

    return result


def generate_alternate_sql(question: str, original_sql: str, schema_context: str) -> dict:
    """Generate an alternative SQL using a different approach for cross-validation."""
    user_prompt = f"""{schema_context}

Original question: {question}
Original SQL (do NOT copy this approach): {original_sql}

Generate an ALTERNATIVE SQL query that answers the same question using a DIFFERENT approach.
For example: if the original used a subquery, use a JOIN instead. If it used GROUP BY, try window functions.

{_FEW_SHOT_EXAMPLES}

Q: {question} (generate alternative approach)
A:"""

    raw = complete(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.2,
        max_tokens=1500,
    )

    try:
        return parse_json_response(raw)
    except Exception:
        return {"sql": None, "error": "Could not generate alternative SQL"}
