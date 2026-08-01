"""Second batch of WeChat-OA crawlers (added 2026-07-28).

Why this exists
---------------
/goal wave: another >=100 WeChat Official Accounts focused on macro
economics, investment strategy, industry research (semiconductors /
new energy / pharma / consumer / finance), tech commentary and
business deep-dives — excluding pure marketing / clickbait /
advertorial accounts.

The public wechat2rss mirror (``wechat2rss.xlab.app``) that
``wechat2rss_batch.py`` draws from indexes only 395 accounts, ~326 of
them security-research; after batch 1 took the 90 usable ones, only a
handful of qualified accounts remained. A second public wechat2rss
instance — ``wechat2rss.bestblogs.dev`` (the BestBlogs project's
self-hosted mirror, 375 accounts, published as OPML) — covers exactly
the finance / business / tech space, so this batch draws 100 of its
103 feeds from that mirror and the remaining 3 from the original
xlab mirror. Both mirrors speak the identical RSS format (full post
body in ``content:encoded``), so one crawler handles both.

Every feed below was verified from the production ECS on 2026-07-28:
HTTP 200, ``items > 0``, real body text in ``content:encoded`` /
``description``, and a newest item within ~30 days. 9 candidates
failed the bar and were dropped (7 stale: 老钱说钱/孟岩/刘言飞语/
43 Talks/晚点对话/Delphi研习社/金色钱江; 1 gadget-PR: 科技美学;
1 clickbait: 毛有话说). See
``docs/dev-notes/20260728-wechat-batch2.md`` for the full evidence
table including per-feed newest-item dates.

Design notes
------------
* **Table-driven**: one row per account
  ``(slug, display_name, category, feed_url)``; ``source`` becomes
  ``wechat_{slug}`` — the same namespace as batch 1 and the wewe-rss
  feeds, so the News page / health grid treat every WeChat account
  uniformly. ``category`` is one of ``macro`` / ``strategy`` /
  ``industry`` / ``tech`` / ``business``; since 2026-08-02 it is also
  persisted to ``news_article.category`` via
  ``parse_rss_items(default_category=...)`` → ``extra["category"]`` →
  ``normalizer._derive_category`` (学习中心打标接通).
* **Batched jobs**: 103 feeds as 103 scheduler jobs would drown the
  health grid and amplify the APScheduler misfire problem (see the
  20260727 runbook §2). The table is sliced into
  :data:`WECHAT2B_BATCHES` groups of ~11 feeds (keys ``w2a`` …);
  one scheduler job crawls one group sequentially with a polite
  inter-feed delay.
* **No overlap**: slugs, display names and feed URLs are disjoint
  from ``wechat2rss_batch.WECHAT2RSS_FEEDS``, the single-feed
  crawlers (``wechat_maobidao`` / ``wechat_sixianggangyin`` /
  ``wechat_zeping``) and the wewe-rss ``WECHAT_RSS_FEED_MAP`` slugs
  (zhigu / yuanchuan / canghai / fupeng / lixunlei / congming /
  beiwei / latepost). Accounts already covered by direct platform
  sources (华尔街见闻 / 财新 / 界面 / 36氪 / 虎嗅 / 财联社 / 雪球 …)
  were deliberately excluded at selection time.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

#: Mirrors the feeds are served by (for tests / docs only — each row
#: already carries its full URL).
MIRROR_XLAB = "https://wechat2rss.xlab.app"
MIRROR_BESTBLOGS = "https://wechat2rss.bestblogs.dev"

CATEGORIES = ("macro", "strategy", "industry", "tech", "business")

# (slug, display_name, category, feed_url). source = "wechat_{slug}".
WECHAT2B_FEEDS: list[tuple[str, str, str, str]] = [
    # ── 宏观经济 (macro) ──
    ("zepinghongguan", "泽平宏观", "macro",
     "https://wechat2rss.bestblogs.dev/feed/4457d527901114d399a081ba4cf74688617a0ff4.xml"),
    ("xiangshuai", "香帅的金融江湖", "macro",
     "https://wechat2rss.bestblogs.dev/feed/14cb1167539ceb3e3b235e1fb01e478056244e23.xml"),
    ("zhongjin", "中金点睛", "macro",
     "https://wechat2rss.bestblogs.dev/feed/5d4eef298108dd63ce77f40257436e0585bab425.xml"),
    ("cf40", "中国金融四十人论坛", "macro",
     "https://wechat2rss.bestblogs.dev/feed/effdfffc5993e7260f3766aaafafc5536b685a54.xml"),
    ("worldbank", "世界银行", "macro",
     "https://wechat2rss.bestblogs.dev/feed/8914290fa6b113568831e7e8ae52a3c9cbd061e4.xml"),
    ("eeo", "经济观察报", "macro",
     "https://wechat2rss.bestblogs.dev/feed/d930069e140c08f249e636f46a2c1f03182b3d0f.xml"),
    ("yetan", "叶檀财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/6c0b8961f68734b500af357c85e31bd77b9107e9.xml"),
    ("zhangyong", "张湧说财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/ca54330be89d40f35f8ec253a253d32fdb9d5549.xml"),
    ("gongfucaijing", "功夫财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/6471fce0de540deb1b8b977824aab1c86487fcfd.xml"),
    ("cjzaocan", "财经早餐", "macro",
     "https://wechat2rss.bestblogs.dev/feed/fa79da40977d8741fa9ec8a24989718f0707cfcf.xml"),
    ("econdaily", "一天一篇经济学人", "macro",
     "https://wechat2rss.bestblogs.dev/feed/fc75f34053a2d04d099e2e797b88df189f0cd76a.xml"),
    ("caijing", "财经杂志", "macro",
     "https://wechat2rss.bestblogs.dev/feed/746c29d98c0bec3969f2613b04c4755fd4786f53.xml"),
    ("yicai", "第一财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/e2cc4ff2ae914ebfd4150420ece80dd93be7a6d9.xml"),
    ("herald21", "21世纪经济报道", "macro",
     "https://wechat2rss.bestblogs.dev/feed/c6a39cae0e7e0979ed9f2eece16695c5f664f147.xml"),
    ("nbd", "每日经济新闻", "macro",
     "https://wechat2rss.bestblogs.dev/feed/2a223faf5b8fdf7b95e2ad2f7ab8bfb8e21e5075.xml"),
    ("qszg", "券商中国", "macro",
     "https://wechat2rss.bestblogs.dev/feed/eb2d4afb6b3f89a5dda9f796a95ca5372bd83621.xml"),
    ("lengjing", "棱镜", "macro",
     "https://wechat2rss.bestblogs.dev/feed/ebf208faff5c5ad865ab5e5a30548633f3b51da7.xml"),
    ("shenwang", "深网腾讯新闻", "macro",
     "https://wechat2rss.bestblogs.dev/feed/396591aa7d3ef15fa3b5b17ec4b1aa840ebde335.xml"),
    ("ifengcj", "凤凰网财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/404573560480142fd2322430f3c1efe696cc89af.xml"),
    ("gelonghui", "格隆汇APP", "macro",
     "https://wechat2rss.bestblogs.dev/feed/379ce45e27b2c096121d11c0eccdda4cc15511de.xml"),
    ("eastmoney", "东方财富网", "macro",
     "https://wechat2rss.bestblogs.dev/feed/704303062c285fa1417079b9c95c5c143378bbd8.xml"),
    ("wind", "Wind万得", "macro",
     "https://wechat2rss.bestblogs.dev/feed/db72a8e611d59e9184668bbdf5089fb298cde97d.xml"),
    ("barrons", "Barrons巴伦", "macro",
     "https://wechat2rss.bestblogs.dev/feed/707728196d05deab425a8dfa96f0084b6946f8cf.xml"),
    ("txcaijing", "腾讯财经", "macro",
     "https://wechat2rss.bestblogs.dev/feed/2bbef5993740fcd6ed968d19203962f24db7b442.xml"),
    ("xiaolinshuo", "小Lin说的公众号", "macro",
     "https://wechat2rss.bestblogs.dev/feed/57bdb3ca8c26dd738f78e44985b1030c4d38ddbf.xml"),
    ("dashuilai", "大水来", "macro",
     "https://wechat2rss.xlab.app/feed/1cd29c6df63ddc61880618cf57ed7198aa3c76d3.xml"),
    # ── 投资策略 (strategy) ──
    ("dianshi", "点拾投资", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/e460ce1e8b48d9c4baa4fb762e93e4409c7a14fd.xml"),
    ("luosiding", "银行螺丝钉", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/06bb878110fe389ca828db3bacaec38630c7ddc7.xml"),
    ("laoqian", "老钱日日谈", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/6e8528014a81863ccd43207355399c224314e405.xml"),
    ("tzshixi", "投资实习所", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/1324caa248157b73a64412393f5612931368dd52.xml"),
    ("gududanao", "孤独大脑", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/700f40ffc993431fec55d910ceee880fb4e4eec3.xml"),
    ("sanzhe", "三折人生", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/70169da59e7e342ec7b63c90351b224b50cf7cb7.xml"),
    ("gelan", "格兰投研", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/fdb968fa04c741aee954dc36c25d3dee8063ecee.xml"),
    ("laozhang", "老张投研", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/90d66a1550113ac5ee878490529a3bf9f3da8c74.xml"),
    ("investguru", "investguru", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/4fb41730a2fa1140fef4d0c1e8e8e70780c7a2c8.xml"),
    ("haitun", "海豚研究", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/60b1f9007c87ab75cd83314bf5cfede30addd40a.xml"),
    ("fengrui", "峰瑞资本", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/add0d6261e87b188e868179f1dc5afc0a5d06c3f.xml"),
    ("gaoling", "高瓴创投", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/c678fe78920139132d57163ee5612dc880566ce4.xml"),
    ("jingwei", "经纬创投", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/05efb1c4cf91e5a37443cc323150ea38a838e9fd.xml"),
    ("zhenge", "真格基金", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/47798a14d51da72e68fae4f7a259f096750cf03e.xml"),
    ("hongshan", "红杉汇", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/fb9c7a3ba3666dc1b0956b0dac916cd5c56ecf9f.xml"),
    ("shanxing", "山行资本", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/76787a745daab4bbc83fe3155aa74aaa1d54c7a0.xml"),
    ("etfjinhua", "ETF进化论", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/0f497c4aabdb12a8831aaa266d595e971962bb68.xml"),
    ("liubei", "刘备教授", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/1491cf7d5d9179503e809e6e9ffb1da27fed027d.xml"),
    ("zhenglitao", "郑立涛", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/14fb6a008b286103e05bc153c9dc37d7f5d42c36.xml"),
    ("xieyin", "携隐Melody", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/42992fc03cdcee9ef03dfc4623b538b18dd923ce.xml"),
    ("sjfendui", "随机小分队", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/115e814e7b12d373a55459cb2aea3223152f2af2.xml"),
    ("taiyang", "太阳照常升起", "strategy",
     "https://wechat2rss.bestblogs.dev/feed/ddca396fc887ac5006719b240d232ef517bca30e.xml"),
    # ── 行业研究 (industry) ──
    ("bandaoti", "半导体行业观察", "industry",
     "https://wechat2rss.bestblogs.dev/feed/39f625822b35f7573a7e70d3b27a735a3c0d24a4.xml"),
    ("zhidongxi", "智东西", "industry",
     "https://wechat2rss.bestblogs.dev/feed/cfd52b4245ca6119b2fda4ef934832c689028927.xml"),
    ("jiazi", "甲子光年", "industry",
     "https://wechat2rss.bestblogs.dev/feed/1c4008936645d5c17239d99bba91522cf2bdfa26.xml"),
    ("daofa", "刀法研究所", "industry",
     "https://wechat2rss.bestblogs.dev/feed/9a650290a6093330e410549cea75251cb5a3249c.xml"),
    ("zhaibo", "窄播", "industry",
     "https://wechat2rss.bestblogs.dev/feed/61bdf2799e5208df45c8bbbd96ba81dd088d2483.xml"),
    ("xinbang", "新榜", "industry",
     "https://wechat2rss.bestblogs.dev/feed/16647c855b3c08c6406fb029f3cd9bb826e70d0c.xml"),
    ("yunying", "运营研究社", "industry",
     "https://wechat2rss.bestblogs.dev/feed/bc7bf2a738eebe7ef9728f407721300ac884ad74.xml"),
    ("jianshi", "见实", "industry",
     "https://wechat2rss.bestblogs.dev/feed/194b072227430108e54f40a67c9a514aff599a2f.xml"),
    ("medsci", "梅斯医学", "industry",
     "https://wechat2rss.bestblogs.dev/feed/f062c077bc14545b7c8ebc429fc9883a73d50f36.xml"),
    ("deeptech", "DeepTech深科技", "industry",
     "https://wechat2rss.bestblogs.dev/feed/7229d3e3e0c59e13fb0b8b3626881488bab76156.xml"),
    ("naojiti", "脑极体", "industry",
     "https://wechat2rss.bestblogs.dev/feed/5044161439fe8773e9d906a04d6df8f711e770ea.xml"),
    ("langchao", "浪潮工作室", "industry",
     "https://wechat2rss.bestblogs.dev/feed/4badc49b90ce718fb6f4b9e80393463916eaca77.xml"),
    ("saasbyx", "SaaS白夜行", "industry",
     "https://wechat2rss.bestblogs.dev/feed/a0f20f6277c356668a2567632a67e15b0413f395.xml"),
    ("fangwei", "方伟看十年", "industry",
     "https://wechat2rss.bestblogs.dev/feed/eaf95898f79359a2e689481c249e4009cde21bd6.xml"),
    # ── 科技评论 (tech) ──
    ("sota", "机器之心SOTA模型", "tech",
     "https://wechat2rss.bestblogs.dev/feed/2f520471856d56c7b3a95cd09eb777149b32828a.xml"),
    ("infoq", "InfoQ", "tech",
     "https://wechat2rss.bestblogs.dev/feed/13da94d7eb314b49fa251cb7e8399cae29d772db.xml"),
    ("sspai", "少数派", "tech",
     "https://wechat2rss.bestblogs.dev/feed/f0e37a7d597231efed4bf6dd05b5d904de6dbcc1.xml"),
    ("appso", "APPSO", "tech",
     "https://wechat2rss.bestblogs.dev/feed/4ae111e5b509609a5ee96c9894f1868fbafd793e.xml"),
    ("leifeng", "雷峰网", "tech",
     "https://wechat2rss.bestblogs.dev/feed/5e4d00adff41e5f5b2bd823215c9949e7e678bd5.xml"),
    ("taimeiti", "钛媒体", "tech",
     "https://wechat2rss.bestblogs.dev/feed/3d5672d87be7aba570671c8cb2fdbda36a5dfd9e.xml"),
    ("guixingren", "硅星人Pro", "tech",
     "https://wechat2rss.bestblogs.dev/feed/c62ceda9eed269d851802bdbc5f33c4fabbf7462.xml"),
    ("lanxi", "阑夕", "tech",
     "https://wechat2rss.bestblogs.dev/feed/fe0fc82458663820d6e91f6331dea05f3db223d4.xml"),
    ("caoz", "caoz的梦呓", "tech",
     "https://wechat2rss.bestblogs.dev/feed/8e2047ef236238b91abf91562b79ef4a1e7ba39d.xml"),
    ("guaidao", "互联网怪盗团", "tech",
     "https://wechat2rss.bestblogs.dev/feed/59d988bead1c70401df2a3a11544e2c5d4df6dc3.xml"),
    ("mactalk", "MacTalk", "tech",
     "https://wechat2rss.bestblogs.dev/feed/a657b0a3a865418b8ed7c619214cd4b8c7a28218.xml"),
    ("wangjianshuo", "王建硕", "tech",
     "https://wechat2rss.bestblogs.dev/feed/98bc4f50442b51ab17e9e07ff42799377abeabe2.xml"),
    ("mitreview", "麻省理工科技评论APP", "tech",
     "https://wechat2rss.bestblogs.dev/feed/b776c2d89a99c852e9eb17d0d46f7f6d79febde4.xml"),
    ("znyx", "智能涌现", "tech",
     "https://wechat2rss.bestblogs.dev/feed/049f4d78f94b31ab6afda95b1a65f0e562c8d5c2.xml"),
    ("txkeji", "腾讯科技", "tech",
     "https://wechat2rss.bestblogs.dev/feed/a81bdfcbb9eefe870d285e81510ffa1af26e4520.xml"),
    ("wangyikeji", "网易科技", "tech",
     "https://wechat2rss.bestblogs.dev/feed/028fbc21062e744c7b606880ebca01e22cb4b7b7.xml"),
    ("baijing", "白鲸出海", "tech",
     "https://wechat2rss.bestblogs.dev/feed/2b8f03a73a0f2ac92a8ca69c124e5be6f442dbdc.xml"),
    ("woshipm", "人人都是产品经理", "tech",
     "https://wechat2rss.bestblogs.dev/feed/2d790e38f8af54c5af77fa5fed687a7c66d34c22.xml"),
    ("founderpark", "Founder Park", "tech",
     "https://wechat2rss.bestblogs.dev/feed/f940695505f2be1399d23cc98182297cadf6f90d.xml"),
    ("kazike", "数字生命卡兹克", "tech",
     "https://wechat2rss.bestblogs.dev/feed/ff621c3e98d6ae6fceb3397e57441ffc6ea3c17f.xml"),
    ("guicang", "歸藏的AI工具箱", "tech",
     "https://wechat2rss.bestblogs.dev/feed/1c3e3571b1627d23ee9c64521a0b0a41d3fe2987.xml"),
    ("saibo", "赛博禅心", "tech",
     "https://wechat2rss.bestblogs.dev/feed/752c31ca0446b837339463fc5440539e20267d2f.xml"),
    ("crossing", "十字路口Crossing", "tech",
     "https://wechat2rss.bestblogs.dev/feed/20492a5f2d3637c178c01ab0bab7ed86a4a0995b.xml"),
    ("newin", "有新Newin", "tech",
     "https://wechat2rss.bestblogs.dev/feed/74554dcb3da8982083426b871bc8c314a9de9729.xml"),
    ("hwunicorn", "海外独角兽", "tech",
     "https://wechat2rss.bestblogs.dev/feed/7200d3a5e976d231deb1e40ad33745c0e649b029.xml"),
    ("shensiquan", "深思圈", "tech",
     "https://wechat2rss.bestblogs.dev/feed/3e6fcb56a39b2e18f1036113655d4ff8fe726b62.xml"),
    ("guigu", "硅谷科技评论", "tech",
     "https://wechat2rss.bestblogs.dev/feed/4515ee058133ff68570ad586abdd81f54f2b6ee3.xml"),
    ("thoughtworks", "思特沃克洞见", "tech",
     "https://wechat2rss.bestblogs.dev/feed/6c6865b59e528f6f86d80b9a2071052416ef561f.xml"),
    ("wadianai", "晚点AI", "tech",
     "https://wechat2rss.bestblogs.dev/feed/316def62ee3a6d499bf3981ffe22a09bf7256265.xml"),
    # ── 商业深度 (business) ──
    ("dailaoban", "饭统戴老板", "business",
     "https://wechat2rss.bestblogs.dev/feed/5f4c620560bd63023df9fb7d330aeee524e41676.xml"),
    ("wuxiaobo", "吴晓波频道", "business",
     "https://wechat2rss.bestblogs.dev/feed/604fd0bfbb0214958f7fd2718509e4ea038c6afc.xml"),
    ("liurun", "刘润", "business",
     "https://wechat2rss.bestblogs.dev/feed/c1354f67c314d25d6e236a58724043bdc46d6079.xml"),
    ("bijixia", "笔记侠", "business",
     "https://wechat2rss.bestblogs.dev/feed/4c5d9bcc2fbfcd1dc81fb67559653f8957ef4760.xml"),
    ("lishi", "砺石商业评论", "business",
     "https://wechat2rss.bestblogs.dev/feed/5cdd765d3973322da7992e0c919a99246fbcd0fc.xml"),
    ("hbr", "哈佛商业评论", "business",
     "https://wechat2rss.bestblogs.dev/feed/205f074dd6b962e0f4de876e9ebfe70a33bd8f66.xml"),
    ("zhenghedao", "正和岛", "business",
     "https://wechat2rss.bestblogs.dev/feed/1c03ed468f442bd1c16633c05cc39225884f468a.xml"),
    ("chuangyebang", "创业邦", "business",
     "https://wechat2rss.bestblogs.dev/feed/f5e0d8e342d9e2ec5b2942f08522cfaec17acc8d.xml"),
    ("pedaily", "投资界", "business",
     "https://wechat2rss.bestblogs.dev/feed/94251955e48961a24956ccb721652d02c75a75d0.xml"),
    ("anyong", "暗涌Waves", "business",
     "https://wechat2rss.bestblogs.dev/feed/bd586c1499b56aaec02dfefa87126232d234b010.xml"),
    ("jiubian", "九边", "business",
     "https://wechat2rss.bestblogs.dev/feed/b85be415c6565525bb31dffeceb24109bc5dfc77.xml"),
    ("caobian", "槽边往事", "business",
     "https://wechat2rss.bestblogs.dev/feed/0e8853d7a9fba6a4ed3556806c0ee832539a703e.xml"),
]

_BATCH_SIZE = 11
WECHAT2B_BATCHES: dict[str, list[tuple[str, str, str, str]]] = {
    f"w2{chr(ord('a') + i)}": WECHAT2B_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(WECHAT2B_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    category: str
    url: str


class Wechat2RssBatch2Crawler:
    """Sequentially crawl one batch of second-wave wechat2rss feeds.

    Parameters
    ----------
    batch_key:
        Key into :data:`WECHAT2B_BATCHES` (``"w2a"`` …). Unknown keys
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
        rows = WECHAT2B_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, category=c, url=u)
            for s, n, c, u in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "AD-Research wechat2rss batch2 crawler/1.0"},
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
                            # 行内 category（macro/strategy/industry/tech/
                            # business）落进 extra["category"]，
                            # normalizer._derive_category 会写入
                            # news_article.category（2026-08-02 接通）。
                            default_category=feed.category,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "wechat2rss batch2 %s: feed %s failed: %s",
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
