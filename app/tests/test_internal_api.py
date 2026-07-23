"""Tests for the internal/orchestrate-alert endpoint (added 2026-07-23).

We don't reload the ``app.main`` module between tests because that pulls
in the scheduler, the LLM provider, and other heavy side effects on a
production database. Instead we drive the *router* directly via FastAPI's
``APIRouter`` + ``TestClient`` and patch ``os.environ`` per test via
``monkeypatch``.
"""
import os
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.v1.internal as internal_mod


@pytest.fixture
def app_instance(monkeypatch):
    """Build a fresh FastAPI app containing only the internal router."""
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token-xyz")
    # Reloading the module refreshes the token-cached behaviour: the
    # endpoint reads ``_expected_token()`` lazily on each call, but the
    # underlying ``os.getenv`` happens in the dependency ``require_internal_token``.
    importlib.reload(internal_mod)
    app = FastAPI()
    app.include_router(internal_mod.router, prefix="/api/v1/internal")
    yield app


@pytest.fixture
def client(app_instance):
    return TestClient(app_instance)


@pytest.fixture
def fake_db_session():
    """Stand-in DB session that records adds/commits without a real engine.

    The ``query()`` chain returns a sentinel that emulates the auto-create
    path in ``_ensure_alert_config`` — i.e. ``one_or_none()`` returns None,
    so the route falls into the INSERT branch. ``flush()`` is a no-op (the
    ``id`` is set explicitly via ``refresh()``) so we don't need a real
    SQLAlchemy session.
    """
    from app.models.notification import NotificationConfig, NotificationLog

    class _FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def one_or_none(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.added: list[object] = []
            self.committed = 0
            self.flushed = 0

        def query(self, *args, **kwargs):
            return _FakeQuery(None)

        def add(self, obj):
            self.added.append(obj)

        def flush(self):
            self.flushed += 1

        def commit(self):
            self.committed += 1

        def refresh(self, obj):
            obj.id = 42  # fake assignment for response payload

        def close(self):
            pass

    return _FakeSession()


def _hdr(token: str = "test-token-xyz") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_orchestrate_alert_requires_token(client):
    """Without the bearer token the route returns 403."""
    resp = client.post(
        "/api/v1/internal/orchestrate-alert",
        json={"failed_workers": [], "schedule": "all"},
    )
    assert resp.status_code == 403


def test_orchestrate_alert_rejects_wrong_token(client):
    resp = client.post(
        "/api/v1/internal/orchestrate-alert",
        json={"failed_workers": [], "schedule": "all"},
        headers={"Authorization": "Bearer not-the-token"},
    )
    assert resp.status_code == 403


def test_orchestrate_alert_skipped_when_no_failures(client):
    resp = client.post(
        "/api/v1/internal/orchestrate-alert",
        json={"failed_workers": [], "schedule": "quick", "threshold": 2},
        headers=_hdr(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["status"] == "skipped"
    assert body["failed_count"] == 0


def test_orchestrate_alert_below_threshold_does_not_log(client):
    """One worker failure with threshold=2 should not log; just acknowledge."""
    resp = client.post(
        "/api/v1/internal/orchestrate-alert",
        json={
            "failed_workers": [
                {"name": "xueqiu", "exit_code": 1, "items": 0, "duration": 1.0, "error": "exit 1"}
            ],
            "schedule": "all",
            "threshold": 2,
        },
        headers=_hdr(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "below_threshold"
    assert body["failed_count"] == 1
    assert body["notification_log_id"] is None


def test_orchestrate_alert_at_threshold_log_calls_get_db(client, app_instance, fake_db_session):
    """Two worker failures with threshold=2 should call into ``get_db`` and log."""
    from app.models.notification import NotificationConfig, NotificationLog
    from app.api.deps import get_db

    # FastAPI's ``dependency_overrides`` is the canonical way to substitute
    # a ``Depends(get_db)`` resolution without monkey-patching module-level
    # symbols (which can be bypassed by module reloads / late binding).
    app_instance.dependency_overrides[get_db] = lambda: (yield fake_db_session)

    resp = client.post(
        "/api/v1/internal/orchestrate-alert",
        json={
            "failed_workers": [
                {"name": "xueqiu_playwright", "exit_code": 66, "items": 0, "duration": 5.0,
                 "error": "image not found"},
                {"name": "reddit_curl_cffi", "exit_code": 1, "items": 0, "duration": 10.0,
                 "error": "WAF block"},
            ],
            "schedule": "logged_in",
            "threshold": 2,
            "total_duration_seconds": 60.0,
            "host": "test-host",
        },
        headers=_hdr(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "logged"
    assert body["failed_count"] == 2
    assert body["notification_log_id"] == 42  # fake refresh() assigns id=42
    # Fake session received a NotificationConfig row + a NotificationLog row.
    assert any(isinstance(o, NotificationConfig) for o in fake_db_session.added)
    assert any(isinstance(o, NotificationLog) for o in fake_db_session.added)
    # ``commit`` only fires after the NotificationLog row is added (the
    # auto-created NotificationConfig is ``flush``-ed but not commit-isolated).
    assert fake_db_session.committed == 1
    assert fake_db_session.flushed == 1  # cfg.flush() to populate id


def test_orchestrate_alert_without_token_env_returns_503(monkeypatch):
    """When INTERNAL_API_TOKEN is not set, the route returns 503 — never opens up."""
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    importlib.reload(internal_mod)
    app = FastAPI()
    app.include_router(internal_mod.router, prefix="/api/v1/internal")
    client_no_token = TestClient(app)
    resp = client_no_token.post(
        "/api/v1/internal/orchestrate-alert",
        json={"failed_workers": [], "schedule": "all"},
        headers={"Authorization": "Bearer anything"},
    )
    assert resp.status_code == 503
