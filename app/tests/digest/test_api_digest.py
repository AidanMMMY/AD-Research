"""Daily Digest API 测试（2026-08-03，B5）。

Coverage（照 test_research_reports_api.py 的 fixture 模式）：
  - 鉴权：未登录 → 401/403；regenerate 普通用户 → 403，admin → 202。
  - GET /digest：空列表、分页、report_date 倒序、不含 content_md。
  - GET /digest/latest：全文字段齐全；无记录 404。
  - GET /digest/latest/summary：轻量 5 字段；无记录 404。
  - GET /digest/{id}：全文；无记录 404。
  - GET /digest/by-date/{date}：命中；非法格式 400；无记录 404。
  - POST /digest/regenerate：默认 target_date=今天（Asia/Shanghai），
    后台线程同步替身验证确实调用了 run_daily_digest。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 注册全部 ORM 模型（create_all 需要，同 test_service.py）
import app.models  # noqa: F401
from app.api import deps as api_deps
from app.core.database import Base
from app.main import app
from app.models import (  # noqa: F401
    etf_scan_log,
    etl,
    favorite,
    listing,
    notification,
    research,
    user_article_state,
)
from app.models.digest import DailyDigest

BASE = "/api/v1/digest"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """内存 SQLite（StaticPool 共享连接，TestClient 线程可见）。"""
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
    from app.schemas.auth import UserResponse

    def _dep():
        return UserResponse(id=1, username="tester", role=role)

    return _dep


def _make_client(db_session, role: str = "user") -> TestClient:
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[api_deps.get_current_user] = _override_user(role=role)
    return TestClient(app)


@pytest.fixture
def client(db_session):
    c = _make_client(db_session, role="user")
    with c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def admin_client(db_session):
    c = _make_client(db_session, role="admin")
    with c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


def _seed(db, rows: list[DailyDigest]) -> list[DailyDigest]:
    for r in rows:
        db.add(r)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def _digest(
    report_date: date,
    *,
    status: str = "success",
    title: str = "每日综合研报",
    summary_md: str = "摘要",
    content_md: str = "# 全文\n\n## 一\n正文",
    sections=None,
) -> DailyDigest:
    return DailyDigest(
        report_date=report_date,
        status=status,
        title=title,
        summary_md=summary_md,
        content_md=content_md,
        sections_json=sections
        or [{"key": "overnight_news", "title": "一、隔夜全球要闻",
             "status": "success", "chars": 100}],
        data_snapshot_json={"report_date": report_date.isoformat()},
        llm_model="fake-model-v1",
    )


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


def test_endpoints_require_auth(db_session):
    """未登录（无 auth override）→ 401/403。"""
    with TestClient(app) as c:
        for path in (BASE, f"{BASE}/latest", f"{BASE}/latest/summary",
                     f"{BASE}/1", f"{BASE}/by-date/2026-08-03"):
            assert c.get(path).status_code in (401, 403), path
        assert c.post(f"{BASE}/regenerate", json={}).status_code in (401, 403)


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------


def test_list_empty(client):
    resp = client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0


def test_list_pagination_and_order(client, db_session):
    _seed(db_session, [
        _digest(date(2026, 8, 1)),
        _digest(date(2026, 8, 3)),
        _digest(date(2026, 8, 2)),
    ])
    resp = client.get(f"{BASE}?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 2
    # report_date 倒序
    assert [i["report_date"] for i in body["items"]] == [
        "2026-08-03", "2026-08-02",
    ]
    # 列表项不含 content_md 全文，但带 content_chars
    item = body["items"][0]
    assert "content_md" not in item
    assert item["content_chars"] == len("# 全文\n\n## 一\n正文")
    assert {"id", "report_date", "status", "title", "summary_md",
            "created_at"} <= set(item)


# ---------------------------------------------------------------------------
# latest / latest/summary
# ---------------------------------------------------------------------------


def test_latest_returns_full_report(client, db_session):
    _seed(db_session, [
        _digest(date(2026, 8, 1), title="旧"),
        _digest(date(2026, 8, 3), title="新"),
    ])
    resp = client.get(f"{BASE}/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_date"] == "2026-08-03"
    assert body["title"] == "新"
    assert body["content_md"].startswith("# 全文")
    assert body["sections_json"][0]["key"] == "overnight_news"
    assert body["data_snapshot_json"]["report_date"] == "2026-08-03"
    assert body["llm_model"] == "fake-model-v1"


def test_latest_404_when_empty(client):
    resp = client.get(f"{BASE}/latest")
    assert resp.status_code == 404


def test_latest_summary_lightweight(client, db_session):
    _seed(db_session, [_digest(date(2026, 8, 3))])
    resp = client.get(f"{BASE}/latest/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_date"] == "2026-08-03"
    assert body["status"] == "success"
    assert body["title"] == "每日综合研报"
    assert body["summary_md"] == "摘要"
    # 轻量：不回全文 / 章节
    assert "content_md" not in body
    assert "sections_json" not in body


def test_latest_summary_404_when_empty(client):
    assert client.get(f"{BASE}/latest/summary").status_code == 404


def test_latest_sections_null_falls_back_to_empty_list(client, db_session):
    """failed 行 sections_json 为 NULL 时按 [] 返回（前端按数组渲染）。"""
    _seed(db_session, [
        DailyDigest(report_date=date(2026, 8, 3), status="failed",
                    error_msg="boom"),
    ])
    resp = client.get(f"{BASE}/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["sections_json"] == []
    assert body["title"] == ""


# ---------------------------------------------------------------------------
# /{id} 与 /by-date/{date}
# ---------------------------------------------------------------------------


def test_get_by_id(client, db_session):
    rows = _seed(db_session, [_digest(date(2026, 8, 3))])
    resp = client.get(f"{BASE}/{rows[0].id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rows[0].id
    assert resp.json()["content_md"]


def test_get_by_id_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_get_by_date(client, db_session):
    _seed(db_session, [_digest(date(2026, 8, 2))])
    resp = client.get(f"{BASE}/by-date/2026-08-02")
    assert resp.status_code == 200
    assert resp.json()["report_date"] == "2026-08-02"


def test_get_by_date_404(client, db_session):
    _seed(db_session, [_digest(date(2026, 8, 2))])
    assert client.get(f"{BASE}/by-date/2026-08-01").status_code == 404


def test_get_by_date_invalid_format_400(client):
    # 注："2026/08/02" 含斜杠会在路由层 404（路径段不匹配），不属于
    # 参数校验语义，故这里只测单段非法格式。
    for bad in ("20260802", "08-02-2026", "not-a-date", "2026-13-01"):
        resp = client.get(f"{BASE}/by-date/{bad}")
        assert resp.status_code == 400, bad


# ---------------------------------------------------------------------------
# regenerate（admin 限定 + 后台线程）
# ---------------------------------------------------------------------------


class _SyncThread:
    """threading.Thread 的同步替身：start() 立即执行 target。"""

    def __init__(self, target=None, args=(), kwargs=None, **_kw):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def test_regenerate_forbidden_for_normal_user(client):
    resp = client.post(f"{BASE}/regenerate", json={})
    assert resp.status_code == 403


def test_regenerate_accepts_and_dispatches(admin_client):
    fake_run = MagicMock()
    with patch("app.api.v1.digest.run_daily_digest", fake_run), \
         patch("app.api.v1.digest.threading.Thread", _SyncThread):
        resp = admin_client.post(
            f"{BASE}/regenerate", json={"target_date": "2026-08-01"}
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["report_date"] == "2026-08-01"
    fake_run.assert_called_once_with(target_date=date(2026, 8, 1))


def test_regenerate_default_date_is_today_shanghai(admin_client):
    from datetime import datetime as dt

    from app.services.digest.collector import SHANGHAI

    expected = dt.now(SHANGHAI).date()
    fake_run = MagicMock()
    with patch("app.api.v1.digest.run_daily_digest", fake_run), \
         patch("app.api.v1.digest.threading.Thread", _SyncThread):
        resp = admin_client.post(f"{BASE}/regenerate")
    assert resp.status_code == 202
    assert resp.json()["report_date"] == expected.isoformat()
    fake_run.assert_called_once_with(target_date=expected)
