from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
from app.config import settings
import structlog

log = structlog.get_logger()

# Read-only engine (restricted user, auto-rollback)
readonly_engine = create_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"options": "-c statement_timeout=30000"},  # 30s timeout
    echo=False,
)

# Admin engine for schema introspection
admin_engine = create_engine(
    settings.admin_database_url,
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
def admin_session():
    """Admin session for schema introspection only."""
    with admin_engine.connect() as conn:
        try:
            yield conn
        finally:
            conn.close()
