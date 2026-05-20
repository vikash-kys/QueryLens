from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    QueryRequest, QueryResponse, FeedbackRequest,
    SchemaResponse, EvalResult,
)
from app.services.orchestrator import process_query, record_feedback, get_history
from app.services.schema_extractor import get_schema
from app.services.evals import run_evals
import structlog

log = structlog.get_logger()
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Translate a natural language question to SQL, execute it safely,
    and return results with confidence scores and hallucination flags.
    """
    try:
        return process_query(request)
    except Exception as e:
        log.error("query_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema", response_model=SchemaResponse)
async def schema(refresh: bool = Query(False)):
    """Return the database schema with table/column metadata."""
    try:
        return get_schema(force_refresh=refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def history(limit: int = Query(20, ge=1, le=100)):
    """Return recent query history."""
    return get_history(limit)


@router.post("/feedback")
async def feedback(request: FeedbackRequest):
    """Record user feedback on a query result."""
    record_feedback(request.query_id, request.is_correct, request.comment)
    return {"status": "recorded"}


@router.get("/eval", response_model=EvalResult)
async def eval_suite():
    """Run the automated evaluation suite against golden queries."""
    try:
        return run_evals()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}
