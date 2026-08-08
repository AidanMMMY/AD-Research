"""Daily Digest 门面服务测试（2026-08-03，B3）。

Coverage:
  - 正常路径：mock collector + generator → daily_digest 落库（含
    sections_json / data_snapshot_json / llm_model）+ report_metadata
    伴随行（report_type="daily_digest", pool_id=NULL, format=
    "markdown", file_path=NULL）+ report_metadata_id 回链。
  - 同日重生成 → upsert：仍各 1 行，内容被覆盖。
  - generator 异常 → status=failed + error_msg 落库 + 异常 re-raise。
  - 无通知配置时 notify 安全返回空（不炸主链路）。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 注册全部 ORM 模型（create_all 需要）
import app.models  # noqa: F401
from app.core.database import Base
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
from app.models.scoring import ReportMetadata
from app.services.digest.context import DigestContext
from app.services.digest.generator import DigestResult
from app.services.digest.service import REPORT_TYPE, DailyDigestService

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_DATE = date(2026, 8, 3)


@pytest.fixture
def digest_db():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _fake_ctx() -> DigestContext:
    return DigestContext(
        report_date=REPORT_DATE,
        window_start=datetime(2026, 8, 2, 6, 30, tzinfo=SHANGHAI),
        window_end=datetime(2026, 8, 3, 6, 30, tzinfo=SHANGHAI),
        degraded=["macro"],
    )


class FakeCollector:
    def __init__(self, ctx):
        self._ctx = ctx
        self.calls = []

    def collect(self, report_date):
        self.calls.append(report_date)
        return self._ctx


class FakeGenerator:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def generate(self, ctx):
        if self._exc:
            raise self._exc
        return self._result


def _result(content: str = "# 全文\n\n## 一\n正文") -> DigestResult:
    return DigestResult(
        title="2026-08-03 每日综合研报",
        content_md=content,
        summary_md="摘要",
        status="success",
        llm_model="fake-model-v1",
        sections=[{"key": "overnight_news", "title": "一、隔夜全球要闻",
                   "status": "success", "chars": 100}],
    )


def test_generate_persist_and_companion_row(digest_db):
    service = DailyDigestService(
        digest_db,
        collector=FakeCollector(_fake_ctx()),
        generator=FakeGenerator(result=_result()),
    )
    digest = service.generate(REPORT_DATE)

    assert digest.id is not None
    assert digest.report_date == REPORT_DATE
    assert digest.status == "success"
    assert digest.title == "2026-08-03 每日综合研报"
    assert digest.summary_md == "摘要"
    assert digest.llm_model == "fake-model-v1"
    assert digest.sections_json[0]["key"] == "overnight_news"
    # data_snapshot：窗口 + degraded 元数据
    snap = digest.data_snapshot_json
    assert snap["degraded"] == ["macro"]
    assert snap["report_date"] == "2026-08-03"
    assert digest.started_at is not None and digest.finished_at is not None

    # report_metadata 伴随行
    meta = digest_db.execute(
        select(ReportMetadata).where(ReportMetadata.report_type == REPORT_TYPE)
    ).scalars().one()
    assert meta.report_date == REPORT_DATE
    assert meta.pool_id is None
    assert meta.format == "markdown"
    assert meta.file_path is None
    assert meta.status == "success"
    assert digest.report_metadata_id == meta.id


def test_regenerate_same_date_upserts(digest_db):
    collector = FakeCollector(_fake_ctx())
    service = DailyDigestService(
        digest_db, collector=collector, generator=FakeGenerator(result=_result())
    )
    first = service.generate(REPORT_DATE)

    service2 = DailyDigestService(
        digest_db,
        collector=collector,
        generator=FakeGenerator(result=_result(content="# 新全文")),
    )
    second = service2.generate(REPORT_DATE)

    rows = digest_db.execute(select(DailyDigest)).scalars().all()
    metas = digest_db.execute(
        select(ReportMetadata).where(ReportMetadata.report_type == REPORT_TYPE)
    ).scalars().all()
    assert len(rows) == 1
    assert len(metas) == 1
    assert second.id == first.id
    assert second.content_md == "# 新全文"


def test_generator_exception_marks_failed_and_reraises(digest_db):
    service = DailyDigestService(
        digest_db,
        collector=FakeCollector(_fake_ctx()),
        generator=FakeGenerator(exc=RuntimeError("generator blew up")),
    )
    with pytest.raises(RuntimeError, match="generator blew up"):
        service.generate(REPORT_DATE)

    digest = digest_db.execute(select(DailyDigest)).scalars().one()
    assert digest.status == "failed"
    assert "generator blew up" in digest.error_msg
    assert digest.finished_at is not None


def test_notify_without_configs_is_noop(digest_db):
    """无 NotificationConfig 时 notify 返回空列表，不影响落库。"""
    service = DailyDigestService(
        digest_db,
        collector=FakeCollector(_fake_ctx()),
        generator=FakeGenerator(result=_result()),
    )
    digest = service.generate(REPORT_DATE)
    assert digest.status == "success"
    assert service.notify(digest, digest.report_metadata_id) == []


def test_notify_skipped_when_failed(digest_db):
    service = DailyDigestService(
        digest_db,
        collector=FakeCollector(_fake_ctx()),
        generator=FakeGenerator(result=_result()),
    )
    digest = service.generate(REPORT_DATE)
    digest.status = "failed"
    assert service.notify(digest, digest.report_metadata_id) == []
