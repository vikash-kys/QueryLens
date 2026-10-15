import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.models.schemas import QueryRequest, QueryResponse, SchemaResponse, GeneratedQuery
from app.services import orchestrator as pipeline
from app.services import sql_generator, hallucination_detector as detector, evals
from app.services.guardrails import check_guardrails, is_blocked, inject_limit
from app.services.executor import execute_query, ExecutionResult
from app.config import settings


@pytest.fixture(autouse=True)
def clean_history(monkeypatch):
    monkeypatch.setattr(settings, "enable_ai_review", True)
    pipeline._query_history.clear()
    pipeline._feedback.clear()
    yield
    pipeline._query_history.clear()
    pipeline._feedback.clear()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "DROP TABLE products",
        "SELECT 1; SELECT 2",
        "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x",
        "SELECT * INTO stolen FROM customers",
        "SELECT * FROM customers FOR UPDATE",
        "SELECT pg_sleep(10)",
        "SELECT public.pg_sleep(10)",
        "SELECT * FROM pg_catalog.pg_authid",
        'SELECT * FROM "pg_catalog"."pg_authid"',
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_user",
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT custom_side_effect()",
        "SELECT lo_export(1, '/tmp/a')",
        "WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT 1 FROM x) SELECT * FROM x",
        "COPY customers TO STDOUT",
        "",
        "BEGIN",
        "SELECT 1; -- comment\n DELETE FROM customers",
    ],
)
def test_unsafe_sql_rejected(sql):
    assert is_blocked(check_guardrails(sql))
    with pytest.raises(ValueError):
        execute_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'DELETE and DROP are text' AS label",
        "SELECT COUNT(*) FROM customers",
        "WITH x AS (SELECT country FROM customers) SELECT * FROM x",
        "SELECT country, COUNT(*) FROM customers GROUP BY country",
        "SELECT DATE_TRUNC('month', created_at), SUM(discount_pct) FROM orders GROUP BY 1",
        "SELECT name, ROUND(unit_price, 2) FROM products ORDER BY name LIMIT 5",
        "SELECT 1 UNION ALL SELECT 2",
    ],
)
def test_safe_analytics_allowed(sql):
    assert not is_blocked(check_guardrails(sql))


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers LIMIT 999999",
        "SELECT * FROM (SELECT * FROM customers LIMIT 1) AS x",
        "SELECT 'LIMIT' AS label",
        "SELECT country, COUNT(*) FROM customers GROUP BY country",
        "SELECT * FROM customers LIMIT ALL",
    ],
)
def test_outer_limit_always_capped(sql):
    import sqlglot

    tree = sqlglot.parse_one(inject_limit(sql, 7), read="postgres")
    assert tree.args["limit"].expression.this == "7"


def test_existing_small_limit_preserved():
    assert inject_limit("SELECT * FROM customers LIMIT 2", 7).endswith("LIMIT 2")


def test_request_and_model_output_validation():
    with pytest.raises(ValidationError):
        QueryRequest(question="   ")
    with pytest.raises(ValidationError):
        GeneratedQuery(sql="SELECT 1", confidence=2)
    with pytest.raises(ValidationError):
        GeneratedQuery(confidence=0.5, needs_clarification=True)


def test_invalid_generation_is_explicit(monkeypatch):
    monkeypatch.setattr(
        sql_generator, "complete", lambda **kwargs: '{"sql": ["SELECT 1"], "confidence": 0.9}'
    )
    assert sql_generator.generate_sql("question", "schema")["sql"] is None


def test_clarification_incorporated_and_no_execution(monkeypatch):
    monkeypatch.setattr(pipeline, "get_schema", lambda: SchemaResponse(tables=[], relationships=[]))
    questions = []

    def generate(question, context):
        questions.append(question)
        return {
            "needs_clarification": True,
            "clarification_options": [
                {"label": "Net", "description": "After discounts", "example_sql": "SELECT 1"}
            ],
        }

    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(
        pipeline, "execute_query", lambda _: pytest.fail("Clarification must not execute SQL")
    )
    response = pipeline.process_query(
        QueryRequest(question="Revenue?", clarification_choice="Net after discounts")
    )
    assert response.status == "clarification_needed"
    assert "Net after discounts" in questions[0]
    assert pipeline.get_history()[0]["status"] == "clarification_needed"


def test_low_confidence_does_not_execute(monkeypatch):
    monkeypatch.setattr(pipeline, "get_schema", lambda: SchemaResponse(tables=[], relationships=[]))
    monkeypatch.setattr(pipeline, "generate_sql", lambda *args: {"sql": "SELECT 1", "confidence": 0.1})
    monkeypatch.setattr(pipeline, "execute_query", lambda _: pytest.fail("Low confidence SQL executed"))
    assert pipeline.process_query(QueryRequest(question="How many?")).status == "blocked"


def test_alternate_sql_is_guarded_at_executor(monkeypatch):
    monkeypatch.setattr(pipeline, "get_schema", lambda: SchemaResponse(tables=[], relationships=[]))
    monkeypatch.setattr(pipeline, "generate_sql", lambda *args: {"sql": "SELECT 1", "confidence": 0.9})
    monkeypatch.setattr(pipeline, "generate_alternate_sql", lambda *args: {"sql": "SELECT pg_sleep(10)"})
    monkeypatch.setattr(pipeline, "back_translate", lambda _: ("How many?", 0.9))
    monkeypatch.setattr(pipeline, "score_alignment", lambda *args: (0.7, []))
    monkeypatch.setattr(pipeline, "check_result_sanity", lambda *args: (0.8, []))
    seen = []

    def execute(sql):
        seen.append(sql)
        if len(seen) == 1:
            return ExecutionResult(["count"], [[1]], 1, 1, 1)
        return execute_query(sql)  # Actual executor must reject before connecting.

    monkeypatch.setattr(pipeline, "execute_query", execute)
    response = pipeline.process_query(QueryRequest(question="How many?"))
    assert response.status == "success"
    assert response.confidence.multi_query_agreement is None
    assert len(seen) == 2


def test_compare_all_values_not_just_first_row():
    a = ExecutionResult(["name"], [["same"], ["A"]], 2, 2, 1)
    b = ExecutionResult(["name"], [["same"], ["B"]], 2, 2, 1)
    assert detector.validate_multi_query(a, b)[0] == 0
    b.rows = [["A"], ["same"]]
    assert detector.validate_multi_query(a, b)[0] == 1


def test_unmeasured_confidence_is_not_fabricated():
    score = detector.compute_confidence(True, 1, 1, 1, None)
    assert score.multi_query_agreement is None
    assert score.overall == 1


def test_api_validation_feedback_and_bounded_history(monkeypatch):
    monkeypatch.setattr(settings, "history_limit", 2)
    monkeypatch.setattr(settings, "enable_live_evals", False)
    with TestClient(app) as client:
        assert client.post("/v1/query", json={"question": "   "}).status_code == 422
        assert (
            client.post("/v1/feedback", json={"query_id": "missing", "is_correct": True}).status_code == 404
        )
        assert client.post("/v1/eval").status_code == 403
        assert client.get("/v1/eval").status_code == 405
        ids = []
        for _ in range(3):
            result = client.post(
                "/v1/query", json={"question": "DELETE FROM customers", "mode": "sql"}
            ).json()
            assert result["status"] == "blocked"
            ids.append(result["query_id"])
        assert len(client.get("/v1/history").json()) == 2
        assert client.post("/v1/feedback", json={"query_id": ids[-1], "is_correct": True}).status_code == 200
        assert client.post("/v1/feedback", json={"query_id": ids[0], "is_correct": True}).status_code == 404


def test_database_failure_is_sanitized_and_recorded(monkeypatch):
    def fail():
        raise RuntimeError("secret password and connection string")

    monkeypatch.setattr(pipeline, "get_schema", fail)
    response = pipeline.process_query(QueryRequest(question="How many customers?"))
    assert response.status == "error"
    assert "secret" not in response.error_message
    assert pipeline.get_history()[0]["status"] == "error"


def test_eval_denominator_includes_failures_and_exceptions(monkeypatch):
    monkeypatch.setattr(
        evals,
        "GOLDEN_CASES",
        [{"question": "one", "expect_rows": 1}, {"question": "two"}, {"question": "three"}],
    )

    def process(request):
        if request.question == "three":
            raise RuntimeError("test failure")
        return QueryResponse(
            query_id=request.question,
            question=request.question,
            status="success" if request.question == "one" else "error",
            row_count=1,
        )

    monkeypatch.setattr(evals, "process_query", process)
    result = evals.run_evals()
    assert result.shape_pass_rate == 0.333
    assert len(result.details) == 3


def test_settings_env_paths_point_inside_repository():
    from pathlib import Path
    from app.config import Settings

    paths = Settings.model_config["env_file"]
    root = Path(__file__).resolve().parents[1]
    assert paths == (root / ".env", root / "backend" / ".env")


def test_provider_failure_does_not_look_like_success(monkeypatch):
    monkeypatch.setattr(pipeline, "get_schema", lambda: SchemaResponse(tables=[], relationships=[]))

    def unavailable(*args):
        raise TimeoutError("sensitive provider details")

    monkeypatch.setattr(pipeline, "generate_sql", unavailable)
    response = pipeline.process_query(QueryRequest(question="How many customers?"))
    assert response.status == "error"
    assert "sensitive" not in response.error_message


def test_malformed_alignment_fails_conservatively(monkeypatch):
    monkeypatch.setattr(detector, "complete", lambda **kwargs: '{"alignment_score": 5, "issues": []}')
    score, issues = detector.score_alignment("question", "interpretation")
    assert score == 0
    assert issues


def test_query_concurrency_returns_retryable_response():
    from app.api.routes import _pipeline_slots

    assert _pipeline_slots.acquire(blocking=False)
    assert _pipeline_slots.acquire(blocking=False)
    try:
        with TestClient(app) as client:
            assert client.post("/v1/query", json={"question": "SELECT 1", "mode": "sql"}).status_code == 429
            assert client.get("/v1/health").status_code == 200
    finally:
        _pipeline_slots.release()
        _pipeline_slots.release()


def test_single_call_mode_skips_all_model_review(monkeypatch):
    monkeypatch.setattr(settings, "enable_ai_review", False)
    monkeypatch.setattr(pipeline, "get_schema", lambda: SchemaResponse(tables=[], relationships=[]))
    calls = []

    def generate(*args):
        calls.append("generate")
        return {"sql": "SELECT 1", "confidence": 0.95, "explanation": "One row"}

    monkeypatch.setattr(pipeline, "generate_sql", generate)
    monkeypatch.setattr(pipeline, "execute_query", lambda _: ExecutionResult(["value"], [[1]], 1, 1, 1))

    def forbidden(*args):
        pytest.fail("Single-call mode must not invoke extra model checks")

    for stage in ["back_translate", "score_alignment", "check_result_sanity", "generate_alternate_sql"]:
        monkeypatch.setattr(pipeline, stage, forbidden)
    response = pipeline.process_query(QueryRequest(question="Return one row"))
    assert calls == ["generate"]
    assert response.status == "success"
    assert response.confidence is None
    assert "Single-call AI mode" in response.hallucination_flags[0]
