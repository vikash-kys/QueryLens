"""Opt-in tests against the real sample database; never calls an LLM."""

import os
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import readonly_session
from app.services.executor import execute_query
from app.services.schema_extractor import get_schema

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 with the sample database running"
    ),
]


def test_sample_schema_and_database_role():
    assert {"customers", "products", "orders", "product_performance"} <= {
        t.name for t in get_schema(force_refresh=True).tables
    }
    with readonly_session() as conn:
        assert conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
        role = conn.execute(
            text("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(role) == (False, False, False)
        assert not conn.execute(
            text("SELECT has_table_privilege(current_user, 'customers', 'UPDATE')")
        ).scalar()


def test_database_rejects_write_even_without_parser():
    with pytest.raises(DBAPIError):
        with readonly_session() as conn:
            conn.execute(text("UPDATE customers SET is_active = is_active WHERE false"))


def test_real_queries_caps_decimal_and_empty_results():
    assert execute_query("SELECT COUNT(*) AS customers FROM customers").rows == [[20]]
    rows = execute_query("SELECT name, unit_price FROM products ORDER BY name LIMIT 999999", max_rows=3)
    assert len(rows.rows) == 3
    assert isinstance(rows.rows[0][1], float)
    assert execute_query("SELECT name FROM products WHERE false").rows == []


def test_view_excludes_cancelled_and_refunded_orders():
    with readonly_session() as conn:
        actual = conn.execute(text("SELECT SUM(revenue) FROM product_performance")).scalar()
        expected = conn.execute(
            text(
                "SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi JOIN orders o USING(order_id) WHERE o.status NOT IN ('cancelled','refunded')"
            )
        ).scalar()
        assert actual == expected
        assert conn.execute(text("SELECT COUNT(*) FROM product_performance")).scalar() == 20


def test_real_api_journey_and_feedback():
    with TestClient(app) as client:
        assert client.get("/v1/ready").status_code == 200
        response = client.post(
            "/v1/query",
            json={
                "question": "SELECT name, unit_price FROM products ORDER BY unit_price DESC LIMIT 5",
                "mode": "sql",
            },
        ).json()
        assert response["status"] == "success"
        assert response["row_count"] == 5
        assert response["confidence"] is None
        assert (
            client.post(
                "/v1/feedback", json={"query_id": response["query_id"], "is_correct": True}
            ).status_code
            == 200
        )
        assert client.get("/v1/history").json()[0]["is_correct"] is True


def test_natural_language_pipeline_with_stubbed_provider_and_real_database(monkeypatch):
    """Provider is explicitly mocked; SQL execution and all pipeline stages are real."""
    import json
    from app.services import sql_generator, hallucination_detector
    from app.services.orchestrator import process_query
    from app.models.schemas import QueryRequest

    def provider(system, user):
        if "SQL generation assistant" in system:
            return json.dumps(
                {
                    "sql": "SELECT COUNT(*) AS customers FROM customers",
                    "explanation": "Count customers",
                    "confidence": 0.95,
                    "tables_used": ["customers"],
                }
            )
        if "SQL analyst" in system:
            return json.dumps({"question": "How many customers are there?", "confidence": 0.9})
        if "expert evaluator" in system:
            return json.dumps({"alignment_score": 0.95, "issues": []})
        return json.dumps({"score": 1, "flags": []})

    monkeypatch.setattr(sql_generator, "complete", provider)
    monkeypatch.setattr(hallucination_detector, "complete", provider)
    response = process_query(QueryRequest(question="How many customers are there?"))
    assert response.status == "success"
    assert response.rows == [[20]]
    assert response.sql.endswith("LIMIT 1000")
    assert response.confidence.back_translation_alignment == 0.95
    assert response.confidence.multi_query_agreement is None
