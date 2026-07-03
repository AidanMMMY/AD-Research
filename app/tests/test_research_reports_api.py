"""Tests for the research-reports API endpoints.

Covers:
- List endpoint: pagination, filter combinations (industry / org_name / ts_code / date range / has_summary).
- Detail endpoint: success + 404.
- Facets endpoint: distinct values for industries / orgs / ratings.
- Refresh endpoint: admin-only, with mocked pipeline.
- Summarize endpoint: admin-only, with mocked service.
- Auth: every endpoint requires a logged-in user.

The ``get_db`` / ``get_research_report_service`` dependencies are overridden
to use the in-memory test session, and the cache layer is patched to a
no-op so the tests don't require Redis.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import research_reports as research_reports_module
from app.core.database import Base
from app.main import app
from app.models.research_report import ResearchReport
from app.services.research_report_service import ResearchReportService


# The router defines ``prefix="/research-reports"`` and is mounted with
# an additional ``prefix="/research-reports"`` in main.py, so the live
# URL is the doubled path below.
BASE = "/api/v1/research-reports"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Uses ``StaticPool`` so the same connection is shared across threads —
    required because ``TestClient`` runs requests in a worker thread that
    would otherwise get a fresh connection that cannot see the schema.

    The ``research_reports`` ORM model declares some indexes both via
    ``Column(index=True)`` and as named ``Index`` entries in
    ``__table_args__``; SQLAlchemy does not deduplicate those, so
    ``Base.metadata.create_all`` errors on SQLite with "index already
    exists".  To stay aligned with the model the test instead creates
    the table by stripping the duplicate Index entries from a copy of
    the table's ``__table_args__``.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Build a one-off Table definition that mirrors the ORM model but
    # omits the duplicate ``Index`` declarations. The ORM stays the
    # single source of truth for the test.
    from sqlalchemy import (
        JSON, Column, Date, DateTime, Integer, Numeric, String, Text,
        UniqueConstraint, func,
    )
    test_table = ResearchReport.__table__.to_metadata(Base.metadata)
    # Drop all extra indexes; keep only those from Column(index=True).
    test_table.indexes.clear()
    test_table.create(engine, checkfirst=False)

    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        test_table.drop(engine, checkfirst=False)
        engine.dispose()


def _override_user(role: str = "user"):
    """Build a dependency override for ``get_current_user``."""
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _seed_reports(db, rows):
    """Insert a list of dicts as ResearchReport rows directly via SQLAlchemy."""
    for r in rows:
        db.add(ResearchReport(**r))
    db.commit()


def _report_row(
    ts_code: str = "600519.SH",
    name: str = "贵州茅台",
    title: str = "Sample title",
    org_name: str = "国泰君安",
    industry: str | None = "食品饮料",
    publish_date: date = date(2026, 6, 1),
    rating: str | None = "买入",
    summary: str | None = None,
    target_price=None,
):
    return {
        "ts_code": ts_code,
        "name": name,
        "title": title,
        "org_name": org_name,
        "industry": industry,
        "publish_date": publish_date,
        "rating": rating,
        "pdf_url": None,
        "summary": summary,
        "key_points": None,
        "target_price": target_price,
        "source": "eastmoney",
    }


@pytest.fixture
def client(db_session):
    """Return a TestClient with DB / auth / cache dependencies overridden.

    By default authenticates as a regular user. Tests that need admin
    requests re-register the override themselves, then restore it.
    """

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return ResearchReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[research_reports_module.get_research_report_service] = _get_service_override
    app.dependency_overrides[research_reports_module.get_current_user] = _override_user(role="user")

    with patch("app.api.v1.research_reports.SessionLocal", return_value=db_session), \
         patch("app.services.research_report_service.cache_get", return_value=None), \
         patch("app.services.research_report_service.cache_set", return_value=None), \
         TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    """Same as ``client`` but the current user has admin role."""

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return ResearchReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[research_reports_module.get_research_report_service] = _get_service_override
    app.dependency_overrides[research_reports_module.get_current_user] = _override_user(role="admin")

    with patch("app.api.v1.research_reports.SessionLocal", return_value=db_session), \
         patch("app.services.research_report_service.cache_get", return_value=None), \
         patch("app.services.research_report_service.cache_set", return_value=None), \
         TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_list_requires_auth(db_session):
    """Without an auth override, the API should reject the request.

    Built with a separate TestClient that does NOT have the auth override
    applied. The real ``get_current_user`` dependency runs and returns 401.
    """

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return ResearchReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[research_reports_module.get_research_report_service] = _get_service_override

    with patch("app.services.research_report_service.cache_get", return_value=None), \
         patch("app.services.research_report_service.cache_set", return_value=None), \
         TestClient(app) as c:
        try:
            resp = c.get("/api/v1/research-reports")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_returns_paginated_items(client, db_session):
    _seed_reports(db_session, [
        _report_row(ts_code="600519.SH", name="贵州茅台", title="Report A"),
        _report_row(ts_code="000858.SZ", name="五粮液", title="Report B"),
        _report_row(ts_code="601318.SH", name="中国平安", title="Report C"),
    ])
    resp = client.get("/api/v1/research-reports?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_filter_by_ts_code(client, db_session):
    _seed_reports(db_session, [
        _report_row(ts_code="600519.SH", name="贵州茅台", title="R1"),
        _report_row(ts_code="000858.SZ", name="五粮液", title="R2"),
    ])
    resp = client.get("/api/v1/research-reports?ts_code=600519.SH")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["ts_code"] == "600519.SH"


def test_list_filter_by_industry_and_org(client, db_session):
    _seed_reports(db_session, [
        _report_row(industry="食品饮料", org_name="国泰君安", title="R1"),
        _report_row(industry="电子", org_name="中信证券", title="R2"),
        _report_row(industry="食品饮料", org_name="中信证券", title="R3"),
    ])
    resp = client.get("/api/v1/research-reports?industry=%E9%A3%9F%E5%93%81%E9%A5%AE%E6%96%99&org_name=%E4%B8%AD%E4%BF%A1%E8%AF%81%E5%88%B8")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "R3"


def test_list_filter_by_date_range(client, db_session):
    _seed_reports(db_session, [
        _report_row(publish_date=date(2026, 5, 1), title="Early"),
        _report_row(publish_date=date(2026, 6, 15), title="Mid"),
        _report_row(publish_date=date(2026, 6, 30), title="Late"),
    ])
    resp = client.get(
        "/api/v1/research-reports?start_date=2026-06-01&end_date=2026-06-30"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    titles = {it["title"] for it in body["items"]}
    assert titles == {"Mid", "Late"}


def test_list_filter_by_rating(client, db_session):
    _seed_reports(db_session, [
        _report_row(title="Buy", rating="买入"),
        _report_row(title="Hold", rating="中性"),
        _report_row(title="Add", rating="增持"),
    ])
    resp = client.get("/api/v1/research-reports?rating=%E4%B9%B0%E5%85%A5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Buy"


def test_list_filter_by_has_summary(client, db_session):
    _seed_reports(db_session, [
        _report_row(title="WithSum", summary="Short summary"),
        _report_row(title="NoSum"),
    ])
    resp_yes = client.get("/api/v1/research-reports?has_summary=true")
    assert resp_yes.status_code == 200
    body_yes = resp_yes.json()
    assert body_yes["total"] == 1
    assert body_yes["items"][0]["title"] == "WithSum"

    resp_no = client.get("/api/v1/research-reports?has_summary=false")
    assert resp_no.status_code == 200
    body_no = resp_no.json()
    assert body_no["total"] == 1
    assert body_no["items"][0]["title"] == "NoSum"


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_get_detail_returns_report(client, db_session):
    _seed_reports(db_session, [_report_row(title="Detail Me", summary="abc")])
    rid = (
        db_session.query(ResearchReport)
        .filter(ResearchReport.title == "Detail Me")
        .first()
        .id
    )
    resp = client.get(f"/api/v1/research-reports/{rid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Detail Me"
    assert body["summary"] == "abc"
    assert "raw_payload" in body


def test_get_detail_returns_404_for_missing(client):
    resp = client.get("/api/v1/research-reports/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Facets endpoint
# ---------------------------------------------------------------------------


def test_facets_returns_distinct_values(client, db_session):
    _seed_reports(db_session, [
        _report_row(title="Facet-A", industry="食品饮料", org_name="国泰君安", rating="买入"),
        _report_row(title="Facet-B", industry="电子", org_name="中信证券", rating="增持"),
        _report_row(title="Facet-C", industry="食品饮料", org_name="中信证券", rating="中性"),
    ])
    resp = client.get("/api/v1/research-reports/facets")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["industries"]) == {"食品饮料", "电子"}
    assert set(body["orgs"]) == {"国泰君安", "中信证券"}
    assert set(body["ratings"]) == {"买入", "增持", "中性"}


# ---------------------------------------------------------------------------
# Refresh endpoint (admin only)
# ---------------------------------------------------------------------------


def test_refresh_requires_admin(client):
    """Non-admin user should be forbidden from triggering a refresh."""
    resp = client.post("/api/v1/research-reports/refresh")
    assert resp.status_code == 403


def test_refresh_runs_pipeline_as_admin(admin_client):
    """Admin can trigger a refresh; the pipeline is mocked to return success."""
    with patch.object(
        research_reports_module,
        "ResearchReportsPipeline",
        return_value=MagicMock(
            run_with_retry=MagicMock(
                return_value=MagicMock(success=True, records=11, error=None)
            )
        ),
    ):
        resp = admin_client.post("/api/v1/research-reports/refresh")
    assert resp.status_code == 202
    assert resp.json() == {"status": "ok", "records": "11"}


def test_refresh_returns_500_when_pipeline_fails(admin_client):
    with patch.object(
        research_reports_module,
        "ResearchReportsPipeline",
        return_value=MagicMock(
            run_with_retry=MagicMock(
                return_value=MagicMock(success=False, error="boom")
            )
        ),
    ):
        resp = admin_client.post("/api/v1/research-reports/refresh")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Summarize endpoint (authenticated + per-user rate limit)
# ---------------------------------------------------------------------------


def test_summarize_requires_auth(db_session):
    """Without an auth override the real ``get_current_user`` runs and
    rejects anonymous callers. FastAPI's HTTPBearer returns 403 when
    no token is provided and 401 for an invalid/expired token — accept
    either, mirroring ``test_list_requires_auth``."""
    _seed_reports(db_session, [_report_row(title="ToSummarize")])
    rid = (
        db_session.query(ResearchReport)
        .filter(ResearchReport.title == "ToSummarize")
        .first()
        .id
    )

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return ResearchReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[research_reports_module.get_research_report_service] = _get_service_override

    with patch("app.services.research_report_service.cache_get", return_value=None), \
         patch("app.services.research_report_service.cache_set", return_value=None), \
         TestClient(app) as c:
        try:
            resp = c.post(f"/api/v1/research-reports/{rid}/summarize")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code in (401, 403)


def test_summarize_runs_service_as_user(client, db_session):
    """Any authenticated user (not just admin) can trigger summarize."""
    _seed_reports(db_session, [_report_row(title="ToSummarize")])
    rid = (
        db_session.query(ResearchReport)
        .filter(ResearchReport.title == "ToSummarize")
        .first()
        .id
    )
    with patch.object(
        research_reports_module.ResearchReportService,
        "summarize_with_deepseek",
        return_value="generated summary text",
    ) as mock_sum:
        resp = client.post(f"/api/v1/research-reports/{rid}/summarize")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ok"
    assert body["id"] == str(rid)
    assert body["summary"] == "generated summary text"
    mock_sum.assert_called_once_with(rid)


def test_summarize_returns_404_for_missing(client):
    resp = client.post("/api/v1/research-reports/99999/summarize")
    assert resp.status_code == 404


def test_summarize_rate_limit_enforced(client, db_session):
    """The 101st call in a day for the same user should return 429."""
    _seed_reports(db_session, [_report_row(title="ToSummarize")])
    rid = (
        db_session.query(ResearchReport)
        .filter(ResearchReport.title == "ToSummarize")
        .first()
        .id
    )

    fake_redis = MagicMock()
    # Simulate the counter already at the daily cap on the first hit so
    # any call from this user is rejected.
    fake_redis.incr.return_value = 101

    with patch.object(
        research_reports_module.ResearchReportService,
        "summarize_with_deepseek",
        return_value="generated summary text",
    ), patch(
        "app.api.v1.research_reports.get_redis_client", return_value=fake_redis
    ):
        resp = client.post(f"/api/v1/research-reports/{rid}/summarize")

    assert resp.status_code == 429
    body = resp.json()
    # Detail should mention the daily cap so the frontend can show the
    # user a clear message.
    assert "100" in body["detail"]
    assert "今日" in body["detail"]