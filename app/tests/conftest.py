"""Shared pytest fixtures for service-level tests.

Provides an in-memory SQLite database and a session fixture that service
tests can use to exercise real ORM flows without touching the dev DB.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Tables are created on the in-memory engine so service tests can
    use real SQLAlchemy queries without depending on the dev database.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_session_module():
    """Module-scoped in-memory SQLite session (shared across a test file)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
