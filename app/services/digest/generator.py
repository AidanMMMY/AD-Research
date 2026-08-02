"""Daily Digest LLM 生成层（2026-08-03，B3）。

``DigestGenerator`` 把 :class:`DigestContext` 渲染成 6 章节 markdown
全文 + ≤200 字摘要：

- 每章节一次独立 LLM 调用（provider.chat），重试 2 次（退避 2s/5s，
  参照 research_service._call_llm_with_retry 的双attempt模式）。
- **中文占位串特判**：provider 无 API key 时不抛错、返回占位文案
  （"AI 功能未配置" / 提及 API_KEY 环境变量），照抄
  research_report_service.py:355-358 的检测逻辑判为失败。
- 单节最终失败 → 写降级占位段并记 sections_json；≥2 节 failed →
  整体 status=partial，仍出报仍推送。
- 摘要（第 7 次调用）失败 → 第 1 节前 200 字兜底。
- 落库前校验：总字数 2000-8000 + 6 个 ``##`` 标题齐全，不满足 →
  partial（不阻断，宁可降级出报也不让 06:30 窗口空报）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import sleep as _sleep
from typing import Any

from app.services.digest.context import DigestContext
from app.services.digest.prompts import (
    SECTION_FALLBACK_TEXT,
    SECTIONS,
    SYSTEM_PROMPT,
    SectionSpec,
    build_section_user_prompt,
    build_summary_user_prompt,
)

logger = logging.getLogger(__name__)

# 重试：首次失败后退避 2s，第二次失败后退避 5s，共 3 次尝试
_RETRY_BACKOFF_SECONDS = (2.0, 5.0)
# 单节 max_tokens：中文 1200 字 ≈ 1800+ tokens，留足余量
_SECTION_MAX_TOKENS = 3000
_SUMMARY_MAX_TOKENS = 600
# 落库前校验阈值。上限是给"失控超长"的保险丝，不是目标篇幅：
# 首跑实测 7.3k/8.6k（用户要 3000-5000 字，LLM 自然输出偏长属正常），
# 8000 会误杀 → 放宽到 12000。
MIN_TOTAL_CHARS = 2000
MAX_TOTAL_CHARS = 12000

# provider 无 key 时返回的中文占位串特征（不抛错，必须按内容识别）
_PLACEHOLDER_MARKERS = ("AI 功能未配置", "DEEPSEEK_API_KEY", "MINIMAX_API_KEY")


def _strip_leading_heading(text: str) -> str:
    """剥掉正文开头复读的标题行（``#``/``##`` 开头），章节标题由拼装层统一加。

    LLM 经常把 prompt 里的章节标题原样写在正文第一行；连续空行一并吃掉。
    正文中间出现的子标题不受影响。
    """
    lines = text.lstrip().splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


@dataclass
class DigestResult:
    """生成层产出（service 落库用）。"""

    title: str
    content_md: str
    summary_md: str
    status: str  # "success" | "partial"
    llm_model: str | None = None
    sections: list[dict[str, Any]] = field(default_factory=list)


def _is_placeholder(text: str) -> bool:
    """识别 provider 无 key 时的占位文案（参照 research_report_service:355）。"""
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


class DigestGenerator:
    """分章节生成日报。provider 可注入（测试用 fake）。"""

    def __init__(self, provider: Any | None = None) -> None:
        if provider is None:
            from app.services.llm import get_llm_provider

            provider = get_llm_provider()
        self.provider = provider

    # ------------------------------------------------------------------
    # 单次调用（重试 + 占位串特判）
    # ------------------------------------------------------------------

    def _call_llm(self, user_prompt: str, max_tokens: int) -> str | None:
        """调用 LLM，最多 1+2 次尝试；失败/占位串返回 None。"""
        for attempt in range(1 + len(_RETRY_BACKOFF_SECONDS)):
            try:
                content = self.provider.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=SYSTEM_PROMPT,
                    max_tokens=max_tokens,
                )
                if not content or not content.strip():
                    logger.warning("digest LLM empty content (attempt %d)", attempt + 1)
                elif _is_placeholder(content):
                    # 无 API key 的占位文案——重试无意义，直接判失败
                    logger.info("digest LLM: no API key configured, treating as failed")
                    return None
                else:
                    return content.strip()
            except Exception as exc:  # noqa: BLE001 - LLM 调用各种网络/限流异常
                logger.warning(
                    "digest LLM attempt %d failed: %s", attempt + 1, exc
                )
            if attempt < len(_RETRY_BACKOFF_SECONDS):
                _sleep(_RETRY_BACKOFF_SECONDS[attempt])
        return None

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def generate(self, ctx: DigestContext) -> DigestResult:
        """生成 6 章节 + 摘要，返回 DigestResult（不抛 LLM 异常）。"""
        window_text = (
            f"{ctx.window_start.strftime('%Y-%m-%d %H:%M')} 至 "
            f"{ctx.window_end.strftime('%Y-%m-%d %H:%M')}（北京时间）"
        )
        title = f"{ctx.report_date.strftime('%Y-%m-%d')} 每日综合研报"

        section_records: list[dict[str, Any]] = []
        bodies: list[tuple[SectionSpec, str, bool]] = []  # (spec, text, ok)
        prev_summaries: list[tuple[str, str]] = []

        for spec in SECTIONS:
            user_prompt = build_section_user_prompt(
                spec, ctx.facts, ctx.degraded, prev_summaries, window_text
            )
            content = self._call_llm(user_prompt, _SECTION_MAX_TOKENS)
            ok = content is not None
            text = content if ok else SECTION_FALLBACK_TEXT
            # LLM 有时会在正文开头复读章节标题（首跑实测第 2/5 节各重复
            # 一次），拼装前剥掉开头的标题行，避免页面上出现双标题。
            if ok:
                text = _strip_leading_heading(text)
            bodies.append((spec, text, ok))
            section_records.append(
                {
                    "key": spec.key,
                    "title": spec.title,
                    "status": "success" if ok else "failed",
                    "chars": len(text),
                }
            )
            # 前节 100 字摘要供下一节保持连贯（失败节也带，标注占位）
            brief = text[:100] if ok else "（本节生成失败）"
            prev_summaries.append((spec.title, brief))

        # 拼装全文：# 标题 + 6 个 ## 章节
        parts = [f"# {title}"]
        for spec, text, _ok in bodies:
            parts.append(f"## {spec.title}\n\n{text}")
        content_md = "\n\n".join(parts)

        # 第 7 次调用：≤200 字摘要；失败 → 第 1 节前 200 字兜底
        summary = self._call_llm(
            build_summary_user_prompt(content_md), _SUMMARY_MAX_TOKENS
        )
        if not summary:
            first_body = bodies[0][1]
            summary = first_body[:200]
            logger.info("digest summary LLM failed; fallback to section-1 head")

        # 状态判定：≥2 节失败 → partial；字数/标题校验不过 → partial
        failed_count = sum(1 for _s, _t, ok in bodies if not ok)
        status = "success"
        if failed_count >= 2:
            status = "partial"
        # 标题校验：6 个章节标题由上方拼装保证必含；LLM 正文可能自带
        # ## 子标题（首跑实测 8 个），所以只查下限不查精确相等。
        heading_count = content_md.count("\n## ")
        total_chars = len(content_md)
        if heading_count < len(SECTIONS):
            logger.warning(
                "digest heading check failed: %d < %d", heading_count, len(SECTIONS)
            )
            status = "partial"
        if not (MIN_TOTAL_CHARS <= total_chars <= MAX_TOTAL_CHARS):
            logger.warning("digest length check failed: %d chars", total_chars)
            status = "partial"

        llm_model = getattr(self.provider, "model", None) or type(
            self.provider
        ).__name__

        return DigestResult(
            title=title,
            content_md=content_md,
            summary_md=summary,
            status=status,
            llm_model=llm_model,
            sections=section_records,
        )
