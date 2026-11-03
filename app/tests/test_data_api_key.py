"""静态数据 API Key（X-API-Key）认证测试（2026-11-04）。

外部只读数据消费方专用通道：一个请求头，无登录/无续期/无过期。
语义边界：映射到专用服务账号（普通 user 角色）；admin 域仍 403；
key 未配置（空）时通道整体关闭；错误 key 与服务账号异常统一 401
（不泄漏服务账号是否存在）。

线程说明：deps 内部直连 ``SessionLocal()``（非 Depends），TestClient 的
应用线程与测试线程会共用连接，因此本文件自建
``check_same_thread=False + StaticPool`` 引擎，不复用 conftest 的
``db_session``（其引擎无跨线程豁免；注册类测试无此问题是因为种子数据
全部经 HTTP 完成）。
"""

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import auth as auth_module
from app.config import auth_settings
from app.core.database import Base
from app.main import app
from app.models.user import User

SERVICE_USER = "external_data_1"
GOOD_KEY = "unit-test-data-key-0123456789"


def _seed_service_user(session) -> User:
    user = User(
        username=SERVICE_USER,
        password_hash=bcrypt.hashpw(b"irrelevant-1234", bcrypt.gensalt()).decode(),
        role="user",
        is_active=True,
        must_change_password=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def env(monkeypatch):
    """Yields ``(client, session)`` sharing one cross-thread in-memory DB."""
    monkeypatch.setattr(auth_settings, "DATA_API_KEY", GOOD_KEY)
    monkeypatch.setattr(auth_settings, "DATA_API_USERNAME", SERVICE_USER)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()

    from unittest.mock import patch

    def _dep():
        yield Session_()

    with patch("app.api.deps.SessionLocal", side_effect=lambda: Session_()):
        app.dependency_overrides[auth_module._get_db] = _dep
        with TestClient(app) as c:
            yield c, session
        app.dependency_overrides.pop(auth_module._get_db, None)
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_api_key_authenticates_read_endpoint(env):
    client, session = env
    _seed_service_user(session)
    r = client.get("/api/v1/news", headers={"X-API-Key": GOOD_KEY}, params={"page": 1})
    assert r.status_code == 200


def test_wrong_key_is_401(env):
    client, session = env
    _seed_service_user(session)
    r = client.get("/api/v1/news", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_empty_key_disables_the_path(env, monkeypatch):
    client, session = env
    _seed_service_user(session)
    monkeypatch.setattr(auth_settings, "DATA_API_KEY", "")
    r = client.get("/api/v1/news", headers={"X-API-Key": "anything"})
    assert r.status_code == 401


def test_missing_user_is_401_without_leaking(env):
    client, _ = env
    r = client.get("/api/v1/news", headers={"X-API-Key": GOOD_KEY})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid API key"


def test_admin_still_forbidden_for_key_identity(env):
    client, session = env
    _seed_service_user(session)
    r = client.get("/api/v1/admin/users", headers={"X-API-Key": GOOD_KEY})
    assert r.status_code == 403


def test_bearer_jwt_path_still_works(env):
    """auto_error=False 改造后，普通 Bearer 流不能回归。"""
    client, session = env
    _seed_service_user(session)
    assert client.get("/api/v1/news").status_code == 401
    assert (
        client.get("/api/v1/news", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    )


def test_access_audit_row_written_for_key_request(env):
    client, session = env
    _seed_service_user(session)
    r = client.get(
        "/api/v1/news",
        headers={"X-API-Key": GOOD_KEY, "User-Agent": "friend-project/1.0"},
        params={"page": 1},
    )
    assert r.status_code == 200
    from app.models.data_api_access_log import DataApiAccessLog

    session.expire_all()
    rows = session.query(DataApiAccessLog).all()
    assert len(rows) >= 1
    row = rows[-1]
    assert row.username == SERVICE_USER
    assert row.path == "/api/v1/news"
    assert row.status_code == 200
    assert row.user_agent == "friend-project/1.0"


def test_admin_usage_endpoint_aggregates(env, monkeypatch):
    from app.api import deps as deps_module
    from app.schemas.auth import UserResponse

    client, session = env
    _seed_service_user(session)
    client.get("/api/v1/news", headers={"X-API-Key": GOOD_KEY})  # 造一条审计
    client.get("/api/v1/news", headers={"X-API-Key": "bad"})  # 401 也应留痕

    fake_admin = UserResponse(id=1, username="admin", role="admin", must_change_password=False)
    # 关键：override 的 key 必须是路由注册时捕获的原函数对象（勿先 monkeypatch 替换属性）
    app.dependency_overrides[deps_module.require_admin] = lambda: fake_admin
    try:
        r = client.get("/api/v1/admin/data-api/usage", params={"days": 7})
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["requests"] >= 2
        assert body["totals"]["errors"] >= 1  # 401 那次
        assert any(x["path"] == "/api/v1/news" for x in body["top_paths"])
        assert len(body["recent"]) >= 2
    finally:
        app.dependency_overrides.pop(deps_module.require_admin, None)
