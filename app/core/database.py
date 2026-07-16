"""SQLAlchemy database core.

Provides the engine, session factory, declarative base, and a FastAPI
dependency generator for database sessions.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    # Always validate connections before handing them out. Production has
    # seen idle connections dropped by PostgreSQL (idle_timeout, LB, etc.)
    # which then surface as OperationalError and accelerate pool exhaustion.
    pool_pre_ping=True,
    echo=settings.is_development,
    # Pool sizing — defaults (5/10/30s) were too tight for the
    # AD-Research workload: several pages fire /etfs?page_size=10000
    # concurrently and the cel-worker also holds connections, so the
    # default 5+10=15 saturated and /health's `SELECT 1` timed out →
    # nginx 504. Action-253 root-cause analysis (2026-07-16):
    # bump to 10/20, halve the timeout, recycle every 30 min so
    # stale connections don't accumulate. ``pool_timeout=10`` makes
    # overload fail fast (and visible) instead of stacking 30s waits.
    pool_size=10,
    max_overflow=20,
    pool_timeout=10,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection.

    Usage:
        @router.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
