"""Batch crawler for Chinese-language independent podcasts (2026-07-29).

Why this exists
---------------
Fourth wave of the 资讯源扩充 push: >=30 **Chinese-language podcasts**
covering investing / macro / business analysis / industry depth /
tech commentary. Previous waves covered WeChat accounts
(``wechat2rss_batch.py`` / ``wechat2rss_batch2.py``), 144 CN/EN blogs
and podcasts (``independent_batch.py``), 125 multi-language
publications (``global_rss_batch.py``), 104 English independent voices
(``global_indie_batch.py``) and Asia-English outlets
(``asia_en_batch.py``). This wave fills the remaining gap: opinionated
Chinese audio shows (小宇宙 / 喜马拉雅 / SoundOn / Firstory / Fireside /
自托管), whose shownotes land in ``description`` and become the stored
article body.

Selection rule (same spirit as the earlier waves)
-------------------------------------------------
* Topic must be 财经 / 投资 / 宏观 / 商业分析 / 产业深度 / 科技评论 —
  pure newsreaders, government/official outlets, corporate-brand PR
  shows (基金公司 / 券商 / 平台官方出品, e.g. 中欧基金, 雪球《厚雪长波》,
  纪源资本《创业内幕》) and entertainment chat shows are excluded.
* Still publishing: newest episode within 30 days at verification time
  (2026-07-29); a handful of high-quality ~monthly shows are kept with
  an explicit note when their newest episode is 30–60 days old
  (商业WHY酱 34d, 小马宋商业观察 37d, 少数派播客 43d, 大头侃人 50d).
* Native RSS only — the previous wave established that RSSHub public
  instances are unreachable from the production network, so every feed
  below is the show's own RSS (feed.xyzfm.space / ximalaya / SoundOn /
  Firstory / Fireside / Acast / SoundCloud / self-hosted).

Every feed was live-verified from the production ECS on 2026-07-29:
HTTP 200 after redirects, valid RSS 2.0, items > 0, newest item date
checked, and >=6/8 of the latest items carrying >=80 chars of
shownotes. 68 candidates were tested; 40 survived (28 rejections —
mostly stale feeds, 3 corporate-brand shows, 1 official-media show, 4
off-topic, 1 with no working RSS). The full evidence table and the
rejection log live in ``docs/dev-notes/20260729-zh-multi-batch.md``.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``zhx_{slug}`` so this wave has its own namespace alongside
  ``wechat_*``, ``indie_*``, ``global_*``, ``gind_*`` and ``asen_*``.
* **Batches start at "a"**: batch keys are independent of the other
  tables (the job namespace ``news_zhx_*`` is what must be unique, and
  it is), so this table is simply sliced into batches ``a``–``d`` of
  10 feeds each.
* **Market**: all rows are ``cn_a`` / ``zh`` on purpose — the news
  API's ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)`` and
  these are Chinese-language shows for the CN audience (same precedent
  as the Chinese podcasts inside ``independent_batch``).
* **No LLM marketing filter**: curated editorial voices, same
  precedent as ``independent_batch`` / ``global_indie_batch`` — the
  scheduler job writes directly after fetch, keeping LLM cost flat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language). source = "zhx_{slug}".
ZH_MULTI_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 投资 / 理财对谈（大陆） ──
    ("zhixingjiuguan", "知行小酒馆", "https://feed.xyzfm.space/j8yp8gxkmgqr", "cn_a", "zh"),
    ("touzishizhanpai", "投资实战派", "https://feed.xyzfm.space/rgnq4rbx9tpv", "cn_a", "zh"),
    ("mancangyihou", "满仓以后", "https://feed.xyzfm.space/jgqnv6dwllut", "cn_a", "zh"),
    ("sandianxiaban", "三点下班", "https://feed.xyzfm.space/tlel9j4tg3eu", "cn_a", "zh"),
    ("huiyoubiaoju", "会友镖局", "https://feed.xyzfm.space/xgeyj6a3mngc", "cn_a", "zh"),
    # ── VC / 创业 / 商业分析（大陆） ──
    ("fengtouquan", "疯投圈", "https://crazy.capital/feed", "cn_a", "zh"),
    ("sishierzhangjing", "42章经", "https://feed.xyzfm.space/evgg6xle9rdc", "cn_a", "zh"),
    ("shangyewhyjiang", "商业WHY酱", "https://feed.xyzfm.space/twj7n6rmffpd", "cn_a", "zh"),
    ("jinjibocaijing", "进击波财经", "https://feed.xyzfm.space/wjvqp9jxdhtn", "cn_a", "zh"),
    ("xiaomasong", "小马宋商业观察", "https://feed.xyzfm.space/kbkftb78gb4e", "cn_a", "zh"),
    ("wandianliao", "晚点聊 LateTalk", "https://feeds.fireside.fm/latetalk/rss", "cn_a", "zh"),
    ("zhaiboyixia", "窄播一下", "https://feed.xyzfm.space/cp8gttbug8v6", "cn_a", "zh"),
    ("datoukanren", "大头侃人", "https://feed.xyzfm.space/jtumdxxt8fjt", "cn_a", "zh"),
    # ── AI / 出海 / 新消费（大陆） ──
    ("shizilukou", "十字路口Crossing", "https://feed.xyzfm.space/68fyjknth9hj", "cn_a", "zh"),
    ("chuhaixiangduilun", "出海相对论", "https://feed.xyzfm.space/y3cpdhbar4ap", "cn_a", "zh"),
    ("equalocean", "EqualOcean出海全球化会客厅", "https://feed.xyzfm.space/rjl4uflbdr33", "cn_a", "zh"),
    ("yingdihaike", "硬地骇客", "https://feed.xyzfm.space/byhkljlbep9j", "cn_a", "zh"),
    ("xiaofeixinzhi", "消费新知", "http://www.ximalaya.com/album/46604249.xml", "cn_a", "zh"),
    # ── 科技评论 / 国际政经 / 深度访谈（大陆 & 海外华语） ──
    ("daxiaoma", "大小马聊科技", "http://www.ximalaya.com/album/55951710.xml", "cn_a", "zh"),
    ("guigudaobdao", "硅谷叨B叨", "http://www.ximalaya.com/album/21685160.xml", "cn_a", "zh"),
    ("fengyanfengyu", "枫言枫语", "https://justinyan.me/feed/podcast", "cn_a", "zh"),
    ("sspaipodcast", "少数派播客", "https://sspai.typlog.io/feed/audio.xml", "cn_a", "zh"),
    ("dongyaguanchaju", "东亚观察局", "http://www.ximalaya.com/album/37399737.xml", "cn_a", "zh"),
    ("bumingbai", "不明白播客", "https://feeds.acast.com/public/shows/68004395b4ef799a7a410371", "cn_a", "zh"),
    # ── 台湾 / 海外华语：投资与财经评论 ──
    ("gooaye", "股癌 Gooaye", "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml", "cn_a", "zh"),
    ("zhaohuaguhuozai", "兆華與股惑仔", "https://feeds.soundon.fm/podcasts/91be014b-9f55-4bf3-a910-b232eda82d11.xml", "cn_a", "zh"),
    ("gushiyinzhe", "股市隱者", "https://feeds.soundon.fm/podcasts/eb9e90a8-a889-425b-8855-4cf8cdf92c73.xml", "cn_a", "zh"),
    ("caibaogou", "財報狗", "https://feed.firstory.me/rss/user/clcftm46z000201z45w1c47fi", "cn_a", "zh"),
    ("bubaijiaozhu", "不敗教主陳重銘", "https://feeds.soundon.fm/podcasts/f93d43ed-f938-45f1-9e71-d915f806bae4.xml", "cn_a", "zh"),
    ("touzihaishenme", "投資嗨什麼", "https://feeds.soundon.fm/podcasts/bf960cfe-3cd1-4723-a980-52711c69a3c8.xml", "cn_a", "zh"),
    ("xiabanjingjixue", "下班經濟學", "https://feeds.soundon.fm/podcasts/208dfd5b-d11b-4236-ab87-d8f0bf01d7d0.xml", "cn_a", "zh"),
    ("caijinghaojiao", "游庭皓的財經皓角", "https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss", "cn_a", "zh"),
    ("taiwantongqin", "台灣通勤第一品牌", "https://anchor.fm/s/1ea77470/podcast/rss", "cn_a", "zh"),
    # ── 台湾 / 海外华语：国际政经 / 科技商业 / 深度报导 ──
    ("mindixuandu", "敏迪選讀", "https://feeds.soundon.fm/podcasts/44833083-490d-4f97-a782-fd5e34c0abef.xml", "cn_a", "zh"),
    ("meiguotaiwanguance", "美國台灣觀測站", "https://feeds.soundon.fm/podcasts/6cdfccc6-7c47-4c35-8352-7f634b1b6f71.xml", "cn_a", "zh"),
    ("mguandian", "M觀點", "https://feeds.soundon.fm/podcasts/b8f5a471-f4f7-4763-9678-65887beda63a.xml", "cn_a", "zh"),
    ("kejikamaila", "科技開麥拉", "https://feed.firstory.me/rss/user/cl0bwfpls02rt0847zq8ru6js", "cn_a", "zh"),
    ("baodaozhe", "報導者 The Real Story", "https://feeds.soundon.fm/podcasts/c1f1f3c9-8d28-42ad-9f1c-908018b8d9fc.xml", "cn_a", "zh"),
    ("darensmalltalk", "大人的Small Talk", "https://feeds.soundon.fm/podcasts/6731d283-54f0-49ec-a040-e5a641c3125f.xml", "cn_a", "zh"),
    ("beimeijinshijiao", "北美金事角", "https://anchor.fm/s/7aa7f5d8/podcast/rss", "cn_a", "zh"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcd"  # job namespace news_zhx_* is unique, so keys restart at "a".
ZH_MULTI_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: ZH_MULTI_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if ZH_MULTI_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (see docs/dev-notes/20260729-zh-multi-batch-integration.md).
ZH_MULTI_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_zhx_{key}_60m", f"中文播客 {key.upper()} 组", key)
    for key in ZH_MULTI_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class ZhMultiBatchCrawler:
    """Sequentially crawl one batch of Chinese podcast RSS feeds.

    Mirrors :class:`GlobalIndieBatchCrawler`. Unknown batch keys yield
    an empty crawl (defensive — a config typo must never crash the
    scheduler). Podcast ``<enclosure>`` / ``itunes:*`` tags need no
    special handling: shownotes in ``description`` are the article body.
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
        rows = ZH_MULTI_BATCHES.get(self._batch_key, [])
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
                            source=f"zhx_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "zh podcast batch %s: feed %s failed: %s",
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
