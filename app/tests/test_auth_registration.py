"""邮箱自助注册后端链路测试（红测先行，2026-10-25 设计 §3）。

覆盖：注册建号未验证态 / 登录门 403 文案区分 / 验证成功双令牌 / 码错计数与
第 5 次作废 / 码过期 410 / 重发冷却 429 / 防枚举（已注册邮箱回 201）/
用户名占用 400 / check-username / 限流 / 密码策略 / 魔法链接过期与
purpose 校验 / 开关关闭行为 / 事务邮件封装。

Redis 依赖说明：主链路测试把限流守卫 patch 掉（与 test_auth_login 同款做法），
只有冷却/限流专项测试用真实 Redis（conftest 指向 db 15，且逐测试 flushdb），
Redis 不可用时这些用例 skip。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
from app.models.user import User
from app.services import registration_service

API = "/api/v1/auth"
VALID_PASSWORD = "hunter2secure99"


# ── Fixtures ──


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
def reg_enabled(monkeypatch):
    monkeypatch.setattr(auth_settings, "REGISTRATION_ENABLED", True)


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
def client(db_session, monkeypatch, reg_enabled, sent_emails):
    """TestClient: DB overridden, all rate-limit guards patched open."""
    monkeypatch.setattr(auth_module, "check_login_rate_limit", lambda ip, u: (True, 1))
    monkeypatch.setattr(auth_module, "check_register_rate_limit", lambda ip, e: (True, 1))
    monkeypatch.setattr(auth_module, "check_verify_rate_limit", lambda e: (True, 1))
    monkeypatch.setattr(auth_module, "arm_resend_cooldown", lambda e: (True, 0))
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


def _register(client, email="u1@example.com", username="aidan1", password=VALID_PASSWORD):
    return client.post(
        f"{API}/register",
        json={"email": email, "username": username, "password": password},
    )


def _latest_verification(db_session, user_id):
    return (
        db_session.query(EmailVerification)
        .filter(EmailVerification.user_id == user_id)
        .order_by(EmailVerification.id.desc())
        .first()
    )


# ── 注册主链路 ──


def test_register_creates_unverified_user_and_sends_email(
    client, db_session, sent_emails, fixed_code
):
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"detail": "verification email sent"}

    user = db_session.query(User).filter(User.username == "aidan1").first()
    assert user is not None
    assert user.email == "u1@example.com"
    assert user.email_verified_at is None
    assert user.role == "user"
    assert user.must_change_password is False

    row = _latest_verification(db_session, user.id)
    assert row is not None
    assert row.consumed_at is None
    assert row.attempts == 0
    # 验证码只能以哈希形态落库，明文绝不入库
    assert fixed_code["code"] not in row.code_hash
    assert row.code_hash == registration_service._hash_code(fixed_code["code"])

    assert len(sent_emails) == 1
    mail = sent_emails[0]
    assert mail["to"] == "u1@example.com"
    assert fixed_code["code"] in mail["html"]
    assert mail["html"].count("/api/v1/auth/verify-link?token=") == 1
    assert fixed_code["code"] in mail["text"]


def test_register_normalizes_email_case(client, db_session, fixed_code):
    resp = _register(client, email="Mixed.Case@Example.COM")
    assert resp.status_code == 201, resp.text
    user = db_session.query(User).filter(User.username == "aidan1").first()
    assert user.email == "mixed.case@example.com"


# ── 登录门 ──


def test_login_blocked_for_unverified_email(client, db_session, fixed_code):
    _register(client)
    resp = client.post(f"{API}/login", json={"username": "aidan1", "password": VALID_PASSWORD})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "email not verified"
    # 必须与 must_change_password 的 403 文案可区分（前端靠 detail 路由）
    assert resp.json()["detail"] != "请先修改密码后再访问"


def test_login_gate_inactive_when_registration_disabled(
    client, db_session, monkeypatch, fixed_code
):
    _register(client)
    monkeypatch.setattr(auth_settings, "REGISTRATION_ENABLED", False)
    resp = client.post(f"{API}/login", json={"username": "aidan1", "password": VALID_PASSWORD})
    assert resp.status_code == 200, resp.text


# ── 验证码核对 ──


def test_verify_success_returns_token_pair(client, db_session, fixed_code):
    _register(client)
    resp = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": fixed_code["code"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "aidan1"
    assert body["user"]["role"] == "user"
    assert body["user"]["must_change_password"] is False
    assert "id" in body["user"]

    payload = jwt.decode(body["access_token"], auth_settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == "aidan1"

    user = db_session.query(User).filter(User.username == "aidan1").first()
    db_session.refresh(user)
    assert user.email_verified_at is not None


def test_verify_code_single_use(client, fixed_code):
    _register(client)
    first = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": fixed_code["code"]},
    )
    assert first.status_code == 200
    replay = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": fixed_code["code"]},
    )
    assert replay.status_code == 400
    assert replay.json()["detail"] == "invalid code"


def test_verify_wrong_code_counts_and_voids_after_fifth(client, db_session, fixed_code):
    _register(client)
    for i in range(5):
        resp = client.post(
            f"{API}/verify-registration",
            json={"email": "u1@example.com", "code": "000000"},
        )
        assert resp.status_code == 400, f"attempt {i + 1}: {resp.text}"
        body = resp.json()
        assert body["detail"] == "invalid code"
        assert body["remaining_attempts"] == 4 - i

    # 第 5 次错误已作废验证码；第 6 次任何输入都回 410
    sixth = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": fixed_code["code"]},
    )
    assert sixth.status_code == 410
    assert sixth.json() == {"detail": "code expired"}


def test_verify_expired_code_returns_410(client, db_session, fixed_code):
    _register(client)
    user = db_session.query(User).filter(User.username == "aidan1").first()
    row = _latest_verification(db_session, user.id)
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    resp = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": fixed_code["code"]},
    )
    assert resp.status_code == 410
    assert resp.json() == {"detail": "code expired"}


def test_verify_unknown_email_invalid_code(client):
    resp = client.post(
        f"{API}/verify-registration",
        json={"email": "ghost@example.com", "code": "123456"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"] == "invalid code"
    assert body["remaining_attempts"] == 0


# ── 重发 ──


def test_resend_reissues_code_and_voids_old(client, db_session, fixed_code):
    _register(client)
    fixed_code["code"] = "777888"
    resp = client.post(f"{API}/resend-verification", json={"email": "u1@example.com"})
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"detail": "resent"}

    # 旧码失效（对不上新码 → invalid code），新码可用
    old = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": "493701"},
    )
    assert old.status_code == 400
    assert old.json()["detail"] == "invalid code"

    fresh = client.post(
        f"{API}/verify-registration",
        json={"email": "u1@example.com", "code": "777888"},
    )
    assert fresh.status_code == 200, fresh.text


def test_resend_cooldown_429(client, require_redis, fixed_code):
    """注册即武装 60s 冷却；冷却期内重发 → 429 cooldown。"""
    real_arm = __import__(
        "app.core.rate_limit", fromlist=["arm_resend_cooldown"]
    ).arm_resend_cooldown
    with patch.object(auth_module, "arm_resend_cooldown", real_arm):
        _register(client)
        resp = client.post(f"{API}/resend-verification", json={"email": "u1@example.com"})
    assert resp.status_code == 429
    assert resp.json() == {"detail": "cooldown"}


def test_resend_unknown_email_202_anti_enumeration(client, fixed_code):
    resp = client.post(f"{API}/resend-verification", json={"email": "ghost@example.com"})
    assert resp.status_code == 202
    assert resp.json() == {"detail": "resent"}


# ── 防枚举与占用 ──


def test_register_existing_email_returns_201_and_sends_notice(
    client, db_session, sent_emails, fixed_code
):
    first = _register(client, email="dup@example.com", username="first1")
    assert first.status_code == 201
    # 同邮箱换用户名再注册 → 照样 201（防枚举），发「已有账号」提醒邮件
    second = _register(client, email="dup@example.com", username="second2")
    assert second.status_code == 201, second.text
    assert second.json() == {"detail": "verification email sent"}

    assert db_session.query(User).count() == 1
    assert len(sent_emails) == 2
    assert "already" in sent_emails[1]["subject"].lower()
    assert "/api/v1/auth/verify-link" not in sent_emails[1]["html"]


def test_register_username_taken_400(client, db_session, sent_emails):
    _register(client, username="taken1")
    resp = _register(client, email="other@example.com", username="taken1")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "username already taken"}
    assert db_session.query(User).count() == 1
    assert len(sent_emails) == 1


# ── 输入校验 ──


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "username": "okname", "password": VALID_PASSWORD},
        {"email": "u1@example.com", "username": "ab", "password": VALID_PASSWORD},
        {"email": "u1@example.com", "username": "bad name!", "password": VALID_PASSWORD},
        {"email": "u1@example.com", "username": "x" * 31, "password": VALID_PASSWORD},
        {"email": "u1@example.com", "username": "okname", "password": "short1"},
        {"email": "u1@example.com", "username": "okname", "password": "nodigitpassword"},
    ],
)
def test_register_rejects_invalid_input(client, db_session, payload, sent_emails):
    resp = client.post(f"{API}/register", json=payload)
    assert resp.status_code == 422, resp.text
    assert db_session.query(User).count() == 0
    assert sent_emails == []


# ── check-username ──


def test_check_username_available_taken_and_suggestions(client, fixed_code):
    ok = client.get(f"{API}/check-username", params={"username": "free1"})
    assert ok.status_code == 200
    assert ok.json() == {"available": True, "suggestions": None}

    _register(client, username="aidan1")

    taken = client.get(f"{API}/check-username", params={"username": "aidan1"})
    assert taken.status_code == 200
    body = taken.json()
    assert body["available"] is False
    assert body["suggestions"] is not None
    assert len(body["suggestions"]) == 3
    for suggestion in body["suggestions"]:
        assert re.fullmatch(r"[a-zA-Z0-9_]{3,30}", suggestion)
        assert suggestion != "aidan1"

    invalid = client.get(f"{API}/check-username", params={"username": "nope!"})
    assert invalid.status_code == 200
    assert invalid.json() == {"available": False, "suggestions": None}


# ── 魔法链接 ──


def test_magic_link_verifies_and_redirects(client, db_session, fixed_code):
    _register(client)
    user = db_session.query(User).filter(User.username == "aidan1").first()
    token = registration_service.create_magic_link_token(user.id)

    resp = client.get(f"{API}/verify-link", params={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("http://localhost:5173/register/verify?")
    assert "verified=1" in location
    assert "email=u1%40example.com" in location

    db_session.refresh(user)
    assert user.email_verified_at is not None

    # 验证后可正常登录
    login = client.post(f"{API}/login", json={"username": "aidan1", "password": VALID_PASSWORD})
    assert login.status_code == 200


def test_magic_link_expired_reason(client, db_session, fixed_code):
    _register(client)
    user = db_session.query(User).filter(User.username == "aidan1").first()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "register_verify",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        auth_settings.SECRET_KEY,
        algorithm="HS256",
    )
    resp = client.get(f"{API}/verify-link", params={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "verified=0" in resp.headers["location"]
    assert "reason=expired" in resp.headers["location"]


def test_magic_link_wrong_purpose_invalid(client, db_session, fixed_code):
    _register(client)
    user = db_session.query(User).filter(User.username == "aidan1").first()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "password_reset",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        auth_settings.SECRET_KEY,
        algorithm="HS256",
    )
    resp = client.get(f"{API}/verify-link", params={"token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert "verified=0" in resp.headers["location"]
    assert "reason=invalid" in resp.headers["location"]


# ── 开关关闭 ──


def test_register_disabled_returns_404(client, monkeypatch, sent_emails):
    monkeypatch.setattr(auth_settings, "REGISTRATION_ENABLED", False)
    resp = _register(client)
    assert resp.status_code == 404
    assert sent_emails == []


# ── 限流（真实 Redis）──


def test_register_rate_limit_per_ip(
    db_session, monkeypatch, reg_enabled, sent_emails, fixed_code, require_redis
):
    monkeypatch.setattr(auth_module, "check_login_rate_limit", lambda ip, u: (True, 1))
    monkeypatch.setattr(auth_module, "blacklist_token", lambda jti, ttl: None)

    def _dep():
        yield db_session

    app.dependency_overrides[auth_module._get_db] = _dep
    try:
        with TestClient(app) as c:
            for i in range(5):
                resp = _register(c, email=f"u{i}@example.com", username=f"user{i}")
                assert resp.status_code == 201, resp.text
            # 同 IP 第 6 次注册 → 429
            sixth = _register(c, email="u5@example.com", username="user5")
            assert sixth.status_code == 429
            assert "Retry-After" in sixth.headers
    finally:
        app.dependency_overrides.pop(auth_module._get_db, None)


def test_verify_rate_limit_per_email(client, db_session, require_redis, fixed_code):
    """client fixture 不 patch 守卫时才走真实限流；这里重建未 patch 的客户端。"""
    # client fixture 已把 check_verify_rate_limit patch 掉，这里手动恢复真实实现
    real_check = __import__(
        "app.core.rate_limit", fromlist=["check_verify_rate_limit"]
    ).check_verify_rate_limit
    with patch.object(auth_module, "check_verify_rate_limit", real_check):
        _register(client)
        for _ in range(10):
            resp = client.post(
                f"{API}/verify-registration",
                json={"email": "u1@example.com", "code": "000000"},
            )
            assert resp.status_code in (400, 410)
        eleventh = client.post(
            f"{API}/verify-registration",
            json={"email": "u1@example.com", "code": "000000"},
        )
        assert eleventh.status_code == 429


# ── 事务邮件封装 ──


def test_send_email_smtp_unconfigured_returns_false(monkeypatch, caplog):
    import app.services.transactional_email as te

    monkeypatch.setattr(
        te,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="",
            smtp_port=465,
            smtp_user="",
            smtp_password="",
            smtp_from="",
            smtp_use_tls=True,
        ),
    )
    with caplog.at_level("WARNING"):
        ok = te.send_email("a@example.com", "s", "<b>x</b>", "x")
    assert ok is False
    assert any("SMTP" in r.message for r in caplog.records)


def test_send_email_retries_once_then_succeeds(monkeypatch):
    import app.services.transactional_email as te

    calls = {"n": 0}

    class FlakySMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, from_addr, to_addrs, msg):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("connection reset")
            calls["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(
        te,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_user="bot@example.com",
            smtp_password="secret",
            smtp_from="AlloyResearch <bot@example.com>",
            smtp_use_tls=True,
        ),
    )
    monkeypatch.setattr(te.smtplib, "SMTP_SSL", FlakySMTP)
    monkeypatch.setattr(te, "_RETRY_DELAY_SECONDS", 0)

    ok = te.send_email("a@example.com", "subject", "<b>hi</b>", "hi")
    assert ok is True
    assert calls["n"] == 2
    assert "Subject: subject" in calls["msg"]


def test_register_still_201_when_email_send_fails(client, monkeypatch, fixed_code):
    monkeypatch.setattr(registration_service, "send_email", lambda *a, **k: False)
    resp = _register(client)
    assert resp.status_code == 201
    assert resp.json() == {"detail": "verification email sent"}
