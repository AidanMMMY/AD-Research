"""Tests for the password policy, admin create/reset and self change-password.

Covers the 2026-10-24 user-management enhancement:
  * shared policy: >=12 chars, at least one letter and one digit, <=64 chars
  * admin create/reset generate a random password when none is given and
    flag ``must_change_password=True``; the plaintext is returned once in
    the response and never persisted
  * POST /auth/change-password verifies the old password, clears the flag,
    revokes old refresh tokens and returns a usable replacement session
  * login / /auth/me expose the ``must_change_password`` flag

Uses the in-memory SQLite pattern from test_auth_login.py (dependency
overrides + patched Redis helpers) — no real Postgres/Redis needed.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as deps_module
from app.api.v1 import auth as auth_module
from app.api.v1 import deployments as deployments_module
from app.core.database import Base
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import UserResponse
from app.services.password_policy import (
    MAX_LENGTH,
    generate_random_password,
    validate_password,
)

ADMIN_PASSWORD = "Adm1n-passw0rd!"
USER_PASSWORD = "Us3r-passw0rd!"


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
def seeded_users(db_session):
    """One admin + one regular user with known passwords."""
    admin = User(
        username="pw_admin",
        password_hash=auth_module._hash_password(ADMIN_PASSWORD),
        role="admin",
        is_active=True,
    )
    member = User(
        username="pw_member",
        password_hash=auth_module._hash_password(USER_PASSWORD),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, member])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(member)
    return {"admin": admin, "member": member}


def _override_db(db_session):
    def _dep():
        try:
            yield db_session
        finally:
            pass

    return _dep


def _admin_override(user: User):
    return lambda: UserResponse(id=user.id, username=user.username, role=user.role)


class _AdminClient:
    """Context manager: TestClient wired for admin API calls."""

    def __init__(self, db_session, admin: User):
        self._db = db_session
        self._admin = admin
        self._cm = None

    def __enter__(self) -> TestClient:
        app.dependency_overrides[deps_module.get_db] = _override_db(self._db)
        app.dependency_overrides[deps_module.require_admin] = _admin_override(self._admin)
        self._cm = TestClient(app)
        return self._cm.__enter__()

    def __exit__(self, *exc):
        try:
            return self._cm.__exit__(*exc)
        finally:
            app.dependency_overrides.clear()


# ── Policy unit tests ──


def test_policy_rejects_too_short():
    assert validate_password("a1" * 5) is not None  # 10 chars


def test_policy_rejects_letters_only():
    assert validate_password("abcdefghijkl") is not None


def test_policy_rejects_digits_only():
    assert validate_password("123456789012") is not None


def test_policy_rejects_over_long():
    assert validate_password("a1" * 40) is not None  # 80 chars > MAX_LENGTH


def test_policy_rejects_multibyte_password_over_bcrypt_limit():
    # 26 chars but 74 UTF-8 bytes: character length alone is not enough.
    assert validate_password("a1" + "界" * 24) is not None


def test_policy_requires_ascii_digit():
    assert validate_password("abcdefghijk²") is not None


def test_policy_surrogate_returns_validation_error():
    # Lone surrogates cannot be UTF-8 encoded and must not become a 500.
    error = validate_password("a1" + "x" * 9 + "\ud800")
    assert error is not None
    assert "密码" in error


def test_policy_accepts_valid():
    assert validate_password("abcd1234efgh") is None
    assert validate_password("a1" * 6) is None  # exactly 12
    assert validate_password("A9" * (MAX_LENGTH // 2)) is None  # exactly 64


def test_generate_random_password_satisfies_policy():
    for _ in range(50):
        pw = generate_random_password()
        assert len(pw) == 16
        assert validate_password(pw) is None
        # No characters that break copy-paste into shells/JSON.
        assert not any(ch in pw for ch in ("'", '"', "\\", " "))


# ── Admin create / reset ──


def test_create_user_auto_generates_password(db_session, seeded_users):
    """Omitting password ⇒ server generates one, returns it once, flags
    must_change_password, and never stores the plaintext."""
    with _AdminClient(db_session, seeded_users["admin"]) as client:
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "newbie", "role": "user"},
        )
        list_resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    initial = body["initial_password"]
    assert initial and validate_password(initial) is None
    assert body["must_change_password"] is True

    # The plaintext is a create-only field, never exposed by user lists.
    assert list_resp.status_code == 200, list_resp.text
    assert all("initial_password" not in item for item in list_resp.json())

    user = db_session.query(User).filter(User.username == "newbie").one()
    assert user.must_change_password is True
    assert initial not in user.password_hash
    assert auth_module._verify_password(initial, user.password_hash)


def test_create_user_explicit_weak_password_422(db_session, seeded_users):
    with _AdminClient(db_session, seeded_users["admin"]) as client:
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "weakpw", "password": "short1"},
        )
        too_long = client.post(
            "/api/v1/admin/users",
            json={"username": "longpw", "password": "a1" * 40},
        )
    assert resp.status_code == 422
    assert "密码" in resp.json()["detail"]
    assert too_long.status_code == 422
    assert "64" in too_long.json()["detail"]


def test_create_user_explicit_password_also_forces_change(db_session, seeded_users):
    with _AdminClient(db_session, seeded_users["admin"]) as client:
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "explicit1", "password": "Good-pass123"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["initial_password"] == "Good-pass123"
    user = db_session.query(User).filter(User.username == "explicit1").one()
    assert user.must_change_password is True


def test_reset_password_auto_generates_and_flags(db_session, seeded_users):
    member = seeded_users["member"]
    # Give the member an active refresh token to prove revocation.
    db_session.add(
        RefreshToken(
            user_id=member.id,
            token_hash="deadbeef" * 8,
            expires_at=auth_module.datetime.now(auth_module.UTC) + auth_module.timedelta(days=1),
        )
    )
    db_session.commit()

    with _AdminClient(db_session, seeded_users["admin"]) as client:
        resp = client.post(f"/api/v1/admin/users/{member.id}/reset-password", json={})
    assert resp.status_code == 200, resp.text
    initial = resp.json()["initial_password"]
    assert initial and validate_password(initial) is None

    db_session.refresh(member)
    assert member.must_change_password is True
    assert auth_module._verify_password(initial, member.password_hash)
    remaining = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == member.id, RefreshToken.revoked.is_(False))
        .count()
    )
    assert remaining == 0


def test_reset_password_explicit_weak_422(db_session, seeded_users):
    member = seeded_users["member"]
    with _AdminClient(db_session, seeded_users["admin"]) as client:
        resp = client.post(
            f"/api/v1/admin/users/{member.id}/reset-password",
            json={"new_password": "onlyletters"},
        )
    assert resp.status_code == 422


# ── Login / me flag ──


def test_login_response_carries_must_change_password(db_session, seeded_users):
    member = seeded_users["member"]
    member.must_change_password = True
    db_session.commit()

    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    with (
        patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)),
        TestClient(app) as client,
    ):
        try:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": member.username, "password": USER_PASSWORD},
            )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["must_change_password"] is True


def test_me_response_carries_must_change_password(db_session, seeded_users):
    member = seeded_users["member"]
    member.must_change_password = True
    db_session.commit()
    token = auth_module.create_access_token(member.username, member.role, "me-test-jti")

    # Exercise the real JWT dependency; only its DB/Redis infrastructure
    # is replaced with the in-memory fixtures.
    with (
        patch("app.api.deps.SessionLocal", return_value=db_session),
        patch("app.api.deps.is_token_blacklisted", return_value=False),
        TestClient(app) as client,
    ):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["must_change_password"] is True


def test_password_change_pending_auth_boundaries_and_new_access(db_session, seeded_users):
    """Pending users may only use the password-recovery endpoints. After
    changing the password, the new access token passes the real auth
    dependency on a normal protected endpoint."""
    member = seeded_users["member"]
    member.must_change_password = True
    db_session.commit()
    old_access = auth_module.create_access_token(member.username, member.role, "pending-jti")
    old_headers = {"Authorization": f"Bearer {old_access}"}

    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    try:
        with (
            patch(
                "app.api.deps.SessionLocal",
                sessionmaker(bind=db_session.get_bind()),
            ),
            patch("app.api.deps.is_token_blacklisted", return_value=False),
            patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)),
            patch("app.api.v1.auth.clear_login_attempts"),
            TestClient(app) as client,
        ):
            blocked = client.get("/api/v1/auth/devices", headers=old_headers)
            assert blocked.status_code == 403, blocked.text

            me = client.get("/api/v1/auth/me", headers=old_headers)
            assert me.status_code == 200, me.text
            assert me.json()["must_change_password"] is True

            changed = client.post(
                "/api/v1/auth/change-password",
                headers=old_headers,
                json={"old_password": USER_PASSWORD, "new_password": "Fr3sh-pass1234"},
            )
            assert changed.status_code == 200, changed.text
            new_access = changed.json()["access_token"]

            # No get_current_user override: this exercises JWT decoding,
            # the DB lookup and the post-change flag through the real path.
            allowed = client.get(
                "/api/v1/auth/devices",
                headers={"Authorization": f"Bearer {new_access}"},
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json() == []
    finally:
        app.dependency_overrides.clear()


def test_password_change_pending_admin_is_blocked(db_session, seeded_users):
    admin = seeded_users["admin"]
    admin.must_change_password = True
    db_session.commit()
    token = auth_module.create_access_token(admin.username, admin.role, "pending-admin-jti")

    app.dependency_overrides[deps_module.get_db] = _override_db(db_session)
    try:
        with (
            patch(
                "app.api.deps.SessionLocal",
                sessionmaker(bind=db_session.get_bind()),
            ),
            patch("app.api.deps.is_token_blacklisted", return_value=False),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.clear()


async def test_deployment_sse_rejects_password_change_pending_admin(db_session, seeded_users):
    """The SSE query-token auth helper must apply the same pending-password
    boundary as the standard admin dependency."""
    admin = seeded_users["admin"]
    admin.must_change_password = True
    db_session.commit()
    token = auth_module.create_access_token(admin.username, admin.role, "pending-sse-jti")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/deployments/logs/stream",
            "headers": [],
            "query_string": f"token={token}".encode("ascii"),
        }
    )

    with patch("app.core.database.SessionLocal", return_value=db_session):
        with pytest.raises(HTTPException) as exc_info:
            await deployments_module._require_admin_for_sse(request)

    assert exc_info.value.status_code == 403


# ── change-password flow ──


def _change_password_client(db_session, user: User):
    """Wire overrides so /auth/change-password acts as ``user``."""
    app.dependency_overrides[auth_module._get_db] = _override_db(db_session)
    app.dependency_overrides[deps_module.get_current_user_allow_password_change] = _admin_override(
        user
    )
    return TestClient(app)


def test_change_password_full_flow(db_session, seeded_users):
    member = seeded_users["member"]
    member.must_change_password = True
    db_session.commit()

    with _change_password_client(db_session, member) as client:
        try:
            resp = client.post(
                "/api/v1/auth/change-password",
                json={"old_password": USER_PASSWORD, "new_password": "N3w-password99"},
            )
        finally:
            app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    assert resp.json()["refresh_token"]

    db_session.refresh(member)
    assert member.must_change_password is False
    assert auth_module._verify_password("N3w-password99", member.password_hash)
    assert not auth_module._verify_password(USER_PASSWORD, member.password_hash)


def test_change_password_rate_limit_returns_429_and_retry_after(db_session, seeded_users):
    member = seeded_users["member"]
    with _change_password_client(db_session, member) as client:
        try:
            with patch(
                "app.api.v1.auth.check_login_rate_limit", return_value=(False, 37)
            ) as limited:
                resp = client.post(
                    "/api/v1/auth/change-password",
                    headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
                    json={"old_password": USER_PASSWORD, "new_password": "N3w-password99"},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 429, resp.text
    assert resp.headers["Retry-After"] == "37"
    limited.assert_called_once_with("203.0.113.9", member.username)


def test_change_password_success_clears_rate_limit_counter(db_session, seeded_users):
    member = seeded_users["member"]
    with _change_password_client(db_session, member) as client:
        try:
            with (
                patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)) as limited,
                patch("app.api.v1.auth.clear_login_attempts") as cleared,
            ):
                resp = client.post(
                    "/api/v1/auth/change-password",
                    json={"old_password": USER_PASSWORD, "new_password": "N3w-password99"},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    cleared.assert_called_once_with(member.username)
    assert limited.call_args.args[1] == member.username


def test_change_password_wrong_old_password_400(db_session, seeded_users):
    member = seeded_users["member"]
    with _change_password_client(db_session, member) as client:
        try:
            resp = client.post(
                "/api/v1/auth/change-password",
                json={"old_password": "wr0ng-password", "new_password": "N3w-password99"},
            )
        finally:
            app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert "旧密码" in resp.json()["detail"]


def test_change_password_rejects_same_old_and_new_password(db_session, seeded_users):
    member = seeded_users["member"]
    old_hash = member.password_hash
    with _change_password_client(db_session, member) as client:
        try:
            with patch("app.api.v1.auth.check_login_rate_limit", return_value=(True, 1)):
                resp = client.post(
                    "/api/v1/auth/change-password",
                    json={"old_password": USER_PASSWORD, "new_password": USER_PASSWORD},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 422, resp.text
    assert "不能与旧密码相同" in resp.json()["detail"]
    db_session.refresh(member)
    assert member.password_hash == old_hash


def test_change_password_weak_new_password_422(db_session, seeded_users):
    member = seeded_users["member"]
    with _change_password_client(db_session, member) as client:
        try:
            resp = client.post(
                "/api/v1/auth/change-password",
                json={"old_password": USER_PASSWORD, "new_password": "short1"},
            )
        finally:
            app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_change_password_rotates_current_session_and_revokes_old_refresh(db_session, seeded_users):
    """Old refresh tokens die, but the returned replacement keeps the
    current browser session usable after its access token expires."""
    member = seeded_users["member"]
    old_refresh = "old-session-refresh"
    db_session.add(
        RefreshToken(
            user_id=member.id,
            token_hash=auth_module._hash_token(old_refresh),
            expires_at=auth_module.datetime.now(auth_module.UTC) + auth_module.timedelta(days=1),
        )
    )
    db_session.commit()

    with _change_password_client(db_session, member) as client:
        try:
            resp = client.post(
                "/api/v1/auth/change-password",
                json={"old_password": USER_PASSWORD, "new_password": "An0ther-pass77"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["access_token"]
            new_refresh = body["refresh_token"]
            assert new_refresh != old_refresh

            # Exactly one active token remains: the newly issued session.
            active = (
                db_session.query(RefreshToken)
                .filter(RefreshToken.user_id == member.id, RefreshToken.revoked.is_(False))
                .all()
            )
            assert len(active) == 1
            assert active[0].token_hash == auth_module._hash_token(new_refresh)

            old_session = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
            assert old_session.status_code == 401

            new_session = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
            assert new_session.status_code == 200, new_session.text
            assert new_session.json()["access_token"]
            assert new_session.json()["refresh_token"] != new_refresh
        finally:
            app.dependency_overrides.clear()
