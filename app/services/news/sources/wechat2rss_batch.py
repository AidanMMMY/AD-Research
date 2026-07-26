"""Batch WeChat-OA crawler backed by the public wechat2rss mirror.

Why this exists (2026-07-27, /goal 公众号扩充 >=100)
---------------------------------------------------
The self-hosted wewe-rss bridge covers accounts we explicitly subscribe
(one article link + one ``feed.add`` call each, rate-limited by 微信读书).
The public `wechat2rss <https://wechat2rss.xlab.app>`_ service already
indexes ~400 accounts as plain RSS — no login, no rate-limit coupling to
our own 微信读书 account. We hand-picked independent finance / business /
tech / geopolitics / essay accounts from its free list (see
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
    ("quanpindai", "全频带阻塞干扰", "d2b0dc03acc579a8a9c7aa45bf1f531ed5563f59"),
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
    ("qingbaogongjvxiang", "丁爸情报分析师的工具箱", "4fad165589ac854de97e576a6dbcfbd8b9f75320"),
    ("qingbaofenxishi", "情报分析师", "f50063f977eea0ce26836189fb7c3034f7e3d4f8"),
    ("qingbaomifeng", "情报小蜜蜂", "78f3da7a79babd1ab1a2831f37718630f41b77b5"),
    ("weixielengjing", "威胁棱镜", "63688861efb2362716368e36b7f8b8b61d0394a9"),
    ("aptguancha", "APT观察", "01cfcd4441ecc8f68af1df0d3669b9233133932a"),
    ("heiniao", "黑鸟", "f22e132bbbc4e8070cd51c0a84802f940e131a20"),
    ("kongtianfangyu", "空天防务观察", "b3da5de3b7697f10c0e22ce8909063ea84c44bbd"),
    ("wengehuayu", "温哥华的鱼", "51ed4848e5bfbf298b0d2b2becdc3a7d067ff5be"),
    ("hangkongxiaozhu", "方方的航空小筑", "b146ee0c6a719d7d3d86c93f4fdd4ca27b91baa2"),
    ("daoge", "道哥的黑板报", "980128c3a0c9ff852a06dd4a2bc3391338e05760"),
    ("heiqishi", "黑奇士", "47cf1260cf37d1de55b263afbf47e6cb6cae7d29"),
    ("lanrensikao", "懒人在思考", "773908acbc527a9a8637862bc6fad7fc8a916090"),
    ("economistjingdu", "经济学人双语精读", "3db1babbdeeb84327cf6b5315e98d5f40925ae13"),
    ("mlchuxuezhe", "机器学习初学者", "c5f385197ef56f9345db0daf1e46419af8c7d664"),
    ("cvai", "我爱计算机视觉", "b81ffcfff1107b5265cd7e39de610dc7ca72caf4"),
    ("gumingdi", "古明地觉的编程教室", "9e21dbf7a7cca45762bbed43f86cf04f82b23e1a"),
    ("aspirin42195", "阿司匹林42195米", "644f104d713e906e00ad1c5a0f91db5374cb5fb1"),
    ("dbaplus", "dbaplus社群", "3b9cc8887fccb80d3f083cd6eb8c344628d101b6"),
    ("weiwencode", "未闻Code", "a148ed0a542de4be305ffa1b93e8663ad252e22c"),
    ("hanyantalk", "寒雁Talk", "bbbe847b63f498801792fb7a08d67d0fbf167a04"),
    ("jishumaowu", "技术猫屋", "c48bba56bd4329af4db5c7b0eacf3d2f1c43c8df"),
    ("zhaowu", "赵武的自留地", "1bbf7fc5fac024226f86a1851c682253a7eae63f"),
    ("saibohuiyilu", "赛博回忆录", "b2fd128a6c259f160f380ffe90c17ce05bdc780f"),
    ("nieshangchongsheng", "逆熵重生", "95efa9e55cc1f8b14fb09b246bfacb6b9cd0c1e8"),
    ("neican", "互联网安全内参", "d5eb8577bf93aacdd7481ad0c3364939096b99a1"),
    ("luorijian", "落日间", "9c4b3d62a24fdf1863421984ad23e0c63e317614"),
    ("paohui", "有价值炮灰", "ca9e6f3e905e64301c6f00a21f2e3f135df1e691"),
    ("pixiang", "皮相", "41a459a80e37e15d9706465eee48ff491911a36f"),
    ("wangzhiyi", "网安志异", "e8caa9248c7b6a8d8d462a4ab3d7ab9181abeefb"),
    ("xiaoheiwu", "漕河泾小黑屋", "f38c9a9f230e19f49918faefc5d0d0fc71e52d29"),
    ("djzhaji", "DJ的札记", "d34c4b291ce2c15655ac1e7d54aa316902ef8968"),
    ("xiaodisuibi", "小迪随笔", "5086d647f212ae93f39db2da1973dc3f446b0d95"),
    ("huiyipiaoxue", "回忆飘如雪", "fa41acf1a0d9c54d4caf973349e7bd99d5de61c6"),
    ("sushiba", "俗世吧", "892464522627f503ae525d1df3c2690bca98b424"),
    ("quanxianhua", "全闲话", "a36d83e725f688bd999b039c259940f72d3514b3"),
    ("digejiangshi", "迪哥讲事", "6fbc842cdb8fd52f341af76f6aaf6cba21a23f7c"),
    ("hangxingbiji", "航行笔记", "4a76fbd471f0952829df9c488986bbcc67ff8790"),
    ("fangzhi", "放之", "672af7872ddae7ee20df9a3f2560224fb16babc3"),
    ("biaotu", "表图", "657873c2f534ea1c50875c8657bc405270ce7cd0"),
    ("tianwenjishibu", "天问记事簿", "a6b4c4531776fa4f4e837ca1fd56e5acd1df8f54"),
    ("wangxiaoming", "王小明的事", "4d5625268306f53fca5c6e8cb59daf73ca57d5e0"),
    ("sunmaojianghu", "榫卯江湖", "d1988b840deaf6a79edd32e83a1b152038f1b6a1"),
    ("juexueshe", "觉学社", "238759eb3e9d042d4e1ef515cfc3686c977c6ddd"),
    ("songzhao", "宋钊的小站", "667c03c3823e7c2c9da0c197b7b40f5b3ee94f8e"),
    ("axutongxue", "阿虚同学", "808d3625c2b1915142f09e2d4bb2acd636aa956d"),
    ("jungetili", "君哥的体历", "947b46dba9754e10360d267a5ee9a87597e0bafe"),
    ("tianheishuoheihua", "天黑说嘿话", "d5a661c1beccdff18ba1ae018514e4d702feac74"),
    ("anquanpenzi", "安全喷子", "158efac9a94e62404af4bc804a6d6dcd55caa44f"),
    ("loudongzhanzheng", "漏洞战争", "a884cb33e3393db2f683c48d82012836295ec005"),
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
