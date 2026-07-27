"""Batch crawler for independent non-WeChat voices (2026-07-27/28).

Why this exists
---------------
Second wave of the /goal 资讯源扩充: >=100 additional sources with an
independent voice — no official media, no government outlets, no
corporate PR channels. The first wave covered WeChat accounts via the
wechat2rss mirror (``wechat2rss_batch.py``) plus 13 English
blog/Substack feeds (``rss_simple.py``). This module covers everything
that is NOT behind WeChat:

* **English independent blogs / newsletters** — macro, markets, tech,
  geopolitics and essay writers (custom-domain Substacks and
  self-hosted blogs; ``*.substack.com`` itself is unreachable from the
  production network, so only custom domains were kept).
* **English independent podcasts** — investing / business shows with
  public RSS (shownotes land in ``description``).
* **Chinese independent blogs** — hand-picked from the public
  chinese-independent-blogs list by topic tag (创业 / 产品 / 投资 /
  读书 / 认知 / 人文 / 科技评论), then verified live.
* **Chinese independent podcasts** — 小宇宙 (xyzfm CDN), Fireside,
  喜马拉雅, 荔枝 and self-hosted feeds; personal or small-team shows.

Every feed below was curl-verified before inclusion: HTTP 200, valid
RSS/Atom, ``items > 0`` and a newest item within 30 days. See
``docs/dev-notes/20260728-independent-sources-batch.md`` for the full
evidence table.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``indie_{slug}`` so all four channels share one namespace.
* **Batched jobs**: like the wechat2rss mirror, the table is sliced
  into ~11-feed batches crawled sequentially with a polite delay —
  one scheduler job per batch instead of 100+ jobs.
* **No LLM marketing filter**: unlike the WeChat batches, these are
  curated editorial voices (same precedent as the 13 INDEPENDENT_RSS
  jobs, which also skip the filter), so the job writes directly after
  fetch. This keeps LLM cost flat as the source count grows.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language).
# source = "indie_{slug}".
INDEPENDENT_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── English independent blogs / newsletters (macro · markets · tech · geo) ──
    ("collabfund", "Collaborative Fund (Morgan Housel)", "https://collabfund.com/feed", "us", "en"),
    ("slowboring", "Slow Boring", "https://www.slowboring.com/feed", "us", "en"),
    ("stratechery", "Stratechery", "https://stratechery.com/feed", "us", "en"),
    ("notboring", "Not Boring", "https://www.notboring.co/feed", "us", "en"),
    ("generalist", "The Generalist", "https://www.generalist.com/feed", "us", "en"),
    ("platformer", "Platformer", "https://www.platformer.news/rss/", "us", "en"),
    ("bigtechnology", "Big Technology", "https://www.bigtechnology.com/feed", "us", "en"),
    ("oneusefulthing", "One Useful Thing", "https://www.oneusefulthing.org/feed", "us", "en"),
    ("importai", "Import AI", "https://jack-clark.net/feed/", "us", "en"),
    ("aisnakeoil", "AI Snake Oil", "https://www.normaltech.ai/feed", "us", "en"),
    ("bigstoller", "BIG by Matt Stoller", "https://www.thebignewsletter.com/feed", "us", "en"),
    ("lynalden", "Lyn Alden", "https://www.lynalden.com/feed/", "us", "en"),
    ("alphaarchitect", "Alpha Architect", "https://alphaarchitect.com/feed/", "us", "en"),
    ("priceactionlab", "Price Action Lab", "https://www.priceactionlab.com/Blog/feed", "us", "en"),
    ("abnormalreturns", "Abnormal Returns", "https://abnormalreturns.com/feed/", "us", "en"),
    ("financialsamurai", "Financial Samurai", "https://www.financialsamurai.com/feed/", "us", "en"),
    ("earlyretirementnow", "Early Retirement Now", "https://earlyretirementnow.com/feed/", "us", "en"),
    ("farnamstreet", "Farnam Street", "https://fs.blog/feed/", "us", "en"),
    ("intrinsicperspective", "The Intrinsic Perspective", "https://www.theintrinsicperspective.com/feed", "us", "en"),
    ("asteriskmag", "Asterisk Magazine", "https://asteriskmag.com/feed", "us", "en"),
    ("interconnected", "Interconnected (Matt Webb)", "https://interconnected.org/home/feed", "us", "en"),
    ("simonwillison", "Simon Willison", "https://simonwillison.net/atom/everything/", "us", "en"),
    ("juliaevans", "Julia Evans", "https://jvns.ca/atom.xml", "us", "en"),
    ("danluu", "Dan Luu", "https://danluu.com/atom.xml", "us", "en"),
    ("thedefiant", "The Defiant", "https://thedefiant.io/feed", "crypto", "en"),
    ("popularinfo", "Popular Information", "https://popular.info/feed", "us", "en"),
    ("investmentmoats", "Investment Moats", "https://investmentmoats.com/feed", "us", "en"),
    ("financialhorse", "Financial Horse", "https://financialhorse.com/feed/", "us", "en"),
    ("madfientist", "Mad Fientist", "https://www.madfientist.com/feed/", "us", "en"),
    ("physicianonfire", "Physician on FIRE", "https://www.physicianonfire.com/feed/", "us", "en"),
    ("whitecoatinvestor", "The White Coat Investor", "https://www.whitecoatinvestor.com/feed/", "us", "en"),
    ("obliviousinvestor", "Oblivious Investor", "https://obliviousinvestor.com/feed/", "us", "en"),
    ("retirementmanifesto", "The Retirement Manifesto", "https://www.theretirementmanifesto.com/feed/", "us", "en"),
    ("millennialrevolution", "Millennial Revolution", "https://www.millennial-revolution.com/feed/", "us", "en"),
    ("coachcarson", "Coach Carson", "https://www.coachcarson.com/feed/", "us", "en"),
    ("heisenbergreport", "Heisenberg Report", "https://heisenbergreport.com/feed/", "us", "en"),
    ("constructionphysics", "Construction Physics", "https://www.construction-physics.com/feed", "us", "en"),
    ("nintil", "Nintil", "https://nintil.com/rss.xml", "us", "en"),
    ("teachablemoment", "A Teachable Moment", "https://tonyisola.com/feed/", "us", "en"),
    ("bellecurve", "The Belle Curve", "https://blairbellecurve.com/feed/", "us", "en"),
    ("monevator", "Monevator", "https://monevator.com/feed/", "us", "en"),
    ("firevlondon", "FIRE v London", "https://firevlondon.com/feed/", "us", "en"),
    # ── English independent podcasts (investing / business / tech) ──
    ("rationalreminder", "Rational Reminder", "https://rationalreminder.libsyn.com/rss", "us", "en"),
    ("investlikethebest", "Invest Like the Best", "https://feeds.megaphone.fm/investlikethebest", "us", "en"),
    ("chatwithtraders", "Chat With Traders", "https://chatwithtraders.libsyn.com/rss", "us", "en"),
    ("lexfridman", "Lex Fridman Podcast", "https://lexfridman.com/feed/podcast/", "us", "en"),
    ("timferriss", "The Tim Ferriss Show", "https://rss.art19.com/tim-ferriss-show", "us", "en"),
    # ── Chinese independent blogs (well-known voices) ──
    ("ruanyifeng", "阮一峰的网络日志", "https://www.ruanyifeng.com/blog/atom.xml", "cn_a", "zh"),
    ("williamlong", "月光博客", "https://www.williamlong.info/rss.xml", "cn_a", "zh"),
    ("zhangxinxu", "张鑫旭-鑫空间", "https://www.zhangxinxu.com/wordpress/feed/", "cn_a", "zh"),
    ("devtang", "唐巧的博客", "https://blog.devtang.com/atom.xml", "cn_a", "zh"),
    ("codingnow", "云风的 BLOG", "https://blog.codingnow.com/atom.xml", "cn_a", "zh"),
    ("hongxian", "虹线", "https://1q43.blog/feed", "cn_a", "zh"),
    ("greatdk", "王登科-DK博客", "https://greatdk.com/feed", "cn_a", "zh"),
    # ── Chinese independent podcasts (小宇宙/喜马拉雅/Fireside/荔枝/自托管) ──
    ("mianji", "面基", "https://feed.xyzfm.space/6hpdgggtxpxb", "cn_a", "zh"),
    ("qizhulou", "起朱楼宴宾客", "https://feed.xyzfm.space/ahng8d9qlywl", "cn_a", "zh"),
    ("bannatie", "半拿铁 | 商业沉浮录", "https://proxy.wavpub.com/caffebreve.xml", "cn_a", "zh"),
    ("sanwuhuan", "三五环", "https://proxy.wavpub.com/35huan.xml", "cn_a", "zh"),
    ("luanfanshu", "乱翻书", "https://feed.xyzfm.space/yxuruh3f9mc4", "cn_a", "zh"),
    ("zhangxiaojun", "张小珺Jùn｜商业访谈录", "https://feed.xyzfm.space/dk4yh3pkpjp3", "cn_a", "zh"),
    ("taoban", "逃班｜Talking Band", "https://feed.xyzfm.space/yeuabxxl7ylm", "cn_a", "zh"),
    ("sv101", "硅谷101", "https://feeds.fireside.fm/sv101/rss", "cn_a", "zh"),
    ("kejizaozhidao", "What's Next｜科技早知道", "https://feeds.fireside.fm/guiguzaozhidao/rss", "cn_a", "zh"),
    ("shengdongjixi", "声东击西", "https://feeds.fireside.fm/shengdongjixi/rss", "cn_a", "zh"),
    ("beiwanglu", "贝望录", "http://www.ximalaya.com/album/42715423.xml", "cn_a", "zh"),
    ("storyfm", "故事FM", "https://feeds.storyfm.cn/storyfm.xml", "cn_a", "zh"),
    ("huzuohuyou", "忽左忽右", "https://feed.xyzfm.space/cv4bkgpuglwp", "cn_a", "zh"),
    ("wenhuayouxian", "文化有限", "https://s1.proxy.wavpub.com/weknownothing.xml", "cn_a", "zh"),
    ("daneimitan", "大内密谈", "http://rss.lizhi.fm/rss/14275.xml", "cn_a", "zh"),
    ("ritangongyuan", "日谈公园", "http://www.ximalaya.com/album/5574153.xml", "cn_a", "zh"),
    ("genyuzhoujiehun", "跟宇宙结婚", "http://rss.lizhi.fm/rss/1307862.xml", "cn_a", "zh"),
    ("mihuanchishu", "蜜獾吃书", "https://www.ximalaya.com/album/64689453.xml", "cn_a", "zh"),
    ("penti", "喷嚏", "https://feed.xyzfm.space/9unxvjbetgyu", "cn_a", "zh"),
    ("dongqiangxidiao", "东腔西调", "https://www.ximalaya.com/album/41153937.xml", "cn_a", "zh"),
    ("wuliaozhai", "无聊斋", "https://feed.xyzfm.space/njwyhpcjqn9t", "cn_a", "zh"),
    ("buheshiyi", "不合时宜", "https://feed.xyzfm.space/ww7cqnybekty", "cn_a", "zh"),
    ("waidazhengzhao", "洪晃播客｜歪打正着", "https://feed.xyzfm.space/tewruhycd3hp", "cn_a", "zh"),
    ("zonghengsihai", "纵横四海", "https://www.ximalaya.com/album/67531569.xml", "cn_a", "zh"),
    ("laidoulai", "来都来了", "http://www.ximalaya.com/album/31677988.xml", "cn_a", "zh"),
    ("heshiqitan", "核市奇谭", "https://alioss.gcores.com/feeds/heshi.xml", "cn_a", "zh"),
    ("shenjiao", "深焦DeepFocus Radio", "https://www.ximalaya.com/album/37990930.xml", "cn_a", "zh"),
    ("tianzhen", "天真不天真", "https://feed.xyzfm.space/mcklbwxjdvfu", "cn_a", "zh"),
    ("zitanzichang", "字谈字畅", "https://www.thetype.com/typechat/feed/", "cn_a", "zh"),
    ("bianjiaoliao", "边角聊", "https://feed.xyzfm.space/ug6camnfa6bu", "cn_a", "zh"),
    ("jinjinledao", "津津乐道", "http://www.ximalaya.com/album/3785430.xml", "cn_a", "zh"),
    ("zhankaijiangjiang", "展开讲讲", "http://www.ximalaya.com/album/24672021.xml", "cn_a", "zh"),
    # ── Chinese independent blogs (chinese-independent-blogs list, tag-curated) ──
    ("forecho", "forecho 的独立博客", "https://blog.forecho.com/atom.xml", "cn_a", "zh"),
    ("debuginn", "Debug客栈", "https://blog.debuginn.com/index.xml", "cn_a", "zh"),
    ("susheng", "素生", "https://z.arlmy.me/atom.xml", "cn_a", "zh"),
    ("tumutanzi", "土木坛子", "https://tumutanzi.com/feed", "cn_a", "zh"),
    ("life61", "61's life", "https://61.life/feed.xml", "cn_a", "zh"),
    ("lenciel", "Lenciel", "https://lenciel.com/feed.xml", "cn_a", "zh"),
    ("numb", "双绞麻痹", "https://numb.tech/atom.xml", "cn_a", "zh"),
    ("maxos", "maxOS", "https://maxoxo.me/rss/", "cn_a", "zh"),
    ("ioerr", "读写错误", "https://ioerr.github.io/index.xml", "cn_a", "zh"),
    ("gtdstudy", "学无止境@一点一滴", "http://www.gtdstudy.com/index.xml", "cn_a", "zh"),
    ("skyue", "SKYue's Home", "https://www.skyue.com/feed/", "cn_a", "zh"),
    ("yinji", "印记", "https://yinji.org/feed", "cn_a", "zh"),
    ("conge", "conge", "https://conge.livingwithfcs.org/feed.xml", "cn_a", "zh"),
    ("leonhe", "远飞闲记", "https://leonhe.cn/index.xml", "cn_a", "zh"),
    ("owenyoung", "Owen的博客", "https://www.owenyoung.com/feed", "cn_a", "zh"),
    ("lhcy", "林海草原", "https://lhcy.org/feed", "cn_a", "zh"),
    ("kqh", "赫赫文王", "https://kqh.me/index.xml", "cn_a", "zh"),
    ("macin", "Macin", "https://macin.org/atom.xml", "cn_a", "zh"),
    ("jfsay", "静风说", "https://www.jfsay.com/feed", "cn_a", "zh"),
    ("xianrenlife", "闲人Life", "https://www.xianrenlife.com/feeds/posts/default", "cn_a", "zh"),
    ("dongjunke", "东评西就", "https://dongjunke.cn/atom.xml", "cn_a", "zh"),
    ("demochen", "特立独行的异类", "https://demochen.com/atom.xml", "cn_a", "zh"),
    ("raymondhouch", "雷蒙三十", "https://raymondhouch.com/feed/", "cn_a", "zh"),
    ("chaoniulian", "骑行超过牛", "https://www.chaoniulian.com/rss/", "cn_a", "zh"),
    ("bluehe", "云心怀鹤", "https://bluehe.cn/feed/", "cn_a", "zh"),
    ("cosmopolite", "Cosmos的博客", "https://cosmo-polite.com/feed/", "cn_a", "zh"),
    ("sehnsucht", "Sehnsucht", "https://blog.sehnsucht.top/rss.xml", "cn_a", "zh"),
    ("kangaroogao", "Maohang Gao's Blog", "https://kangaroogao.com/atom.xml", "cn_a", "zh"),
    ("jiangcl", "蒙需", "https://jiangcl.com/feed", "cn_a", "zh"),
    ("citydatum", "橙树志", "https://citydatum.cn/feed", "cn_a", "zh"),
    ("mingnify", "明立非 Mingnify", "https://mingnify.com/zh/blog/atom.xml", "cn_a", "zh"),
    ("whyya", "小陶持续精进", "https://whyya.xyz/rss.xml", "cn_a", "zh"),
    ("jaketao", "Jake Blog", "https://jaketao.com/feed/", "cn_a", "zh"),
    ("giveanornot", "資工小廢物 JN", "https://blog.giveanornot.com/index.xml", "cn_a", "zh"),
    ("qingccl", "QingCCL", "https://qingccl.com/rss.xml", "cn_a", "zh"),
    ("fengcan", "创见思考", "https://www.fengcan.net/feed/", "cn_a", "zh"),
    ("leesaitool", "Arthur's Review", "https://blog.leesaitool.com/feed.xml", "cn_a", "zh"),
    ("wjd", "王佳冬中文博客", "http://wjd.name/feed/", "cn_a", "zh"),
    ("baicai", "白菜", "https://blog.baicai.me/index.xml", "cn_a", "zh"),
    ("hutusi", "胡涂说", "https://hutusi.com/feed.xml", "cn_a", "zh"),
    ("kanchuan", "陈看川博客", "https://kanchuan.com/feed.xml", "cn_a", "zh"),
    ("wocai", "kok的笔记本", "https://wocai.de/index.xml/", "cn_a", "zh"),
    ("xiaket", "年华转瞬", "https://blog.xiaket.org/feed.xml", "cn_a", "zh"),
    ("wangjiezhe", "如鱼饮水", "https://wangjiezhe.com/atom.xml", "cn_a", "zh"),
    ("mecll", "流浪天下", "https://mecll.com/feed", "cn_a", "zh"),
    ("styunlen", "九仞之行", "https://styunlen.cn/feed", "cn_a", "zh"),
    ("sion", "子虚栈", "https://blog.si-on.top/atom.xml", "cn_a", "zh"),
    ("trumandu", "TrumanDu 博客", "http://blog.trumandu.top/atom.xml", "cn_a", "zh"),
    ("domon", "Domon", "https://www.domon.cn/rss/", "cn_a", "zh"),
    ("zhheo", "张洪Heo", "https://blog.zhheo.com/rss.xml", "cn_a", "zh"),
    ("taoshu", "涛叔", "https://tao.zz.ac/feed.xml", "cn_a", "zh"),
    ("chegva", "安志合的学习博客", "https://chegva.com/feed/", "cn_a", "zh"),
    ("tianheg", "一大加贝", "https://tianheg.co/index.xml", "cn_a", "zh"),
    ("ourai", "欧雷流", "https://ourai.ws/atom.xml", "cn_a", "zh"),
    ("cyrusyip", "叶寻的博客", "https://cyrusyip.org/zh-cn/index.xml", "cn_a", "zh"),
    ("lyunvy", "Lyunvy's Blog", "https://blog.lyunvy.top/atom.xml", "cn_a", "zh"),
    ("cheshirex", "柴郡猫", "https://www.cheshirex.com/feed", "cn_a", "zh"),
    ("hehysh", "十贰的小窝", "https://hehysh.github.io/atom.xml", "cn_a", "zh"),
]

_BATCH_SIZE = 11
INDEPENDENT_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    chr(ord("a") + i): INDEPENDENT_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(INDEPENDENT_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class IndependentBatchCrawler:
    """Sequentially crawl one batch of independent RSS/Atom feeds.

    Mirrors :class:`Wechat2RssBatchCrawler` but each table row carries
    its own ``market`` / ``language`` because the batch mixes Chinese
    and English sources. Unknown batch keys yield an empty crawl
    (defensive — a config typo must never crash the scheduler).
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
        rows = INDEPENDENT_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, url=u, market=m, language=lang)
            for s, n, u, m, lang in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "AD-Research independent batch crawler/1.0"},
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
                            source=f"indie_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "independent batch %s: feed %s failed: %s",
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
