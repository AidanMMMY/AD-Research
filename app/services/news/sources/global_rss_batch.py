"""Global multi-language RSS batch crawler (second source-expansion wave).

Why this exists (2026-07-27, /goal 资讯源扩充 — agent B)
-------------------------------------------------------
Complements ``wechat2rss_batch`` (WeChat OA mirror accounts) and
``INDEPENDENT_RSS_JOBS`` (13 English independent blogs/Substacks) with
**multi-language** high-quality feeds (125 live-verified): Japanese / German / French /
Korean / Spanish publications plus a second wave of English central-bank,
think-tank, university and engineering-team blogs, plus Chinese
non-blog industry press.

Every feed in :data:`GLOBAL_RSS_FEEDS` was live-verified at table time
(curl → HTTP 200, valid RSS/Atom, ≥1 item, average body >200 chars over
the first 10 items, newest item within 30 days). Feeds that ship only
headlines (common for Japanese media) were rejected — the ingest
pipeline needs a real body for the Chinese translation pass.

Design notes
------------
* **Table-driven**: one row per feed ``(slug, display_name, feed_url,
  language, market)``. ``source`` becomes ``global_{slug}`` so the News
  page / health grid can distinguish this wave from ``wechat_*`` and
  the ``rss_simple`` sources.
* **Batched jobs**: 132 feeds as 132 scheduler jobs would drown the
  health grid and amplify the APScheduler misfire problem (see the
  20260727 runbook §2). The table is sliced into
  :data:`GLOBAL_RSS_BATCHES` groups (11 feeds each); one scheduler job
  crawls one group sequentially with a polite inter-feed delay.
* **Language/market are per-feed** (unlike the wechat2rss crawler where
  they are class constants) — the translation drain picks up every
  non-Chinese language automatically (``translation_service`` only
  excludes Chinese variants).
* **Selection rule**: no Substack / RSSHub / podcast / WeChat channels
  (assigned to the parallel expansion agent), no overlap with the 13
  ``INDEPENDENT_RSS_JOBS`` blogs or the existing media sources, and no
  feeds whose bodies are headline-length.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, language, market). source = "global_{slug}".
GLOBAL_RSS_FEEDS: list[tuple[str, str, str, str, str]] = [
    ("freee_dev", "freee Developers Blog", "https://developers.freee.co.jp/feed", "ja", "us"),
    ("huffpost_jp", "ハフポスト日本版", "https://www.huffingtonpost.jp/feeds/index.xml", "ja", "us"),
    ("moneyforward_dev", "Money Forward Developers", "https://moneyforward-dev.jp/feed", "ja", "us"),
    ("publickey", "Publickey", "https://www.publickey1.jp/atom.xml", "ja", "us"),
    ("sirabee", "Sirabee", "https://sirabee.com/feed/", "ja", "us"),
    ("zozo_tech", "ZOZO Tech Blog", "https://techblog.zozo.com/feed", "ja", "us"),
    ("zuuonline", "ZUU online", "https://zuuonline.com/feed", "ja", "us"),
    ("computerwoche", "Computerwoche", "https://www.computerwoche.de/rss/", "de", "us"),
    ("der_bank_blog", "Der Bank Blog", "https://www.der-bank-blog.de/feed/", "de", "us"),
    ("finanzrocker", "Finanzrocker", "https://www.finanzrocker.net/feed/", "de", "us"),
    ("mobilegeeks_de", "MobileGeeks", "https://www.mobilegeeks.de/feed/", "de", "us"),
    ("netzpolitik", "netzpolitik.org", "https://netzpolitik.org/feed/", "de", "us"),
    ("neunetz", "neunetz", "https://neunetz.com/feed/", "de", "us"),
    ("t3n", "t3n Magazin", "https://t3n.de/rss.xml", "de", "us"),
    ("bfm_eco", "BFM Économie", "https://www.bfmtv.com/rss/economie/", "fr", "us"),
    ("bfmtv", "BFM TV", "https://www.bfmtv.com/rss/news-24-7/", "fr", "us"),
    ("challenges", "Challenges", "https://www.challenges.fr/rss.xml", "fr", "us"),
    ("clubic", "Clubic", "https://www.clubic.com/feed/rss", "fr", "us"),
    ("courrierinter", "Courrier International", "https://www.courrierinternational.com/feed/all/rss.xml", "fr", "us"),
    ("developpez", "Developpez.com", "https://www.developpez.com/rss.php", "fr", "us"),
    ("france24", "France 24", "https://www.france24.com/fr/rss", "fr", "us"),
    ("lalibre", "La Libre Belgique", "https://www.lalibre.be/rss", "fr", "us"),
    ("lesnumeriques", "Les Numériques", "https://www.lesnumeriques.com/rss.xml", "fr", "us"),
    ("next_ink", "next.ink (ex-Next INpact)", "https://next.ink/feed/", "fr", "us"),
    ("ouestfrance", "Ouest-France", "https://www.ouest-france.fr/rss/une", "fr", "us"),
    ("valeurs", "Valeurs Actuelles", "https://www.valeursactuelles.com/rss", "fr", "us"),
    ("chosun", "조선일보", "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml", "ko", "us"),
    ("coindeskkorea", "코인데스크코리아", "https://www.coindeskkorea.com/rss", "ko", "us"),
    ("donga", "동아일보", "https://rss.donga.com/total.xml", "ko", "us"),
    ("etnews", "전자신문", "https://rss.etnews.com/Section901.xml", "ko", "us"),
    ("nocutnews", "노컷뉴스", "https://rss.nocutnews.co.kr/nocutnews.xml", "ko", "us"),
    ("ohmynews", "오마이뉴스", "https://rss.ohmynews.com/rss/ohmynews.xml", "ko", "us"),
    ("sbs_news", "SBS 뉴스", "https://news.sbs.co.kr/news/TopicRssFeed.do?plink=RSSREADER", "ko", "us"),
    ("tokenpost", "토큰포스트", "https://www.tokenpost.kr/rss", "ko", "us"),
    ("20minutos_es", "20minutos", "https://www.20minutos.es/rss/", "es", "us"),
    ("elblogsalmon", "El Blog Salmón", "https://www.elblogsalmon.com/index.xml", "es", "us"),
    ("eldiario", "eldiario.es", "https://www.eldiario.es/rss/", "es", "us"),
    ("elfinanciero_mx", "El Financiero (MX)", "https://www.elfinanciero.com.mx/rss/", "es", "us"),
    ("expansion", "Expansión", "https://e00-expansion.uecdn.es/rss/portada.xml", "es", "us"),
    ("hiperderecho", "Derecho Digital", "https://hiperderecho.org/feed/", "es", "us"),
    ("hipertextual", "Hipertextual", "https://hipertextual.com/feed", "es", "us"),
    ("lanacion", "La Nación (AR)", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", "es", "us"),
    ("latercera", "La Tercera", "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml", "es", "us"),
    ("microsiervos", "Microsiervos", "https://microsiervos.com/index.xml", "es", "us"),
    ("wwwhatsnew", "WWWhatsnew", "https://wwwhatsnew.com/feed/", "es", "us"),
    ("xataka", "Xataka", "https://www.xataka.com/index.xml", "es", "us"),
    ("acquirers_multiple", "The Acquirer's Multiple", "https://acquirersmultiple.com/feed/", "en", "us"),
    ("american_compass", "American Compass", "https://americancompass.org/feed/", "en", "us"),
    ("android_dev", "Android Developers Blog", "https://android-developers.googleblog.com/feeds/posts/default", "en", "us"),
    ("apple_ml", "Apple Machine Learning Research", "https://machinelearning.apple.com/rss.xml", "en", "us"),
    ("arstechnica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "en", "us"),
    ("automatic_earth", "The Automatic Earth", "https://www.theautomaticearth.com/feed", "en", "us"),
    ("aws_blog", "AWS News Blog", "https://aws.amazon.com/blogs/aws/feed/", "en", "us"),
    ("axios", "Axios", "https://api.axios.com/feed/top/", "en", "us"),
    ("bankunderground", "Bank Underground (BoE)", "https://bankunderground.co.uk/feed/", "en", "us"),
    ("brooker", "Marc Brooker's Blog", "https://brooker.co.za/blog/rss.xml", "en", "us"),
    ("business_insider", "Business Insider", "https://www.businessinsider.com/rss", "en", "us"),
    ("chainalysis_blog", "Chainalysis Blog", "https://www.chainalysis.com/blog/feed/", "en", "us"),
    ("cloudflare_blog", "Cloudflare Blog", "https://blog.cloudflare.com/rss/", "en", "us"),
    ("cncf_blog", "CNCF Blog", "https://www.cncf.io/feed/", "en", "us"),
    ("contra_corner", "David Stockman's Contra Corner", "https://davidstockmanscontracorner.com/feed/", "en", "us"),
    ("conversable_economist", "Conversable Economist (Timothy Taylor)", "https://conversableeconomist.com/feed/", "en", "us"),
    ("dropbox_tech", "Dropbox.Tech", "https://dropbox.tech/feed", "en", "us"),
    ("econlib", "EconLog / Econlib", "https://www.econlib.org/feed/", "en", "us"),
    ("financial_post", "Financial Post", "https://financialpost.com/feed/", "en", "us"),
    ("flyio_blog", "Fly.io Blog", "https://fly.io/blog/feed.xml", "en", "us"),
    ("fortune", "Fortune", "https://fortune.com/feed/", "en", "us"),
    ("github_blog", "The GitHub Blog", "https://github.blog/feed/", "en", "us"),
    ("grumpy_economist", "The Grumpy Economist (John Cochrane)", "https://www.grumpy-economist.com/feed", "en", "us"),
    ("guardian_business", "The Guardian Business", "https://www.theguardian.com/uk/business/rss", "en", "us"),
    ("hashicorp_blog", "HashiCorp Blog", "https://www.hashicorp.com/blog/feed.xml", "en", "us"),
    ("heritage", "Heritage Foundation", "https://www.heritage.org/rss", "en", "us"),
    ("heroku_blog", "Heroku Blog", "https://blog.heroku.com/feed", "en", "us"),
    ("honeycomb_blog", "Honeycomb Blog", "https://www.honeycomb.io/feed/", "en", "us"),
    ("incrementum", "Incrementum", "https://www.incrementum.li/en/feed/", "en", "us"),
    ("infoq_en", "InfoQ", "https://feed.infoq.com/", "en", "us"),
    ("international_man", "International Man (Doug Casey)", "https://internationalman.com/feed/", "en", "us"),
    ("jamestown", "Jamestown Foundation", "https://jamestown.org/feed/", "en", "us"),
    ("jetbrains_blog", "JetBrains Blog", "https://blog.jetbrains.com/feed/", "en", "us"),
    ("koreatimes", "The Korea Times", "https://www.koreatimes.co.kr/www/rss/rss.xml", "en", "us"),
    ("kubernetes_blog", "Kubernetes Blog", "https://kubernetes.io/feed.xml", "en", "us"),
    ("liberty_street", "Liberty Street Economics (NY Fed)", "https://libertystreeteconomics.newyorkfed.org/feed/", "en", "us"),
    ("lse_business", "LSE Business Review", "https://blogs.lse.ac.uk/businessreview/feed/", "en", "us"),
    ("martinfowler", "Martin Fowler", "https://martinfowler.com/feed.atom", "en", "us"),
    ("meta_engineering", "Engineering at Meta", "https://engineering.fb.com/feed/", "en", "us"),
    ("mozilla_blog", "Mozilla Blog", "https://blog.mozilla.org/en/feed/", "en", "us"),
    ("msft_blog", "Microsoft Blog", "https://blogs.microsoft.com/feed/", "en", "us"),
    ("msft_research", "Microsoft Research Blog", "https://www.microsoft.com/en-us/research/feed/", "en", "us"),
    ("nber", "NBER", "https://back.nber.org/rss/new.xml", "en", "us"),
    ("netflix_tech", "Netflix TechBlog", "https://netflixtechblog.com/feed", "en", "us"),
    ("niskanen", "Niskanen Center", "https://www.niskanencenter.org/feed/", "en", "us"),
    ("nvidia_blog", "NVIDIA Blog", "https://blogs.nvidia.com/feed/", "en", "us"),
    ("nvidia_dev", "NVIDIA Technical Blog", "https://developer.nvidia.com/blog/feed/", "en", "us"),
    ("pewresearch", "Pew Research Center", "https://www.pewresearch.org/feed/", "en", "us"),
    ("postman_blog", "Postman Blog", "https://blog.postman.com/feed/", "en", "us"),
    ("project_syndicate", "Project Syndicate", "https://www.project-syndicate.org/rss", "en", "us"),
    ("promarket", "ProMarket (Chicago Booth)", "https://www.promarket.org/feed/", "en", "us"),
    ("prometheus_blog", "Prometheus Blog", "https://prometheus.io/blog/feed.xml", "en", "us"),
    ("quantocracy", "Quantocracy", "https://quantocracy.com/feed/", "en", "us"),
    ("realinvestmentadvice", "Real Investment Advice (Lance Roberts)", "https://realinvestmentadvice.com/feed/", "en", "us"),
    ("reason", "Reason", "https://reason.com/feed/", "en", "us"),
    ("rust_blog", "Rust Blog", "https://blog.rust-lang.org/feed.xml", "en", "us"),
    ("scmp_business", "SCMP Business", "https://www.scmp.com/rss/4/feed", "en", "us"),
    ("slack_eng", "Slack Engineering", "https://slack.engineering/feed/", "en", "us"),
    ("sovereign_man", "Sovereign Man (Simon Black)", "https://www.sovereignman.com/feed/", "en", "us"),
    ("spectrum_ieee", "IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "en", "us"),
    ("spotify_eng", "Spotify Engineering", "https://engineering.atspotify.com/feed/", "en", "us"),
    ("stackoverflow_blog", "The Stack Overflow Blog", "https://stackoverflow.blog/feed/", "en", "us"),
    ("stripe_blog", "Stripe Blog", "https://stripe.com/blog/feed.rss", "en", "us"),
    ("taxfoundation", "Tax Foundation", "https://taxfoundation.org/feed/", "en", "us"),
    ("technologyreview", "MIT Technology Review", "https://www.technologyreview.com/feed/", "en", "us"),
    ("thenewstack", "The New Stack", "https://thenewstack.io/feed/", "en", "us"),
    ("theverge", "The Verge", "https://www.theverge.com/rss/index.xml", "en", "us"),
    ("vercel_blog", "Vercel Blog", "https://vercel.com/atom", "en", "us"),
    ("vox", "Vox", "https://www.vox.com/rss/index.xml", "en", "us"),
    ("war_on_the_rocks", "War on the Rocks", "https://warontherocks.com/feed/", "en", "us"),
    ("webkit_blog", "WebKit Blog", "https://webkit.org/feed/", "en", "us"),
    ("cyzone", "创业邦", "https://www.cyzone.cn/rss/", "zh", "cn_a"),
    ("eastmoney_rss", "东方财富网", "https://rss.eastmoney.com/rss_partener.xml", "zh", "cn_a"),
    ("ifanr", "爱范儿", "https://www.ifanr.com/feed", "zh", "cn_a"),
    ("ithome_cn", "IT之家", "https://www.ithome.com/rss/", "zh", "cn_a"),
    ("leiphone", "雷峰网", "https://www.leiphone.com/feed", "zh", "cn_a"),
    ("segmentfault", "SegmentFault", "https://segmentfault.com/feeds", "zh", "cn_a"),
    ("solidot", "Solidot 奇客", "https://www.solidot.org/index.rss", "zh", "cn_a"),
    ("tmtpost", "钛媒体", "https://www.tmtpost.com/rss.xml", "zh", "cn_a"),
]

_BATCH_SIZE = 11
GLOBAL_RSS_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    chr(ord("a") + i): GLOBAL_RSS_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(GLOBAL_RSS_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}

# 已知时区标注错误的 feed（2026-08-01 生产事故排查结论）：
# nocutnews 的 <dc:date> 是韩国本地墙钟时间（KST, UTC+9）却标注 "GMT"，
# 解析器按字面信任 GMT 后入库即比真实 UTC 快 9 小时，前端 +8 显示成
# "未来时间"。对命中此映射的 feed，解析时忽略其自带时区标注，按此处
# 指定的发行方本地时区重新解释墙钟时间。新增条目前务必先 curl 该
# feed 对比实时 UTC 确认是"标注错误"而非"定时发布"。
GLOBAL_RSS_TZ_OVERRIDE: dict[str, str] = {
    "nocutnews": "Asia/Seoul",
}


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    language: str
    market: str


class GlobalRssBatchCrawler:
    """Sequentially crawl one batch of global multi-language feeds.

    Parameters
    ----------
    batch_key:
        Key into :data:`GLOBAL_RSS_BATCHES` (``"a"`` …). Unknown keys
        yield an empty crawl (defensive — a config typo must never
        crash the scheduler).
    delay_seconds:
        Polite pause between feeds; several feeds are community blogs
        on shared infrastructure.
    """

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
        rows = GLOBAL_RSS_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, url=u, language=row, market=m)
            for s, n, u, row, m in rows
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
                    # 时区标注错误的 feed（见 GLOBAL_RSS_TZ_OVERRIDE）按
                    # 发行方本地时区重新解释墙钟时间。
                    tz_override = (
                        ZoneInfo(GLOBAL_RSS_TZ_OVERRIDE[feed.slug])
                        if feed.slug in GLOBAL_RSS_TZ_OVERRIDE
                        else None
                    )
                    out.extend(
                        parse_rss_items(
                            resp.text,
                            source=f"global_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                            tz_override=tz_override,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "global rss batch %s: feed %s failed: %s",
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
