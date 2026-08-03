"""Batch crawler for the English-language AI industry chain wave (2026-08-04).

Why this exists
---------------
AI 产业链扩源英文批次：聚合三份 2026-08-04 搜罗报告中全部实测通过（✅）
且不重复的英文源，覆盖美国 AI 全产业链——模型层/研究层/VC 视角、
半导体/硬件/数据中心/能源/政策/云上游、英文 Newsletter、实验室官方
博客、英文播客与 YouTube 频道。共 99 个 feed。

Source reports (all in ``docs/dev-notes/ai-chain-sources/``)
-----------------------------------------------------------
1. ``20260804-self-media.md`` — 英文源以此报告为准（slug 用其
   gind_/ofc_/pod_/yt_ 前缀版）：英文 Newsletter 9 个、实验室官方
   博客 3 个、英文播客 15 个、英文 YouTube 频道 11 个（yt_hungyilee
   为中文教学频道，连同 3 个中文播客一起归中文批次，本模块不收）。
2. ``20260804-us-ai-models-research.md`` — 模型层/研究层/VC 候选总表
   ✅ 条目，跳过与 self-media 报告重复者。arXiv 例外：本模块只收
   **cs.LG 与 cs.CV**（cs.AI/cs.CL/cs.MA 按协调会话裁决归中文批次）。
3. ``20260804-us-ai-upstream.md`` — 上游（半导体/DC/能源/政策/云）
   实测通过 ✅ 43 个全部收录（去重后 37 个唯一入库，见下）。

Cross-report dedup decisions (self-media slug wins for the same site)
---------------------------------------------------------------------
* ``ai_openai_news`` (openai.com/news/rss.xml) → dropped, kept
  ``ofc_openai_blog`` (openai.com/blog/rss.xml, self-media).
* ``ai_deepmind_blog`` / upstream ``deepmind_blog`` → dropped, kept
  ``ofc_deepmind_blog``.
* ``ai_google_ai_blog`` → dropped, kept ``ofc_google_ai_blog``.
* ``ai_importai`` (importai.substack.com/feed) → dropped, kept
  ``gind_importai`` (jack-clark.net/feed).
* ``ai_thesequence`` → dropped, kept ``gind_thesequence``.
* ``ai_bensbites`` (bensbites.com/feed) → dropped, kept
  ``gind_bensbites`` (bensbites.substack.com/feed).
* ``ai_thegradient`` → dropped, kept ``gind_thegradient``.
* ``ai_latentspace`` (www.latent.space/feed) → dropped, kept
  ``gind_latentspace`` (latent.space/feed).
* ``ai_dwarkesh`` (dwarkesh.com/feed, blog) → dropped, kept
  ``pod_dwarkesh`` (podcast feed, self-media; same author).
* ``ai_stratechery`` / upstream ``stratechery`` → dropped, kept
  ``gind_stratechery``.
* ``ai_google_research`` vs upstream ``google_research`` (same URL) →
  kept once as ``google_research``.
* ``ai_huggingface_blog`` vs upstream ``huggingface_blog`` → kept once
  as ``huggingface_blog``.
* ``ai_databricks_blog`` vs upstream ``databricks_blog`` → kept once
  as ``databricks_blog``.

Skipped — already in the library (zero-overlap rule against
``/tmp/adresearch-build/existing_sources.txt``, 1012 slugs)
-----------------------------------------------------------
* ``ai_aheadofai`` —存量 ``gind_aheadofai`` (Ahead of AI, Raschka)。
* ``ai_simonwillison`` — 存量 ``indie_simonwillison``。
* us-models "排重发现"一节全部存量源：ofc_semianalysis /
  gind_interconnects / indie_interconnected / indie_oneusefulthing /
  indie_platformer / indie_bigtechnology / indie_notboring /
  indie_generalist / gind_chinatalk / gind_eladgil / gind_newcomer /
  gind_pragmaticengineer / gind_bairblog / global_apple_ml /
  global_nvidia_blog / global_nvidia_dev / asen_thedecoder /
  asen_venturebeat / ofc_techcrunch / global_theverge /
  global_arstechnica / global_technologyreview，以及 upstream 报告
  列出的 asen_semiengineering / asen_eetimes / gind_chipsandcheese /
  ofc_eia / ofc_doe / gind_merics / global_infoq_en 等，一律跳过。
* 注意：ai_techcrunch_ai / ai_theverge_ai / ai_arstechnica_ai /
  ai_mittr_ai 与存量全站 feed 存在**内容**重叠（slug/URL 均不同），
  按 AI 栏目精确版收录（us-models 报告建议的升级选项），如后续主
  会话决策下线存量全站 feed 可平滑切换。

Skipped — assigned to the Chinese batch (per coordinator ruling)
----------------------------------------------------------------
* ai_arxiv_csai / ai_arxiv_cscl / ai_arxiv_csma (arXiv 其余三个栏目)
* yt_hungyilee（李宏毅，中文）、pod_sdzaokafei / pod_shangyejushi /
  pod_haiwaidujiaoshou（中文播客）、全部公众号/知乎源。

Rejected — no usable feed (❌ in the reports, recorded for the record)
----------------------------------------------------------------------
* 实验室：Anthropic / Meta AI / xAI / Mistral / Cohere / AI21 / AI2
  （无官方 RSS 或 Cloudflare 403）——靠 ai_thezvi / ai_theinformation /
  ai_simonwillison(存量) / ai_theverge_ai 二手覆盖。
* VC/通讯：a16z 主站 / BVP Atlas / Greylock / Stanford HAI /
  DeepLearning.AI The Batch / The Rundown AI（无公开 feed）。
* 上游：videocardz / hpcwire / aiwire / nextplatform / blocksandfiles /
  insidehpc / datacenterdynamics / datacenterfrontier / sdxcentral /
  lightreading / dgtlinfra / baxtel / allaboutcircuits / guru3d /
  electronicsweekly / thememoryguy / counterpoint / yole / omdia /
  techinsights / semi_org / semiconductor_today / compoundsemi /
  microgrid_knowledge / lightwave / powergrid_intl / tdworld / epri /
  rmi / lawfare / brookings / federalregister_ai / cisa_alerts /
  ferc_news / commerce_gov / nerc_news / broadcom_blog / asml_news /
  tsmc_blog / amd_blog / appliedmaterials_blog / qualcomm_blog /
  nxp_blog / oracle_cloud_infra / coreweave_blog（403/PoW/无 feed，
  高价值者建议后续走 Jina/浏览器通道，见 upstream 报告第四节）。

Design notes
------------
* **Table-driven**: one row per source
  ``(slug, display_name, url, market, language)``; the slug **is** the
  full source id (it already carries the gind_/ofc_/pod_/yt_/ai_
  namespace or is a bare upstream slug), matching the dedup semantics
  of ``existing_sources.txt``.
* **Batches restart at "a"**: 99 feeds sliced into batches ``a``-``j``
  of <=10 (job namespace ``news_aius_*``).
* **Market is ``us`` for every row — never ``global``**: the news
  API's ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)`` and the
  frontend "global" filter expands to that same set, so articles
  written with market="global" would be invisible in the default view
  (``app/api/v1/news.py::_expand_market_filter``). Same ruling as
  ``en_fin_batch`` / ``asia_en_batch``. Language is uniformly ``en``;
  the translation drain picks articles up automatically.
* **Podcast feeds (pod_*)**: content is shownotes/episode descriptions
  (low text density) — titles+links land directly; the article-body
  fetch layer will try to enrich. YouTube feeds (yt_*) likewise carry
  the video description inside the entry.
* **Browser UA mandatory**: ``digitimes`` and ``micron_pr`` only serve
  the feed to browser UAs (upstream report §4.1); the crawler UA below
  is what the verification rounds used. Substack feeds are rate-limit
  sensitive — the crawler is sequential with a 2s inter-feed delay.
* **arXiv volume**: cs.LG/cs.CV publish dozens of papers/day; the
  default ``max_items_per_feed=10`` caps each run, same as every other
  batch wave.
* **No LLM marketing filter**: curated outlets/blogs, same precedent
  as every earlier batch wave — the scheduler job writes directly
  after fetch, keeping LLM cost flat.
* **No ``default_tz`` override**: every feed carries proper
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

# (slug, display_name, feed_url, market, language). The slug is the full
# source id (gind_/ofc_/pod_/yt_/ai_ namespace or bare upstream slug).
AI_US_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 英文 Newsletter / Substack（self-media 报告 §1，9 个）──
    ("gind_thegradient", "The Gradient", "https://thegradient.pub/rss/", "us", "en"),
    ("gind_stratechery", "Stratechery (Ben Thompson)", "https://stratechery.com/feed/", "us", "en"),
    ("gind_aisupremacy", "AI Supremacy", "https://aisupremacy.substack.com/feed", "us", "en"),
    ("gind_importai", "Import AI (Jack Clark)", "https://jack-clark.net/feed/", "us", "en"),
    ("gind_thesequence", "The Sequence", "https://thesequence.substack.com/feed", "us", "en"),
    ("gind_latentspace", "Latent Space (swyx)", "https://latent.space/feed", "us", "en"),
    ("gind_chinai", "ChinAI (Jeff Ding)", "https://chinai.substack.com/feed", "us", "en"),
    ("gind_garymarcus", "Marcus on AI (Gary Marcus)", "https://garymarcus.substack.com/feed", "us", "en"),
    ("gind_bensbites", "Ben's Bites", "https://bensbites.substack.com/feed", "us", "en"),
    # ── AI 实验室官方博客（self-media 报告 §2，3 个）──
    ("ofc_openai_blog", "OpenAI Blog", "https://openai.com/blog/rss.xml", "us", "en"),
    ("ofc_google_ai_blog", "Google AI Blog", "https://blog.google/technology/ai/rss/", "us", "en"),
    ("ofc_deepmind_blog", "Google DeepMind Blog", "https://deepmind.google/blog/rss.xml", "us", "en"),
    # ── 模型层/研究层/社区/VC（us-models 报告去重后唯一条目）──
    ("google_research", "Google Research Blog", "https://research.google/blog/rss/", "us", "en"),
    ("ai_msft_research", "Microsoft Research Blog", "https://www.microsoft.com/en-us/research/feed/", "us", "en"),
    ("ai_amazon_science", "Amazon Science", "https://www.amazon.science/index.rss", "us", "en"),
    ("ai_eleutherai", "EleutherAI Blog", "https://blog.eleuther.ai/index.xml", "us", "en"),
    ("databricks_blog", "Databricks Blog", "https://www.databricks.com/feed", "us", "en"),
    ("ai_tldr_ai", "TLDR AI", "https://tldr.tech/api/rss/ai", "us", "en"),
    ("ai_mitnews_ai", "MIT News - AI", "https://news.mit.edu/rss/topic/artificial-intelligence2", "us", "en"),
    ("huggingface_blog", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "us", "en"),
    ("ai_swyx", "swyx (Shawn Wang)", "https://www.swyx.io/rss.xml", "us", "en"),
    ("ai_thezvi", "Don't Worry About the Vase (Zvi)", "https://thezvi.substack.com/feed", "us", "en"),
    ("ai_chiphuyen", "Chip Huyen Blog", "https://huyenchip.com/feed.xml", "us", "en"),
    ("ai_lilianweng", "Lil'Log (Lilian Weng)", "https://lilianweng.github.io/index.xml", "us", "en"),
    ("ai_sequoia", "Sequoia Capital", "https://www.sequoiacap.com/feed/", "us", "en"),
    ("ai_epoch_ai", "Epoch AI (Gradient Updates)", "https://epochai.substack.com/feed", "us", "en"),
    ("ai_exponentialview", "Exponential View (Azeem Azhar)", "https://www.exponentialview.co/feed", "us", "en"),
    ("ai_usv", "Union Square Ventures", "https://www.usv.com/feed", "us", "en"),
    ("ai_cerebralvalley", "Cerebral Valley", "https://cerebralvalley.substack.com/feed", "us", "en"),
    # ── 论文（us-models 报告；只收 cs.LG / cs.CV，其余归中文批次）──
    ("ai_arxiv_cslg", "arXiv cs.LG (Machine Learning)", "https://arxiv.org/rss/cs.LG", "us", "en"),
    ("ai_arxiv_cscv", "arXiv cs.CV (Computer Vision)", "https://arxiv.org/rss/cs.CV", "us", "en"),
    # ── 深度评论与媒体 AI 栏目（us-models 报告）──
    # ai_theinformation 正文付费，标题+摘要层免费可抓。
    ("ai_theinformation", "The Information", "https://www.theinformation.com/feed", "us", "en"),
    ("ai_techcrunch_ai", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "us", "en"),
    ("ai_theverge_ai", "The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "us", "en"),
    ("ai_arstechnica_ai", "Ars Technica AI", "https://arstechnica.com/ai/feed/", "us", "en"),
    ("ai_mittr_ai", "MIT Technology Review - AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "us", "en"),
    # ── 上游：供应链/半导体（upstream 报告 §1）──
    # digitimes / micron_pr 需浏览器 UA 才出 feed（crawler 默认 UA 已覆盖）。
    ("trendforce", "TrendForce", "https://www.trendforce.com/news/feed/", "us", "en"),
    ("digitimes", "DIGITIMES", "https://www.digitimes.com/rss/daily.xml", "us", "en"),
    ("micron_pr", "Micron Investor News", "https://investors.micron.com/rss/news-releases.xml", "us", "en"),
    ("lamresearch_pr", "Lam Research Newsroom", "https://newsroom.lamresearch.com/press-releases?pagetemplate=rss", "us", "en"),
    ("intel_newsroom", "Intel Newsroom", "https://newsroom.intel.com/feed", "us", "en"),
    ("arm_newsroom", "Arm Newsroom", "https://newsroom.arm.com/news/feed/", "us", "en"),
    ("semiconductor_digest", "Semiconductor Digest", "https://www.semiconductor-digest.com/feed/", "us", "en"),
    ("morethanmoore", "More than Moore (Ian Cutress)", "https://morethanmoore.substack.com/feed", "us", "en"),
    ("thechipletter", "The Chip Letter", "https://thechipletter.substack.com/feed", "us", "en"),
    ("phoronix", "Phoronix", "https://www.phoronix.com/rss.php", "us", "en"),
    ("igorslab", "Igor's Lab (EN)", "https://www.igorslab.de/en/feed/", "us", "en"),
    ("eejournal", "EE Journal", "https://www.eejournal.com/feed/", "us", "en"),
    ("3dincites", "3D InCites", "https://3dincites.com/feed/", "us", "en"),
    # ── 上游：数据中心/网络 ──
    ("datacenterknowledge", "Data Center Knowledge", "https://www.datacenterknowledge.com/rss.xml", "us", "en"),
    ("uptime_journal", "Uptime Institute Journal", "https://journal.uptimeinstitute.com/feed/", "us", "en"),
    ("fierce_network", "Fierce Network", "https://www.fierce-network.com/rss.xml", "us", "en"),
    ("capacitymedia", "Capacity Media", "https://www.capacitymedia.com/rss", "us", "en"),
    ("rcrwireless", "RCR Wireless", "https://www.rcrwireless.com/feed", "us", "en"),
    ("datacenterpost", "Data Center POST", "https://datacenterpost.com/feed/", "us", "en"),
    ("cloudflare_blog", "Cloudflare Blog", "https://blog.cloudflare.com/rss/", "us", "en"),
    ("siliconangle", "SiliconANGLE", "https://siliconangle.com/feed", "us", "en"),
    ("networkworld", "Network World", "https://www.networkworld.com/feed/", "us", "en"),
    # ── 上游：能源/电力 ──
    ("heatmap", "Heatmap News", "https://heatmap.news/feeds/feed.rss", "us", "en"),
    ("latitudemedia", "Latitude Media", "https://www.latitudemedia.com/feed/", "us", "en"),
    ("rtoinsider", "RTO Insider", "https://www.rtoinsider.com/feed/", "us", "en"),
    ("energystorage_news", "Energy Storage News", "https://www.energy-storage.news/feed/", "us", "en"),
    ("pvmagazine_usa", "pv magazine USA", "https://pv-magazine-usa.com/feed/", "us", "en"),
    ("berkeley_lab", "Berkeley Lab News", "https://newscenter.lbl.gov/feed/", "us", "en"),
    # ── 上游：政策/智库 ──
    ("nist_news", "NIST News", "https://www.nist.gov/news-events/news/rss.xml", "us", "en"),
    ("csis", "CSIS", "https://www.csis.org/rss.xml", "us", "en"),
    ("cset", "Georgetown CSET", "https://cset.georgetown.edu/rss/", "us", "en"),
    ("rhodium", "Rhodium Group", "https://rhg.com/feed/", "us", "en"),
    ("itif", "ITIF", "https://itif.org/feed/", "us", "en"),
    # ── 上游：云厂商 AI 基建 ──
    ("aws_hpc", "AWS HPC Blog", "https://aws.amazon.com/blogs/hpc/feed/", "us", "en"),
    ("azure_blog", "Azure Blog", "https://azure.microsoft.com/en-us/blog/feed/", "us", "en"),
    ("google_cloud_blog", "Google Cloud Blog", "https://cloudblog.withgoogle.com/rss/", "us", "en"),
    ("lambda_blog", "Lambda Blog", "https://lambda.ai/blog/rss.xml", "us", "en"),
    # ── 英文播客（self-media 报告 §3，15 个；正文以 shownotes/
    #    description 为主，正文层会尝试补抓）──
    ("pod_dwarkesh", "Dwarkesh Podcast", "https://apple.dwarkesh-podcast.workers.dev/feed.rss", "us", "en"),
    ("pod_bg2", "BG2Pod (Gerstner & Gurley)", "https://anchor.fm/s/f06c2370/podcast/rss", "us", "en"),
    ("pod_acquired", "Acquired", "https://feeds.transistor.fm/acquired", "us", "en"),
    ("pod_a16z", "The a16z Show", "https://feeds.simplecast.com/JGE3yC0V", "us", "en"),
    ("pod_nopriors", "No Priors (Conviction)", "https://feeds.megaphone.fm/nopriors", "us", "en"),
    ("pod_trainingdata", "Training Data (Sequoia)", "https://feeds.megaphone.fm/trainingdata", "us", "en"),
    ("pod_allin", "All-In Podcast", "https://rss.libsyn.com/shows/254861/destinations/1928300.xml", "us", "en"),
    ("pod_20vc", "The Twenty Minute VC", "https://rss.libsyn.com/shows/61840/destinations/240976.xml", "us", "en"),
    ("pod_eyeonai", "Eye On A.I. (Craig Smith)", "https://rss.libsyn.com/shows/123267/destinations/727317.xml", "us", "en"),
    ("pod_aibreakdown", "AI Breakdown (NLW)", "https://media.rss.com/ai-breakdown/feed.xml", "us", "en"),
    ("pod_mlstreettalk", "Machine Learning Street Talk", "https://anchor.fm/s/1e4a0eac/podcast/rss", "us", "en"),
    ("pod_cognitiverev", "The Cognitive Revolution", "https://feeds.megaphone.fm/RINTP3108857801", "us", "en"),
    ("pod_hardfork", "Hard Fork (NYT)", "https://feeds.simplecast.com/6HKOhNgS", "us", "en"),
    ("pod_sharptech", "Sharp Tech (Ben Thompson)", "https://sharptech.fm/feed/podcast", "us", "en"),
    ("pod_twimlai", "TWIML AI Podcast", "https://twimlai.com/feed/podcast/", "us", "en"),
    # ── 英文 YouTube 频道（self-media 报告 §5，11 个；description 在
    #    entry 内，同播客规则由正文层补抓）──
    ("yt_asianometry", "Asianometry", "https://www.youtube.com/feeds/videos.xml?channel_id=UC1LpsuAUaKoMzzJSEt5WImw", "us", "en"),
    ("yt_mooreslawisdead", "Moore's Law Is Dead", "https://www.youtube.com/feeds/videos.xml?channel_id=UCRPdsCVuH53rcbTcEkuY4uQ", "us", "en"),
    ("yt_twominutepapers", "Two Minute Papers", "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg", "us", "en"),
    ("yt_yannickilcher", "Yannic Kilcher", "https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew", "us", "en"),
    ("yt_aiexplained", "AI Explained", "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw", "us", "en"),
    ("yt_matthewberman", "Matthew Berman", "https://www.youtube.com/feeds/videos.xml?channel_id=UCawZsQWqfGSbCI5yjkdVkTA", "us", "en"),
    ("yt_wesroth", "Wes Roth", "https://www.youtube.com/feeds/videos.xml?channel_id=UCqcbQf6yw5KzRoDDcZ_wBSw", "us", "en"),
    ("yt_theaigrid", "TheAIGRID", "https://www.youtube.com/feeds/videos.xml?channel_id=UCbY9xX3_jW5c2fjlZVBI4cg", "us", "en"),
    ("yt_mattvidpro", "MattVidPro AI", "https://www.youtube.com/feeds/videos.xml?channel_id=UCXD9sGdcD3-l12dPo_PhTZQ", "us", "en"),
    ("yt_coldfusion", "ColdFusion", "https://www.youtube.com/feeds/videos.xml?channel_id=UC4QZ_LsYcvcq7qOsOhpAX4A", "us", "en"),
    ("yt_bloombergtech", "Bloomberg Technology", "https://www.youtube.com/feeds/videos.xml?channel_id=UCrM7B7SL_g1edFOnmj-SDKg", "us", "en"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcdefghij"  # job namespace news_aius_* is unique, so keys restart at "a".
AI_US_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: AI_US_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if AI_US_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py in the wiring commit (handled by the coordinating
# session, not this module).
AI_US_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_aius_{key}_60m", f"AI链-英文 批次{key.upper()}", key)
    for key in AI_US_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class AiUsBatchCrawler:
    """Sequentially crawl one batch of English AI-chain RSS/Atom feeds.

    Mirrors :class:`EnFinBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: ``digitimes``
    and ``micron_pr`` only serve the feed to browser UAs, and this UA
    string is exactly what the verification rounds used.
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
        rows = AI_US_BATCHES.get(self._batch_key, [])
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
                            # The slug is the full source id (see module
                            # docstring) — no extra prefix is added.
                            source=feed.slug,
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                            # English feeds all carry proper RFC-2822 /
                            # ISO-8601 timestamps (verified 2026-08-04);
                            # no default_tz override needed — naive
                            # values correctly fall back to UTC.
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ai us batch %s: feed %s failed: %s",
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


def crawl_ai_us_batch(batch_key: str) -> list[RawArticle]:
    """Synchronous entry point: crawl one batch, return RawArticles.

    Same shape as the other batch waves' crawl path (crawler +
    ``fetch_recent``); the scheduler wrapper handles DB writes and ETL
    recording. Unknown batch keys return an empty list.
    """

    async def _go() -> list[RawArticle]:
        return await AiUsBatchCrawler(batch_key).fetch_recent()

    return asyncio.run(_go())
