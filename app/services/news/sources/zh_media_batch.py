"""Batch crawler for Chinese mainstream media + Japan/Korea + SEA + crypto increment (2026-08-02).

Why this exists
---------------
资讯源扩容 C 组 — the wave *after* the ">=100 中文圈独立思考资讯源" goal
was reached (wechat_* x100 + zhx_* podcasts x40 + zhb_* blogs x38).
This wave is pure **increment**, not part of that count: Chinese
mainstream media that still publishes native RSS (HK/TW mostly — the
mainland portals are RSS-dead, see rejections below), Japanese/Korean
original-language media, Southeast-Asian English outlets, and a second
crypto pass beyond the existing coindesk/cointelegraph/decrypt/
defiant/unchained set.

Selection rule
--------------
* Every feed below was live-verified **from the production ECS**
  (mainland China network) on 2026-08-01/02 in three candidate rounds
  (~260 URLs tried): HTTP 200 with a desktop browser UA, body >5KB,
  valid RSS/Atom parseable by ``xml.etree`` (and spot-checked through
  ``rss_common.parse_rss_items``), newest item within 30 days, >=5
  items. Native RSS/Atom only — no RSSHub (public instances unreachable
  from production, established in the podcast wave).
* Zero overlap: URLs and slugs were deduped against every table under
  ``app/services/news/sources/`` and ``scheduler_jobs.py`` — 14 verified-
  alive candidates were dropped *solely* because an earlier wave already
  carries them (chosun/donga/etnews/publickey in ``global_rss_batch``,
  sinocism in ``global_indie_batch``, bworldonline/vulcanpost/khaosod in
  ``asia_en_batch``, cyzone/ifanr/leiphone in ``global_rss_batch``,
  jisilu in ``wechat2rss_batch``, sspai in ``wechat2rss_batch2``,
  techsauce in ``global_indie_batch``).
* Crypto tabloids with price-prediction/clickbait-heavy front pages
  (Coinpedia, CryptoNewsZ, CoinChapter, The Coin Republic, NullTX,
  Live Bitcoin News) passed the network test but were rejected on
  editorial quality — same "no 标题党/纯营销" bar as the earlier waves.

Market/language notes
---------------------
* ``market`` is one of ``cn_a`` / ``us`` / ``crypto`` — the news API's
  ``_GLOBAL_MARKETS`` whitelist (``app/api/v1/news.py``). The task brief
  said "日韩东南亚=global", but ``market="global"`` is *invisible* in
  the frontend's default view (established in ``asia_en_batch.py``'s
  docstring), so JP/KR/SEA rows use ``us``, same precedent as
  ``asen_*``.
* ``language`` is the feed's actual language: zh (incl. HK/TW
  traditional — the ingest layer already OpenCC t2s-converts), ja, ko,
  or en. Non-zh rows flow through the auto-translate drain that is
  already live.

Per-feed caveats discovered during verification
-----------------------------------------------
* ``nikkeiasia`` (Nikkei Asia) is RSS 1.0/RDF and carries **no item
  dates** — ``rss_common`` fills ``published_at`` with fetch time;
  freshness was verified by reading the current-day headlines in the
  feed (2026-08-01). Dedup by URL keeps the hourly re-stamp harmless.
* ``mt`` (Money Today) and ``gvm`` (遠見) are total-feed business
  outlets — their feeds mix in lifestyle/entertainment items; kept for
  the business core, same precedent as the general dailies.
* ``sspai``/``coolloud`` cadence is daily-ish; everything else updates
  many times per day.

Rejections worth remembering (verified dead/blocked from ECS 2026-08-01/02)
---------------------------------------------------------------------------
Mainland (RSS-dead or portal HTML): 第一财经, 观察者网, 网易财经,
凤凰网, 和讯, 南方周末, 经济观察网(403), 格隆汇, 智通财经(500), 每经,
中金在线, 金融界, 科创板日报, 中国经济网, 证券时报, 上证报, 中证网,
21财经, 澎湃, 中国经营网(521), 财经杂志, 搜狐财经, 亿邦动力, 亿欧,
中国基金报, 机器之心(HTML), 快科技(404), 差评(502), 南风窗,
三联生活周刊(timeout), Global Times.
HK/TW: 信报(403), 明报, 经济通, am730(403), Now财经, 风传媒(HTML),
工商时报(403), 联合系(403), 钜亨网(404/406), 今周刊/商周(HTML),
财讯(stale 2026-06), 自由时报(404/HTML), 新头壳, 上报, 镜周刊主域
(only /rss/rss.xml works), NOWnews, 民视(403), 公视(404), 中时(404),
TOPick(404), AASTOCKS(HTML), 东网(403), 点新闻(403), 橙新闻(403),
巴士的报(404), INSIDE(404), Smart智富(404), 上下游(403),
环境资讯中心(404), ETtoday(404).
Japan: 共同通信(403), 时事通信(403), ZDNet Japan(404), Diamond(HTML),
Newsweek Japan(404), Forbes Japan(404), President(404), JBpress(404),
CNET Japan(301/404), Mynavi(404), The Bridge(403), Gihyo(404).
Korea: 中央日报(too small), 韩国经济(403), 每日经济(403), Bloter(403),
Edaily(timeout), 亚洲经济(404), ZDNet Korea(404), IT조선(403),
文化日报(timeout), 首尔新闻(403), Newsis(HTML), DT(404), 首尔经济(HTML),
Financial News(HTML), AsiaToday(403), Digital Today(403),
세계일보(502), YTN(404), 국민일보(timeout), Korea Herald(HTML/420B),
Korea JoongAng Daily(404).
SEA: The Business Times(HTML), The Edge SG(403), The Edge MY(404),
DealStreetAsia(503 twice), KrASIA(HTML), TechNode(403), The Star(404),
Jakarta Post(404), Bangkok Post(451 geo-block), Philstar(403),
Asean Post(404), Tech Collective(403), VIR(404), FMT(403),
Borneo Post(403), Tempo(403), Antara(HTML), Jakarta Globe(404),
VietnamPlus(404), Vietnam News(403), Saigoneer(HTML), Tuoi Tre(timeout),
Prachatai(HTML), Irrawaddy(403), Frontier(403), Manila Bulletin(403),
BusinessMirror(403), TODAY SG(timeout), Mothership(invalid XML),
AsiaOne(404), Asia Tech Daily(403), TechWire Asia(timeout).
Crypto: The Block(403), Bankless(timeout), CryptoSlate(403),
Bitcoin Magazine(403), CoinGape(403), AMBCrypto(403), Blockworks(feed
frozen 2026-01), DL News(closing 2026-05), Wu Blockchain substack(1
stale 2021 item), PANews(HTML), 深潮TechFlow(404), MarsBit(404),
Coinness(timeout), 律动BlockBeats(404), 链得得(timeout), 巴比特(timeout),
ChainCatcher(404), Bloomingbit(404), Decenter(404), Cointelegraph
KR/JP(410 gone), CoinPost(stale 2024), 仮想通貨Watch(404), a16z
crypto(404), Paradigm(404), Rekt(500), Coinbase blog(403),
Glassnode(403), Blockonomi(403), Messari(404), Milk Road(HTML),
CMC Academy(404), Inside Bitcoins(stale 2026-02).

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``zhm_{slug}`` — own namespace alongside ``wechat_*``, ``indie_*``,
  ``global_*``, ``gind_*``, ``asen_*``, ``zhx_*`` and ``zhb_*``.
* **Batches restart at "a"**: the job namespace ``news_zhm_*`` is
  unique, so this table is sliced into batches ``a``-``f`` of <=10.
* **No LLM marketing filter**: curated editorial voices, same precedent
  as every earlier batch wave — the scheduler job writes directly after
  fetch, keeping LLM cost flat.
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

# (slug, display_name, feed_url, market, language). source = "zhm_{slug}".
ZH_MEDIA_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 港台中文媒体（大陆门户原生 RSS 已全灭，见模块 docstring 淘汰清单） ──
    ("rthk_finance", "香港电台 财经", "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml", "cn_a", "zh"),
    ("rthk_local", "香港电台 本地", "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml", "cn_a", "zh"),
    ("stheadline", "星岛日报", "https://std.stheadline.com/rss", "cn_a", "zh"),
    ("twreporter", "报导者", "https://www.twreporter.org/a/rss2.xml", "cn_a", "zh"),
    ("techorange", "科技报橘", "https://buzzorange.com/techorange/feed/", "cn_a", "zh"),
    ("gvm", "远见杂志", "https://www.gvm.com.tw/rss", "cn_a", "zh"),
    ("thenewslens", "关键评论网", "https://feeds.feedburner.com/TheNewsLens", "cn_a", "zh"),
    # 镜周刊：主域 /rss 404，仅 /rss/rss.xml 有效
    ("mirrormedia", "镜周刊", "https://www.mirrormedia.mg/rss/rss.xml", "cn_a", "zh"),
    ("coolloud", "苦劳网", "https://www.coolloud.org.tw/rss.xml", "cn_a", "zh"),
    ("infoqcn", "InfoQ 中文", "https://www.infoq.cn/feed", "cn_a", "zh"),
    # ── 大陆存活媒体 / 英文视角看中国 ──
    ("timeweekly", "时代周报", "https://www.time-weekly.com/rss", "cn_a", "zh"),
    ("chinamoneynet", "China Money Network", "https://www.chinamoneynetwork.com/feed", "cn_a", "en"),
    # ── 日本媒体（日语） ──
    ("nhk_top", "NHK 主要新闻", "https://www3.nhk.or.jp/rss/news/cat0.xml", "us", "ja"),
    ("nhk_econ", "NHK 经济新闻", "https://www3.nhk.or.jp/rss/news/cat6.xml", "us", "ja"),
    ("itmedia", "ITmedia", "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "us", "ja"),
    ("itmedia_ent", "ITmedia Enterprise", "https://rss.itmedia.co.jp/rss/2.0/enterprise.xml", "us", "ja"),
    ("impress", "Impress Watch", "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "us", "ja"),
    ("internetwatch", "INTERNET Watch", "https://internet.watch.impress.co.jp/data/rss/1.0/iw/feed.rdf", "us", "ja"),
    ("madonomori", "窓の杜", "https://forest.watch.impress.co.jp/data/rss/1.0/wf/feed.rdf", "us", "ja"),
    ("toyokeizai", "东洋经济", "https://toyokeizai.net/list/feed/rss", "us", "ja"),
    ("asahi", "朝日新闻", "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "us", "ja"),
    ("mainichi", "每日新闻", "https://mainichi.jp/rss/etc/mainichi-flash.rss", "us", "ja"),
    ("sankei", "产经新闻", "https://www.sankei.com/arc/outboundfeeds/rss/?outputType=xml", "us", "ja"),
    ("wiredjp", "WIRED Japan", "https://wired.jp/rssfeeder/", "us", "ja"),
    ("gizmodojp", "Gizmodo Japan", "https://www.gizmodo.jp/index.xml", "us", "ja"),
    ("asciijp", "ASCII.jp", "https://ascii.jp/rss.xml", "us", "ja"),
    ("codezine", "CodeZine", "https://codezine.jp/rss/new/20/index.xml", "us", "ja"),
    # ── 日本媒体（英文） ──
    ("nippon", "Nippon.com", "https://www.nippon.com/en/feed/", "us", "en"),
    ("japantimes", "The Japan Times", "https://www.japantimes.co.jp/feed/", "us", "en"),
    # nikkeiasia：RSS 1.0 无条目日期，published_at 回填抓取时间（见 docstring）
    ("nikkeiasia", "Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar", "us", "en"),
    # ── 韩国媒体 ──
    ("yna", "韩联社", "https://www.yna.co.kr/rss/news.xml", "us", "ko"),
    ("khan", "京乡新闻", "https://www.khan.co.kr/rss/rssdata/total_news.xml", "us", "ko"),
    ("mt", "Money Today", "https://rss.mt.co.kr/mt_news.xml", "us", "ko"),
    ("yna_en", "Yonhap News English", "https://en.yna.co.kr/RSS/news.xml", "us", "en"),
    # ── 东南亚英文 ──
    ("cna_biz", "CNA Business", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936", "us", "en"),
    ("cna_asia", "CNA Asia", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311", "us", "en"),
    ("techinasia", "Tech in Asia", "https://www.techinasia.com/feed", "us", "en"),
    ("rappler", "Rappler Business", "https://www.rappler.com/business/rss/", "us", "en"),
    ("thesun", "The Sun Daily (MY)", "https://thesun.my/rss", "us", "en"),
    # ── 加密货币（英文增量：已有 coindesk/cointelegraph/decrypt/defiant/unchained） ──
    ("cryptobriefing", "Crypto Briefing", "https://cryptobriefing.com/feed/", "crypto", "en"),
    ("dailyhodl", "The Daily Hodl", "https://dailyhodl.com/feed/", "crypto", "en"),
    ("newsbtc", "NewsBTC", "https://www.newsbtc.com/feed/", "crypto", "en"),
    ("beincrypto", "BeInCrypto", "https://beincrypto.com/feed/", "crypto", "en"),
    ("cryptopotato", "CryptoPotato", "https://cryptopotato.com/feed/", "crypto", "en"),
    ("utoday", "U.Today", "https://u.today/rss", "crypto", "en"),
    ("cryptonews", "CryptoNews", "https://crypto.news/feed/", "crypto", "en"),
    ("protos", "Protos", "https://protos.com/feed/", "crypto", "en"),
    ("bitcoincom", "Bitcoin.com News", "https://news.bitcoin.com/feed/", "crypto", "en"),
    ("coinjournal", "CoinJournal", "https://coinjournal.net/feed/", "crypto", "en"),
    ("cointribune", "Cointribune", "https://www.cointribune.com/feed/", "crypto", "en"),
    ("bitcoinist", "Bitcoinist", "https://bitcoinist.com/feed/", "crypto", "en"),
    ("zycrypto", "ZyCrypto", "https://zycrypto.com/feed/", "crypto", "en"),
    ("cryptopolitan", "Cryptopolitan", "https://www.cryptopolitan.com/feed/", "crypto", "en"),
    # ── 加密货币（日文/韩文原文） ──
    ("coindeskjapan", "CoinDesk Japan", "https://www.coindeskjapan.com/rss", "crypto", "ja"),
    ("neweconomyjp", "あたらしい経済", "https://www.neweconomy.jp/rss/", "crypto", "ja"),
    ("cryptotimesjp", "CRYPTO TIMES", "https://crypto-times.jp/feed", "crypto", "ja"),
    ("coinotaku", "CoinOtaku", "https://coinotaku.com/feed", "crypto", "ja"),
    ("blockmedia", "BlockMedia", "https://www.blockmedia.co.kr/rss", "crypto", "ko"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcdef"  # job namespace news_zhm_* is unique, so keys restart at "a".
ZH_MEDIA_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: ZH_MEDIA_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if ZH_MEDIA_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (see _zhb_batch_job for the pattern to mirror).
ZH_MEDIA_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_zhm_{key}_60m", f"中文媒体·亚太 {key.upper()} 组", key)
    for key in ZH_MEDIA_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class ZhMediaBatchCrawler:
    """Sequentially crawl one batch of Chinese-media/Asia/crypto feeds.

    Mirrors :class:`ZhBlogBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: plain
    curl-style UAs get 403 on most of these sites (verified from ECS).
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
        rows = ZH_MEDIA_BATCHES.get(self._batch_key, [])
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
                            source=f"zhm_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                            # 中文（含台湾/香港）源的 naive 时间戳一律按
                            # UTC+8 本地墙钟处理（2026-08-01 iThome 台湾
                            # +8h 事故的既有惯例）。本批日韩源时间戳全部
                            # 自带时区标注（ECS 验证确认），不受此参数影响。
                            default_tz=ZoneInfo("Asia/Shanghai"),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "zh media batch %s: feed %s failed: %s",
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
