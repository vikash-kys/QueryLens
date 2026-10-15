from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Literal
from pathlib import Path
from pydantic import Field


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://readonly:readonly@127.0.0.1:5433/analytics"

    # LLM
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    llm_provider: Literal["anthropic", "openai", "gemini"] = "anthropic"
    llm_model_anthropic: str = ""
    llm_model_openai: str = ""
    llm_model_gemini: str = ""
    gemini_reasoning_effort: str = "low"

    # Guardrails
    max_rows: int = Field(1000, ge=1, le=10000)
    max_subquery_depth: int = Field(3, ge=1, le=10)
    query_timeout_seconds: int = Field(30, ge=1, le=120)
    llm_timeout_seconds: int = Field(30, ge=1, le=120)
    llm_max_output_tokens: int = Field(4096, ge=256, le=8192)
    enable_ai_review: bool = True
    enable_live_evals: bool = False
    history_limit: int = Field(100, ge=1, le=1000)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Confidence thresholds
    min_confidence_to_execute: float = Field(0.3, ge=0, le=1)
    hallucination_flag_threshold: float = Field(0.5, ge=0, le=1)

    # Repo-root .env when run from backend/, local .env wins if present
    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env", Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
