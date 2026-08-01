"""Batch crawler for official-institution & industry-vertical feeds (2026-08-01).

Why this exists
---------------
Sixth wave of the 资讯源扩充 push ("资讯源扩容 B 组：官方机构+行业垂直").
Earlier waves: wechat2rss (3 batches), Chinese podcasts (``zhx_*``),
global multi-language RSS (``global_*``), Chinese independent blogs
(``zhb_*``), Asia-English (``asen_*``). This wave covers **official
institutions** (central banks, US/EU regulators, statistical agencies,
multilateral bodies, think tanks) and **industry-vertical trade press**
(energy, semiconductors, autos/EV, aviation, defense, mining, shipping,
retail, housing, healthcare) — the "authoritative primary source"
channel the platform lacked beyond Fed/ECB/BoE (``rss_simple``).

Selection rule & live verification (from production ECS, 2026-08-01/02)
----------------------------------------------------------------------
Every feed below was live-verified from the production ECS with a
browser User-Agent: HTTP 200, valid RSS/Atom, ≥5 items, newest item
within 30 days (full evidence table in the companion runbook
``docs/dev-notes/20260801-official-industry-batch.md``). Candidate URLs
were cross-checked against every earlier wave for zero URL/slug
overlap.

Known data quirks (kept deliberately, with eyes open)
-----------------------------------------------------
* ``hoover`` / ``mckinsey`` / ``fca`` / ``fiercehealth`` ship pubDates
  in non-standard formats ("July 31, 2026", "Fri, 31 Jul 2026") or no
  per-item date at all. ``parse_rss_items`` cannot parse those and
  falls back to crawl time — acceptable for hourly-crawled press feeds
  (crawl time ≈ publish time), but their ``published_at`` is *not* the
  feed's date. Content freshness was verified manually (2026-07-31).
* The three ``cftc*`` feeds are 4.5-4.9 KB — marginally under the 5 KB
  size heuristic used during verification — but are valid RSS 2.0 with
  10 items each dated 2026-07-31. Kept on content evidence.
* ``fdic`` (GovDelivery) is slow (~20 s for a 900 KB body with 25
  items). The 25 s crawler timeout covers it, and ``max_items`` caps
  parse cost; if it starts timing out, drop it first.

Rejections worth remembering (verified from ECS 2026-08-01/02)
-------------------------------------------------------------
* **WAF-blocked (403 Cloudflare/Akamai, unfixable from the crawler)**:
  IMF (all feeds), OECD, VoxEU/CEPR, IEA, PIIE, AEI, Bruegel, Chatham
  House, IFS, NIESR, WEF, FINRA, BLS, Census, USDA, CFPB, Commerce,
  NCUA, FERC, DOT, NHTSA, RBA, RBNZ, Banque de France, DNB, OPEC,
  Rigzone, FreightWaves, FlightGlobal, AgWeb, Farm Progress, pv
  magazine, CleanTechnica, Renewable Energy World, SpaceNews,
  NASASpaceflight, BioSpace, GEN, MassDevice, Pharmaceutical
  Technology, Inman, The Real Deal, Zillow, Benzinga, Investopedia,
  AgFunder, Brownfield, Philadelphia Fed, Simple Flying (conn reset).
* **No working native RSS (404/HTML)**: BOJ, PBoC (skipped per spec),
  SNB, Norges Bank, Bundesbank, MAS, HKMA, ESMA, Eurostat (JS app),
  White House briefing-room (``/news/feed/`` works), OCC, FHFA, FAA,
  EPA, NY Fed press (HTML), World Bank blogs (all variants), StatCan
  (conn error), KC/Minneapolis/Cleveland Fed, Energy Central, Natural
  Gas World, Motor1 (only an HTML index), autoblog, Gizmodo, AgDaily
  (406), RTO Insider (JS challenge), Skies Magazine (stale 2024).
* **Stale beyond 30 days**: BIS press releases (newest 2026-06-28),
  BIS management speeches, Riksbank speeches, Chicago Fed (all feeds),
  Boston Fed (all feeds), Atlanta Fed macroblog, SF Fed, CSIS
  (events-dominated feed), Calculated Risk duplicates aside.
* **Bad data inside the feed**: BIS research papers (one item
  mis-dated 2035-09-01 — would surface as "future news"), Bank of
  Canada (``/feed/`` mixes future-dated calendar/holiday notices,
  e.g. Boxing Day 2026-12-28), Richmond Fed ``?cc_view=rss`` (4116
  items incl. 2027 future events).
* **Already covered by earlier waves** (zero-overlap rule): Fed
  press_all & ECB & BoE news (``rss_simple``), NBER / Liberty Street /
  FRED blog / Bank Underground / Heritage / Niskanen / Tax Foundation /
  Pew / Atlantic Council / Project Syndicate, Oilprice / gCaptain /
  Loadstar / HousingWire / RetailDive / UtilityDive / FiercePharma /
  FierceBiotech / SemiEngineering / Electrek / Endpoints / STAT /
  Canary Media and the rest of the Industry Dive family
  (banking/biopharma/food/healthcare/hr/marketing/supply-chain/waste/
  house/construction) via ``global_*`` / ``asen_*`` / ``rss_simple``.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``ofc_{slug}`` — own namespace alongside ``zhb_*``, ``global_*``,
  ``asen_*`` etc.
* **Batches restart at "a"**: the job namespace ``news_ofc_*`` is
  unique, so this table is sliced into batches of ≤10.
* **Market is ``us`` for every row** — including the EU/UK/SE/AU
  institutions. Rationale: ``news_article.market="global"`` is a
  frontend-only *sentinel* (``_GLOBAL_MARKETS`` maps it to the
  cn_a/us/crypto union), so rows stored with ``market="global"`` would
  be invisible under the frontend's 全球 chip and inconsistent with
  every earlier English wave (``global_*``/``asen_*`` all store
  ``us``). ``language="en"`` everywhere; the auto-translate pipeline
  picks rows up for Chinese translation.
* **No LLM marketing filter**: official/primary sources, same
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

# (slug, display_name, feed_url, market, language). source = "ofc_{slug}".
OFFICIAL_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 央行 / 货币当局 ──
    ("fedspeeches", "Federal Reserve Speeches", "https://www.federalreserve.gov/feeds/speeches.xml", "us", "en"),
    ("fedmonetary", "Fed Monetary Policy Press", "https://www.federalreserve.gov/feeds/press_monetary.xml", "us", "en"),
    ("bisspeeches", "BIS Central Bank Speeches", "https://www.bis.org/doclist/cbspeeches.rss", "us", "en"),
    ("riksbank", "Riksbank Press Releases", "https://www.riksbank.se/en-gb/rss/press-releases/", "us", "en"),
    # ── 美国监管 / 官方机构 ──
    ("secpress", "SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss", "us", "en"),
    ("secspeeches", "SEC Speeches", "https://www.sec.gov/news/speeches.rss", "us", "en"),
    ("cftcpress", "CFTC Press Releases", "https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "us", "en"),
    ("cftcenf", "CFTC Enforcement Actions", "https://www.cftc.gov/RSS/RSSENF/rssenf.xml", "us", "en"),
    ("cftcspeeches", "CFTC Speeches & Testimony", "https://www.cftc.gov/RSS/RSSST/rssst.xml", "us", "en"),
    ("treasury", "US Treasury Press", "https://home.treasury.gov/rss.xml", "us", "en"),
    ("fdic", "FDIC Press Releases", "https://public.govdelivery.com/topics/USFDIC_26/feed.rss", "us", "en"),
    ("ftc", "FTC Press Releases", "https://www.ftc.gov/feeds/press-release.xml", "us", "en"),
    ("ftccomp", "FTC Competition", "https://www.ftc.gov/feeds/press-release-competition.xml", "us", "en"),
    ("whitehouse", "White House News", "https://www.whitehouse.gov/news/feed/", "us", "en"),
    ("bea", "BEA News Releases", "https://apps.bea.gov/rss/rss.xml", "us", "en"),
    ("eia", "EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml", "us", "en"),
    ("doe", "DOE News", "https://www.energy.gov/rss", "us", "en"),
    ("cbo", "CBO Publications", "https://www.cbo.gov/rss/publications.xml", "us", "en"),
    # ── 欧洲监管 ──
    ("fca", "FCA News", "https://www.fca.org.uk/news/rss.xml", "us", "en"),
    # ── 地方联储 ──
    ("dallasfed", "Dallas Fed News", "https://www.dallasfed.org/rss/dallasfed.xml", "us", "en"),
    ("dallasfedrel", "Dallas Fed Releases", "https://www.dallasfed.org/rss/releases.xml", "us", "en"),
    ("dallasspeeches", "Dallas Fed Speeches", "https://www.dallasfed.org/rss/speeches.xml", "us", "en"),
    # ── 智库 / 研究 ──
    ("cfr", "Council on Foreign Relations", "https://www.cfr.org/feed", "us", "en"),
    ("cato", "Cato Institute", "https://www.cato.org/feed", "us", "en"),
    # hoover/mckinsey: pubDate 非标准格式（见模块 docstring），published_at 落 crawl 时间
    ("hoover", "Hoover Institution", "https://www.hoover.org/rss.xml", "us", "en"),
    ("mckinsey", "McKinsey Insights", "https://www.mckinsey.com/insights/rss", "us", "en"),
    # ── 行业垂直：金融 / 企服（Industry Dive 家族补全） ──
    ("cfodive", "CFO Dive", "https://www.cfodive.com/feeds/news/", "us", "en"),
    ("cyberdive", "Cybersecurity Dive", "https://www.cybersecuritydive.com/feeds/news/", "us", "en"),
    ("grocerydive", "Grocery Dive", "https://www.grocerydive.com/feeds/news/", "us", "en"),
    ("paymentsdive", "Payments Dive", "https://www.paymentsdive.com/feeds/news/", "us", "en"),
    ("mfgdive", "Manufacturing Dive", "https://www.manufacturingdive.com/feeds/news/", "us", "en"),
    ("packagingdive", "Packaging Dive", "https://www.packagingdive.com/feeds/news/", "us", "en"),
    ("truckingdive", "Trucking Dive", "https://www.truckingdive.com/feeds/news/", "us", "en"),
    ("medtechdive", "MedTech Dive", "https://www.medtechdive.com/feeds/news/", "us", "en"),
    # ── 行业垂直：医药 / 医疗 ──
    # fiercehealth: pubDate "Jul 31, 2026 5:38pm" 非标准（见 docstring）
    ("fiercehealth", "Fierce Healthcare", "https://www.fiercehealthcare.com/rss/xml", "us", "en"),
    ("beckers", "Becker's Hospital Review", "https://www.beckershospitalreview.com/feed", "us", "en"),
    # ── 行业垂直：科技媒体 ──
    ("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "us", "en"),
    ("engadget", "Engadget", "https://www.engadget.com/rss.xml", "us", "en"),
    ("zdnet", "ZDNet", "https://www.zdnet.com/news/rss.xml", "us", "en"),
    ("wired", "Wired", "https://www.wired.com/feed/rss", "us", "en"),
    ("mac9to5", "9to5Mac", "https://9to5mac.com/feed/", "us", "en"),
    ("macrumors", "MacRumors", "https://feeds.macrumors.com/MacRumors-All", "us", "en"),
    # ── 行业垂直：汽车 / 电动化 ──
    ("insideevs", "InsideEVs", "https://insideevs.com/rss/news/all/", "us", "en"),
    ("carscoops", "CarScoops", "https://www.carscoops.com/feed/", "us", "en"),
    ("motor1", "Motor1", "https://www.motor1.com/rss/news/all/", "us", "en"),
    ("teslarati", "Teslarati", "https://www.teslarati.com/feed/", "us", "en"),
    # ── 行业垂直：半导体 ──
    ("semianalysis", "SemiAnalysis", "https://semianalysis.substack.com/feed", "us", "en"),
    ("semidigest", "Semiconductor Digest", "https://www.semiconductor-digest.com/feed/", "us", "en"),
    # ── 行业垂直：矿业 / 航运 / 航空 / 国防 ──
    ("miningcom", "MINING.COM", "https://www.mining.com/feed/", "us", "en"),
    ("shipandbunker", "Ship & Bunker", "https://shipandbunker.com/rss", "us", "en"),
    ("aerotime", "AeroTime", "https://www.aerotime.aero/feed", "us", "en"),
    ("breakingdefense", "Breaking Defense", "https://breakingdefense.com/feed/", "us", "en"),
    ("defensescoop", "DefenseScoop", "https://defensescoop.com/feed/", "us", "en"),
    # ── 行业垂直：地产 / 零售 ──
    ("digiday", "Digiday", "https://digiday.com/feed/", "us", "en"),
    ("realtor", "Realtor.com News", "https://www.realtor.com/news/feed/", "us", "en"),
    ("redfin", "Redfin Blog", "https://www.redfin.com/blog/feed/", "us", "en"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcdefg"  # job namespace news_ofc_* is unique, so keys restart at "a".
OFFICIAL_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: OFFICIAL_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if OFFICIAL_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (registration snippet in the companion runbook).
OFFICIAL_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_ofc_{key}_60m", f"官方机构+行业垂直 {key.upper()} 组", key)
    for key in OFFICIAL_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class OfficialBatchCrawler:
    """Sequentially crawl one batch of official/industry RSS/Atom feeds.

    Mirrors :class:`ZhBlogBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: US/EU
    government sites 403 plain curl-style UAs (verified from ECS).
    Timeout is 25 s (not 20 s) because the FDIC GovDelivery feed takes
    ~20 s for its 900 KB body.
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
        rows = OFFICIAL_BATCHES.get(self._batch_key, [])
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
                            source=f"ofc_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "official batch %s: feed %s failed: %s",
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
