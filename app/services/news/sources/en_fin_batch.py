"""Batch crawler for English-language financial media & analysis blogs (2026-08-02).

Why this exists
---------------
资讯源扩容 "A 组": a wave of **English-language mainstream financial
media, macro/analysis blogs, official-sector feeds and international
English business outlets**, complementing the existing English coverage
which skewed toward tech blogs (``global_rss_batch``), newsletters
(``independent_batch`` / ``global_indie_batch``) and Asia-focused
outlets (``asia_en_batch``). 63 live-verified feeds.

Selection & verification rule
-----------------------------
* Every feed was live-verified **from the production ECS (Aliyun,
  mainland-China egress)** on 2026-08-01/02 in three curl rounds
  (browser UA, HTTP 200, body >5KB, valid RSS/Atom, >=5 items, newest
  item within 30 days). ~235 candidates were tested; every rejection
  (Cloudflare-blocked, dead feed, headline-only, stale) is recorded in
  the module docstring below and in
  ``docs/dev-notes/`` wave notes written by the coordinating session.
* Paywalled outlets whose RSS ships only teasers (The Economist,
  FT Alphaville, NZ Herald) are kept deliberately — the article-body
  fetch layer fills the text (same rule the task brief set; precedent:
  the metered feeds already ingested in earlier waves).
* ``boj`` (Bank of Japan) ships title+link+date only (no
  ``<description>``); kept as an official primary source — bodies come
  from the fetch layer. Commercial headline-only feeds (Small Caps,
  Sifted) were rejected for the same reason.
* Notable rejections (all verified from ECS): Forbes (killed RSS,
  404), Morningstar (killed RSS), Zacks (dead), Quartz (empty feed),
  CNN Business (dead since 2018), MarketWatch realtimeheadlines
  (stale since 2025-06), Investopedia/Benzinga/IBD/Finviz/StreetInsider/
  This is Money/Proactive Investors/DailyFX/FXStreet/ForexCrunch/
  MishTalk/PragCap/Advisor Perspectives/Morning Brew (Cloudflare or
  TCP-blocked from Aliyun), Kitco (no working RSS), BIS/IMF/WorldBank/
  Treasury/Epsilon Theory/CFR (no working feed URL found), regional
  Feds except Board feeds (Richmond/Cleveland/Philadelphia 403,
  KC/StL/Minneapolis unreachable, Atlanta macroblog stale >30d,
  Dallas/Boston/Chicago index pages only), A Wealth of Common Sense /
  Calculated Risk / Wolf Street / Marginal Revolution / Econbrowser /
  Of Dollars and Data / Ritholtz / Noahpinion / Oilprice / Forexlive
  (→investingLive) / City A.M. / Fortune / Business Insider / FT home /
  Seeking Alpha currents / CNBC combinedcms / MarketWatch topstories /
  Yahoo Finance / ValueWalk — **already covered** by earlier waves
  (zero-overlap rule).

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``enf_{slug}`` — own namespace alongside ``zhb_*``, ``asen_*``,
  ``global_*``, ``gind_*``, ``indie_*``, ``zhx_*``, ``wechat_*``.
* **Batches restart at "a"**: 63 feeds sliced into batches ``a``-``g``
  of <=10 (job namespace ``news_enf_*``).
* **Market is ``us`` for every row — never ``global``**: the news
  API's ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)`` and the
  frontend "global" filter expands to that same set, so articles
  written with market="global" would be invisible in the default view
  (``app/api/v1/news.py::_expand_market_filter``). This overrides the
  wave brief's "宏观/国际=global" suggestion — same ruling as
  ``asia_en_batch`` (see its docstring). Language is uniformly ``en``;
  the translation drain picks articles up automatically.
* **No LLM marketing filter**: curated outlets/blogs, same precedent
  as every earlier batch wave — the scheduler job writes directly
  after fetch, keeping LLM cost flat.
* **No ``default_tz`` override**: every feed below carries proper
  RFC-2822/ISO-8601 timestamps (verified during the curl rounds);
  naive values correctly fall back to UTC.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language). source = "enf_{slug}".
EN_FIN_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── US mainstream broadcast/wire business desks ──
    ("cnbceconomy", "CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "us", "en"),
    ("cnbcbusiness", "CNBC Business News", "https://www.cnbc.com/id/10001147/device/rss/rss.html", "us", "en"),
    ("cnbcworld", "CNBC International", "https://www.cnbc.com/id/100727362/device/rss/rss.html", "us", "en"),
    ("cnbcinvesting", "CNBC Investing", "https://www.cnbc.com/id/15839069/device/rss/rss.html", "us", "en"),
    ("nytbusiness", "NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "us", "en"),
    ("nyteconomy", "NYT Economy", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml", "us", "en"),
    ("nytyourmoney", "NYT Your Money", "https://rss.nytimes.com/services/xml/rss/nyt/YourMoney.xml", "us", "en"),
    ("cbsmoneywatch", "CBS MoneyWatch", "https://www.cbsnews.com/latest/rss/moneywatch", "us", "en"),
    ("pbseconomy", "PBS NewsHour Economy", "https://www.pbs.org/newshour/feeds/rss/economy", "us", "en"),
    ("nypostbusiness", "NY Post Business", "https://nypost.com/business/feed/", "us", "en"),
    # ── US/UK financial media (paywalled teasers kept per wave rule) ──
    ("latimesbusiness", "LA Times Business", "https://www.latimes.com/business/rss2.0.xml", "us", "en"),
    ("economistfinance", "The Economist Finance & Economics", "https://www.economist.com/finance-and-economics/rss.xml", "us", "en"),
    ("economistbusiness", "The Economist Business", "https://www.economist.com/business/rss.xml", "us", "en"),
    ("ftalphaville", "FT Alphaville", "https://ftalphaville.ft.com/feed/", "us", "en"),
    ("motleyfool", "The Motley Fool", "https://www.fool.com/feeds/index.aspx", "us", "en"),
    ("fooluk", "Motley Fool UK", "https://www.fool.co.uk/feed/", "us", "en"),
    ("marketbeat", "MarketBeat", "https://www.marketbeat.com/feed/", "us", "en"),
    ("nasdaqmarkets", "Nasdaq Markets", "https://www.nasdaq.com/feed/rssoutbound?category=Markets", "us", "en"),
    ("semafor", "Semafor", "https://www.semafor.com/rss.xml", "us", "en"),
    ("financemagnates", "Finance Magnates", "https://www.financemagnates.com/feed/", "us", "en"),
    # ── Investment industry / alternatives / commodities ──
    ("hedgeweek", "Hedgeweek", "https://www.hedgeweek.com/feed/", "us", "en"),
    ("bespoke", "Bespoke Investment Group", "https://www.bespokepremium.com/feed/", "us", "en"),
    ("macrobusiness", "MacroBusiness", "https://www.macrobusiness.com.au/feed/", "us", "en"),
    ("portfolioadviser", "Portfolio Adviser", "https://portfolio-adviser.com/feed", "us", "en"),
    ("moneyweb", "Moneyweb", "https://www.moneyweb.co.za/feed/", "us", "en"),
    # mining.com/feed/ also collected by the parallel official wave
    # (slug miningcom) — lives in official_batch.py only.
    ("artemis", "Artemis (ILS & Reinsurance)", "https://www.artemis.bm/feed/", "us", "en"),
    ("reinsurancenews", "Reinsurance News", "https://www.reinsurancene.ws/feed/", "us", "en"),
    ("euronewsbiz", "Euronews Business", "https://www.euronews.com/rss?level=theme&name=business", "us", "en"),
    ("france24business", "France 24 Business", "https://www.france24.com/en/business/rss", "us", "en"),
    # ── International English business outlets ──
    ("spiegelintl", "Der Spiegel International", "https://www.spiegel.de/international/index.rss", "us", "en"),
    ("euobserver", "EUobserver", "https://euobserver.com/rss", "us", "en"),
    ("globeandmailbiz", "Globe and Mail Business", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/", "us", "en"),
    ("mortgagetrends", "Canadian Mortgage Trends", "https://www.canadianmortgagetrends.com/feed/", "us", "en"),
    ("theagebusiness", "The Age Business", "https://www.theage.com.au/rss/business.xml", "us", "en"),
    ("moneymagau", "Money Magazine Australia", "https://www.moneymag.com.au/feed", "us", "en"),
    ("nzheraldbusiness", "NZ Herald Business", "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/business/?outputType=xml", "us", "en"),
    ("nhkbiz", "NHK World Business", "https://www3.nhk.or.jp/rss/news/cat6.xml", "us", "en"),
    ("finshots", "Finshots", "https://finshots.in/rss", "us", "en"),
    ("economymiddleeast", "Economy Middle East", "https://economymiddleeast.com/feed/", "us", "en"),
    # ── Emerging-market English outlets ──
    ("howwemadeit", "How we made it in Africa", "https://www.howwemadeitinafrica.com/feed/", "us", "en"),
    ("businessdayng", "BusinessDay Nigeria", "https://businessday.ng/feed/", "us", "en"),
    ("mercopress", "MercoPress", "https://en.mercopress.com/rss", "us", "en"),
    ("riotimes", "The Rio Times", "https://www.riotimesonline.com/feed/", "us", "en"),
    ("emergingeurope", "Emerging Europe", "https://emerging-europe.com/feed/", "us", "en"),
    ("globalnewsmoney", "Global News Money (CA)", "https://globalnews.ca/money/feed/", "us", "en"),
    # ── Macro/analysis blogs & newsletters ──
    ("krugman", "Paul Krugman", "https://paulkrugman.substack.com/feed", "us", "en"),
    ("chartbook", "Chartbook (Adam Tooze)", "https://adamtooze.substack.com/feed", "us", "en"),
    ("sumner", "Scott Sumner (The Money Illusion)", "https://scottsumner.substack.com/feed", "us", "en"),
    ("braddelong", "Brad DeLong", "https://braddelong.substack.com/feed", "us", "en"),
    ("bonddad", "Bonddad Blog", "https://bonddad.blogspot.com/feeds/posts/default", "us", "en"),
    ("nakedcapitalism", "Naked Capitalism", "https://www.nakedcapitalism.com/feed", "us", "en"),
    ("pensionpulse", "Pension Pulse", "https://pensionpulse.blogspot.com/feeds/posts/default", "us", "en"),
    # ── Think tanks / official sector / fintech trades ──
    # Dedup note (2026-08-02 wiring): cato / paymentsdive / cfodive /
    # fedspeeches / fedmonetary / cbo were collected by BOTH this wave and
    # the parallel official_batch wave; they live in official_batch.py
    # (ofc_* jobs), so they are intentionally absent here.
    ("epi", "Economic Policy Institute Blog", "https://www.epi.org/blog/feed/", "us", "en"),
    ("gfmag", "Global Finance Magazine", "https://gfmag.com/feed/", "us", "en"),
    ("fedtestimony", "Federal Reserve Testimony", "https://www.federalreserve.gov/feeds/testimony.xml", "us", "en"),
    # boj ships title+link+date only — official primary source, bodies
    # come from the fetch layer (see module docstring).
    ("boj", "Bank of Japan", "https://www.boj.or.jp/en/rss/whatsnew.xml", "us", "en"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcdefg"  # job namespace news_enf_* is unique, so keys restart at "a".
EN_FIN_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: EN_FIN_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if EN_FIN_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py in the wiring commit (see the wave runbook in
# docs/dev-notes/ written by the coordinating session).
EN_FIN_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_enf_{key}_60m", f"英文财经 {key.upper()} 组", key)
    for key in EN_FIN_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class EnFinBatchCrawler:
    """Sequentially crawl one batch of English finance RSS/Atom feeds.

    Mirrors :class:`ZhBlogBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: several
    outlets 403 plain curl-style UAs, and this UA string is exactly
    what the ECS verification rounds used.
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
        rows = EN_FIN_BATCHES.get(self._batch_key, [])
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
                            source=f"enf_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                            # English feeds all carry proper RFC-2822 /
                            # ISO-8601 timestamps (verified 2026-08-01);
                            # no default_tz override needed — naive
                            # values correctly fall back to UTC.
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "en fin batch %s: feed %s failed: %s",
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
