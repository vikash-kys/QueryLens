"""Synchronous handlers run in FastAPI's worker pool, not its event loop."""

from threading import BoundedSemaphore
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from app.config import settings
from app.core.database import readonly_session
from app.models.schemas import QueryRequest, QueryResponse, FeedbackRequest, SchemaResponse, EvalResult
from app.services.orchestrator import process_query, record_feedback, get_history
from app.services.schema_extractor import get_schema
from app.services.evals import run_evals, GOLDEN_CASES
import structlog

log = structlog.get_logger()
router = APIRouter()
_pipeline_slots = BoundedSemaphore(2)
_eval_slot = BoundedSemaphore(1)


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    if not _pipeline_slots.acquire(blocking=False):
        raise HTTPException(429, "Two queries are already running. Please retry shortly.")
    try:
        return process_query(request)
    except Exception as exc:
        log.error("query_endpoint_error", error_type=type(exc).__name__)
        raise HTTPException(500, "Query processing failed. Check the server logs.") from None
    finally:
        _pipeline_slots.release()


@router.get("/schema", response_model=SchemaResponse)
def schema(refresh: bool = Query(False)):
    try:
        return get_schema(force_refresh=refresh)
    except Exception as exc:
        log.error("schema_endpoint_error", error_type=type(exc).__name__)
        raise HTTPException(
            503, "Database unavailable. Check the database service and connection settings."
        ) from None


@router.get("/history")
def history(limit: int = Query(20, ge=1, le=100)):
    return get_history(limit)


@router.post("/feedback")
def feedback(request: FeedbackRequest):
    try:
        record_feedback(request.query_id, request.is_correct, request.comment)
    except KeyError:
        raise HTTPException(
            404, "Query not found. History may have expired or the server restarted."
        ) from None
    return {"status": "recorded"}


@router.post("/eval", response_model=EvalResult)
def eval_suite():
    if not settings.enable_live_evals:
        raise HTTPException(
            403,
            "Live evaluations are disabled. They incur provider usage; enable ENABLE_LIVE_EVALS explicitly.",
        )
    if not _eval_slot.acquire(blocking=False):
        raise HTTPException(409, "An evaluation is already running.")
    try:
        return run_evals()
    except Exception as exc:
        log.error("eval_error", error_type=type(exc).__name__)
        raise HTTPException(500, "Evaluation failed. Check server logs.") from None
    finally:
        _eval_slot.release()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    try:
        with readonly_session() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ready", "database": "connected"}


@router.get("/config")
def public_config():
    return {
        "provider": settings.llm_provider,
        "ai_configured": bool(
            getattr(settings, f"{settings.llm_provider}_api_key")
            and getattr(settings, f"llm_model_{settings.llm_provider}")
        ),
        "live_evals_enabled": settings.enable_live_evals,
        "eval_cases": len(GOLDEN_CASES),
        "max_rows": settings.max_rows,
    }
