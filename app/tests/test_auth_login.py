"""Tests for the login endpoint, focused on response shape.

Regression coverage for the 2026-07-01 incident where ``UserResponse``
was constructed without ``id`` in the login handler, causing a 500
Pydantic ValidationError that the frontend mis-rendered as
"用户名密码不正确".
"""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import auth as auth_module
from app.core.database import Base
from app.main import app
from app.models.user import User


@pytest.fixture
def db_session():
    """In-memory SQLite session shared across threads via StaticPool."""
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


@pytest.fixture
def seeded_user(db_session):
    """Insert one admin user with a known password."""
    from app.api.v1.auth import _hash_password

    user = User(
        username="regression_admin",
        password_hash=_hash_password("s3cret-passw0rd!"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _override_db(db_session):
    def _dep():
        try:
            yield db_session
        finally:
            pass

    return _dep


def test_login_response_includes_user_id(db_session, seeded_user):
    """The login response's ``user`` object must include ``id``.

    Regression for 2026-07-01: missing ``id`` caused Pydantic to raise
    ValidationError -> HTTP 500 -> frontend shows "用户名密码不正确".
    """
    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    # Disable Redis-backed blacklist writes (no Redis in tests).
    with patch("app.api.v1.auth.blacklist_token", return_value=None), \
         patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)), \
         TestClient(app) as client:
        try:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": seeded_user.username, "password": "s3cret-passw0rd!"},
            )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "user" in body
    user_payload = body["user"]
    assert "id" in user_payload, f"missing 'id' in login response: {user_payload}"
    assert user_payload["id"] == seeded_user.id
    assert user_payload["username"] == "regression_admin"
    assert user_payload["role"] == "admin"
    assert body.get("access_token")
    assert body.get("refresh_token")


def test_login_invalid_credentials_returns_401(db_session, seeded_user):
    """Wrong password must surface as 401 (not 500)."""
    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    with patch("app.api.v1.auth.blacklist_token", return_value=None), \
         patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)), \
         TestClient(app) as client:
        try:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": seeded_user.username, "password": "wrong"},
            )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 401


def test_login_inactive_user_returns_401(db_session, seeded_user):
    """Inactive accounts must surface as 401 (not 500)."""
    seeded_user.is_active = False
    db_session.commit()

    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    with patch("app.api.v1.auth.blacklist_token", return_value=None), \
         patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)), \
         TestClient(app) as client:
        try:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": seeded_user.username, "password": "s3cret-passw0rd!"},
            )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 401


def test_refresh_rotates_and_returns_new_refresh_token(db_session, seeded_user):
    """/auth/refresh must return the rotated refresh token and revoke the old one.

    Regression for the refresh-rotation break: the endpoint revoked the old
    refresh token but never returned the new one, so clients kept replaying a
    revoked token and were force-logged-out once the access token expired.
    """
    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    with patch("app.api.v1.auth.blacklist_token", return_value=None), \
         patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)), \
         TestClient(app) as client:
        try:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": seeded_user.username, "password": "s3cret-passw0rd!"},
            )
            assert login.status_code == 200, login.text
            old_refresh = login.json()["refresh_token"]

            resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
            assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
            body = resp.json()
            assert body.get("access_token")
            assert body.get("refresh_token"), f"missing rotated refresh_token: {body}"
            assert body["refresh_token"] != old_refresh

            # The rotated-out token must be rejected on replay.
            replay = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
            assert replay.status_code == 401

            # The new token must be usable for the next rotation.
            second = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
            )
            assert second.status_code == 200, second.text
        finally:
            app.dependency_overrides.clear()