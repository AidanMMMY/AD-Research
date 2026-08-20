"""Daily Digest 生成层测试（2026-08-03，B3）。

Coverage:
  - 正常路径：6 章节 + 1 次摘要调用拼装全文，status=success，
    6 个 ## 标题齐全，sections_json 全 success。
  - 单节连败（3 次尝试全挂）→ 该节降级占位段、sections_json 记
    failed；仅 1 节失败时整体仍 success。
  - 两节失败 → 整体 partial。
  - provider 中文占位串（无 API key 时的占位文案）特判为失败，
    且不做无谓重试。
  - 摘要调用失败 → 第 1 节前 200 字兜底。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.digest import generator as gen_mod
from app.services.digest.context import DigestContext
from app.services.digest.generator import DigestGenerator
from app.services.digest.prompts import SECTION_FALLBACK_TEXT, SECTIONS

SHANGHAI = ZoneInfo("Asia/Shanghai")
REPORT_DATE = date(2026, 8, 3)

# 每节 420 字：全成功 6 节 ≈ 2600 字；即便 1 节失败换占位段仍 > 2000，
# 两种路径都落在 2000-8000 校验区间内
_SECTION_BODY = "本节分析内容。" * 60
_SUMMARY_TEXT = "今日结论：全球风险偏好回升，组合以不变应万变。"


class FakeProvider:
    """可编排的 fake LLM provider。

    fail_on: user prompt 含任一子串时抛异常（模拟持续故障）。
    placeholder_on: user prompt 含子串时返回无 key 占位文案。
    """

    model = "fake-model-v1"

    def __init__(self, fail_on: tuple[str, ...] = (), placeholder_on: tuple[str, ...] = ()):
        self.fail_on = fail_on
        self.placeholder_on = placeholder_on
        self.calls: list[str] = []

    def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
        user = messages[0]["content"]
        self.calls.append(user)
        if any(marker in user for marker in self.fail_on):
            raise RuntimeError("LLM down")
        if any(marker in user for marker in self.placeholder_on):
            return "AI 功能未配置，请设置 DEEPSEEK_API_KEY 后重试"
        if "【研报全文】" in user:  # 摘要调用
            return _SUMMARY_TEXT
        return _SECTION_BODY


@pytest.fixture
def no_sleep(monkeypatch):
    """退避等待归零，测试不等 2s/5s。"""
    monkeypatch.setattr(gen_mod, "_sleep", lambda _s: None)


@pytest.fixture
def ctx():
    start = datetime(2026, 8, 2, 6, 30, tzinfo=SHANGHAI)
    end = datetime(2026, 8, 3, 6, 30, tzinfo=SHANGHAI)
    return DigestContext(
        report_date=REPORT_DATE,
        window_start=start,
        window_end=end,
        facts={key: f"{key} 事实清单" for key in (
            "macro", "sector", "scores", "fund_flow",
            "news", "watchlist", "sentiment", "sellside",
        )},
    )


def _task_marker(spec) -> str:
    """只命中该节自身 prompt 的标记（前节摘要链里是 "- <标题>" 格式）。"""
    return f"【本节任务】{spec.title}"


def test_generate_success_assembly(ctx, no_sleep):
    provider = FakeProvider()
    result = DigestGenerator(provider=provider).generate(ctx)

    assert result.status == "success"
    assert result.title == "2026-08-03 每日综合研报"
    assert result.summary_md == _SUMMARY_TEXT
    assert result.llm_model == "fake-model-v1"
    # 6 次章节 + 1 次摘要
    assert len(provider.calls) == 7
    # content_md 只含 6 个 ## 章节，不内嵌 `# 标题` H1（标题唯一来源是
    # title 列；2026-08-21 前内嵌 H1 导致网页/邮件/TG/原生端四端双标题）
    assert not result.content_md.startswith("# ")
    assert result.content_md.startswith(f"## {SECTIONS[0].title}")
    assert result.title not in result.content_md.splitlines()[0]
    # 6 个 ## 标题齐全且按序（行首计数，含文档开头的第一节）
    assert len(gen_mod._SECTION_HEADING_RE.findall(result.content_md)) == 6
    for spec in SECTIONS:
        assert f"## {spec.title}" in result.content_md
    assert all(s["status"] == "success" for s in result.sections)
    # 第 2 节起的 user prompt 带前节摘要（连贯性）
    assert "【前序章节摘要" in provider.calls[1]


def test_single_section_failure_fallback(ctx, no_sleep):
    # 第 3 节的【本节任务】标记 → 该节每次尝试都抛错
    provider = FakeProvider(fail_on=(_task_marker(SECTIONS[2]),))
    result = DigestGenerator(provider=provider).generate(ctx)

    assert result.status == "success"  # 仅 1 节失败 < 2
    rec = result.sections[2]
    assert rec["status"] == "failed"
    assert SECTION_FALLBACK_TEXT in result.content_md
    # 该节尝试了 1+2 次：总调用 = 6 节 + 2 次重试 + 1 摘要 = 9
    assert len(provider.calls) == 9
    # 后续节仍生成（占位节也进前节摘要链）
    assert result.sections[3]["status"] == "success"


def test_two_sections_failed_partial(ctx, no_sleep):
    provider = FakeProvider(
        fail_on=(_task_marker(SECTIONS[1]), _task_marker(SECTIONS[3]))
    )
    result = DigestGenerator(provider=provider).generate(ctx)

    assert result.status == "partial"
    failed = [s["key"] for s in result.sections if s["status"] == "failed"]
    assert failed == [SECTIONS[1].key, SECTIONS[3].key]


def test_placeholder_treated_as_failure_without_retry(ctx, no_sleep):
    provider = FakeProvider(placeholder_on=(_task_marker(SECTIONS[0]),))
    result = DigestGenerator(provider=provider).generate(ctx)

    rec = result.sections[0]
    assert rec["status"] == "failed"
    # 占位串判失败后立即放弃：该节只调 1 次（总 7 次 = 6 节 + 1 摘要）
    assert len(provider.calls) == 7
    assert SECTION_FALLBACK_TEXT in result.content_md


def test_summary_failure_fallback_to_section1_head(ctx, no_sleep):
    provider = FakeProvider(fail_on=("【研报全文】",))
    result = DigestGenerator(provider=provider).generate(ctx)

    assert result.summary_md == _SECTION_BODY[:200]
    # 摘要 1+2 次尝试全挂：6 节 + 3 次摘要尝试 = 9 次调用
    assert len(provider.calls) == 9


def test_total_length_out_of_range_partial(ctx, no_sleep):
    """全文 < 2000 字 → partial（校验逻辑兜底）。"""

    class TinyProvider(FakeProvider):
        def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
            user = messages[0]["content"]
            self.calls.append(user)
            if "【研报全文】" in user:
                return "短摘要"
            return "很短。"  # 6 节 × 3 字 ≪ 2000

    result = DigestGenerator(provider=TinyProvider()).generate(ctx)
    assert result.status == "partial"


def test_leading_duplicate_heading_stripped(ctx, no_sleep):
    """LLM 在正文开头复读章节标题 → 拼装前剥掉，页面不出现双标题。

    （2026-08-03 ECS 首跑实测：第 2/5 节各重复一次 `## 标题`，
    且导致 heading 计数 8 != 6 误判 partial。）
    """

    class EchoProvider(FakeProvider):
        def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
            user = messages[0]["content"]
            self.calls.append(user)
            if "【研报全文】" in user:
                return _SUMMARY_TEXT
            return f"## 某章节标题\n\n{_SECTION_BODY}"

    result = DigestGenerator(provider=EchoProvider()).generate(ctx)

    assert result.status == "success"
    # 6 个章节标题各恰好出现一次（拼装层加的），无复读残留
    for spec in SECTIONS:
        assert result.content_md.count(f"## {spec.title}") == 1


def test_extra_llm_subheadings_do_not_fail_heading_check(ctx, no_sleep):
    """正文自带 ## 子标题属合法输出，heading 校验只查下限（≥6）。"""

    class SubProvider(FakeProvider):
        def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
            user = messages[0]["content"]
            self.calls.append(user)
            if "【研报全文】" in user:
                return _SUMMARY_TEXT
            return f"{_SECTION_BODY}\n\n## 深入分析\n\n{_SECTION_BODY}"

    result = DigestGenerator(provider=SubProvider()).generate(ctx)
    assert result.status == "success"
    # 6 章节 + 6 个正文自带子标题 = 12 个行首 ##（含文档开头的第一节）
    assert len(gen_mod._SECTION_HEADING_RE.findall(result.content_md)) == 12


def test_first_section_heading_at_doc_start_counts(ctx, no_sleep):
    """首节 `##` 位于文档开头时 heading 校验仍计 6 个——防退回
    count("\\n## ") 的数法（会漏掉没有前置换行的第一节 → 永远 partial）。"""

    result = DigestGenerator(provider=FakeProvider()).generate(ctx)

    # 字符串数法只能数到 5 个（首节前面没有 \n），正则行首数法才是 6
    assert result.content_md.count("\n## ") == 5
    assert len(gen_mod._SECTION_HEADING_RE.findall(result.content_md)) == 6
    assert result.status == "success"
