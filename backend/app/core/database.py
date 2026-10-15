from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
from app.config import settings
import structlog

log = structlog.get_logger()


# Read-only engine (restricted user, auto-rollback)
def psycopg_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


readonly_engine = create_engine(
    psycopg_url(settings.database_url),
    poolclass=NullPool,
    connect_args={
        "connect_timeout": 5,
        "options": f"-c statement_timeout={settings.query_timeout_seconds * 1000}",
    },
    echo=False,
)

# Restricted engine for cached schema introspection
schema_engine = create_engine(
    psycopg_url(settings.database_url),
    connect_args={
        "connect_timeout": 5,
        "options": f"-c statement_timeout={settings.query_timeout_seconds * 1000}",
    },
    pool_pre_ping=True,
    echo=False,
)


@contextmanager
def readonly_session():
    """Execute in a read-only transaction that always rolls back."""
    with readonly_engine.connect() as conn:
        # Force read-only at transaction level
        conn.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield conn
        finally:
            conn.rollback()


@contextmanager
def schema_session():
    """Restricted session for schema introspection only."""
    with schema_engine.connect() as conn:
        try:
            yield conn
        finally:
            conn.close()
