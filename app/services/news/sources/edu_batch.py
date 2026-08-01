"""Batch crawler for curated investment *education / explainer* feeds (2026-08-02).

Why this exists
---------------
The 学习中心 (learning centre) push — the "贵精不贵多" knowledge/education
source wave from the learning-section analysis (§2.2). Unlike the
volume-driven expansion waves (``enf_*``/``ofc_*``/``zhm_*``), this batch
is deliberately small: **17 hand-picked feeds** whose output is
overwhelmingly evergreen educational content (index-investing
philosophy, personal-finance craft, valuation teaching, behavioural
science, macro explainers) rather than market news. It is the content
backbone for the ``news_source_meta`` ``content_type='edu'`` bucket.

Selection & verification rule
-----------------------------
* Every feed was live-verified **from the production ECS** on
  2026-08-01/02 in three curl rounds (browser User-Agent +
  Accept/Accept-Language headers, HTTP 200, body >5KB, valid RSS/Atom,
  >=5 items, newest item within 30 days, **newest item not in the
  future**). 36 candidates were tested across the rounds.
* Editorial bar: clickbait / promo-deal / price-prediction outlets are
  rejected even when technically fresh — this batch feeds the learning
  centre, so signal purity beats volume (任务书原话「贵精不贵多」).
* YouTube channels ship Atom feeds whose bodies live in
  ``<media:group><media:description>`` — ``parse_rss_items`` does not
  read that tag, so :class:`EduBatchCrawler` copies it into an Atom
  ``<summary>`` before parsing (video description becomes the article
  body; the translation drain then makes it readable in Chinese).
  Channel IDs were resolved from ECS via the channel pages / search
  (2026-08-01) and title-verified against each feed.

Verification evidence (ECS, 2026-08-01/02; size/items/newest)
-------------------------------------------------------------
* humbledollar  127KB/15/2026-08-01 · choosefi 30KB/50/2026-07-30
* behavioralsci 428KB/10/2026-07-19 · klement 191KB/20/2026-07-30
* macrocompass  561KB/20/2026-07-13 · napkinfinance 79KB/10/2026-07-06
  (low cadence — 26 days at verification, kept inside the 30d rule)
* stockfeel     2.4MB/100/2026-07-31 (繁中 feed, pubDate carries proper
  RFC-2822 ``+0000`` labels that convert plausibly — e.g. a post-close
  wrap at 08:37 UTC = 16:37 Taipei — so no ``tz_override``)
* YouTube ×10   27-80KB/15 each, newest 2026-07-24..08-01: benfelix
  07-30 · plainbagel 07-24 · twocents 07-30 · damodaran 07-29 ·
  pboyle 07-25 · pensioncraft 08-01 · moneyguy 08-01 · damien 07-28 ·
  jamesshack 07-27 · moneymacro 07-24

Rejections worth remembering (all ECS-verified unless noted)
------------------------------------------------------------
* **Cloudflare/Sucuri IP-reputation 403 from Aliyun egress**
  (WordPress blogs mostly): JL Collins, Mr Money Mustache, Kitces,
  Afford Anything, Behavioural Investment, Biglaw Investor, Financial
  Mentor, Dough Roller, ETF Stream, Canadian Portfolio Manager,
  The Finance Buff, The College Investor, Rational Walk, Corporate
  Finance Institute, 市場先生 rich01. Same class of failure as the
  en_fin wave's Investopedia/Benzinga block — these are dead for
  production regardless of feed quality.
* **Investopedia** — Cloudflare 403 (confirms the en_fin wave finding;
  the task brief's "实测不过就弃" applies).
* **Stale/dead**: Bogleheads blog (newest 2025-09-14 — blog winding
  down), The Simple Dollar (feed degraded to 1 item, 2025-04), Listen
  Money Matters (stale since 2020), DQYDJ (40d), Millionaire Educator
  (44d), Kyla Scanlon (65d), Meaningful Money YouTube (45d).
* **My Money Blog** — technically PASS (111KB/15/2026-07-29) but ~half
  the posts are bank/credit-card promo deals → 导购向, rejected on the
  editorial rule (this batch feeds the learning centre).
* **Cloudflare origin errors**: Get Rich Slowly (522), Good Financial
  Cents (520), The Physician Philosopher (520).
* **Unreachable (timeout)**: Four Pillar Freedom, Retire by 40,
  Root of Good, The Investment Ecosystem, Banker on Wheels,
  Felder Report, FactorResearch.
* **Feed URL serves HTML** (site rebuilt, RSS dropped): The Irrelevant
  Investor, The Decision Lab, Compounding Quality; The Evidence-Based
  Investor (feed 404 + homepage carries no RSS link); Can I Retire Yet
  (WAF JS-challenge interstitial); Paul Merriman (/feed/ 404,
  Squarespace ``?format=rss`` 404).
* **中文候选**: 綠角財經筆記 — Blogger feed now redirects to a follow.it
  subscription landing page (HTML, not a feed); 怪老子 — site has no
  RSS; PG財經筆記 — DNS resolution failure (domain lapsed); 陽志平 —
  /feed & /feed.xml both 404; CMoney — /feed/ 404; MoneyDJ —
  rss.djxml returns a 1.1KB stub with 0 items.
* **Already covered (never re-added)**: Early Retirement Now,
  Physician on FIRE, Monevator, White Coat Investor, Oblivious
  Investor, Mad Fientist, Financial Samurai, Coach Carson, Millennial
  Revolution, Alpha Architect, Budgets Are Sexy, ESI Money, The
  Retirement Manifesto, Wallet Hacks, Farnam Street, Acquirer's
  Multiple, QuantStart, epchan — plus every "已有" entry in
  ``/tmp/learning-section-analysis.md`` §2.2 (Ben Carlson, Nick
  Maggiulli, the ~20-strong FIRE系, Conversable Economist…). Programmatic
  zero-overlap against all 917 existing feed URLs is enforced in
  ``app/tests/news/test_edu_batch.py``.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``edu_{slug}`` — own namespace alongside ``zhb_*``, ``enf_*``,
  ``ofc_*``, ``zhm_*`` etc.
* **Batches restart at "a"**: 17 feeds sliced into batches ``a``-``b``
  of <=10 (job namespace ``news_edu_*``).
* **Market rule**: English rows are ``us`` — never ``global`` (the
  news API's ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)``;
  ``global`` rows are invisible in the frontend default view).
  stockfeel (繁体中文, 台湾) is ``cn_a``/``zh`` per the same ruling as
  the zhb/zhm waves; the 繁转简 pipeline is already live.
* **No LLM marketing filter**: curated educational voices, same
  precedent as every earlier batch wave — the scheduler job writes
  directly after fetch, keeping LLM cost flat.
* **No ``default_tz``/``tz_override``**: every feed below carries
  proper RFC-2822/ISO-8601 timezone-labelled timestamps (verified
  during the curl rounds); naive values correctly fall back to UTC.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language). source = "edu_{slug}".
EDU_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 英文博客 / Substack（理财科普·行为科学·宏观教学） ──
    ("humbledollar", "Humble Dollar", "https://humbledollar.com/feed/", "us", "en"),
    ("choosefi", "ChooseFI", "https://www.choosefi.com/feed/", "us", "en"),
    ("behavioralsci", "Behavioral Scientist", "https://behavioralscientist.org/feed/", "us", "en"),
    ("klement", "Klement on Investing", "https://klementoninvesting.substack.com/feed", "us", "en"),
    ("macrocompass", "The Macro Compass", "https://themacrocompass.substack.com/feed", "us", "en"),
    # Napkin Finance：视觉化理财基础卡片，低产（月更级），30 天规则内保留
    ("napkinfinance", "Napkin Finance", "https://napkinfinance.com/feed/", "us", "en"),
    # ── YouTube 教育频道（Atom feed；视频描述经注入后入正文） ──
    ("ytbenfelix", "Ben Felix (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCOErWFfNOQzXsgE7f5S_ULw", "us", "en"),
    ("ytplainbagel", "The Plain Bagel (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCFCEuCsyWP0YkP3CZ3Mr01Q", "us", "en"),
    ("yttwocents", "Two Cents - PBS (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCSPYNpQ2fHv9HJ-q6MIMaPw", "us", "en"),
    ("ytdamodaran", "Aswath Damodaran (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCLvnJL8htRR1T9cbSccaoVw", "us", "en"),
    ("ytpboyle", "Patrick Boyle (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCASM0cgfkJxQ1ICmRilfHLw", "us", "en"),
    ("ytpensioncraft", "PensionCraft (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UC9OIwUcx-Uss7xj7s1P5XGw", "us", "en"),
    ("ytmoneyguy", "The Money Guy Show (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UC9vUu4vlIlMC0dHQCTvQPbg", "us", "en"),
    ("ytdamien", "Damien Talks Money (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCjPR68IfHV0aY9s6cF5u0uQ", "us", "en"),
    ("ytjamesshack", "James Shack (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCLXQalldcm6gMYMQfLMliww", "us", "en"),
    ("ytmoneymacro", "Money & Macro (YouTube)", "https://www.youtube.com/feeds/videos.xml?channel_id=UCCKpicnIwBP3VPxBAZWDeNA", "us", "en"),
    # ── 中文（繁体）科普 ──
    ("stockfeel", "股感 StockFeel", "https://www.stockfeel.com.tw/feed/", "cn_a", "zh"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "ab"  # job namespace news_edu_* is unique, so keys restart at "a".
EDU_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: EDU_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if EDU_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (see docs/dev-notes/20260802-news-expansion-abc-wiring.md).
EDU_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_edu_{key}_60m", f"投资科普 {key.upper()} 组", key)
    for key in EDU_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_MEDIA_NS = "{http://search.yahoo.com/mrss/}"
_YOUTUBE_FEED_PREFIX = "https://www.youtube.com/feeds/"


def _youtube_descriptions_to_summary(xml_text: str) -> str:
    """Copy YouTube ``media:description`` into an Atom ``<summary>``.

    YouTube channel feeds are Atom documents whose video descriptions
    live in ``<media:group><media:description>`` — a tag
    :func:`parse_rss_items` does not read, so entries would otherwise be
    ingested with empty bodies. For each entry lacking a ``<summary>``,
    clone the media description into one and re-serialize. Namespace
    prefixes may be rewritten (``ns0:``) by ElementTree; namespace URIs
    are preserved, which is all the downstream parser keys on.
    Non-XML / non-YouTube input is returned unchanged.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text
    changed = False
    for entry in root.findall(f"{_ATOM_NS}entry"):
        if entry.find(f"{_ATOM_NS}summary") is not None:
            continue
        desc = entry.find(f"{_MEDIA_NS}group/{_MEDIA_NS}description")
        if desc is None or not (desc.text or "").strip():
            continue
        summary = ET.SubElement(entry, f"{_ATOM_NS}summary")
        summary.text = desc.text
        changed = True
    if not changed:
        return xml_text
    return ET.tostring(root, encoding="unicode")


class EduBatchCrawler:
    """Sequentially crawl one batch of education/explainer feeds.

    Mirrors :class:`ZhBlogBatchCrawler` / :class:`EnFinBatchCrawler`.
    Unknown batch keys yield an empty crawl (defensive — a config typo
    must never crash the scheduler). A desktop browser User-Agent is
    mandatory: plain curl-style UAs get 403 on most of these sites
    (verified from ECS). YouTube rows get their ``media:description``
    promoted to the article body (see
    :func:`_youtube_descriptions_to_summary`).
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
        rows = EDU_BATCHES.get(self._batch_key, [])
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
                    text = resp.text
                    if feed.url.startswith(_YOUTUBE_FEED_PREFIX):
                        text = _youtube_descriptions_to_summary(text)
                    out.extend(
                        parse_rss_items(
                            text,
                            source=f"edu_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "edu batch %s: feed %s failed: %s",
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
