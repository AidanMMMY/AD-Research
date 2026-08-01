"""繁体→简体转换（``app.services.news.zh_convert``）与入库链路集成测试。

覆盖场景：
1. 繁体特征检测：繁体文本命中、简体文本不误判（含两岸同形字
   「解 / 面 / 加 / 密」的常见简体词）、空值安全。
2. 转换函数：繁体正文转简体、已是简体幂等、非中文语言门控跳过、
   HTML 标签不被破坏。
3. 写入路径集成：
   * ``NewsNormalizer.normalize`` — 繁体 zh 文章入库即简体；简体
     zh 文章原样；en 文章即便含繁体字也不动。
   * ``ContentFetcher.fetch`` — 补抓回来的繁体 full_content 入库
     前转简体。
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.news._model_loader import load_news_models
from app.services.news.content_fetcher import ContentFetcher
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer
from app.services.news.zh_convert import (
    convert_article_text_fields,
    has_traditional,
    to_simplified,
    to_simplified_if_traditional,
)

load_news_models()


# ---------------------------------------------------------------------------
# 检测与转换单元测试
# ---------------------------------------------------------------------------

def test_has_traditional_detects_traditional_text() -> None:
    assert has_traditional("台灣資訊軟體產業的最新發展") is True
    assert has_traditional("這裡什麼瞭解") is True


def test_has_traditional_ignores_simplified_text() -> None:
    # 「解决方案」「页面」「加密」里的 解/面/加/密 两岸同形，不能误判
    assert has_traditional("这是一篇简体中文文章，讨论解决方案和加密货币政策。") is False
    assert has_traditional("页面上的信息显示，市场发展稳定。") is False


def test_has_traditional_handles_empty() -> None:
    assert has_traditional(None) is False
    assert has_traditional("") is False


def test_to_simplified_converts_traditional() -> None:
    assert to_simplified("臺灣資訊軟體這裡什麼瞭解") == "台湾资讯软体这里什么了解"


def test_to_simplified_if_traditional_converts_traditional() -> None:
    text = "台積電先進製程的最新進展，為產業帶來什麼樣的變化？"
    converted = to_simplified_if_traditional(text)
    assert converted is not None
    assert "進" not in converted
    assert "為" not in converted
    assert "先进" in converted or "先進" not in converted
    assert has_traditional(converted) is False


def test_to_simplified_if_traditional_keeps_simplified() -> None:
    text = "这是一篇简体中文正文，什么内容都不会改变。"
    assert to_simplified_if_traditional(text) == text


def test_to_simplified_if_traditional_keeps_empty() -> None:
    assert to_simplified_if_traditional(None) is None
    assert to_simplified_if_traditional("") == ""


def test_convert_gate_skips_non_chinese_language() -> None:
    fields = {"body": "這是繁體中文，但文章語言標記為日文。"}
    assert convert_article_text_fields(fields, language="ja") == fields
    assert convert_article_text_fields(fields, language="en") == fields


def test_convert_gate_applies_to_chinese_variants() -> None:
    fields = {"body": "這裡是繁體正文"}
    for lang in ("zh", "zh-tw", "zh-hant", "zh-hk"):
        converted = convert_article_text_fields(dict(fields), language=lang)
        assert converted["body"] == "这里是繁体正文"


def test_html_tags_survive_conversion() -> None:
    html = '<p class="lead">這是<strong>繁體</strong>段落，含<a href="https://example.com/資訊">連結</a></p>'
    converted = to_simplified_if_traditional(html)
    assert converted is not None
    assert "<p class=\"lead\">" in converted
    assert "<strong>繁体</strong>" in converted
    assert "这是" in converted
    # 标签结构未被破坏
    assert converted.count("<") == html.count("<")
    assert "</a></p>" in converted


# ---------------------------------------------------------------------------
# 写入路径集成测试
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


def _normalize(db_session, **kwargs) -> object:
    defaults = {
        "source": "zhb_technews",
        "url": "https://example.com/articles/trad-1",
        "title": "標題",
        "published_at": datetime.now(tz=UTC),
        "language": "zh",
    }
    defaults.update(kwargs)
    normalizer = NewsNormalizer(db_session)
    article = normalizer.normalize(RawArticle(**defaults))
    db_session.commit()
    return article


def test_normalizer_converts_traditional_article(db_session) -> None:
    body = "台灣科技產業的最新資訊：這裡我們瞭解到軟體開發的趨勢正在改變。" * 15
    article = _normalize(
        db_session,
        title="台積電先進製程進展順利，為產業帶來新機會",
        body=body,
    )
    assert article is not None
    assert article.title == "台积电先进制程进展顺利，为产业带来新机会"
    assert article.body is not None
    assert has_traditional(article.body) is False
    assert "台湾科技产业的最新资讯" in article.body
    # full_content 从完整正文播种，也应是简体
    assert article.full_content is not None
    assert has_traditional(article.full_content) is False


def test_normalizer_keeps_simplified_article(db_session) -> None:
    body = "这是一篇简体中文资讯正文，讨论市场发展趋势和解决方案。" * 5
    article = _normalize(
        db_session,
        url="https://example.com/articles/simp-1",
        title="简体中文标题：市场发展稳定",
        body=body,
    )
    assert article is not None
    assert article.title == "简体中文标题：市场发展稳定"
    assert article.body == body


def test_normalizer_skips_non_chinese_article(db_session) -> None:
    # 非 zh 文章即便正文含繁体字（例如日文/英文源引用），也不转换
    body = "English article quoting 繁體資訊 verbatim for context. " * 5
    article = _normalize(
        db_session,
        source="global_rss",
        url="https://example.com/articles/en-1",
        title="English headline 繁體",
        body=body,
        language="en",
        market="us",
    )
    assert article is not None
    assert article.title == "English headline 繁體"
    assert article.body == body


def test_normalizer_converts_body_derived_from_body_html(db_session) -> None:
    """只有 body_html 时，strip 出来的正文同样要转简体。"""
    html = "<p>這裡是繁體正文的第一段，內容足夠長。</p>" * 5
    article = _normalize(
        db_session,
        url="https://example.com/articles/trad-html-1",
        title="繁體標題這裡",
        body=None,
        body_html=html,
    )
    assert article is not None
    assert article.body is not None
    assert "这里是繁体正文的第一段" in article.body
    assert has_traditional(article.body) is False


def test_content_fetcher_converts_traditional_full_content(db_session) -> None:
    """补抓回来的繁体正文在写入 full_content 前转简体。"""
    article = _normalize(
        db_session,
        url="https://example.com/articles/trad-fetch-1",
        title="繁體補抓標題這裡",
        body="短摘要。",  # 短 blurb → full_content 为 None，走补抓
    )
    assert article is not None and article.full_content is None

    trad_md = (
        "台灣半導體產業的最新動態，這裡我們可以看到先進製程的發展趨勢，"
        "為整個供應鏈帶來深遠的影響與變化，業界專家表示後續值得持續觀察。"
    ) * 3

    with (
        patch.object(ContentFetcher, "_fetch_html", return_value="<html></html>"),
        patch(
            "app.services.news.content_fetcher._extract_with_trafilatura",
            return_value=trad_md,
        ),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    db_session.refresh(article)
    assert article.full_content is not None
    assert has_traditional(article.full_content) is False
    assert "台湾半导体产业的最新动态" in article.full_content


def test_content_fetcher_keeps_non_chinese_full_content(db_session) -> None:
    """英文文章补抓结果不经过转换。"""
    article = _normalize(
        db_session,
        source="global_rss",
        url="https://example.com/articles/en-fetch-1",
        title="English headline",
        body="Short blurb.",
        language="en",
        market="us",
    )
    assert article is not None and article.full_content is None

    en_md = (
        "This is a full English article body with enough length to pass the "
        "minimum body threshold after deterministic cleaning. 繁體引用保留。"
    ) * 3

    with (
        patch.object(ContentFetcher, "_fetch_html", return_value="<html></html>"),
        patch(
            "app.services.news.content_fetcher._extract_with_trafilatura",
            return_value=en_md,
        ),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    db_session.refresh(article)
    assert article.full_content is not None
    assert "繁體引用保留" in article.full_content  # 未被转换
