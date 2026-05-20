from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    session_id: Optional[str] = None
    clarification_choice: Optional[str] = None  # when resolving ambiguity


class GuardrailViolation(BaseModel):
    rule: str
    detail: str
    severity: str  # "block" | "warn"


class ConfidenceBreakdown(BaseModel):
    syntax_valid: float
    back_translation_alignment: float
    result_sanity: float
    schema_coverage: float
    overall: float


class ClarificationOption(BaseModel):
    label: str
    description: str
    example_sql: str


class QueryResponse(BaseModel):
    query_id: str
    question: str
    sql: Optional[str] = None
    explanation: Optional[str] = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    total_rows_available: int = 0
    execution_time_ms: Optional[float] = None
    confidence: Optional[ConfidenceBreakdown] = None
    guardrail_violations: list[GuardrailViolation] = []
    hallucination_flags: list[str] = []
    back_translation: Optional[str] = None
    tables_used: list[str] = []
    status: str  # "success" | "blocked" | "clarification_needed" | "error"
    error_message: Optional[str] = None
    clarification_options: list[ClarificationOption] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FeedbackRequest(BaseModel):
    query_id: str
    is_correct: bool
    comment: Optional[str] = None


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    comment: Optional[str] = None
    sample_values: list[Any] = []


class TableInfo(BaseModel):
    name: str
    comment: Optional[str] = None
    columns: list[ColumnInfo] = []
    row_count: Optional[int] = None
    primary_keys: list[str] = []
    foreign_keys: list[dict] = []


class SchemaResponse(BaseModel):
    tables: list[TableInfo]
    relationships: list[dict]


class HistoryItem(BaseModel):
    query_id: str
    question: str
    sql: Optional[str]
    status: str
    confidence: Optional[float]
    is_correct: Optional[bool]
    timestamp: datetime


class EvalResult(BaseModel):
    total_cases: int
    sql_accuracy: float
    execution_accuracy: float
    hallucination_detection_rate: float
    guardrail_effectiveness: float
    average_confidence: float
    details: list[dict]
