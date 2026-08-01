"""Unit tests for the ContentFetcher tier-3 LLM extraction layer (2026-08-01).

Covered behaviour:

1. **真页面判定** — ``_looks_like_real_page`` accepts a normal 200
   article page and rejects captcha shells / anti-bot interstitials /
   thin pages; ``_fetch_html`` already filters HTTP >= 400 (e.g. 403).
2. **HTML 预处理** — ``_preprocess_html_for_llm`` strips
   script/style/nav/footer noise, prefers the ``<article>`` block and
   truncates to ~12000 chars.
3. **端到端** — tier-1 fails + Jina breaker open + direct 200 real
   page + mocked provider → success with ``\n\n`` paragraphs.
4. **输出校验** — NO_CONTENT / 过短 / 拒答前缀全部判负，不误标成功。
5. **门控** — Jina 正常可用或 ``LLM_EXTRACT_ENABLED=false`` 时 LLM
   层零调用。

Mock 风格参照同目录 ``test_content_fetcher.py``。
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
from app.services.news._model_loader import NewsArticle, load_news_models
from app.services.news.content_fetcher import (
    ContentFetcher,
    _extract_with_llm,
    _JinaError,
    _LLM_MAX_INPUT_CHARS,
    _looks_like_real_page,
    _preprocess_html_for_llm,
    _trip_jina_breaker,
)
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer

load_news_models()


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _seed_article(db_session) -> NewsArticle:
    normalizer = NewsNormalizer(db_session)
    raw = RawArticle(
        source="businesstoday_my",
        url="https://example.com/articles/llm-tier",
        title="某公司第二季度财报超预期",
        published_at=datetime.now(tz=UTC),
        body="x" * 200,
    )
    article = normalizer.normalize(raw)
    db_session.commit()
    assert article is not None and article.id is not None
    return article


def _real_article_html(title: str, n_paras: int = 24) -> str:
    """一页"真文章页"：剥标签后可见文本远超 1500 字符。"""
    para = (
        "这是一段足够长的正文内容，用来模拟真实财经资讯页面的可见文本，"
        "包含公司基本面、行业格局与管理层表态等常见段落信息。"
    )
    paras = "".join(
        f"<p>{para}（第{i}段的差异化收尾内容，避免段落去重。）</p>"
        for i in range(n_paras)
    )
    return (
        "<html><head><title>t</title>"
        "<script>var tracker = 1;</script>"
        "<style>.a{color:red}</style></head><body>"
        "<nav><a href='/'>首页</a><a href='/nav'>导航菜单</a></nav>"
        f"<article><h1>{title}</h1>{paras}</article>"
        "<footer><p>相关阅读</p><p>免责声明</p></footer>"
        "</body></html>"
    )


class _FakeProvider:
    """Minimal stand-in for ``LLMProvider`` with a call counter."""

    def __init__(self, output: str, available: bool = True) -> None:
        self._output = output
        self.is_available = available
        self.calls = 0

    def complete(self, prompt, system=None, max_tokens=1024, temperature=0.7):
        self.calls += 1
        return self._output


_LLM_BODY = (
    "财报显示，该公司第二季度营收同比增长百分之十八，超出市场此前一致预期，"
    "主要得益于核心业务线的强劲表现与严格的成本控制措施，毛利率环比基本持平，"
    "经营性现金流创下上市以来同期新高，资产负债表进一步夯实，为后续扩张预留了"
    "充足的安全边际。\n\n"
    "管理层在电话会议中表示，下半年将继续加大研发投入，并计划在欧洲市场推出"
    "三款新产品以扩大份额，同时维持全年营收与利润指引不变，强调对中长期需求"
    "前景保持乐观态度，并将持续推进供应链多元化布局。\n\n"
    "分析师指出，尽管短期毛利率承压，但公司现金流状况稳健，分红政策保持不变，"
    "负债率持续下降，长期投资价值依然明确，多家机构在财报发布后维持买入评级，"
    "并小幅上调目标价，认为当前估值仍具吸引力。"
)


# ---------------------------------------------------------------------------
# 真页面判定
# ---------------------------------------------------------------------------

def test_real_page_accepts_normal_article() -> None:
    html = _real_article_html("正常标题")
    assert _looks_like_real_page(html) is True


@pytest.mark.parametrize(
    "marker",
    ["captcha", "DataDome", "Just a moment...", "Access Denied", "请完成安全验证"],
)
def test_real_page_rejects_anti_bot_shells(marker: str) -> None:
    # 反爬壳也可能很长（大段混淆 JS），光长不够，特征命中即拒。
    shell = (
        "<html><head><script>/* " + "x" * 5000 + " */</script></head>"
        f"<body><div>{marker}</div><p>verify to continue</p></body></html>"
    )
    assert _looks_like_real_page(shell) is False


def test_real_page_rejects_thin_page() -> None:
    html = "<html><body><p>" + "短文本。" * 100 + "</p></body></html>"
    assert _looks_like_real_page(html) is False  # 可见文本 400 < 1500


def test_real_page_rejects_none_and_empty() -> None:
    assert _looks_like_real_page(None) is False
    assert _looks_like_real_page("") is False


def test_fetch_html_returns_none_on_403() -> None:
    """HTTP 403（硬反爬）在直连层就被过滤，根本到不了真页面判定。"""
    fetcher = ContentFetcher.__new__(ContentFetcher)
    resp = SimpleNamespace(status_code=403, text="<html>Access Denied</html>")
    with patch(
        "app.services.news.content_fetcher.httpx.get", return_value=resp
    ):
        assert fetcher._fetch_html("https://example.com/x") is None


# ---------------------------------------------------------------------------
# HTML 预处理
# ---------------------------------------------------------------------------

def test_preprocess_strips_noise_and_prefers_article() -> None:
    html = _real_article_html("标题")
    text = _preprocess_html_for_llm(html)
    assert "正文内容" in text
    assert "tracker" not in text  # script 整块剔除
    assert "color:red" not in text  # style 剔除
    assert "导航菜单" not in text  # nav 剔除
    assert "免责声明" not in text  # footer 剔除


def test_preprocess_truncates_to_cap() -> None:
    big = "<html><body><article><p>" + "长" * 20000 + "</p></article></body></html>"
    text = _preprocess_html_for_llm(big)
    assert len(text) <= _LLM_MAX_INPUT_CHARS


# ---------------------------------------------------------------------------
# LLM 输出校验（直接调 _extract_with_llm）
# ---------------------------------------------------------------------------

def _long_page_text() -> str:
    return "页面正文句子，混有导航与推广噪音。" * 60  # ~1020 字符


def test_llm_rejects_no_content() -> None:
    with patch(
        "app.services.llm.get_llm_provider",
        return_value=_FakeProvider("NO_CONTENT"),
    ):
        assert _extract_with_llm(_long_page_text(), "标题") is None


def test_llm_rejects_too_short_output() -> None:
    short = "这一段输出虽然超过了八十字的旧阈值，但不足二百字的新下限，一律判负。"
    with patch(
        "app.services.llm.get_llm_provider",
        return_value=_FakeProvider(short),
    ):
        assert _extract_with_llm(_long_page_text(), "标题") is None


@pytest.mark.parametrize("prefix", ["抱歉，我无法从该页面提取正文。", "无法识别正文内容。"])
def test_llm_rejects_refusal_prefix(prefix: str) -> None:
    output = prefix + "后续补长。" * 100
    with patch(
        "app.services.llm.get_llm_provider",
        return_value=_FakeProvider(output),
    ):
        assert _extract_with_llm(_long_page_text(), "标题") is None


def test_llm_accepts_valid_body() -> None:
    with patch(
        "app.services.llm.get_llm_provider",
        return_value=_FakeProvider(_LLM_BODY),
    ):
        result = _extract_with_llm(_long_page_text(), "标题")
    assert result is not None
    assert "财报显示" in result


# ---------------------------------------------------------------------------
# 端到端
# ---------------------------------------------------------------------------

def _llm_tier_patches(html, provider):
    return (
        patch.object(ContentFetcher, "_fetch_html", return_value=html),
        patch(
            "app.services.news.content_fetcher._extract_with_trafilatura",
            return_value=None,
        ),
        patch("app.services.llm.get_llm_provider", return_value=provider),
    )


def test_end_to_end_success_when_jina_breaker_open(db_session) -> None:
    """tier-1 失败 + Jina 断路器开 + 直连 200 真页面 → LLM 层提取成功。"""
    article = _seed_article(db_session)
    provider = _FakeProvider(_LLM_BODY)
    _trip_jina_breaker(402, "")  # 余额耗尽 → 断路器开 1h（conftest 自动复位）

    p_html, p_traf, p_llm = _llm_tier_patches(
        _real_article_html(article.title), provider
    )
    with p_html, p_traf, p_llm:
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert provider.calls == 1
    assert result.content is not None
    assert "\n\n" in result.content  # 保留段落结构
    assert "财报显示" in result.content
    assert "维持买入评级" in result.content
    db_session.refresh(article)
    assert article.full_content is not None
    assert "\n\n" in article.full_content
    assert article.ai_cleanup_status == "cleaned"


def test_end_to_end_llm_tier_fetches_html_itself(db_session) -> None:
    """tier-1 没拿到 HTML 时，LLM 层自己补发一次直连请求。"""
    article = _seed_article(db_session)
    provider = _FakeProvider(_LLM_BODY)
    real_html = _real_article_html(article.title)
    # 第一次（tier-1）失败，第二次（LLM 层）拿到真页面。
    fetch_mock = patch.object(
        ContentFetcher, "_fetch_html", side_effect=[None, real_html]
    )
    _trip_jina_breaker(402, "")

    with (
        fetch_mock,
        patch(
            "app.services.news.content_fetcher._extract_with_trafilatura",
            return_value=None,
        ),
        patch("app.services.llm.get_llm_provider", return_value=provider),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert provider.calls == 1


@pytest.mark.parametrize(
    "output",
    ["NO_CONTENT", "太短", "抱歉，我无法提取该页面正文。" + "补长。" * 100],
    ids=["no_content", "too_short", "refusal_prefix"],
)
def test_end_to_end_bad_llm_output_marks_failed(db_session, output) -> None:
    """NO_CONTENT / 过短 / 拒答前缀 → 判负，绝不误标成功或污染缓存。"""
    article = _seed_article(db_session)
    provider = _FakeProvider(output)
    p_html, p_traf, p_llm = _llm_tier_patches(
        _real_article_html(article.title), provider
    )
    with (
        p_html,
        p_traf,
        p_llm,
        patch.object(
            ContentFetcher, "_call_jina", side_effect=_JinaError("jina down")
        ),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is False
    assert provider.calls == 1
    db_session.refresh(article)
    assert article.full_content is None
    assert article.ai_cleanup_status == "failed"


def test_llm_not_called_when_jina_works(db_session) -> None:
    """Jina 正常可用时不走 LLM 层（provider 零调用）。"""
    article = _seed_article(db_session)
    provider = _FakeProvider(_LLM_BODY)
    jina_md = (
        "Jina 兜底拿到的正文内容，长度足够通过最小正文阈值检查，"
        "用于验证 Jina 可用时不会触发 LLM 提取层，这里再补充一句更长的正文，"
        "确保确定性清洗之后依然稳定超过八十字符的最低门槛要求。"
    )
    with (
        patch.object(ContentFetcher, "_fetch_html", return_value="<html></html>"),
        patch(
            "app.services.news.content_fetcher._extract_with_trafilatura",
            return_value=None,
        ),
        patch.object(ContentFetcher, "_call_jina", return_value=jina_md),
        patch(
            "app.services.llm.get_llm_provider", return_value=provider
        ) as provider_factory,
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    provider_factory.assert_not_called()
    assert provider.calls == 0


def test_llm_skipped_when_env_disabled(db_session, monkeypatch) -> None:
    """LLM_EXTRACT_ENABLED=false → LLM 层整体跳过（provider 零调用）。"""
    monkeypatch.setenv("LLM_EXTRACT_ENABLED", "false")
    article = _seed_article(db_session)
    provider = _FakeProvider(_LLM_BODY)
    _trip_jina_breaker(402, "")

    p_html, p_traf, p_llm = _llm_tier_patches(
        _real_article_html(article.title), provider
    )
    with p_html, p_traf, p_llm:
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is False
    assert provider.calls == 0
