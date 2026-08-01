"""Regression tests for the 2026-08-01 content-fetcher body fixes.

Covers two production incidents:

1. **huxiu 段落粘连** — RSS 全文源（虎嗅）在入库时把块级标签打平成
   空格，``full_content`` 里一个换行都没有，详情页整篇混成一段。
   修复：``_looks_flattened`` 识别"长文 + 零换行"的打平缓存，触发
   重新提取，trafilatura 从原文页面恢复 ``\n\n`` 段落结构。
2. **Jina 余额耗尽（402）** — 2026-07-30 起 Jina 账户余额耗尽，
   investing/marketwatch/ft 等依赖 Jina 的源整体提取失败，10 分钟
   drain 每轮对每篇积压文章都白打一次必然失败的 Jina 请求。修复：
   断路器在 402/429/403 时短路后续调用并给出可操作的日志。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.news import content_fetcher as cf
from app.services.news._model_loader import (
    NewsArticle,
    load_news_models,
)
from app.services.news.content_fetcher import (
    ContentFetcher,
    _JinaError,
    _clean_jina_body,
    _html_to_text,
    _looks_flattened,
    _reset_jina_breaker,
)

load_news_models()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _breaker_reset():
    """每个用例前后都复位 Jina 断路器，避免跨用例串扰。"""
    _reset_jina_breaker()
    yield
    _reset_jina_breaker()


# 虎嗅风格正文：多个 <p> 段落，真实 trafilatura 应恢复 \n\n 分段。
_HUXIU_PARAS = [
    "政策与监管的组合拳，给整个行业带来了希望，也让资本市场重新审视这个被低估已久的板块。" * 3,
    "有不少人说，这轮周期已经快结束了，但事实可能才刚刚开始。关键是需求端的恢复和供给端的出清必须达到均衡点。" * 3,
    "爱旭董事长陈刚判断：这一轮周期已经到尾声了，有些企业已经反转，只是外部的感知会稍微慢一点。" * 3,
    "当下是黎明前至暗时刻，未来数月行情依旧煎熬，各类超预期的承压行情还会出现，但都只是回暖前的倒春寒。" * 3,
]

HUXIU_HTML = (
    "<html><head><title>光伏真正的拐点要到2027年底</title></head>"
    "<body><article>"
    + "".join(f"<p>{p}</p>" for p in _HUXIU_PARAS)
    + "</article></body></html>"
)


def _seed_article(
    db_session,
    *,
    full_content: str | None = None,
    fetched_at: datetime | None = None,
    body: str = "摘要。",
) -> NewsArticle:
    article = NewsArticle(
        source="huxiu",
        source_id="https://www.huxiu.com/article/1.html",
        url="https://www.huxiu.com/article/1.html",
        url_hash="deadbeef",
        title="光伏真正的拐点要到2027年底",
        body=body,
        summary=body,
        language="zh",
        market="cn_a",
        published_at=datetime.now(tz=UTC),
        full_content=full_content,
        full_content_fetched_at=fetched_at,
    )
    db_session.add(article)
    db_session.commit()
    return article


def _fake_response(text: str, status_code: int = 200) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, text=text)


# ---------------------------------------------------------------------------
# 1) Flattened-body detection
# ---------------------------------------------------------------------------


def test_looks_flattened_flags_long_single_block() -> None:
    # 长文 + 零换行 = 入库时块级标签被打平的 RSS 全文（huxiu 案例）。
    assert _looks_flattened("正文" * 300)
    # 有段落换行的正常提取结果不算打平。
    assert not _looks_flattened(("正文" * 150) + "\n\n" + ("正文" * 150))
    # 短快讯（< 400 字）没有换行也不算打平。
    assert not _looks_flattened("快讯：央行降准 25 个基点。")
    assert not _looks_flattened(None)
    assert not _looks_flattened("")


def test_flattened_fresh_cache_triggers_reextraction(db_session) -> None:
    """缓存未过期但已打平：必须重新提取而不是直接返回缓存。"""
    flattened = "".join(_HUXIU_PARAS)  # 粘成一段、零换行，模拟 huxiu 存量数据
    assert "\n" not in flattened and len(flattened) >= 400
    article = _seed_article(
        db_session,
        full_content=flattened,
        fetched_at=datetime.now(tz=UTC),  # 缓存新鲜——打平守卫必须绕过它
        body=flattened,
    )

    with (
        patch.object(ContentFetcher, "_fetch_html", return_value=HUXIU_HTML),
        # Jina 不应被调用：tier-1 trafilatura 已能恢复段落。
        patch.object(ContentFetcher, "_call_jina") as jina_mock,
    ):
        result = ContentFetcher(db_session).fetch(article.id)

    assert result.success
    assert not result.cached, "打平缓存不得当作命中直接返回"
    jina_mock.assert_not_called()
    # 段落结构已恢复：段间恰好 \n\n，无 3+ 连续换行。
    assert "\n\n" in result.content
    assert "\n\n\n" not in result.content
    db_session.refresh(article)
    assert "\n\n" in article.full_content
    assert article.ai_cleanup_status == "cleaned"


def test_structured_fresh_cache_still_hits(db_session) -> None:
    """正常带段落的缓存仍然命中，不会被误伤重抓。"""
    structured = ("第一段。" * 100) + "\n\n" + ("第二段。" * 100)
    article = _seed_article(
        db_session,
        full_content=structured,
        fetched_at=datetime.now(tz=UTC),
    )
    with patch.object(ContentFetcher, "_fetch_html") as html_mock:
        result = ContentFetcher(db_session).fetch(article.id)
    assert result.success and result.cached
    assert result.content == structured
    html_mock.assert_not_called()


def test_huxiu_style_html_extracts_paragraphs_end_to_end(db_session) -> None:
    """无缓存的新文章：真实 trafilatura 从多 <p> HTML 恢复分段。"""
    article = _seed_article(db_session)
    with patch.object(ContentFetcher, "_fetch_html", return_value=HUXIU_HTML):
        result = ContentFetcher(db_session).fetch(article.id, force=True)
    assert result.success
    assert result.content is not None
    # 至少恢复出 3 个段落边界。
    assert result.content.count("\n\n") >= 3
    assert _HUXIU_PARAS[0][:20] in result.content
    assert _HUXIU_PARAS[-1][:20] in result.content


def test_html_to_text_keeps_block_boundaries(db_session) -> None:
    """LLM 兜底层的 HTML→text 也必须在块级元素边界产生换行。"""
    text = _html_to_text(HUXIU_HTML)
    for para in _HUXIU_PARAS:
        assert para[:20] in text
    # 段落之间被换行隔开，而不是粘成一行。
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= len(_HUXIU_PARAS)


def test_clean_body_normalizes_paragraph_spacing() -> None:
    """清洗输出必须是规范 \n\n 分段（与前端折叠 3+ 换行的渲染衔接）。"""
    raw = "第一段。\n\n\n\n第二段。\n\n\n\n\n第三段。"
    cleaned = _clean_jina_body(raw, "不相关标题")
    assert "\n\n\n" not in cleaned
    assert "第一段。\n\n第二段。\n\n第三段。" == cleaned


# ---------------------------------------------------------------------------
# 2) Jina circuit breaker
# ---------------------------------------------------------------------------


def test_jina_402_trips_breaker_and_short_circuits(db_session) -> None:
    """402 余额耗尽：首次调用报错并拉闸，后续调用不再发网络请求。"""
    fetcher = ContentFetcher(db_session)
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("InsufficientBalanceError", status_code=402),
    ) as get_mock:
        with pytest.raises(_JinaError, match="balance exhausted"):
            fetcher._call_jina("https://example.com/a")
        assert get_mock.call_count == 1
        # 断路器已打开：第二次调用直接失败，不再打 Jina。
        with pytest.raises(_JinaError, match="balance exhausted"):
            fetcher._call_jina("https://example.com/b")
        assert get_mock.call_count == 1


def test_jina_429_trips_breaker(db_session) -> None:
    fetcher = ContentFetcher(db_session)
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("rate limit", status_code=429),
    ) as get_mock:
        with pytest.raises(_JinaError, match="rate-limited"):
            fetcher._call_jina("https://example.com/a")
        with pytest.raises(_JinaError, match="rate-limited"):
            fetcher._call_jina("https://example.com/a")
        assert get_mock.call_count == 1


def test_jina_breaker_expires(db_session) -> None:
    """冷却期过后断路器自动恢复，允许重新调用 Jina。"""
    fetcher = ContentFetcher(db_session)
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("InsufficientBalanceError", status_code=402),
    ):
        with pytest.raises(_JinaError):
            fetcher._call_jina("https://example.com/a")
    # 把时间快进到冷却期之后。
    cf._jina_breaker_until = 0.0
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("Markdown Content:\n\n正文"),
    ) as get_mock:
        out = fetcher._call_jina("https://example.com/a")
        assert "正文" in out
        assert get_mock.call_count == 1


def test_jina_generic_error_does_not_trip_breaker(db_session) -> None:
    """普通 5xx 不拉闸（可能是目标站临时故障，与 Jina 账户无关）。"""
    fetcher = ContentFetcher(db_session)
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("upstream error", status_code=500),
    ) as get_mock:
        with pytest.raises(_JinaError, match="http 500"):
            fetcher._call_jina("https://example.com/a")
        with pytest.raises(_JinaError, match="http 500"):
            fetcher._call_jina("https://example.com/b")
        assert get_mock.call_count == 2


def test_fetch_marks_failed_with_actionable_error_when_jina_402(
    db_session,
) -> None:
    """端到端：marketwatch 场景（tier-1 被反爬挡掉 + Jina 402）——
    行被标记 failed，错误信息明确提示充值，而不是含糊的 http 402。"""
    article = _seed_article(db_session)
    with (
        patch.object(ContentFetcher, "_fetch_html", return_value=None),
        patch(
            "app.services.news.content_fetcher.httpx.get",
            return_value=_fake_response("InsufficientBalanceError", status_code=402),
        ),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)
    assert not result.success
    assert "balance exhausted" in (result.error or "")
    db_session.refresh(article)
    assert article.ai_cleanup_status == "failed"
