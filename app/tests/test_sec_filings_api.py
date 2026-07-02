"""Tests for the SEC filings API endpoints.

Covers:
- Listing endpoint: pagination + filters (ticker, form_type, date range).
- Coverage endpoint: aggregate stats.
- Detail endpoint: success + 404.
- Accession-based lookup: success + 404.
- Sync ticker endpoint: admin-only, calls provider.
- Refresh endpoint: admin-only.
- Auth: every endpoint requires a logged-in user.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import sec_filings as sec_filings_module
from app.core.database import Base
from app.main import app
from app.models.sec_filing import SecFiling
from app.services.sec_filing_service import SecFilingService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Only creates the tables this test file touches (``sec_filings``)
    so we sidestep pre-existing duplicate-index issues in unrelated
    tables that share ``Base.metadata``.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.sec_filing import SecFiling as _SecFiling

    _SecFiling.__table__.create(engine, checkfirst=True)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _override_user(role: str = "user"):
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _seed_filings(db, rows):
    for r in rows:
        db.add(SecFiling(**r))
    db.commit()


def _filing_row(
    ticker: str = "AAPL",
    cik: str = "0000320193",
    form_type: str = "10-K",
    filing_date: date = date(2026, 1, 15),
    accession: str | None = None,
    extraction_status: str = "pending",
):
    return {
        "cik": cik,
        "ticker": ticker,
        "company_name": f"{ticker} Inc",
        "form_type": form_type,
        "filing_date": filing_date,
        "report_period": filing_date,
        "accession_number": accession or f"0000{cik}-26-{abs(hash(ticker+form_type)) % 1000000:06d}",
        "primary_document": "form.htm",
        "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar",
        "extraction_status": extraction_status,
        "source": "sec_edgar",
    }


@pytest.fixture
def client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[sec_filings_module.get_current_user] = _override_user(role="user")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[sec_filings_module.get_current_user] = _override_user(role="admin")

    with TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_filings_empty(client):
    resp = client.get("/api/v1/sec-filings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_filings_with_data(client, db_session):
    _seed_filings(
        db_session,
        [
            _filing_row(ticker="AAPL", accession="0000320193-26-000001"),
            _filing_row(ticker="AAPL", form_type="10-Q",
                        accession="0000320193-26-000002",
                        filing_date=date(2026, 4, 15)),
            _filing_row(ticker="MSFT", accession="0000789019-26-000001"),
        ],
    )
    resp = client.get("/api/v1/sec-filings?ticker=AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(item["ticker"] == "AAPL" for item in body["items"])


def test_list_filings_filter_form_type(client, db_session):
    _seed_filings(
        db_session,
        [
            _filing_row(form_type="10-K", accession="0000320193-26-000010"),
            _filing_row(form_type="10-Q", accession="0000320193-26-000011"),
        ],
    )
    resp = client.get("/api/v1/sec-filings?form_type=10-K")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["form_type"] == "10-K"


def test_list_filings_date_range(client, db_session):
    _seed_filings(
        db_session,
        [
            _filing_row(filing_date=date(2025, 6, 1), accession="0000320193-26-000020"),
            _filing_row(filing_date=date(2026, 6, 1), accession="0000320193-26-000021"),
        ],
    )
    resp = client.get("/api/v1/sec-filings?start_date=2026-01-01&end_date=2026-12-31")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["filing_date"] == "2026-06-01"


def test_coverage_endpoint(client, db_session):
    _seed_filings(
        db_session,
        [
            _filing_row(form_type="10-K", accession="0000320193-26-000030",
                        extraction_status="success"),
            _filing_row(ticker="MSFT", accession="0000789019-26-000030",
                        extraction_status="pending"),
        ],
    )
    resp = client.get("/api/v1/sec-filings/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_filings"] == 2
    assert body["tracked_tickers"] == 2
    assert body["extractions_completed"] == 1
    assert body["extractions_pending"] == 1
    assert "10-K" in body["by_form_type"]


def test_filing_detail_success(client, db_session):
    _seed_filings(db_session, [_filing_row(accession="0000320193-26-000040")])
    resp = client.get("/api/v1/sec-filings/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["accession_number"] == "0000320193-26-000040"


def test_filing_detail_not_found(client):
    resp = client.get("/api/v1/sec-filings/999")
    assert resp.status_code == 404


def test_filing_by_accession(client, db_session):
    _seed_filings(db_session, [_filing_row(accession="0000320193-26-000050")])
    resp = client.get("/api/v1/sec-filings/by-accession/0000320193-26-000050")
    assert resp.status_code == 200
    body = resp.json()
    assert body["accession_number"] == "0000320193-26-000050"


def test_filing_by_accession_not_found(client):
    resp = client.get("/api/v1/sec-filings/by-accession/nonexistent")
    assert resp.status_code == 404


def test_sync_ticker_requires_admin(client):
    """Sync endpoint requires admin role."""
    resp = client.post("/api/v1/sec-filings/sync/AAPL")
    assert resp.status_code == 403


def test_sync_ticker_admin_success(admin_client, db_session):
    """Admin sync calls the provider and returns ok."""
    mock_provider = MagicMock()
    mock_provider.load_ticker_to_cik_map.return_value = {"AAPL": "0000320193"}
    mock_provider.fetch_submissions.return_value = {
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q"],
                "filingDate": ["2026-01-15", "2026-04-15"],
                "reportDate": ["2025-12-31", "2026-03-31"],
                "accessionNumber": ["0000320193-26-000100", "0000320193-26-000101"],
                "primaryDocument": ["form10k.htm", "form10q.htm"],
            }
        },
    }

    with patch.object(SecFilingService, "__init__", lambda self, db, provider=None: setattr(self, "db", db) or setattr(self, "provider", mock_provider)):
        # Patch the provider class so service picks up our mock
        with patch("app.services.sec_filing_service.SecEdgarProvider", return_value=mock_provider):
            resp = admin_client.post("/api/v1/sec-filings/sync/AAPL")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "ok"
            assert body["ticker"] == "AAPL"
            assert body["written"] == 2


def test_refresh_requires_admin(client):
    resp = client.post("/api/v1/sec-filings/refresh")
    assert resp.status_code == 403


def test_refresh_admin_success(admin_client):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records = 5
    mock_result.warnings = []
    mock_pipeline.run_with_retry.return_value = mock_result

    with patch("app.api.v1.sec_filings.SecEdgarPipeline", return_value=mock_pipeline):
        with patch("app.api.v1.sec_filings.SessionLocal") as mock_session_local:
            mock_session_local.return_value = MagicMock()
            resp = admin_client.post("/api/v1/sec-filings/refresh")
            assert resp.status_code == 202, resp.text
            assert resp.json()["status"] == "ok"


def test_extract_metrics_requires_admin(client, db_session):
    _seed_filings(db_session, [_filing_row(accession="0000320193-26-000200")])
    resp = client.post("/api/v1/sec-filings/1/extract-metrics")
    assert resp.status_code == 403


def test_extract_metrics_admin_success(admin_client, db_session):
    _seed_filings(db_session, [_filing_row(accession="0000320193-26-000210")])
    mock_provider = MagicMock()
    mock_provider.fetch_company_facts.return_value = {"facts": {}}
    mock_provider.extract_metrics.return_value = [{"concept": "Revenues", "value": 100}]

    with patch("app.api.v1.sec_filings.get_db", return_value=iter([db_session])):
        with patch.object(SecFilingService, "__init__", lambda self, db, provider=None: setattr(self, "db", db) or setattr(self, "provider", mock_provider)):
            with patch("app.services.sec_filing_service.SecEdgarProvider", return_value=mock_provider):
                resp = admin_client.post("/api/v1/sec-filings/1/extract-metrics")
                assert resp.status_code == 200
                assert resp.json()["status"] == "ok"


def test_unauthenticated_request_rejected():
    """No auth override → 401 / 403."""
    with TestClient(app) as c:
        resp = c.get("/api/v1/sec-filings")
        assert resp.status_code in (401, 403)