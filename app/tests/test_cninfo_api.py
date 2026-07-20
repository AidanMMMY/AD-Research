"""Tests for the cninfo-reports API endpoints + service helpers.

Coverage:
- list endpoint: pagination, filters, has_text.
- detail endpoint: success + 404 + preview.
- coverage endpoint: aggregate counts.
- refresh endpoint: admin-only + mocked pipeline.
- download endpoint: admin-only + lazy download.
- provider: HTTP mocked, returns normalised records + never raises.
- org_id lookup: from static table; missing file → None.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import cninfo_reports as cninfo_module
from app.core.database import Base
from app.main import app
from app.models.cninfo_report import CninfoReport
from app.services.cninfo_report_service import CninfoReportService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # ``checkfirst=True`` lets us coexist with pre-existing duplicate
    # indexes elsewhere in Base.metadata (research_reports has duplicate
    # ``ix_research_reports_publish_date`` / ``ix_research_reports_industry``
    # from an earlier migration).  This is a pre-existing issue, not
    # introduced by the cninfo work.
    Base.metadata.create_all(engine, checkfirst=True)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine, checkfirst=True)
        engine.dispose()


def _override_user(role: str = "user"):
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _seed_report(db, **overrides):
    """Insert a single CninfoReport row with sensible defaults."""
    defaults = {
        "ts_code": "600519.SH",
        "stock_code": "600519",
        "org_id": "gssh0600519",
        "sec_code": "600519",
        "announcement_id": "1234567890",
        "announcement_title": "贵州茅台2025年年度报告",
        "adjunct_url": "/finalpage/2026-03-15/1234567890.PDF",
        "announcement_time": datetime(2026, 3, 15, 9, 0, 0),
        "adjunct_type": "annual",
        "is_periodic": True,
        "fiscal_year": 2025,
        "fiscal_quarter": 4,
        "source": "cninfo",
    }
    defaults.update(overrides)
    row = CninfoReport(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def client(db_session):
    """TestClient with DB + service + auth (user) overridden."""

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return CninfoReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[cninfo_module.get_cninfo_report_service] = _get_service_override
    app.dependency_overrides[cninfo_module.get_current_user] = _override_user(role="user")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    """Same as ``client`` but with admin role."""

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_service_override():
        return CninfoReportService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[cninfo_module.get_cninfo_report_service] = _get_service_override
    app.dependency_overrides[cninfo_module.get_current_user] = _override_user(role="admin")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_returns_paginated_items(client, db_session):
    _seed_report(db_session, ts_code="600519.SH", announcement_id="A1")
    _seed_report(db_session, ts_code="601318.SH", announcement_id="A2")
    _seed_report(db_session, ts_code="000001.SZ", announcement_id="A3")

    resp = client.get("/api/v1/cninfo-reports?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_filter_by_ts_code(client, db_session):
    _seed_report(db_session, ts_code="600519.SH", announcement_id="A1")
    _seed_report(db_session, ts_code="601318.SH", announcement_id="A2")

    resp = client.get("/api/v1/cninfo-reports?ts_code=600519.SH")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["ts_code"] == "600519.SH"


def test_list_filter_by_fiscal_year_and_quarter(client, db_session):
    _seed_report(db_session, announcement_id="A1", fiscal_year=2025, fiscal_quarter=4, adjunct_type="annual")
    _seed_report(db_session, announcement_id="A2", fiscal_year=2025, fiscal_quarter=2, adjunct_type="semi")

    resp = client.get("/api/v1/cninfo-reports?fiscal_year=2025&fiscal_quarter=4")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["adjunct_type"] == "annual"


def test_list_filter_by_has_text(client, db_session):
    _seed_report(db_session, announcement_id="A1", extracted_text=None)
    _seed_report(
        db_session,
        announcement_id="A2",
        extracted_text="摘录内容",
        extraction_status="extracted",
        extracted_at=datetime(2026, 4, 1, 10, 0, 0),
    )

    resp = client.get("/api/v1/cninfo-reports?has_text=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["announcement_id"] == "A2"

    resp = client.get("/api/v1/cninfo-reports?has_text=false")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["announcement_id"] == "A1"


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_get_detail_returns_report(client, db_session):
    row = _seed_report(
        db_session,
        announcement_id="XYZ",
        raw_payload='{"announcementId":"XYZ","title":"hi"}',
        extracted_text="这是 PDF 的前 500 字预览" * 30,
    )
    resp = client.get(f"/api/v1/cninfo-reports/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ts_code"] == "600519.SH"
    assert body["announcement_id"] == "XYZ"
    # preview is capped to 500 chars (string, not None)
    assert body["extracted_text_preview"] is not None
    assert len(body["extracted_text_preview"]) <= 500
    assert body["raw_payload"] == {"announcementId": "XYZ", "title": "hi"}


def test_get_detail_404_for_missing(client):
    resp = client.get("/api/v1/cninfo-reports/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Coverage endpoint
# ---------------------------------------------------------------------------


def test_coverage_returns_breakdown(client, db_session):
    _seed_report(db_session, announcement_id="A1", ts_code="600519.SH", fiscal_year=2025, adjunct_type="annual")
    _seed_report(db_session, announcement_id="A2", ts_code="600519.SH", fiscal_year=2025, adjunct_type="annual", extracted_text="x")
    _seed_report(db_session, announcement_id="A3", ts_code="601318.SH", fiscal_year=2025, adjunct_type="semi")

    resp = client.get("/api/v1/cninfo-reports/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_reports"] == 3
    assert body["stocks_covered"] == 2
    assert body["stocks_with_text"] == 1
    assert body["fiscal_year_breakdown"] == {"2025": 3}
    assert body["adjunct_type_breakdown"] == {"annual": 2, "semi": 1}


# ---------------------------------------------------------------------------
# Refresh endpoint
# ---------------------------------------------------------------------------


def test_refresh_requires_admin(client):
    resp = client.post("/api/v1/cninfo-reports/refresh")
    assert resp.status_code == 403


def test_refresh_runs_pipeline_as_admin(admin_client, db_session):
    mock_pipeline = MagicMock()
    mock_pipeline.run_with_retry.return_value = MagicMock(success=True, records=11, error=None)

    with patch.object(cninfo_module, "CninfoReportsPipeline", return_value=mock_pipeline), \
         patch.object(cninfo_module, "redis_lock") as mock_lock, \
         patch.object(cninfo_module, "SessionLocal", return_value=db_session):
        mock_lock.return_value.__enter__.return_value = True
        resp = admin_client.post("/api/v1/cninfo-reports/refresh")

    assert resp.status_code == 202
    assert resp.json() == {"status": "ok", "records": "11"}


def test_refresh_returns_500_when_pipeline_fails(admin_client, db_session):
    mock_pipeline = MagicMock()
    mock_pipeline.run_with_retry.return_value = MagicMock(success=False, error="boom")

    with patch.object(cninfo_module, "CninfoReportsPipeline", return_value=mock_pipeline), \
         patch.object(cninfo_module, "redis_lock") as mock_lock, \
         patch.object(cninfo_module, "SessionLocal", return_value=db_session):
        mock_lock.return_value.__enter__.return_value = True
        resp = admin_client.post("/api/v1/cninfo-reports/refresh")

    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Download endpoint
# ---------------------------------------------------------------------------


def test_download_requires_admin(client, db_session):
    row = _seed_report(db_session, announcement_id="D1")
    resp = client.get(f"/api/v1/cninfo-reports/{row.id}/download")
    assert resp.status_code == 403


def test_download_returns_404_for_missing(admin_client):
    resp = admin_client.get("/api/v1/cninfo-reports/99999/download")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Provider unit tests (mocked HTTP)
# ---------------------------------------------------------------------------


def test_provider_get_org_id_lookup():
    from app.data.providers.cninfo_provider import CninfoProvider

    provider = CninfoProvider()
    # The static table contains 600519.SH
    assert provider.get_org_id("600519.SH") == "gssh0600519"
    # Unknown code returns None (not raises)
    assert provider.get_org_id("999999.SH") is None


def test_provider_fetch_returns_normalised_records():
    """Mocked HTTP: provider returns dicts shaped for the ORM.

    The provider now issues a single ``secid``-based request per page and
    de-duplicates by ``announcementId``, so a duplicate ID in the same
    response must collapse into one record.
    """
    from app.data.providers.cninfo_provider import CninfoProvider

    provider = CninfoProvider()

    def _ann(announcement_id: str) -> dict:
        return {
            "announcementId": announcement_id,
            "announcementTitle": "贵州茅台2025年年度报告",
            "adjunctUrl": f"/finalpage/2026-03-15/{announcement_id}.PDF",
            "announcementTime": "2026-03-15 09:00:00",
            "secCode": "600519",
        }

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "announcements": [_ann("1234"), _ann("1234"), _ann("5678")]
    }

    with patch("app.data.providers.cninfo_provider.requests.post", return_value=fake_response):
        records = provider.fetch_announcements(
            org_id="gssh0600519",
            start_date=__import__("datetime").date(2026, 1, 1),
            end_date=__import__("datetime").date(2026, 12, 31),
            period_type="annual",
        )

    # The duplicate announcementId is deduped → 2 unique records.
    assert len(records) == 2
    assert {r["announcement_id"] for r in records} == {"1234", "5678"}
    assert all(r["adjunct_type"] == "annual" for r in records)
    assert all(r["fiscal_quarter"] == 4 for r in records)
    assert all(r["is_periodic"] is True for r in records)


def test_provider_fetch_handles_http_error_gracefully():
    """Single HTTP failure → returns [] (does not raise)."""
    from app.data.providers.cninfo_provider import CninfoProvider

    provider = CninfoProvider()
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "boom"

    with patch("app.data.providers.cninfo_provider.requests.post", return_value=fake_response):
        records = provider.fetch_announcements(
            org_id="gssh0600519",
            start_date=__import__("datetime").date(2026, 1, 1),
            end_date=__import__("datetime").date(2026, 12, 31),
            period_type="annual",
        )

    assert records == []


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


def test_service_fetch_for_stock_skips_unknown_org_id(db_session):
    """A ts_code not in the static org_id table is silently skipped."""
    service = CninfoReportService(db_session)
    # 999999.SH is not in cninfo_org_ids.json
    written = service.fetch_for_stock(
        ts_code="999999.SH",
        start_date=__import__("datetime").date(2026, 1, 1),
        end_date=__import__("datetime").date(2026, 12, 31),
    )
    assert written == 0
    assert db_session.query(CninfoReport).count() == 0


def test_service_upsert_creates_row(db_session):
    """Service._upsert persists a normalised record."""
    service = CninfoReportService(db_session)
    record = {
        "announcement_id": "TEST-1",
        "announcement_title": "Test annual report",
        "adjunct_url": "/finalpage/2026-03-15/TEST-1.PDF",
        "announcement_time": "2026-03-15 09:00:00",
        "sec_code": "600519",
        "adjunct_type": "annual",
        "is_periodic": True,
        "fiscal_quarter": 4,
        "raw_payload": {"hello": "world"},
    }
    written = service._upsert(record, ts_code="600519.SH", stock_code="600519", org_id="gssh0600519")
    assert written == 1
    row = db_session.query(CninfoReport).filter_by(announcement_id="TEST-1").one()
    assert row.ts_code == "600519.SH"
    assert row.fiscal_year == 2025
    assert row.adjunct_type == "annual"


def test_service_upsert_is_idempotent(db_session):
    """Re-running the upsert does not duplicate rows."""
    service = CninfoReportService(db_session)
    record = {
        "announcement_id": "TEST-2",
        "announcement_title": "Test report 2",
        "adjunct_url": "/finalpage/2026-03-15/TEST-2.PDF",
        "announcement_time": "2026-03-15 09:00:00",
        "sec_code": "600519",
        "adjunct_type": "semi",
        "is_periodic": True,
        "fiscal_quarter": 2,
        "raw_payload": {},
    }
    service._upsert(record, ts_code="600519.SH", stock_code="600519", org_id="gssh0600519")
    service._upsert(record, ts_code="600519.SH", stock_code="600519", org_id="gssh0600519")
    assert db_session.query(CninfoReport).count() == 1


def test_service_list_reports_filters_correctly(db_session):
    _seed_report(db_session, announcement_id="A1", ts_code="600519.SH", adjunct_type="annual")
    _seed_report(db_session, announcement_id="A2", ts_code="601318.SH", adjunct_type="semi")

    service = CninfoReportService(db_session)
    body = service.list_reports(adjunct_type="annual")
    assert body["total"] == 1
    assert body["items"][0]["announcement_id"] == "A1"