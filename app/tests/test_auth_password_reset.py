"""忘记密码 → 邮箱验证码/重置链接 → 自主重置全链路测试（红测先行，2026-10-25）。

覆盖：forgot-password 防枚举 202 / 冷却 429 / 每邮箱 3/h / 开关 404、
reset-password 成功双令牌 + 全量吊销旧 refresh + 未验证用户解锁、码错计数
与第 5 次作废、新旧密码相同拒绝且码不烧、弱密码不烧码、token 模式
（过期 410 / purpose 校验 400）、reset-link 302 契约、注册/重置验证码按
purpose 隔离。

Redis 依赖说明与 test_auth_registration.py 相同：主链路 patch 掉限流守卫，
冷却/限流专项用真实 Redis（db 15，逐测试 flush），不可用时 skip。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import auth as auth_module
from app.config import auth_settings
from app.core.database import Base
from app.main import app
from app.models.email_verification import EmailVerification
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import registration_service

API = "/api/v1/auth"
OLD_PASSWORD = "hunter2secure99"
NEW_PASSWORD = "fresh-start-2026x"


# ── Fixtures（与 test_auth_registration.py 同款骨架）──


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
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def reset_enabled(monkeypatch):
    monkeypatch.setattr(auth_settings, "PASSWORD_RESET_ENABLED", True)


@pytest.fixture
def sent_emails(monkeypatch):
    """Record outgoing transactional emails instead of hitting SMTP."""
    outbox: list[dict] = []

    def _fake_send(to, subject, html_body, text_body):
        outbox.append({"to": to, "subject": subject, "html": html_body, "text": text_body})
        return True

    monkeypatch.setattr(registration_service, "send_email", _fake_send)
    return outbox


@pytest.fixture
def fixed_code(monkeypatch):
    """Deterministic verification code so tests can drive the OTP flow."""
    holder = {"code": "493701"}
    monkeypatch.setattr(registration_service, "_generate_code", lambda: holder["code"])
    return holder


@pytest.fixture
def client(db_session, monkeypatch, reset_enabled, sent_emails):
    """TestClient: DB overridden, all rate-limit guards patched open."""
    monkeypatch.setattr(auth_module, "check_login_rate_limit", lambda ip, u: (True, 1))
    monkeypatch.setattr(auth_module, "check_forgot_password_rate_limit", lambda ip, e: (True, 1))
    monkeypatch.setattr(auth_module, "check_reset_verify_rate_limit", lambda e: (True, 1))
    monkeypatch.setattr(auth_module, "arm_password_reset_cooldown", lambda e: (True, 0))
    monkeypatch.setattr(auth_module, "blacklist_token", lambda jti, ttl: None)

    def _dep():
        yield db_session

    app.dependency_overrides[auth_module._get_db] = _dep
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(auth_module._get_db, None)


@pytest.fixture
def require_redis(_isolated_test_redis):
    """Skip tests that need the real Redis-backed limiter/cooldown."""
    if _isolated_test_redis is None:
        pytest.skip("Redis unavailable — rate-limit/cooldown tests need it")


def _create_user(
    db_session,
    *,
    email="u1@example.com",
    username="aidan1",
    password=OLD_PASSWORD,
    verified=True,
):
    user = User(
        username=username,
        password_hash=auth_module._hash_password(password),
        role="user",
        is_active=True,
        must_change_password=False,
        email=email,
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _forgot(client, email="u1@example.com"):
    return client.post(f"{API}/forgot-password", json={"email": email})


def _latest_verification(db_session, user_id, purpose="password_reset"):
    return (
        db_session.query(EmailVerification)
        .filter(EmailVerification.user_id == user_id, EmailVerification.purpose == purpose)
        .order_by(EmailVerification.id.desc())
        .first()
    )


def _expired_reset_token(user_id: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "purpose": "password_reset_link",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        auth_settings.SECRET_KEY,
        algorithm="HS256",
    )


# ── forgot-password ──


def test_forgot_password_sends_reset_email(client, db_session, sent_emails, fixed_code):
    user = _create_user(db_session)
    resp = _forgot(client)
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"detail": "reset email sent"}

    row = _latest_verification(db_session, user.id)
    assert row is not None
    assert row.attempts == 0
    assert row.consumed_at is None
    assert row.code_hash == registration_service._hash_code(fixed_code["code"])

    assert len(sent_emails) == 1
    mail = sent_emails[0]
    assert mail["to"] == "u1@example.com"
    assert fixed_code["code"] in mail["html"]
    assert mail["html"].count("/api/v1/auth/reset-link?token=") == 1
    assert fixed_code["code"] in mail["text"]


def test_forgot_password_unknown_email_202_anti_enumeration(client, sent_emails):
    resp = _forgot(client, email="ghost@example.com")
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"detail": "reset email sent"}
    # 未注册邮箱不发送任何邮件，但响应与已注册邮箱完全一致
    assert sent_emails == []


def test_forgot_password_invalid_email_422(client, sent_emails):
    resp = _forgot(client, email="not-an-email")
    assert resp.status_code == 422
    assert sent_emails == []


def test_forgot_password_disabled_404(client, monkeypatch, sent_emails):
    monkeypatch.setattr(auth_settings, "PASSWORD_RESET_ENABLED", False)
    resp = _forgot(client)
    assert resp.status_code == 404
    assert sent_emails == []


def test_forgot_password_cooldown_429(client, db_session, require_redis, fixed_code):
    """60s 冷却：同邮箱立刻再请求 → 429 cooldown。"""
    _create_user(db_session)
    real_arm = __import__(
        "app.core.rate_limit", fromlist=["arm_password_reset_cooldown"]
    ).arm_password_reset_cooldown
    with patch.object(auth_module, "arm_password_reset_cooldown", real_arm):
        first = _forgot(client)
        assert first.status_code == 202
        second = _forgot(client)
    assert second.status_code == 429
    assert second.json()["detail"] == "cooldown"
    assert "Retry-After" in second.headers


def test_forgot_password_email_rate_limit(client, db_session, require_redis, fixed_code):
    """每邮箱 3/h：第 4 次 → 429（冷却已 patch 放行）。"""
    _create_user(db_session)
    real_check = __import__(
        "app.core.rate_limit", fromlist=["check_forgot_password_rate_limit"]
    ).check_forgot_password_rate_limit
    with patch.object(auth_module, "check_forgot_password_rate_limit", real_check):
        for _ in range(3):
            resp = _forgot(client)
            assert resp.status_code == 202, resp.text
        fourth = _forgot(client)
    assert fourth.status_code == 429
    assert "Retry-After" in fourth.headers


# ── reset-password（code 模式）──


def test_reset_password_success_returns_tokens_and_revokes_old_refresh(
    client, db_session, fixed_code
):
    user = _create_user(db_session)
    # 先制造一个旧会话（模拟另一台设备的 refresh token）
    old_login = client.post(f"{API}/login", json={"username": "aidan1", "password": OLD_PASSWORD})
    assert old_login.status_code == 200
    old_refresh = old_login.json()["refresh_token"]

    _forgot(client)
    resp = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "aidan1"
    assert body["user"]["must_change_password"] is False

    payload = jwt.decode(body["access_token"], auth_settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == "aidan1"

    # 旧 refresh 全部吊销（另一台设备被踢）
    old_still_valid = (
        db_session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .count()
    )
    assert old_still_valid == 1  # 只剩刚签发的新会话
    rotated = client.post(f"{API}/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 401

    # 新会话可用 + 旧密码失效、新密码可登录
    fresh = client.post(f"{API}/refresh", json={"refresh_token": body["refresh_token"]})
    assert fresh.status_code == 200
    relogin_old = client.post(f"{API}/login", json={"username": "aidan1", "password": OLD_PASSWORD})
    assert relogin_old.status_code == 401
    relogin_new = client.post(f"{API}/login", json={"username": "aidan1", "password": NEW_PASSWORD})
    assert relogin_new.status_code == 200


def test_reset_password_unlocks_unverified_user(client, db_session, fixed_code):
    """未验证用户可以走重置：成功即顺带置 email_verified_at（合理解锁语义）。"""
    _create_user(db_session, verified=False)
    _forgot(client)
    resp = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 200, resp.text

    user = db_session.query(User).filter(User.username == "aidan1").first()
    db_session.refresh(user)
    assert user.email_verified_at is not None
    # 登录门随之放行（用新密码）
    login = client.post(f"{API}/login", json={"username": "aidan1", "password": NEW_PASSWORD})
    assert login.status_code == 200


def test_reset_password_wrong_code_counts_and_voids_after_fifth(client, db_session, fixed_code):
    _create_user(db_session)
    _forgot(client)
    for i in range(5):
        resp = client.post(
            f"{API}/reset-password",
            json={"email": "u1@example.com", "code": "000000", "new_password": NEW_PASSWORD},
        )
        assert resp.status_code == 400, f"attempt {i + 1}: {resp.text}"
        body = resp.json()
        assert body["detail"] == "invalid code"
        assert body["remaining_attempts"] == 4 - i

    sixth = client.post(
        f"{API}/reset-password",
        json={
            "email": "u1@example.com",
            "code": fixed_code["code"],
            "new_password": NEW_PASSWORD,
        },
    )
    assert sixth.status_code == 410
    assert sixth.json() == {"detail": "code expired"}


def test_reset_password_expired_code_410(client, db_session, fixed_code):
    _create_user(db_session)
    _forgot(client)
    user = db_session.query(User).filter(User.username == "aidan1").first()
    row = _latest_verification(db_session, user.id)
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    resp = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 410
    assert resp.json() == {"detail": "code expired"}


def test_reset_password_unknown_email_400(client):
    resp = client.post(
        f"{API}/reset-password",
        json={"email": "ghost@example.com", "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "invalid code"
    assert body["remaining_attempts"] == 0


def test_reset_password_same_as_old_422_and_code_survives(client, db_session, fixed_code):
    """新旧密码相同拒绝 422；验证码不被烧掉，换密码后同码可重试。"""
    _create_user(db_session)
    _forgot(client)
    rejected = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": OLD_PASSWORD},
    )
    assert rejected.status_code == 422

    retry = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": NEW_PASSWORD},
    )
    assert retry.status_code == 200, retry.text


def test_reset_password_weak_password_422_does_not_burn_code(client, db_session, fixed_code):
    """策略不过 422；码的 attempts 不增加，同码可重试。"""
    _create_user(db_session)
    _forgot(client)
    weak = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": "short1"},
    )
    assert weak.status_code == 422

    user = db_session.query(User).filter(User.username == "aidan1").first()
    row = _latest_verification(db_session, user.id)
    db_session.refresh(row)
    assert row.attempts == 0
    assert row.consumed_at is None

    retry = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": fixed_code["code"], "new_password": NEW_PASSWORD},
    )
    assert retry.status_code == 200, retry.text


def test_reset_password_disabled_404(client, monkeypatch, fixed_code):
    monkeypatch.setattr(auth_settings, "PASSWORD_RESET_ENABLED", False)
    resp = client.post(
        f"{API}/reset-password",
        json={"email": "u1@example.com", "code": "123456", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 404


# ── reset-password（token 模式，邮件主按钮链接）──


def test_reset_password_via_token(client, db_session):
    user = _create_user(db_session)
    token = registration_service.create_magic_link_token(
        user.id, registration_service.PASSWORD_RESET_LINK_PURPOSE
    )
    resp = client.post(f"{API}/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["refresh_token"]

    login = client.post(f"{API}/login", json={"username": "aidan1", "password": NEW_PASSWORD})
    assert login.status_code == 200


def test_reset_password_expired_token_410(client, db_session):
    user = _create_user(db_session)
    resp = client.post(
        f"{API}/reset-password",
        json={"token": _expired_reset_token(user.id), "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 410


def test_reset_password_wrong_purpose_token_400(client, db_session):
    user = _create_user(db_session)
    register_token = registration_service.create_magic_link_token(user.id)
    resp = client.post(
        f"{API}/reset-password",
        json={"token": register_token, "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400


# ── GET /reset-link（邮件按钮点击后的 302 萳萃）──


def test_reset_link_redirects_with_token_and_email(client, db_session):
    user = _create_user(db_session)
    token = registration_service.create_magic_link_token(
        user.id, registration_service.PASSWORD_RESET_LINK_PURPOSE
    )
    resp = client.get(f"{API}/reset-link", params={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("http://localhost:5173/reset-password?")
    assert "token=" in location
    assert "email=u1%40example.com" in location


def test_reset_link_expired_reason(client, db_session):
    user = _create_user(db_session)
    resp = client.get(
        f"{API}/reset-link", params={"token": _expired_reset_token(user.id)}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert "error=expired" in resp.headers["location"]


def test_reset_link_wrong_purpose_invalid(client, db_session):
    user = _create_user(db_session)
    register_token = registration_service.create_magic_link_token(user.id)
    resp = client.get(f"{API}/reset-link", params={"token": register_token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "error=invalid" in resp.headers["location"]


# ── purpose 隔离 ──


def test_forgot_password_does_not_void_pending_register_code(client, db_session, fixed_code):
    """重置码的签发/消费不影响待用的注册码（按 purpose 隔离）。"""
    user = _create_user(db_session, verified=False)
    # 手动补一条 pending 注册码（等价于注册后未验证的现场）
    db_session.add(
        EmailVerification(
            user_id=user.id,
            code_hash=registration_service._hash_code("111222"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            attempts=0,
            purpose="register",
        )
    )
    db_session.commit()

    _forgot(client)

    register_row = _latest_verification(db_session, user.id, purpose="register")
    db_session.refresh(register_row)
    assert register_row.consumed_at is None  # 注册码未被重发作废

    # 注册码仍可完成验证（registration 链路按 purpose=register 消费）
    verified = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": "111222"},
    )
    assert verified.status_code == 200, verified.text


def test_registration_rows_default_to_register_purpose(client, db_session, monkeypatch, fixed_code):
    """存量语义不变：注册链路落库的行 purpose 默认 register。"""
    monkeypatch.setattr(auth_settings, "REGISTRATION_ENABLED", True)
    resp = client.post(
        f"{API}/register",
        json={"email": "u2@example.com", "username": "aidan2", "password": OLD_PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    user = db_session.query(User).filter(User.username == "aidan2").first()
    row = _latest_verification(db_session, user.id, purpose="register")
    assert row is not None
