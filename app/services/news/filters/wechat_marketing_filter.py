"""AI marketing filter for WeChat public-account posts.

The WeChat Official Account (公众号) content stream is dominated by two
kinds of pushes:

* Knowledge / analysis — 宏观评论、研报、行业研究、政策解读、读书笔记。
* Marketing / events — 研学计划、课程报名、直播预告、峰会邀请、付费推广。

The platform only wants the first bucket. This filter does a two-step
classification:

1. **Heuristic blocklist** — fast keyword scan. If any of
   :data:`DEFAULT_MARKETING_KEYWORDS` shows up in the title or first
   500 chars of the body, we drop the article immediately. This covers
   ~90% of the noise without paying for an LLM call.
2. **LLM reclassify** — borderline cases get a single-shot prompt to
   DeepSeek asking it to label the post as ``knowledge`` or
   ``marketing``. Results are cached for 24h in-process so we don't
   re-bill DeepSeek for the same article within a polling cycle.

The filter is **fail-open**: if DeepSeek returns garbage, times out, or
isn't configured, we keep the article (``is_knowledge=True``) so a
single transient outage doesn't wipe a feed. Operators can tighten
this later by flipping ``wechat_marketing_filter_llm_enabled`` in
settings.

Public API
----------
* :class:`WechatMarketingFilter` — the filter.
* :data:`DEFAULT_MARKETING_KEYWORDS` — exposed for tests / docs.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heuristic blocklist
# ---------------------------------------------------------------------------

# Matched case-insensitively as a substring of title or first 500 chars
# of body. Keep this list short — false positives on "课程" / "邀请" are
# acceptable (better to lose an article than to spam the feed).
DEFAULT_MARKETING_KEYWORDS: tuple[str, ...] = (
    # Programs / courses / events
    "研学计划", "研学营", "研学项目",
    "课程报名", "课程预告", "课程咨询", "课程购买",
    "直播预告", "直播回放", "直播预约", "直播课程",
    "峰会邀请", "论坛邀请", "论坛报名",
    "全球财富会", "全球财峰会",
    # Calls to action
    "扫码加入", "扫码报名", "扫码进群", "扫码关注",
    "席位预定", "席位剩余", "席位告急",
    "早鸟价", "限时优惠", "限时折扣", "原价",
    "优惠名额", "招生名额",
    "邀请函", "邀请您", "诚邀您",
    # Pure-sales phrasing
    "立即购买", "立即抢购", "点击购买", "点击咨询",
    "咨询客服", "添加微信", "添加好友",
    "内部活动", "私享会", "闭门会", "私董会",
    "知识星球", "星球会员",
    "免费领取", "限时领取", "限时免费",
    # Annual / seasonal marketing
    "年度盛典", "年终盛典", "跨年盛典",
    "发布会", "新品发布",
)


def _build_keyword_regex(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """Compile keywords into a single alternation regex.

    We don't anchor the pattern — substring match is fine because we
    only look at the title + first 500 chars of body. Special regex
    characters in the keywords (rare) are escaped.
    """
    escaped = [re.escape(k) for k in keywords]
    return re.compile("|".join(escaped), flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketingVerdict:
    """Outcome of :meth:`WechatMarketingFilter.classify`.

    Attributes
    ----------
    is_knowledge:
        ``True`` if the article should be persisted (knowledge content),
        ``False`` if it looks like marketing / events.
    reason:
        ``"keyword_blocklist"`` / ``"llm_marketing"`` / ``"llm_knowledge"``
        / ``"llm_error_fallthrough"`` / ``"empty_input"`` — handy for
        debugging and for the health page.
    confidence:
        ``0.0`` (heuristic only) up to ``1.0`` (LLM said yes/no with
        full conviction). Used purely for telemetry; doesn't gate the
        verdict itself.
    """

    is_knowledge: bool
    reason: str
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

# How long to keep LLM verdicts in memory. Articles in a 24h window
# dominate the dedup race anyway — reclassifying once a day per post is
# enough to keep the cache small.
_CACHE_TTL_SECONDS = 86_400

# DeepSeek system prompt — Chinese, opinionated, one-word output.
_LLM_SYSTEM_PROMPT = (
    "你是一位中文财经内容编辑，任务是判断一篇微信公众号文章是否"
    "属于「知识 / 分析」内容。\n"
    "判定标准：\n"
    "- knowledge=true：宏观分析、市场评论、研报、政策解读、行业研究、"
    "读书笔记、作者原创观点。\n"
    "- knowledge=false：营销活动、课程报名、会议 / 直播 / 峰会邀请、"
    "付费推广、内部活动、会员招募、销售导向内容。\n"
    "只输出 JSON，不要任何解释：{\"knowledge\": true|false, \"confidence\": 0.0_to_1.0}"
)


class WechatMarketingFilter:
    """Two-step WeChat content classifier.

    Parameters
    ----------
    llm_provider:
        An optional :class:`app.services.llm.base.LLMProvider`. When
        ``None`` we lazy-build a :class:`DeepSeekProvider` on first
        use. Pass a fake / mock in tests.
    keywords:
        Override the marketing keyword blocklist (default
        :data:`DEFAULT_MARKETING_KEYWORDS`).
    llm_enabled:
        Force-disable the LLM reclassify step even when ``DEEPSEEK_API_KEY``
        is set. Useful as a kill-switch.
    cache_ttl_seconds:
        In-process LLM verdict TTL. Default 24h.
    """

    def __init__(
        self,
        *,
        llm_provider: Any | None = None,
        keywords: tuple[str, ...] | None = None,
        llm_enabled: bool | None = None,
        cache_ttl_seconds: int = _CACHE_TTL_SECONDS,
    ) -> None:
        self._llm_provider_override = llm_provider
        self._keywords = tuple(keywords) if keywords else DEFAULT_MARKETING_KEYWORDS
        self._keyword_re = _build_keyword_regex(self._keywords)
        self._llm_enabled = llm_enabled
        self._cache_ttl = cache_ttl_seconds
        # Cache: hash(title|body[:500]) -> (verdict, expires_at_monotonic)
        self._cache: dict[str, tuple[MarketingVerdict, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        title: str | None,
        body: str | None,
    ) -> MarketingVerdict:
        """Return a verdict for the given article.

        Never raises. A blank title returns
        ``MarketingVerdict(False, "empty_input", 0.0)`` — there's
        nothing to keep.
        """
        title = (title or "").strip()
        body = (body or "").strip()
        if not title:
            return MarketingVerdict(False, "empty_input", 0.0)

        snippet = body[:500]
        haystack = f"{title}\n{snippet}"

        # 1) Heuristic blocklist — fastest path.
        match = self._keyword_re.search(haystack)
        if match:
            return MarketingVerdict(
                is_knowledge=False,
                reason="keyword_blocklist",
                confidence=0.95,
            )

        # 2) LLM reclassify (best-effort). Fail-open on error.
        verdict = self._classify_via_llm(title, snippet)
        return verdict

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cache_key(self, title: str, snippet: str) -> str:
        digest = hashlib.sha256(f"{title}\n{snippet}".encode("utf-8")).hexdigest()
        return f"wechat:filter:{digest[:32]}"

    def _classify_via_llm(self, title: str, snippet: str) -> MarketingVerdict:
        # Honor the kill-switch.
        if self._llm_enabled is False:
            return MarketingVerdict(True, "llm_disabled_knowledge", 0.5)
        # Honor the settings-level switch if it wasn't explicitly passed.
        if self._llm_enabled is None:
            try:
                from app.config import get_settings
                if not get_settings().wechat_marketing_filter_llm_enabled:
                    return MarketingVerdict(True, "llm_disabled_knowledge", 0.5)
            except Exception:  # pragma: no cover - settings unavailable in tests
                pass

        provider = self._get_llm_provider()
        if provider is None or not getattr(provider, "is_available", True):
            return MarketingVerdict(True, "llm_unavailable_fallthrough", 0.5)

        # Cache hit?
        cache_key = self._cache_key(title, snippet)
        cached = self._cache.get(cache_key)
        if cached is not None:
            verdict, expires_at = cached
            if expires_at > time.monotonic():
                return verdict
            # Expired — drop and reclassify.
            self._cache.pop(cache_key, None)

        # Build the prompt.
        prompt = (
            "标题: " + title + "\n"
            "摘要: " + (snippet or "(无摘要)") + "\n\n"
            "请按 system prompt 的 JSON 模式输出。"
        )

        try:
            raw = provider.complete(
                prompt=prompt,
                system=_LLM_SYSTEM_PROMPT,
                max_tokens=64,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "WeChat marketing filter: LLM call failed, fall through: %s", exc
            )
            return MarketingVerdict(True, "llm_error_fallthrough", 0.5)

        verdict = _parse_llm_verdict(raw)
        # Cache it. We cache *all* outcomes (including fallthrough) so a
        # repeated timeout doesn't loop on the same article.
        self._cache[cache_key] = (
            verdict,
            time.monotonic() + self._cache_ttl,
        )
        return verdict

    def _get_llm_provider(self) -> Any | None:
        if self._llm_provider_override is not None:
            return self._llm_provider_override
        try:
            from app.services.llm.deepseek_provider import DeepSeekProvider

            return DeepSeekProvider()
        except Exception:  # pragma: no cover - defensive
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Matches the first JSON object in the response, even if the model
# wraps it in markdown code fences or trailing prose.
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\"knowledge\"[^{}]*\}")


def _parse_llm_verdict(raw: str) -> MarketingVerdict:
    """Best-effort parse of the DeepSeek JSON reply.

    On any failure (no JSON, wrong shape, etc.) returns a
    ``llm_parse_error_fallthrough`` verdict that keeps the article so a
    transient bad response doesn't wipe a feed.
    """
    if not raw:
        return MarketingVerdict(True, "llm_parse_error_fallthrough", 0.5)

    candidate = raw.strip()
    match = _JSON_OBJECT_RE.search(candidate)
    json_blob = match.group(0) if match else candidate
    # Strip markdown fences if present.
    if json_blob.startswith("```"):
        json_blob = re.sub(r"^```(?:json)?\s*", "", json_blob)
        json_blob = re.sub(r"\s*```$", "", json_blob)

    try:
        import json
        data = json.loads(json_blob)
    except Exception:
        # Last-ditch: maybe the model wrote 'true' / 'false' bare.
        lowered = candidate.lower()
        if "false" in lowered and "knowledge" in lowered:
            return MarketingVerdict(False, "llm_marketing", 0.6)
        if "true" in lowered and "knowledge" in lowered:
            return MarketingVerdict(True, "llm_knowledge", 0.6)
        return MarketingVerdict(True, "llm_parse_error_fallthrough", 0.5)

    if not isinstance(data, dict):
        return MarketingVerdict(True, "llm_parse_error_fallthrough", 0.5)

    knowledge = data.get("knowledge")
    confidence_raw = data.get("confidence", 0.5)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    if isinstance(knowledge, bool):
        return MarketingVerdict(
            is_knowledge=knowledge,
            reason="llm_knowledge" if knowledge else "llm_marketing",
            confidence=confidence,
        )

    # String-typed truthy / falsy (some models do "true"/"false" as a string).
    if isinstance(knowledge, str):
        lowered = knowledge.strip().lower()
        if lowered in ("true", "yes", "1", "是", "知识", "分析"):
            return MarketingVerdict(True, "llm_knowledge", confidence)
        if lowered in ("false", "no", "0", "否", "营销", "推广"):
            return MarketingVerdict(False, "llm_marketing", confidence)

    return MarketingVerdict(True, "llm_parse_error_fallthrough", 0.5)