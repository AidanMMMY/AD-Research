"""Batch crawler for Chinese independent blogs & commentary sites (2026-07-30).

Why this exists
---------------
Fifth wave of the 资讯源扩充 push — the last mile of the ">=100 中文圈
独立思考资讯源" goal (D1). Previous waves in this push: WeChat batch 3
(``wechat3_*``, 22 accounts) and Chinese podcasts (``zhx_*``, 40 shows).
This wave covers **Chinese-language blogs, independent commentary
sites, Chinese international media and curated community feeds** — the
"blog" channel the goal explicitly asked for.

Selection rule (same spirit as the earlier waves)
-------------------------------------------------
* Independent voices first: 酷壳 (陈皓), MacTalk (池建强), 异次元,
  小众软件, 标点符, 爱思想, 雪球热帖 etc. — personal/独立 editorial
  judgement, not corporate-brand PR.
* Still publishing: every feed below was live-verified from the
  production ECS on 2026-07-29/30 with a browser User-Agent (plain
  curl UA gets 403 on most CN sites) — HTTP 200, valid RSS/Atom,
  newest item within 14 days, except 喵神 onevcat (monthly cadence,
  newest 2026-07-06, kept with an explicit note, same precedent as the
  monthly podcasts in ``zh_multi_batch``).
* Native RSS/Atom only — no RSSHub (public instances unreachable from
  the production network, established in the podcast wave).

Rejections worth remembering (verified dead/stale from ECS 2026-07-30)
---------------------------------------------------------------------
* 可能吧 kenengba (2026-04), 善用佳软 xbeta (2025-05), t9t 透明创业
  (2025-11), frankcui cnblogs (2025-10), 反斗限免 apprcn (2026-04),
  V2方圆 v2fy (2026-06) — stale, dropped.
* IT之家 / Solidot — alive but **already covered** by
  ``global_rss_batch.py`` rows 174/177; excluded to keep zero overlap.
* BBC中文 — ONLY ``/zhongwen/simp/index.xml`` is fresh; the world/
  china/business/science sub-feeds are stale since 2011-2014.
* 煎蛋 / 极客公园 / 品玩 / 果壳 / 一财 / 华尔街见闻 / 智通 / 联合早报
  / HK01 / 东森 / 中央社 — no working native RSS from ECS.
* ForesightNews / Odaily / 优设 / T客邦 / 数位时代 / 天下杂志 —
  ``/rss``/``/feed`` paths return HTML (SPA or Cloudflare), not feeds.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``zhb_{slug}`` — own namespace alongside ``wechat_*``, ``indie_*``,
  ``global_*``, ``gind_*``, ``asen_*`` and ``zhx_*``.
* **Batches restart at "a"**: the job namespace ``news_zhb_*`` is
  unique, so this table is sliced into batches ``a``-``d`` of <=10.
* **Market/language**: Chinese sources are ``cn_a``/``zh``; the two
  crypto outlets (動區動趨 / 桑幣區識) are ``crypto``/``zh``; the two
  English-on-China publications (Sixth Tone / What's on Weibo) are
  ``cn_a``/``en`` — ``_GLOBAL_MARKETS`` whitelist is
  ``(cn_a, us, crypto)``, and English rows flow through the
  auto-translate pipeline that is already live.
* **No LLM marketing filter**: curated editorial voices, same
  precedent as every earlier batch wave — the scheduler job writes
  directly after fetch, keeping LLM cost flat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language). source = "zhb_{slug}".
ZH_BLOG_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 独立博客 / 个人评论（独立思考核心） ──
    ("coolshell", "酷壳 CoolShell", "https://coolshell.cn/feed", "cn_a", "zh"),
    ("macshuo", "MacTalk 池建强", "https://macshuo.com/?feed=rss2", "cn_a", "zh"),
    ("iplaysoft", "异次元软件世界", "https://www.iplaysoft.com/feed", "cn_a", "zh"),
    ("appinn", "小众软件", "https://www.appinn.com/feed/", "cn_a", "zh"),
    ("biaodianfu", "标点符", "https://www.biaodianfu.com/feed", "cn_a", "zh"),
    ("techug", "技术乌托邦", "https://www.techug.com/feed", "cn_a", "zh"),
    ("aisixiang", "爱思想", "https://www.aisixiang.com/rss", "cn_a", "zh"),
    ("xueqiuhots", "雪球热帖", "https://www.xueqiu.com/hots/topic/rss", "cn_a", "zh"),
    # onevcat 喵神：月更高质量 iOS 开发博客，最新 2026-07-06，明确保留
    ("onevcat", "OneV's Den 喵神", "https://www.onevcat.com/feed.xml", "cn_a", "zh"),
    # ── 中文聚合 / 垂直媒体 ──
    ("cnblogs", "博客园", "https://www.cnblogs.com/rss", "cn_a", "zh"),
    ("gcores", "机核", "https://www.gcores.com/rss", "cn_a", "zh"),
    ("cnbeta", "cnBeta", "https://www.cnbeta.com.tw/backend.php", "cn_a", "zh"),
    ("digitaling", "数英", "https://www.digitaling.com/rss", "cn_a", "zh"),
    ("oschina", "开源中国", "https://www.oschina.net/news/rss", "cn_a", "zh"),
    ("qbitai", "量子位", "https://www.qbitai.com/feed", "cn_a", "zh"),
    ("it199", "199IT 互联网数据", "https://www.199it.com/feed", "cn_a", "zh"),
    ("yunyingpai", "运营派", "https://www.yunyingpai.com/feed", "cn_a", "zh"),
    # ── 中文国际媒体（深度评论） ──
    ("ftchinese", "FT中文网", "https://www.ftchinese.com/rss/news", "cn_a", "zh"),
    ("rfichinese", "RFI 中文", "https://www.rfi.fr/cn/rss", "cn_a", "zh"),
    ("dwchinese", "德国之声中文", "https://rss.dw.com/xml/rss-chi-all", "cn_a", "zh"),
    # BBC中文：仅 simp 主索引新鲜（子频道 2011-2014 停更，勿加）
    ("bbcchinese", "BBC 中文", "https://www.bbc.com/zhongwen/simp/index.xml", "cn_a", "zh"),
    ("theinitium", "端传媒", "https://theinitium.com/zh-hans/rss", "cn_a", "zh"),
    # ── 台湾科技 / 英文视角看中国 ──
    ("technews", "科技新报", "https://technews.tw/feed", "cn_a", "zh"),
    ("ithometw", "iThome 台湾", "https://www.ithome.com.tw/rss", "cn_a", "zh"),
    ("sixthtone", "Sixth Tone", "https://www.sixthtone.com/rss", "cn_a", "en"),
    ("whatsonweibo", "What's on Weibo", "https://www.whatsonweibo.com/feed", "cn_a", "en"),
    # ── 中文加密货币 ──
    ("blocktempo", "動區動趨", "https://www.blocktempo.com/rss", "crypto", "zh"),
    ("zombit", "桑幣區識", "https://www.zombit.info/rss", "crypto", "zh"),
    # ── 科学评论 ──
    ("pansci", "泛科学", "https://pansci.asia/feed", "cn_a", "zh"),
    # ── V2EX 社区精选（9 个官方 tab feed，2026-07-29 全部新鲜） ──
    ("v2exall", "V2EX 全部", "https://www.v2ex.com/feed/tab/all.xml", "cn_a", "zh"),
    ("v2extech", "V2EX 技术", "https://www.v2ex.com/feed/tab/tech.xml", "cn_a", "zh"),
    ("v2excreative", "V2EX 创意", "https://www.v2ex.com/feed/tab/creative.xml", "cn_a", "zh"),
    ("v2explay", "V2EX 好玩", "https://www.v2ex.com/feed/tab/play.xml", "cn_a", "zh"),
    ("v2exapple", "V2EX Apple", "https://www.v2ex.com/feed/tab/apple.xml", "cn_a", "zh"),
    ("v2exjobs", "V2EX 酷工作", "https://www.v2ex.com/feed/tab/jobs.xml", "cn_a", "zh"),
    ("v2exdeals", "V2EX 交易", "https://www.v2ex.com/feed/tab/deals.xml", "cn_a", "zh"),
    ("v2excity", "V2EX 城市", "https://www.v2ex.com/feed/tab/city.xml", "cn_a", "zh"),
    ("v2exqna", "V2EX 问与答", "https://www.v2ex.com/feed/tab/qna.xml", "cn_a", "zh"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcd"  # job namespace news_zhb_* is unique, so keys restart at "a".
ZH_BLOG_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: ZH_BLOG_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if ZH_BLOG_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (see docs/dev-notes/20260730-zh-blog-batch-integration.md).
ZH_BLOG_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_zhb_{key}_60m", f"中文博客 {key.upper()} 组", key)
    for key in ZH_BLOG_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class ZhBlogBatchCrawler:
    """Sequentially crawl one batch of Chinese blog RSS/Atom feeds.

    Mirrors :class:`ZhMultiBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: plain
    curl-style UAs get 403 on most CN sites (verified from ECS).
    """

    def __init__(
        self,
        batch_key: str,
        *,
        delay_seconds: float = 2.0,
        timeout_seconds: float = 20.0,
        max_items_per_feed: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._batch_key = batch_key
        self._delay = float(delay_seconds)
        self._timeout = float(timeout_seconds)
        self._max_items = int(max_items_per_feed)
        self._client = client

    @property
    def feeds(self) -> list[_Feed]:
        rows = ZH_BLOG_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, url=u, market=m, language=lang)
            for s, n, u, m, lang in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            },
        )
        try:
            out: list[RawArticle] = []
            for feed in self.feeds:
                try:
                    resp = await client.get(feed.url)
                    resp.raise_for_status()
                    out.extend(
                        parse_rss_items(
                            resp.text,
                            source=f"zhb_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "zh blog batch %s: feed %s failed: %s",
                        self._batch_key,
                        feed.slug,
                        exc,
                    )
                if self._delay > 0:
                    await asyncio.sleep(self._delay)
            return out
        finally:
            if owns:
                await client.aclose()
