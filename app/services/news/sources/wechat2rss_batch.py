"""Batch WeChat-OA crawler backed by the public wechat2rss mirror.

Why this exists (2026-07-27, /goal 公众号扩充 >=100)
---------------------------------------------------
The self-hosted wewe-rss bridge covers accounts we explicitly subscribe
(one article link + one ``feed.add`` call each, rate-limited by 微信读书).
The public `wechat2rss <https://wechat2rss.xlab.app>`_ service already
indexes ~400 accounts as plain RSS — no login, no rate-limit coupling to
our own 微信读书 account. We hand-picked the independent finance /
business / tech-commentary accounts from its free list (see
``WECHAT2RSS_FEEDS``) and crawl them here.

Design notes
------------
* **Table-driven**: one row per account ``(slug, display_name, hash)``.
  ``source`` becomes ``wechat_{slug}`` — same namespace as the wewe-rss
  feeds, so the News page / health grid treat every WeChat account
  uniformly.
* **Batched jobs**: 41 feeds as 41 scheduler jobs would drown the
  health grid and amplify the APScheduler misfire problem (see
  20260727 runbook §2). Instead the table is sliced into
  ``WECHAT2RSS_BATCHES`` groups (~10 feeds each); one scheduler job
  crawls one group sequentially with a polite inter-feed delay.
* **Selection rule** (user requirement): independent voices only —
  no official-media accounts (人民日报/新华社/央视...), no corporate
  PR accounts. The list deliberately skips the ~280 pure
  security-research accounts on the mirror as off-topic for an
  investment-research platform.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

_FEED_URL = "https://wechat2rss.xlab.app/feed/{hash}.xml"

# (slug, display_name, feed_hash). source = "wechat_{slug}".
WECHAT2RSS_FEEDS: list[tuple[str, str, str]] = [
    ("jisilu", "集思录", "f75bbb0bffd9fd6e0dda725282202ccc23a2bdff"),
    ("changying", "长赢指数投资", "1f35edb36dfda13906f958fc3047e59ce9c234fe"),
    ("yetanqian", "也谈钱", "f2fd5af8dc3590b99509f0c501de09066d063028"),
    ("dingtou", "从零开始定投日记", "0d2c5982deb01d2295ecf8f4891c9cb75d8d8ba3"),
    ("ansheng", "卢瑟经济学安生杂谈", "62ec8c2ba29a16a45c8418a6ecd1945cc80eb380"),
    ("hongseansheng", "红色安生", "e2379df83a2450a7dd45022f0408c65cdf11563f"),
    ("luojijingji", "逻辑与现实经济", "07cd3971227a35b5c35cd94d1961790dad9a87c7"),
    ("liuzhen", "六镇", "fd04a2cecf60d2f3a4da34206e11c07aca561715"),
    ("pinglanyuyan", "凭栏欲言", "01c05fce74822ac6f30656f22e0ca542dfb7c8c0"),
    ("zhenmeiluoji", "真没什么逻辑", "347c1a20a1a8ff2b789e454e938addadc85b2c4b"),
    ("shugongfuli", "数工复利", "9daa406071d03da194ea8a0b35f1982c288ba366"),
    ("tiaodongjisuanqi", "跳动的计算器", "f3ace422519a0db0d5848415f0ad2e36ecf2c069"),
    ("qiankejiuguan", "掮客酒馆", "10fdc27bdac746197d79a7632053fee231f37bcd"),
    ("xisailuo", "海边的西赛罗", "5e25483b324ae2d39510555465b12a2b2dfa4000"),
    ("huigeqitan", "辉哥奇谭", "1b01bd297483509251779f1a02bb90223786a923"),
    ("xianshengzhizao", "先生制造", "313326d41db4f54b1cc09e7c986a5ac4e5f88ca0"),
    ("youyouluming", "呦呦鹿鸣", "fa89f27259f903b92f5f133140dd3f641110f9fd"),
    ("zhangjing42", "42章经", "31436fcc3bba8c2c2a9337a163afcb3b5a57a0a0"),
    ("zhangsanfeng", "张三丰的疯言疯语", "4b0c13b203b74f4d5b366d98ee2d8420bda258ca"),
    ("renzhiduxing", "认知独省", "83f81eece114fa0cb211ab5379fda72760dc5b68"),
    ("sixianghuahuo", "思想花火", "5b925323244e9737c39285596c53e3a2f4a30774"),
    ("jiqizhixin", "机器之心", "51e92aad2728acdd1fda7314be32b16639353001"),
    ("liangziwei", "量子位", "7131b577c61365cb47e81000738c10d872685908"),
    ("xinzhiyuan", "新智元", "ede30346413ea70dbef5d485ea5cbb95cca446e7"),
    ("xixiaoyao", "夕小瑶科技说", "a1cd365aa14ed7d64cabfc8aa086da40ecaba34d"),
    ("paperweekly", "PaperWeekly", "3be891c2f4e526629ab055a297cc2cd6c1f0a563"),
    ("jizhiclub", "集智俱乐部", "8540570d27c0bfe0a219173cf1ace83ae79445cb"),
    ("geekpark", "极客公园", "1a5aec98e71c707c8ca092bc2c255b9d4bac477d"),
    ("chaping", "差评", "8d839de8dd3290a1f1be7a94423cccb30c1b087d"),
    ("xiaozhong", "小众软件", "3261d5a75cfef238650a2cabd4bbf99669c2f334"),
    ("laogao", "老高的互联网杂谈", "574587b13c6f60617fc74605702258ddf4aefac6"),
    ("xunikuangjia", "虚拟框架", "c0f0ee37039f7da55ed6ed4ae160d11af1915007"),
    ("qianhei", "浅黑科技", "6111a6d5ecf28cfdd4fc9b664244c05ddacef15c"),
    ("sanxiu", "钱塘门外的互联网散修", "bf791d6a822e8f48b4f6aa056e42758479362281"),
    ("fusheng", "傅盛", "71257003d43d39b91ff9d38b6f3330c883dc8e0c"),
    ("wulujia", "吴鲁加", "9ce69c7f41d24a340778d34bfc977dd71b40c203"),
    ("datawhale", "Datawhale", "4d620d988cb21cfeefd2263207221f0dc70df9ff"),
    ("xiaohuojian", "小火箭", "ebbf3f8891e7d70626c75dca7b92dd6c075663d5"),
    ("qiuzhenwei", "邱贞玮", "6451f06f5dffd44946bbdc407cf9605396f83437"),
    ("qingbaofanzi", "二道情报贩子", "86512202e74d01447788f355c4a4171a3c86740a"),
    ("janky", "连续创业的Janky", "66f13ba7620a53ca279f679a8a956f43255fb579"),
]

_BATCH_SIZE = 11
WECHAT2RSS_BATCHES: dict[str, list[tuple[str, str, str]]] = {
    chr(ord("a") + i): WECHAT2RSS_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(WECHAT2RSS_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str


class Wechat2RssBatchCrawler:
    """Sequentially crawl one batch of wechat2rss feeds.

    Parameters
    ----------
    batch_key:
        Key into :data:`WECHAT2RSS_BATCHES` (``"a"`` …). Unknown keys
        yield an empty crawl (defensive — a config typo must never
        crash the scheduler).
    delay_seconds:
        Polite pause between feeds; the mirror is a free public
        service.
    """

    market = "cn_a"
    language = "zh"

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
        rows = WECHAT2RSS_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, url=_FEED_URL.format(hash=h))
            for s, n, h in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "AD-Research wechat2rss batch crawler/1.0"},
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
                        "wechat2rss batch %s: feed %s failed: %s",
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
