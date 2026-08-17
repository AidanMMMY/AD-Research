"""2026-08-17 安全审计 HIGH：SSE 端点不阻塞事件循环的回归测试。

覆盖：
  - stream._price_stream：同步 DB 查询经 anyio.to_thread 丢线程池，
    阻塞期间事件循环其他任务仍能调度（旧实现 ticks≈0）。
  - notifications._notification_event_stream：同上，且 connected /
    data 事件格式不变。
  - stream._collect_payload 批量 IN 改写的功能等价性：ETFInfo 命中、
    bare code 候选匹配、ETFInfo 有行但无 bar → unknown、完全未知 code。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  # 注册全部 ORM 模型（create_all 需要）
from app.api.v1 import notifications, stream
from app.core.database import Base
from app.models.etf import ETFInfo, InstrumentDailyBar


@pytest.fixture
def stream_session_factory():
    """跨线程共享的内存库（StaticPool + check_same_thread=False）。

    默认 SingletonThreadPool 下 to_thread 的工作线程会拿到另一条
    connection（空库），无法做端到端断言；StaticPool 让主线程与
    线程池共用同一条连接。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _seed_prices(factory) -> None:
    db = factory()
    try:
        db.add(ETFInfo(code="510300.SH", name="沪深300ETF", market="A股"))
        db.add(ETFInfo(code="159915.SZ", name="创业板ETF", market="A股"))
        db.add_all(
            [
                InstrumentDailyBar(
                    etf_code="510300.SH",
                    trade_date=date(2026, 8, 13),
                    close=Decimal("100"),
                    volume=1000,
                ),
                InstrumentDailyBar(
                    etf_code="510300.SH",
                    trade_date=date(2026, 8, 14),
                    close=Decimal("110"),
                    volume=2000,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


async def _run_with_ticker(gen, take: int) -> tuple[list[str], int]:
    """消费 gen 前 take 个事件，同时跑一个 10ms ticker 统计调度次数。"""
    ticks = 0
    stop = False

    async def ticker() -> None:
        nonlocal ticks
        while not stop:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    events: list[str] = []
    try:
        for _ in range(take):
            events.append(await gen.__anext__())
    finally:
        stop = True
        await task
        await gen.aclose()
    return events, ticks


# ── 事件循环不被同步 DB 查询阻塞 ──


async def test_price_stream_does_not_block_event_loop(monkeypatch):
    """_collect_payload 阻塞 0.2s 期间，ticker 必须持续推进。"""

    def fake_collect(codes):
        time.sleep(0.2)
        return {"data": [], "unknown": list(codes)}

    monkeypatch.setattr(stream, "_collect_payload", fake_collect)

    events, ticks = await _run_with_ticker(stream._price_stream(["X"]), take=1)
    assert events[0].startswith("data: ")
    assert json.loads(events[0][len("data: "):]) == {"data": [], "unknown": ["X"]}
    # 旧实现（生成器内直接同步调用）下这 0.2s 内 ticks 恒为 0
    assert ticks >= 5


async def test_notification_stream_does_not_block_event_loop(monkeypatch):
    """_poll_recent_logs 阻塞 0.2s 期间，ticker 必须持续推进。"""

    def fake_poll(user_id: int) -> dict:
        time.sleep(0.2)
        return {"items": [{"id": 7}], "total": 1, "page": 1, "page_size": 5}

    monkeypatch.setattr(notifications, "_poll_recent_logs", fake_poll)

    events, ticks = await _run_with_ticker(
        notifications._notification_event_stream(user_id=1), take=2
    )
    assert events[0].startswith("event: connected")
    assert events[1].startswith("data: ")
    assert json.loads(events[1][len("data: "):])["items"][0]["id"] == 7
    assert ticks >= 5


async def test_notification_stream_keepalive_unchanged(monkeypatch):
    """newest id 未变时仍发 keepalive 注释（SSE 协议语义回归）。"""
    monkeypatch.setattr(
        notifications,
        "_poll_recent_logs",
        lambda user_id: {"items": [], "total": 0, "page": 1, "page_size": 5},
    )
    events, _ = await _run_with_ticker(
        notifications._notification_event_stream(user_id=1), take=2
    )
    assert events[1] == ": keepalive\n\n"


# ── _collect_payload 批量改写后的功能等价性 ──


def test_collect_payload_batch_matches_and_unknown(
    stream_session_factory, monkeypatch
):
    monkeypatch.setattr(stream, "SessionLocal", stream_session_factory)
    _seed_prices(stream_session_factory)

    # 带后缀精确命中 + bare code 候选命中（去重）+ 无 bar 的 ETF + 未知 code
    payload = stream._collect_payload(
        ["510300.SH", "510300", "159915.SZ", "ZZZ"]
    )

    assert payload is not None
    data = payload["data"]
    assert len(data) == 1  # 510300.SH 与 510300 去重为一条
    snap = data[0]
    assert snap["code"] == "510300.SH"
    assert snap["name"] == "沪深300ETF"
    assert snap["market"] == "A股"
    assert snap["price"] == 110.0
    assert snap["change_pct"] == 10.0
    assert snap["volume"] == 2000
    assert isinstance(snap["timestamp"], int) and snap["timestamp"] > 0
    # 159915.SZ 有 ETFInfo 行但无 bar → unknown；ZZZ 完全未知
    assert sorted(payload["unknown"]) == ["159915.SZ", "ZZZ"]


async def test_price_stream_end_to_end_via_threadpool(
    stream_session_factory, monkeypatch
):
    """端到端：to_thread 跨线程执行真实查询并产出 SSE 事件。"""
    monkeypatch.setattr(stream, "SessionLocal", stream_session_factory)
    _seed_prices(stream_session_factory)

    events, _ = await _run_with_ticker(stream._price_stream(["510300.SH"]), take=1)
    assert events[0].startswith("data: ")
    payload = json.loads(events[0][len("data: "):])
    assert payload["data"][0]["code"] == "510300.SH"
    assert payload["data"][0]["change_pct"] == 10.0
