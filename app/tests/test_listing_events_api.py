"""Tests for the listing-events API endpoints.

Covers:
- Listing endpoint: pagination, filter combinations, sort.
- Detail endpoint: success + 404.
- Facets endpoint: distinct values.
- Refresh endpoint: admin-only, with mocked pipeline.
- Auth: every endpoint requires a logged-in user.

The ``get_db`` and ``get_listing_event_service`` dependencies are overridden
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
from app.api.v1 import listing_events as listing_events_module
from app.core.database import Base
from app.main import app
from app.models.listing import ListingEvent
from app.services.listing_event_service import ListingEventService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Uses ``StaticPool`` so the same connection is shared across threads —
    required because ``TestClient`` runs requests in a worker thread that
    would otherwise get a fresh connection that cannot see the schema.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _override_user(role: str = "user"):
    """Build a dependency override for ``get_current_user``."""
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _seed_events(db, rows):
    """Insert a list of dicts as ListingEvent rows directly via SQLAlchemy."""
    for r in rows:
        db.add(ListingEvent(**r))
    db.commit()


def _listing_row(
    ts_code: str,
    name: str,
    *,
    board: str = "主板",
    market: str = "SZ",
    industry: str | None = "电子",
    status: str = "listed",
    issue_date: date | None = date(2026, 1, 15),
    list_date: date | None = date(2026, 2, 1),
    funds_raised=None,
):
    return {
        "ts_code": ts_code,
        "sub_code": ts_code.split(".")[0],
        "name": name,
        "market": market,
        "board": board,
        "industry": industry,
        "issue_date": issue_date,
        "list_date": list_date,
        "issue_price": 25.0,
        "pe_ratio": 22.0,
        "limit_amount": 10000.0,
        "funds_raised": funds_raised,
        "market_amount": 20000.0,
        "sponsor": "Test Sponsor",
        "underwriter": "Test Underwriter",
        "status": status,
        "source": "tushare",
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

    def _get_listing_event_service_override():
        return ListingEventService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[listing_events_module.get_listing_event_service] = _get_listing_event_service_override
    app.dependency_overrides[listing_events_module.get_current_user] = _override_user(role="user")

    with patch("app.api.v1.listing_events.SessionLocal", return_value=db_session), \
         patch("app.services.listing_event_service.cache_get", return_value=None), \
         patch("app.services.listing_event_service.cache_set", return_value=None), \
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

    def _get_listing_event_service_override():
        return ListingEventService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[listing_events_module.get_listing_event_service] = _get_listing_event_service_override
    app.dependency_overrides[listing_events_module.get_current_user] = _override_user(role="admin")

    with patch("app.api.v1.listing_events.SessionLocal", return_value=db_session), \
         patch("app.services.listing_event_service.cache_get", return_value=None), \
         patch("app.services.listing_event_service.cache_set", return_value=None), \
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
    applied. The real ``get_current_user`` dependency runs and returns 401
    (no token in the request).
    """

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _get_listing_event_service_override():
        return ListingEventService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[listing_events_module.get_listing_event_service] = _get_listing_event_service_override

    with patch("app.services.listing_event_service.cache_get", return_value=None), \
         patch("app.services.listing_event_service.cache_set", return_value=None), \
         TestClient(app) as c:
        try:
            resp = c.get("/api/v1/listing-events")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_returns_paginated_items(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Co A"),
        _listing_row("688981.SH", "Co B", board="科创板", market="SH"),
        _listing_row("300750.SZ", "Co C", board="创业板"),
    ])
    resp = client.get("/api/v1/listing-events?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_filter_by_board(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Main"),
        _listing_row("688981.SH", "Star", board="科创板", market="SH"),
    ])
    resp = client.get("/api/v1/listing-events?board=科创板")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Star"


def test_list_filter_by_status_and_market(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Listed SZ"),
        _listing_row("688981.SH", "Listed SH", board="科创板", market="SH"),
        _listing_row("830799.BJ", "Upcoming BSE", board="北交所", market="BJ", status="upcoming"),
    ])
    resp = client.get("/api/v1/listing-events?status=listed&market=SH")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Listed SH"


def test_list_filter_by_search(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Apple Inc"),
        _listing_row("600519.SH", "Maotai", market="SH"),
    ])
    resp = client.get("/api/v1/listing-events?q=apple")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Apple Inc"


def test_list_filter_by_date_range(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Early", list_date=date(2025, 6, 1)),
        _listing_row("600519.SH", "Late", market="SH", list_date=date(2026, 6, 1)),
    ])
    resp = client.get("/api/v1/listing-events?start_date=2026-01-01&end_date=2026-12-31")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Late"


def test_list_sort_by_funds_desc(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Small", funds_raised=10000.0),
        _listing_row("600519.SH", "Big", market="SH", funds_raised=500000.0),
    ])
    resp = client.get("/api/v1/listing-events?sort_by=funds_raised&sort_dir=desc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["name"] == "Big"
    assert body["items"][1]["name"] == "Small"


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_get_detail_returns_event(client, db_session):
    _seed_events(db_session, [_listing_row("001289.SZ", "Detail Co")])
    listing_id = db_session.query(ListingEvent).filter(ListingEvent.ts_code == "001289.SZ").first().id
    resp = client.get(f"/api/v1/listing-events/{listing_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ts_code"] == "001289.SZ"
    assert body["name"] == "Detail Co"
    assert "raw_payload" in body
    assert "created_at" in body


def test_get_detail_returns_404_for_missing(client):
    resp = client.get("/api/v1/listing-events/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Facets endpoint
# ---------------------------------------------------------------------------


def test_facets_returns_distinct_values(client, db_session):
    _seed_events(db_session, [
        _listing_row("001289.SZ", "Co A", board="主板", market="SZ", industry="电子", status="listed"),
        _listing_row("688981.SH", "Co B", board="科创板", market="SH", industry="信息技术", status="upcoming"),
        _listing_row("300750.SZ", "Co C", board="创业板", market="SZ", industry="电子", status="subscribing"),
    ])
    resp = client.get("/api/v1/listing-events/facets")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["boards"]) == {"主板", "科创板", "创业板"}
    assert set(body["markets"]) == {"SZ", "SH"}
    assert set(body["industries"]) == {"电子", "信息技术"}
    assert set(body["statuses"]) == {"listed", "upcoming", "subscribing"}


# ---------------------------------------------------------------------------
# Refresh endpoint (admin only)
# ---------------------------------------------------------------------------


def test_refresh_requires_admin(client):
    """Non-admin user should be forbidden from triggering a refresh."""
    resp = client.post("/api/v1/listing-events/refresh")
    assert resp.status_code == 403


def test_refresh_runs_pipeline_as_admin(admin_client):
    """Admin can trigger a refresh; the pipeline is mocked to return success."""
    with patch.object(
        listing_events_module,
        "ListingEventsPipeline",
        return_value=MagicMock(run_with_retry=MagicMock(return_value=MagicMock(success=True, records=7, error=None))),
    ):
        resp = admin_client.post("/api/v1/listing-events/refresh")
    assert resp.status_code == 202
    assert resp.json() == {"status": "ok", "records": "7"}


def test_refresh_returns_500_when_pipeline_fails(admin_client):
    with patch.object(
        listing_events_module,
        "ListingEventsPipeline",
        return_value=MagicMock(run_with_retry=MagicMock(return_value=MagicMock(success=False, error="boom"))),
    ):
        resp = admin_client.post("/api/v1/listing-events/refresh")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]