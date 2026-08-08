"""Security tests for report generation (audit 2026-08-06).

Two bugs were fixed here:
1. Path traversal — ``report_type`` / ``format`` were interpolated into the
   output filename unvalidated, so ``report_type="x/../../tmp/pwn"`` wrote
   outside the reports directory.
2. Pool IDOR — report generation/list/status never checked pool ownership,
   so any authenticated user could generate/download reports for any pool.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.pool import ETFPools
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.report import ReportGenerateRequest
from app.services.report_service import ReportService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def owner_scoped(db_session):
    alice = User(username="alice", password_hash="x", role="user", is_active=True)
    bob = User(username="bob", password_hash="x", role="user", is_active=True)
    admin = User(username="admin", password_hash="x", role="admin", is_active=True)
    db_session.add_all([alice, bob, admin])
    db_session.commit()

    p_alice = ETFPools(name="Alice Pool", user_id=alice.id)
    p_shared = ETFPools(name="Shared Pool", user_id=None)
    db_session.add_all([p_alice, p_shared])
    db_session.commit()
    return {"alice": alice, "bob": bob, "admin": admin, "p_alice": p_alice, "p_shared": p_shared}


def _user(u: User) -> UserResponse:
    return UserResponse(id=u.id, username=u.username, role=u.role)


def test_generate_report_rejects_path_traversal_report_type(db_session, owner_scoped):
    """report_type containing path separators must be rejected."""
    svc = ReportService(db_session)
    alice = _user(owner_scoped["alice"])

    with pytest.raises(ValueError):
        svc.generate_pool_report(
            pool_id=owner_scoped["p_alice"].id,
            report_type="x/../../tmp/pwn",
            format="html",
            current_user=alice,
        )


def test_generate_report_rejects_unknown_format(db_session, owner_scoped):
    svc = ReportService(db_session)
    alice = _user(owner_scoped["alice"])

    with pytest.raises(ValueError):
        svc.generate_pool_report(
            pool_id=owner_scoped["p_alice"].id,
            report_type="pool_weekly",
            format="../../evil",
            current_user=alice,
        )


def test_generate_report_other_users_pool_hidden(db_session, owner_scoped):
    """A regular user must not generate a report for another user's pool."""
    svc = ReportService(db_session)
    bob = _user(owner_scoped["bob"])

    with pytest.raises(ValueError):
        svc.generate_pool_report(
            pool_id=owner_scoped["p_alice"].id,
            report_type="pool_weekly",
            format="html",
            current_user=bob,
        )


def test_generate_report_owner_and_shared_visible(db_session, owner_scoped):
    """Own pool + NULL-owner shared pool remain reportable."""
    svc = ReportService(db_session)
    alice = _user(owner_scoped["alice"])

    meta = svc.generate_pool_report(
        pool_id=owner_scoped["p_shared"].id,
        report_type="pool_weekly",
        format="html",
        current_user=alice,
    )
    assert meta.status == "done"
    # File must live inside the reports directory.
    resolved = os.path.realpath(meta.file_path)
    reports_dir = os.path.realpath(svc.reports_dir)
    assert os.path.commonpath([resolved, reports_dir]) == reports_dir


def test_report_request_schema_allowlist():
    """Schema must reject path-traversal report_type / format at the API layer."""
    with pytest.raises(ValueError):
        ReportGenerateRequest(report_type="../../etc/passwd", format="html", pool_id=1)
    with pytest.raises(ValueError):
        ReportGenerateRequest(report_type="pool_weekly", format="../../x", pool_id=1)
    ok = ReportGenerateRequest(report_type="pool_weekly", format="html", pool_id=1)
    assert ok.report_type == "pool_weekly"
