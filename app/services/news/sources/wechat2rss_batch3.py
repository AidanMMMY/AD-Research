"""Third batch of WeChat-OA crawlers (added 2026-07-29).

Why this exists
---------------
/goal wave 3: another >=40 WeChat Official Accounts with independent
voices — macro / strategy / industry research (this round explicitly
widened to pharma / consumer / new-energy / going-global / quant /
FICC), investment essays, business deep-dives and geo-economics
commentary — excluding state media, corporate PR, marketing and pure
news-aggregation accounts.

Honest yield: 22, not 40
------------------------
The two usable public wechat2rss mirrors were already mined by the
first two waves:

* ``wechat2rss.xlab.app`` (395 accounts, ~326 security-research):
  re-fetched the full list on 2026-07-29 — zero additions since the
  2026-07-27 snapshot, and every remaining account is security /
  corporate-dev / dead / literature. Yield: **0**.
* ``wechat2rss.bestblogs.dev`` (375 accounts, OPML re-downloaded
  2026-07-29): after removing wave-1/wave-2/wewe-rss overlaps, 260
  remain, of which ~240 are corporate dev/AI-vendor PR, sports,
  lifestyle, design, course-marketing or aggregation. 45 were
  short-listed and probed; 23 failed the bar (staleness, clickbait,
  advertorial density, same-org duplicates). Yield: **22**.

Other channels re-checked on 2026-07-29 and still unusable:
feeddd.org (dead), werss.app (dead), 今天看啥 (login-walled),
wechatrss.waytomaster.com (login-walled, no public directory),
瓦斯阅读 (no RSS), RSSHub newrank route (unstable, off-channel),
wewe-rss self-host (token still dead — needs user re-scan).
Per the task discipline ("候选不足 40 达标就实报数量，不凑数")
this batch ships the 22 verified feeds only.

Every feed below was verified from the production ECS on 2026-07-29:
HTTP 200, ``items = 10``, full body in ``content:encoded``, newest
item within 30 days. 5 short-listed candidates were dropped after
verification — 心智工具箱 (stale 06-02), iamsujie (stale 06-26),
语言即世界 (stale 05-11), AI科技评论 (雷峰网 same-org dup +
recruitment/ad posts), 硅基观察Pro (clickbait titles), 丁香医生
(advertorial density, consumer-health not industry research). See
``docs/dev-notes/20260729-wechat-batch3.md`` for the evidence table.

Design notes
------------
* **Table-driven**: one row per account
  ``(slug, display_name, category, feed_url)``; ``source`` becomes
  ``wechat_{slug}`` — the same namespace as waves 1/2 and the
  wewe-rss feeds. ``category`` is one of ``macro`` / ``strategy`` /
  ``industry`` / ``tech`` / ``business`` (documentation + tests only).
* **Batched jobs**: the table is sliced into
  :data:`WECHAT3_BATCHES` groups of <=8 feeds (keys ``w3a`` …);
  :data:`WECHAT3_BATCH_JOBS` carries the scheduler metadata
  (``news_wechat3_{batch}_60m``) so ``scheduler_jobs.py`` can
  materialize one hourly job per group without duplicating the table.
* **No overlap**: slugs, display names and feed hashes are disjoint
  from ``wechat2rss_batch.WECHAT2RSS_FEEDS``,
  ``wechat2rss_batch2.WECHAT2B_FEEDS``, the single-feed crawlers
  (``wechat_maobidao`` / ``wechat_sixianggangyin`` / ``wechat_zeping``)
  and all 15 wewe-rss accounts (enforced by tests).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

#: Mirror serving every feed in this batch (for tests / docs only —
#: each row already carries its full URL). The xlab mirror was
#: re-checked on 2026-07-29 and yielded zero qualified accounts.
MIRROR_BESTBLOGS = "https://wechat2rss.bestblogs.dev"

CATEGORIES = ("macro", "strategy", "industry", "tech", "business")

# (slug, display_name, category, feed_url). source = "wechat_{slug}".
WECHAT3_FEEDS: list[tuple[str, str, str, str]] = [
    # ── 宏观经济 / 地缘 (macro) ──
    ("diqiuzhishiju", "地球知识局", "macro",
     "https://wechat2rss.bestblogs.dev/feed/c8500fccbf17324e8e865ef13e1fe972c946ee7c.xml"),
    ("nanfengchuang", "南风窗", "macro",
     "https://wechat2rss.bestblogs.dev/feed/ae718c0cb66cf853eb83a435dc99341942948878.xml"),
    # ── 投资策略 / 思维 (strategy) ──
    ("lxiansheng", "L先生说", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/31c7fb6f7959a5ff90ae997b536e78b8b3f23321.xml"),
    ("xinmuweibi", "心木微笔", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/c4be152d8568cb0de06dbf97f164579b80fe614f.xml"),
    # ── 行业研究 (industry) ──
    ("dalirushan", "大力如山", "industry",
     "https://wechat2rss.bestblogs.dev/feed/e725f176952cae77a5af36a3384eceb4db9b8450.xml"),
    ("xingqiuyanjiusuo", "星球研究所", "industry",
     "https://wechat2rss.bestblogs.dev/feed/1626938486da8a55e24292d98188a33aa4a6050b.xml"),
    ("feifanchanyan", "非凡产研", "industry",
     "https://wechat2rss.bestblogs.dev/feed/fb99bd76d9b9a99155d2f9e03868d29eb43ea3fb.xml"),
    ("youxiputao", "游戏葡萄", "industry",
     "https://wechat2rss.bestblogs.dev/feed/6aadbb03d02c59093f48afa5723fa2c44d1a81dc.xml"),
    ("houlang", "后浪研究所", "industry",
     "https://wechat2rss.bestblogs.dev/feed/7abc9d02f335cf08a49a4957041e5a51da5883d1.xml"),
    # ── 科技评论 (tech) ──
    ("xiaozhongxiaoxi", "小众消息", "tech",
     "https://wechat2rss.bestblogs.dev/feed/317e436475d34a5cfdfa094e1b2cc7085413903d.xml"),
    ("zpotentials", "Z Potentials", "tech",
     "https://wechat2rss.bestblogs.dev/feed/c47f4bc00ea912c37b6e23b22b146db0e85b3e19.xml"),
    ("wangjiwei", "王吉伟", "tech",
     "https://wechat2rss.bestblogs.dev/feed/9ebca45070e74a337b19ca8ff87490194a2b4060.xml"),
    ("kuaidaoqingyi", "快刀青衣", "tech",
     "https://wechat2rss.bestblogs.dev/feed/b528adeff7b27026e7a69163ad77f262d99b33a4.xml"),
    ("zhishifenzi", "知识分子", "tech",
     "https://wechat2rss.bestblogs.dev/feed/e32f65752d69e5ddab37891db2849a93bde4447b.xml"),
    ("ailianjinshu", "AI炼金术", "tech",
     "https://wechat2rss.bestblogs.dev/feed/4915f3747653bbb9c7975323c11b768d2b9cd6c9.xml"),
    # ── 商业深度 (business) ──
    ("guigu101", "硅谷101", "business",
     "https://wechat2rss.bestblogs.dev/feed/8f8fe34034f6123b168ed7847c51d50ff47cd7ee.xml"),
    ("luanfanshu", "乱翻书", "business",
     "https://wechat2rss.bestblogs.dev/feed/43e3aa5cabe4ae49ec50410ecefc859d4501aedf.xml"),
    ("nanfangzhoumo", "南方周末", "business",
     "https://wechat2rss.bestblogs.dev/feed/eeb58b367f5515e9e3b56a8517aac4f7a71ce821.xml"),
    ("sanlian", "三联生活周刊", "business",
     "https://wechat2rss.bestblogs.dev/feed/29d9e4b80072d04e39dc5a25735733853496390d.xml"),
    ("xinwenzhoukan", "中国新闻周刊", "business",
     "https://wechat2rss.bestblogs.dev/feed/d54b08f4e62345d5516c26fbff3de9e499f18cfb.xml"),
    ("sixiangshichang", "澎湃思想市场", "business",
     "https://wechat2rss.bestblogs.dev/feed/96795edb72b7a9580b24e6662c46be99dd9a905a.xml"),
    ("ssircn", "斯坦福社会创新评论", "business",
     "https://wechat2rss.bestblogs.dev/feed/176467712d648b3d629e9a5c229630883cd16eb7.xml"),
]

_BATCH_SIZE = 8
WECHAT3_BATCHES: dict[str, list[tuple[str, str, str, str]]] = {
    f"w3{chr(ord('a') + i)}": WECHAT3_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(WECHAT3_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}

# (job_id, label, batch_key) — scheduler_jobs.py materializes one
# hourly job per row via its ``_wechat3_batch_job`` factory.
WECHAT3_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_wechat3_{key}_60m", f"公众号三批 {key[-1].upper()} 组", key)
    for key in WECHAT3_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    category: str
    url: str


class Wechat2RssBatch3Crawler:
    """Sequentially crawl one batch of third-wave wechat2rss feeds.

    Parameters
    ----------
    batch_key:
        Key into :data:`WECHAT3_BATCHES` (``"w3a"`` …). Unknown keys
        yield an empty crawl (defensive — a config typo must never
        crash the scheduler).
    delay_seconds:
        Polite pause between feeds; the bestblogs mirror is someone's
        self-hosted instance shared publicly — treat it gently.
    """

    market = "cn_a"
    language = "zh"

    def __init__(
        self,
        batch_key: str,
        *,
        delay_seconds: float = 2.0,
        timeout_seconds: float = 25.0,
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
        rows = WECHAT3_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, category=c, url=u)
            for s, n, c, u in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "AD-Research wechat2rss batch3 crawler/1.0"},
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
                            source=f"wechat_{feed.slug}",
                            market=self.market,
                            language=self.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "wechat2rss batch3 %s: feed %s failed: %s",
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
