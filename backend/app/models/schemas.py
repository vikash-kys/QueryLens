from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Any, Literal
from datetime import datetime, timezone


class QueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(..., min_length=3, max_length=2000)
    clarification_choice: Optional[str] = Field(None, max_length=500)
    mode: Literal["natural_language", "sql"] = "natural_language"


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
    multi_query_agreement: Optional[float] = None


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackRequest(BaseModel):
    query_id: str
    is_correct: bool
    comment: Optional[str] = Field(None, max_length=2000)


class GeneratedQuery(BaseModel):
    sql: Optional[str] = Field(None, max_length=20000)
    explanation: Optional[str] = Field(None, max_length=4000)
    tables_used: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarification_options: list[ClarificationOption] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_output(self):
        if self.needs_clarification and not self.clarification_options:
            raise ValueError("Clarification requires options")
        if not self.needs_clarification and not self.sql:
            raise ValueError("SQL is required")
        return self


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
    shape_pass_rate: float
    flagged_case_rate: float
    guardrail_effectiveness: float
    average_confidence: float
    details: list[dict]
