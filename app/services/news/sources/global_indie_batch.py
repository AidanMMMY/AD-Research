"""Batch crawler for English-language independent voices (2026-07-28).

Why this exists
---------------
Third wave of the 资讯源扩充 push: >=100 additional **English-only**
sources with an independent voice — no official media, no government
outlets, no corporate PR channels, no pure aggregators/marketing
funnels. The previous waves covered WeChat accounts
(``wechat2rss_batch.py``), 144 independent CN/EN blogs and podcasts
(``independent_batch.py``) and 125 multi-language publications
(``global_rss_batch.py``). This wave targets what was still missing:

* **Custom-domain Substack / Ghost / beehiiv newsletters** — macro,
  markets, tech and policy analysts with original takes (Substack's
  bare ``*.substack.com`` domain is unreachable from the production
  network, but writers on custom domains resolve fine).
* **Independent finance / macro blogs** — value-investing, quant,
  retirement-research and personal-finance writers across the US, UK,
  Canada, Singapore, India and Australia.
* **Independent tech & security blogs** — single-author engineering
  and security voices, plus dev.to / Hashnode deep authors (dev.to and
  Hashnode both resolve from ECS; Medium's main site does not).
* **Independent research / commentary outlets** — nonprofit
  investigative newsrooms, academic-lab blogs and independent
  policy/geopolitics magazines.

Every feed below was live-verified from the production ECS
(2026-07-27/28): HTTP 200 after redirects, valid RSS/Atom, items > 0,
newest item within ~150 days, and a real body (average >100 words over
the first 8 items — headline-only feeds like Quanta or Naked
Capitalism's excerpt feed were rejected). 473 candidate URLs were
tested; 110 survived verification, of which 6 Asia-focused feeds were
handed to the parallel ``asia_en_batch`` wave (dedup decision by the
coordinator), leaving 104 here. The full evidence table and the
rejection log live in ``docs/dev-notes/20260728-global-indie-batch.md``.

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; ``source`` becomes
  ``gind_{slug}`` (global-indie) so this wave has its own namespace
  alongside ``wechat_*``, ``indie_*`` and ``global_*``.
* **Batches start at "o"**: ``independent_batch`` owns a–n, so this
  table is sliced into batches ``o``–``x`` (11 feeds each, 5 in the
  last) — no key collision when both tables are wired into the
  scheduler.
* **No overlap with ``asia_en_batch``**: pandaily / e27 /
  dollarsandsense / fifthperson / safalniveshak / strongmoneyaustralia
  were verified here first but assigned to the parallel Asia-English
  wave (coordinator decision 2026-07-28); do not re-add them.
* **Market**: all rows are ``us`` or ``crypto`` on purpose. The news
  API's ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)`` —
  writing ``global`` would hide the articles from the frontend's
  default filter (see ``app/api/v1/news.py::_expand_market_filter``),
  so UK/AU/SG/IN commentary sources also use ``us`` (same precedent as
  ``indie_monevator`` / ``indie_firevlondon``).
* **No LLM marketing filter**: curated editorial voices, same
  precedent as ``independent_batch`` — the scheduler job writes
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

# (slug, display_name, feed_url, market, language). source = "gind_{slug}".
GLOBAL_INDIE_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── Macro / geopolitics / China-watch newsletters ──
    ("sinocism", "Sinocism (Bill Bishop)", "https://sinocism.com/feed", "us", "en"),
    ("chinatalk", "ChinaTalk (Jordan Schneider)", "https://www.chinatalk.media/feed", "us", "en"),
    ("sinification", "Sinification", "https://sinification.com/feed", "us", "en"),
    ("merics", "MERICS", "https://merics.org/en/rss", "us", "en"),
    ("uncharted", "Uncharted Territories (Tomas Pueyo)", "https://unchartedterritories.tomaspueyo.com/feed", "us", "en"),
    ("justsecurity", "Just Security", "https://www.justsecurity.org/feed/", "us", "en"),
    ("responsiblestatecraft", "Responsible Statecraft (Quincy Institute)", "https://responsiblestatecraft.org/feed/", "us", "en"),
    # ── Independent policy / politics / ideas newsletters ──
    ("pluralistic", "Pluralistic (Cory Doctorow)", "https://pluralistic.net/feed", "us", "en"),
    ("betonit", "Bet On It (Bryan Caplan)", "https://www.betonit.ai/feed", "us", "en"),
    ("natesilver", "Silver Bulletin (Nate Silver)", "https://www.natesilver.net/feed", "us", "en"),
    ("gelliottmorris", "Strength In Numbers (G. Elliott Morris)", "https://www.gelliottmorris.com/feed", "us", "en"),
    ("hamiltonnolan", "How Things Work (Hamilton Nolan)", "https://www.hamiltonnolan.com/feed", "us", "en"),
    ("publicnotice", "Public Notice", "https://www.publicnotice.co/feed", "us", "en"),
    ("racketnews", "Racket News (Matt Taibbi)", "https://www.racket.news/feed", "us", "en"),
    ("publicnews", "Public (Michael Shellenberger)", "https://www.public.news/feed", "us", "en"),
    ("richardhanania", "Richard Hanania's Newsletter", "https://www.richardhanania.com/feed", "us", "en"),
    ("persuasion", "Persuasion", "https://www.persuasion.community/feed", "us", "en"),
    ("aporia", "Aporia", "https://www.aporiamagazine.com/feed", "us", "en"),
    ("unherd", "UnHerd", "https://unherd.com/feed/", "us", "en"),
    ("thebulwark", "The Bulwark", "https://www.thebulwark.com/feed/", "us", "en"),
    ("areo", "Areo", "https://areomagazine.com/feed/", "us", "en"),
    ("arcdigital", "Arc Digital", "https://arcdigital.media/feed", "us", "en"),
    # ── Independent investigative / commentary outlets ──
    ("thelever", "The Lever", "https://www.levernews.com/rss/", "us", "en"),
    ("dropsitenews", "Drop Site News", "https://www.dropsitenews.com/feed", "us", "en"),
    ("propublica", "ProPublica", "https://www.propublica.org/feeds/propublica/main", "us", "en"),
    ("palladium", "Palladium", "https://www.palladiummag.com/feed", "us", "en"),
    # ── Independent econ / macro research & commentary ──
    ("commoditycontext", "Commodity Context (Rory Johnston)", "https://www.commoditycontext.com/feed", "us", "en"),
    ("volts", "Volts (David Roberts)", "https://www.volts.wtf/feed", "us", "en"),
    ("sustainabilitybynumbers", "Sustainability by Numbers (Hannah Ritchie)", "https://www.sustainabilitybynumbers.com/feed", "us", "en"),
    ("ageofinvention", "Age of Invention (Anton Howes)", "https://www.ageofinvention.xyz/feed", "us", "en"),
    ("itep", "ITEP (Just Taxes Blog)", "https://itep.org/feed/", "us", "en"),
    ("employamerica", "Employ America", "https://www.employamerica.org/feed", "us", "en"),
    ("secondbest", "Second Best (Samuel Hammond)", "https://www.secondbest.ca/feed", "us", "en"),
    ("overcomingbias", "Overcoming Bias (Robin Hanson)", "https://www.overcomingbias.com/feed", "us", "en"),
    ("modeledbehavior", "Modeled Behavior", "https://modeledbehavior.com/feed/", "us", "en"),
    ("lesswrong", "LessWrong (Curated)", "https://www.lesswrong.com/feed.xml?view=curated-rss", "us", "en"),
    ("dynomight", "Dynomight", "https://dynomight.net/feed.xml", "us", "en"),
    ("themarginalian", "The Marginalian (Maria Popova)", "https://www.themarginalian.org/feed/", "us", "en"),
    ("nesslabs", "Ness Labs (Anne-Laure Le Cunff)", "https://nesslabs.com/feed", "us", "en"),
    # ── Independent investing / quant / trading blogs ──
    ("yetanothervalueblog", "Yet Another Value Blog", "https://yetanothervalueblog.com/feed/", "us", "en"),
    ("alhambra", "Alhambra Investments (Jeff Snider)", "https://www.alhambrapartners.com/feed/", "us", "en"),
    ("valueplays", "ValuePlays (Todd Sullivan)", "https://valueplays.net/feed/", "us", "en"),
    ("litquidity", "Litquidity (Exec Sum)", "https://www.litquidity.co/feed", "us", "en"),
    ("quantifiableedges", "Quantifiable Edges (Rob Hanna)", "https://quantifiableedges.com/feed/", "us", "en"),
    ("smbtraining", "SMB Capital Trading Blog", "https://www.smbtraining.com/blog/feed", "us", "en"),
    ("appeconomy", "App Economy Insights", "https://www.appeconomyinsights.com/feed", "us", "en"),
    ("asiancenturystocks", "Asian Century Stocks", "https://www.asiancenturystocks.com/feed", "us", "en"),
    # ── Retirement / personal-finance independent blogs ──
    ("retirementresearcher", "Retirement Researcher (Wade Pfau)", "https://retirementresearcher.com/feed/", "us", "en"),
    ("looniedoctor", "Loonie Doctor", "https://looniedoctor.ca/feed/", "us", "en"),
    ("wallethacks", "Wallet Hacks (Jim Wang)", "https://wallethacks.com/feed/", "us", "en"),
    ("esimoney", "ESI Money", "https://esimoney.com/feed/", "us", "en"),
    ("moneywithkatie", "Money with Katie", "https://moneywithkatie.com/feed", "us", "en"),
    ("meaningfulmoney", "Meaningful Money (Pete Matthew)", "https://meaningfulmoney.tv/feed/", "us", "en"),
    ("mrsmummypenny", "Mrs Mummypenny", "https://www.mrsmummypenny.co.uk/feed/", "us", "en"),
    ("moneytothemasses", "Money to the Masses", "https://moneytothemasses.com/feed", "us", "en"),
    ("budgetsaresexy", "Budgets Are Sexy", "https://www.budgetsaresexy.com/feed/", "us", "en"),
    # ── Science magazines with real bodies ──
    ("newscientist", "New Scientist", "https://www.newscientist.com/feed/home/", "us", "en"),
    # ── Tech / product / VC independent newsletters ──
    ("wheresyoured", "Where's Your Ed At (Ed Zitron)", "https://www.wheresyoured.at/feed", "us", "en"),
    ("newcomer", "Newcomer (Eric Newcomer)", "https://www.newcomer.co/feed", "us", "en"),
    ("exponentialview", "Exponential View (Azeem Azhar)", "https://www.exponentialview.co/feed", "us", "en"),
    ("statecraft", "Statecraft (Santi Ruiz)", "https://www.statecraft.pub/feed", "us", "en"),
    ("lenny", "Lenny's Newsletter", "https://www.lennysnewsletter.com/feed", "us", "en"),
    ("refactoring", "Refactoring (Luca Rossi)", "https://refactoring.fm/feed", "us", "en"),
    ("producttalk", "Product Talk (Teresa Torres)", "https://www.producttalk.org/feed/", "us", "en"),
    ("benedicttevans", "Benedict Evans", "https://www.ben-evans.com/benedictevans?format=rss", "us", "en"),
    ("eladgil", "Elad Gil", "https://blog.eladgil.com/feed", "us", "en"),
    ("dhh", "DHH (37signals)", "https://world.hey.com/dhh/feed.atom", "us", "en"),
    ("jasonfried", "Jason Fried (37signals)", "https://world.hey.com/jason/feed.atom", "us", "en"),
    ("techsauce", "Techsauce (SEA)", "https://techsauce.co/feed", "us", "en"),
    # ── Independent tech / engineering blogs ──
    ("daringfireball", "Daring Fireball (John Gruber)", "https://daringfireball.net/feeds/main", "us", "en"),
    ("marcoorg", "Marco.org (Marco Arment)", "https://marco.org/rss", "us", "en"),
    ("pragmaticengineer", "The Pragmatic Engineer (Gergely Orosz)", "https://blog.pragmaticengineer.com/rss/", "us", "en"),
    ("bytebytego", "ByteByteGo (Alex Xu)", "https://blog.bytebytego.com/feed", "us", "en"),
    ("charitywtf", "Charity Majors", "https://charity.wtf/feed/", "us", "en"),
    ("codinghorror", "Coding Horror (Jeff Atwood)", "https://blog.codinghorror.com/rss/", "us", "en"),
    ("macwright", "Tom MacWright", "https://macwright.com/rss.xml", "us", "en"),
    ("jimnielsen", "Jim Nielsen's Blog", "https://blog.jim-nielsen.com/feed.xml", "us", "en"),
    ("adactio", "Adactio (Jeremy Keith)", "https://adactio.com/journal/rss", "us", "en"),
    ("drewdevault", "Drew DeVault", "https://drewdevault.com/blog/index.xml", "us", "en"),
    ("lucumr", "Armin Ronacher's Thoughts", "https://lucumr.pocoo.org/feed.atom", "us", "en"),
    ("xeiaso", "Xe Iaso", "https://xeiaso.net/blog.rss", "us", "en"),
    ("endler", "Matthias Endler", "https://endler.dev/rss.xml", "us", "en"),
    ("jakewharton", "Jake Wharton", "https://jakewharton.com/atom.xml", "us", "en"),
    ("hackingwithswift", "Hacking with Swift (Paul Hudson)", "https://www.hackingwithswift.com/articles/rss", "us", "en"),
    ("freecodecamp", "freeCodeCamp", "https://www.freecodecamp.org/news/rss/", "us", "en"),
    # ── dev.to / Hashnode deep authors ──
    ("devtoben", "Ben Halpern (dev.to)", "https://dev.to/feed/ben", "us", "en"),
    ("hashnodetapas", "Tapas Adhikary (Hashnode)", "https://blog.greenroots.info/rss.xml", "us", "en"),
    # ── Security / semiconductors ──
    ("krebsonsecurity", "Krebs on Security", "https://krebsonsecurity.com/feed/", "us", "en"),
    ("troyhunt", "Troy Hunt", "https://www.troyhunt.com/rss/", "us", "en"),
    ("danielmiessler", "Daniel Miessler", "https://danielmiessler.com/feed", "us", "en"),
    ("trailofbits", "Trail of Bits Blog", "https://blog.trailofbits.com/feed/", "us", "en"),
    ("media404", "404 Media", "https://www.404media.co/rss/", "us", "en"),
    ("theregister", "The Register", "https://www.theregister.com/headlines.atom", "us", "en"),
    ("osnews", "OSNews", "https://www.osnews.com/feed/", "us", "en"),
    ("itsfoss", "It's FOSS", "https://itsfoss.com/feed/", "us", "en"),
    ("chipsandcheese", "Chips and Cheese", "https://chipsandcheese.com/feed", "us", "en"),
    ("fabricatedknowledge", "Fabricated Knowledge (Doug O'Laughlin)", "https://www.fabricatedknowledge.com/feed", "us", "en"),
    # ── AI research / analysis ──
    ("transformer", "Transformer (Shakeel Hashim)", "https://www.transformernews.ai/feed", "us", "en"),
    ("interconnects", "Interconnects (Nathan Lambert)", "https://www.interconnects.ai/feed", "us", "en"),
    ("aheadofai", "Ahead of AI (Sebastian Raschka)", "https://magazine.sebastianraschka.com/feed", "us", "en"),
    ("lastweekinai", "Last Week in AI", "https://lastweekin.ai/feed", "us", "en"),
    ("bairblog", "BAIR Blog (Berkeley)", "https://bair.berkeley.edu/blog/feed.xml", "us", "en"),
    # ── Crypto independent ──
    ("unchained", "Unchained (Laura Shin)", "https://unchainedcrypto.com/feed/", "crypto", "en"),
    ("bitmexresearch", "BitMEX Research", "https://blog.bitmex.com/feed/", "crypto", "en"),
]

_BATCH_SIZE = 11
_BATCH_KEYS = "opqrstuvwx"  # independent_batch owns a-n; this wave owns o-x.
GLOBAL_INDIE_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: GLOBAL_INDIE_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if GLOBAL_INDIE_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py (see docs/dev-notes/20260728-global-indie-batch-integration.md).
GLOBAL_INDIE_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_gind_{key}_60m", f"全球独立源 {key.upper()} 组", key)
    for key in GLOBAL_INDIE_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class GlobalIndieBatchCrawler:
    """Sequentially crawl one batch of English independent RSS/Atom feeds.

    Mirrors :class:`IndependentBatchCrawler`. Unknown batch keys yield
    an empty crawl (defensive — a config typo must never crash the
    scheduler).
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
        rows = GLOBAL_INDIE_BATCHES.get(self._batch_key, [])
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
                            source=f"gind_{feed.slug}",
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "global indie batch %s: feed %s failed: %s",
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
