from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://readonly:readonly@localhost:5432/analytics"
    admin_database_url: str = "postgresql://admin:password@localhost:5432/analytics"

    # LLM
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    llm_provider: str = "anthropic"  # "anthropic", "openai", or "gemini"
    llm_model_anthropic: str = "claude-sonnet-5-5"
    llm_model_openai: str = "gpt-6-astra"
    llm_model_gemini: str = "gemini-3.8-flash"
    gemini_reasoning_effort: str = "low"  # "low" ≈ 2s/call; "high" is slower and hits more 503s

    # Guardrails
    max_rows: int = 1000
    max_subquery_depth: int = 3
    query_timeout_seconds: int = 30

    # Confidence thresholds
    min_confidence_to_execute: float = 0.3
    hallucination_flag_threshold: float = 0.5

    # Repo-root .env when run from backend/, local .env wins if present
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8")


settings = Settings()
