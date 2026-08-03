"""Batch crawler for China AI industry-chain feeds (2026-08-04).

Why this exists
---------------
AI 产业链资讯源批次 — 面向关注中美 AI 全产业链投资机会的用户，补三类信号：
大模型厂商/云厂商一手发布、AI 应用与开源社区、半导体/算力/政策上游。
全部 feed 均来自 2026-08-04 三份搜罗报告中**实测通过（✅/镜像✅）**的条目：

1. ``docs/dev-notes/ai-chain-sources/20260804-cn-ai-models-apps.md``
   表 1（17 个：6 个 wechat2rss 镜像公众号 + 美团/HelloGitHub/V2EX 原生
   + Qwen/OpenMMLab/HuggingFace/ProductHunt 境外原生 + 4 个 arXiv）
2. ``docs/dev-notes/ai-chain-sources/20260804-cn-ai-upstream.md``
   实测结果总表中 ✅ 的 15 站 18 个 feed（半导体/算力/云/官媒）
3. ``docs/dev-notes/ai-chain-sources/20260804-self-media.md``
   仅中文源：3 个中文播客（喜马拉雅/小宇宙官方 feed）+ 1 个中文 YouTube
   频道（李宏毅）。该报告的英文 newsletter/播客/YouTube/实验室博客全部
   归另一批次（英文 AI 自媒体批），本模块一律不收。

Selection & dedup rule
----------------------
* 排重基准 ``/tmp/adresearch-build/existing_sources.txt``（1012 存量 slug）
  逐条 grep 比对；报告里标注"已覆盖/存量"的源一律不接。
* **被拒/跳过清单（含原因）**：
  - ``wechat_xixiaoyao``（夕小瑶科技说）—— 存量已覆盖：
    ``wechat2rss_batch.py`` 已有 ``("xixiaoyao", ..., 同一 hash
    a1cd365a...)``，source=wechat_xixiaoyao 已在库，跳过。
  - ``cn_meituan_tech``（upstream 报告 atom.xml 变体）—— 与报告 1 的
    ``zhb_meituan_tech``（tech.meituan.com/feed/）同站同源内容重复，
    保留 ``zhb_meituan_tech``，跳过 atom.xml 变体。
  - self-media 报告的 16 个中文公众号（wechat_zimubang /
    wechat_ailanmeihui / wechat_pingwest / wechat_zhinengyongxian /
    wechat_guangzhui / wechat_shuzhiqianxian / wechat_dianchang /
    wechat_jiqizhineng / wechat_xinsixiang / wechat_xinshiye /
    wechat_jiweinet / wechat_bdctzongheng / wechat_touzhongwang /
    wechat_dsstziben / wechat_alphagongchang / wechat_jinduan）——
    报告标注"走存量 wechat2rss 镜像通道，免测"，**未提供实测 feed URL
    （wechat2rss hash 未知）**，本表驱动模块无法凭空造 URL，全部留给
    主会话经 wechat2rss 通道补 hash 后另批接入（注意其中
    智能涌现/集微网 等与存量或本批 cn_laoyaoba 内容重叠，接入前须再
    grep 查重）。
  - self-media 报告的知乎专栏（极市平台/计算机视觉life）—— 依赖自建
    RSSHub，报告自身列为"备选-需镜像"，不接。
  - 三份报告各自的 ❌ 实测失败表（品玩/果壳/智源社区/eet-china/
    esmchina/eetop/政府部委无 RSS 站等）—— 一律不接，原因见各报告。
* 模块内部 slug / feed URL 零重复（测试锁定）。

Charset / encoding notes（重要）
-------------------------------
* 非 UTF-8 编码的 feed（报告实测标注）：
  ``cn_c114_top`` / ``cn_c114_policy`` / ``cn_zol_cpu`` /
  ``cn_yesky_news`` 为 **GB2312**，``cn_cfol`` 为 **GBK**。
* 已核实通用抓取层现状：``rss_common.parse_rss_items`` 只接受 ``str``
  不做编码处理；``en_fin_batch`` 等既有批次直接传 ``resp.text``；httpx
  0.28 在响应头缺 charset 时**不会**自动嗅探（本机实测 GB2312 字节
  无 charset 头时 ``resp.text`` 解码为替换字符 �）。因此本模块在
  抓取层自带 ``_decode_feed_body``：优先按 XML prolog
  （``<?xml ... encoding="GB2312"?>``）声明的编码解码原始字节，
  未声明或声明为 UTF-8 时回落 ``resp.text``（此时 httpx 已按
  Content-Type 头 charset 正确处理，实测 charset=GB2312 头可正确
  解码）。**WARNING 给主会话**：若上述 5 个 legacy 源上线后出现乱码，
  说明其 prolog 未声明编码且响应头也缺 charset，需在抓取层加
  charset_normalizer 嗅探兜底（charset-normalizer 已在依赖树中）。

Market / language ruling
------------------------
* ``market`` 只允许 ``cn_a`` / ``us``——**绝不许用 "global"**：news API
  的 ``_GLOBAL_MARKETS`` 白名单只有 ``(cn_a, us, crypto)``
  （``app/api/v1/news.py::_expand_market_filter``），market="global"
  会在默认视图隐形（同 ``en_fin_batch`` / ``asia_en_batch`` 裁决）。
  中文源（含公众号镜像/中文播客/李宏毅 YT）= ``cn_a``；英文源
  （arXiv x4 / qwen blog / huggingface / producthunt / openmmlab）
  = ``us``。英文行进已有的自动翻译 drain。
* ``source`` 字段 = slug 原样（报告建议 slug 已含 wechat_/zhb_/ofc_/
  global_/asen_/cn_/pod_/yt_ 前缀，沿用报告命名，不再加模块前缀——
  与 enf_/zhm_ 批次的"模块前缀"模式不同，是本批的显式裁决）。

Design notes
------------
* **表驱动**：每行 ``(slug, display_name, url, market, language)``；
  37 个 feed 切成批次 ``a``-``d``，每批 <=10，批次键从 "a" 开始；
  job 命名空间 ``news_aicn_*``（job_id ``news_aicn_{batch}_60m``，
  label "AI链-中文 批次X"）。
* **境外源连通性**：qwenlm.github.io / medium.com / huggingface.co
  在中国大陆间歇不可达（报告实测注明），部署后须先在 ECS 复测，
  不可达则暂缓启用对应行；producthunt.com / arxiv.org 实测稳定。
* **播客/YouTube feed 正文信息量低**（shownotes/description），同
  self-media 报告建议：这类源只取标题+链接入库即可，由既有管线处理。
* **No LLM marketing filter**：与既有所有批次波次同一先例，scheduler
  job 抓取后直接写库，LLM 成本持平。
* 接线（scheduler_jobs.py / scheduler.py / news.py /
  source_meta_seed.py）由主会话统一完成，本模块只提供表与 crawler。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language). source = slug 原样。
AI_CN_FEEDS: list[tuple[str, str, str, str, str]] = [
    # ── 批次 a：wechat2rss 镜像公众号（厂商技术号+产业观察）+ 境外官方 ──
    ("wechat_tanjiti", "碳基体", "https://wechat2rss.xlab.app/feed/4bc6a2ecb1feb2bd2961a898905147c9f76a4c3a.xml", "cn_a", "zh"),
    ("wechat_aliyun_dev", "阿里云开发者", "https://wechat2rss.xlab.app/feed/c74ed6db00cfbf16f2a048a165b4453f982681f0.xml", "cn_a", "zh"),
    ("wechat_alitech", "阿里技术", "https://wechat2rss.xlab.app/feed/6e1f9b775f7a5841ac1a94310f0478b45a02ec01.xml", "cn_a", "zh"),
    ("wechat_bytedance_tech", "字节跳动技术团队", "https://wechat2rss.xlab.app/feed/4025ea55575daf8bfd8227e68b28d9638b073267.xml", "cn_a", "zh"),
    ("wechat_tencent_tech", "腾讯技术工程", "https://wechat2rss.xlab.app/feed/9685937b45fe9c7a526dbc32e4f24ba879a65b9a.xml", "cn_a", "zh"),
    ("zhb_meituan_tech", "美团技术团队", "https://tech.meituan.com/feed/", "cn_a", "zh"),
    # 境外源：中国大陆间歇不可达，ECS 部署后须复测（见 docstring）
    ("ofc_qwen_blog", "Qwen 官方博客（阿里通义）", "https://qwenlm.github.io/blog/index.xml", "us", "en"),
    ("global_openmmlab", "OpenMMLab（商汤系开源社区）", "https://openmmlab.medium.com/feed", "us", "en"),
    # 注意：Hugging Face Blog（huggingface.co/blog/feed.xml）英文源归
    # ai_us_batch（slug huggingface_blog），本波不重复收录（跨波撞车裁决）。
    ("global_producthunt", "Product Hunt", "https://www.producthunt.com/feed", "us", "en"),
    # ── 批次 b：应用/开源/社区 + arXiv 论文上游 + 半导体研究 ──
    ("ofc_hellogithub", "HelloGitHub 月刊", "https://hellogithub.com/rss", "cn_a", "zh"),
    ("zhb_v2ex_create", "V2EX 分享创造节点", "https://www.v2ex.com/feed/create.xml", "cn_a", "zh"),
    ("asen_arxiv_cscl", "arXiv cs.CL（计算与语言）", "https://arxiv.org/rss/cs.CL", "us", "en"),
    ("asen_arxiv_csai", "arXiv cs.AI（人工智能）", "https://arxiv.org/rss/cs.AI", "us", "en"),
    ("asen_arxiv_csro", "arXiv cs.RO（机器人学）", "https://arxiv.org/rss/cs.RO", "us", "en"),
    ("asen_arxiv_csma", "arXiv cs.MA（多智能体系统）", "https://arxiv.org/rss/cs.MA", "us", "en"),
    ("cn_laoyaoba", "集微网", "https://www.laoyaoba.com/api/rss/hbb", "cn_a", "zh"),
    ("cn_trendforce_semi", "集邦咨询-半导体", "https://www.trendforce.cn/feed/Semiconductors.html", "cn_a", "zh"),
    ("cn_trendforce_emerging", "集邦咨询-新兴科技", "https://www.trendforce.cn/feed/Emerging_technology.html", "cn_a", "zh"),
    ("cn_trendforce_energy", "集邦咨询-新能源", "https://www.trendforce.cn/feed/Energy.html", "cn_a", "zh"),
    # ── 批次 c：算力/通信/硬件/开发者上游（含 5 个 GB2312/GBK 源） ──
    ("cn_cena", "电子信息产业网（中国电子报）", "https://www.cena.com.cn/index.rss", "cn_a", "zh"),
    ("cn_c114_top", "C114 中国通信网-要闻精选", "http://www.c114.com.cn/rss/rss_news_489.xml", "cn_a", "zh"),  # GB2312
    ("cn_c114_policy", "C114-行业政策", "http://www.c114.com.cn/rss/rss_news_518.xml", "cn_a", "zh"),  # GB2312
    ("cn_cfol", "光纤在线", "http://www.c-fol.net/news/rss.php", "cn_a", "zh"),  # GBK
    ("cn_dostor", "存储在线", "http://www.dostor.com/rss", "cn_a", "zh"),
    ("cn_zol_cpu", "中关村在线-CPU 频道", "http://rss.zol.com.cn/cpu.xml", "cn_a", "zh"),  # GB2312
    ("cn_yesky_news", "天极网-资讯频道", "http://news.yesky.com/index.xml", "cn_a", "zh"),  # GB2312
    ("cn_elecfans_bbs", "电子发烧友论坛", "https://bbs.elecfans.com/forum.php?mod=rss&auth=0", "cn_a", "zh"),
    ("cn_juejin", "掘金", "https://juejin.cn/rss", "cn_a", "zh"),
    # 注意：与存量 global_aws_blog（英文 AWS News Blog）不同源不同语言
    ("cn_aws_blog", "AWS 中国官方博客", "https://aws.amazon.com/cn/blogs/china/feed/", "cn_a", "zh"),
    # ── 批次 d：官媒政策叙事 + 中文播客/中文 YouTube ──
    ("cn_people_it", "人民网-IT 频道", "http://www.people.com.cn/rss/it.xml", "cn_a", "zh"),
    ("cn_people_scitech", "人民网-科技频道", "http://www.people.com.cn/rss/scitech.xml", "cn_a", "zh"),
    ("cn_people_energy", "人民网-能源频道", "http://www.people.com.cn/rss/energy.xml", "cn_a", "zh"),
    ("pod_sdzaokafei", "声动早咖啡", "https://www.ximalaya.com/album/51076156.xml", "cn_a", "zh"),
    ("pod_shangyejushi", "商业就是这样", "http://www.ximalaya.com/album/46587439.xml", "cn_a", "zh"),
    ("pod_haiwaidujiaoshou", "海外独角兽（播客）", "https://feed.xyzfm.space/ym6ug8jctfp8", "cn_a", "zh"),
    ("yt_hungyilee", "Hung-yi Lee 李宏毅", "https://www.youtube.com/feeds/videos.xml?channel_id=UC2ggjtuuWvxrHHHiaDH1dlQ", "cn_a", "zh"),
]

_BATCH_SIZE = 10
_BATCH_KEYS = "abcd"  # job namespace news_aicn_* is unique, so keys restart at "a".
AI_CN_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    _BATCH_KEYS[i]: AI_CN_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range(len(_BATCH_KEYS))
    if AI_CN_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
}

# (job_id, label, batch_key) — materialized into run_* functions by
# scheduler_jobs.py in the wiring commit (handled by the main session).
AI_CN_BATCH_JOBS: list[tuple[str, str, str]] = [
    (f"news_aicn_{key}_60m", f"AI链-中文 批次{key.upper()}", key)
    for key in AI_CN_BATCHES
]

# XML prolog 编码声明（GB2312/GBK legacy 源，见模块 docstring charset 节）
_XML_PROLOG_ENCODING_RE = re.compile(
    rb'<\?xml[^>]*encoding=["\']([\w.-]+)["\']', re.IGNORECASE
)


def _decode_feed_body(resp: httpx.Response) -> str:
    """Decode a feed body honoring the XML prolog encoding declaration.

    httpx 0.28 在响应头缺 charset 时不做嗅探（实测 GB2312 字节变 �）；
    而这批 legacy 中文源（c114/zol/yesky=GB2312, c-fol=GBK）通常在
    ``<?xml ... encoding="..."?>`` 里声明真实编码。优先按 prolog 声明
    解码原始字节；未声明/声明 UTF-8/声明无法识别时回落 ``resp.text``
    （此时 Content-Type 头 charset 已由 httpx 正确处理）。
    """
    content = resp.content
    match = _XML_PROLOG_ENCODING_RE.search(content[:512])
    if match:
        try:
            declared = match.group(1).decode("ascii", errors="ignore").strip().lower()
        except Exception:  # noqa: BLE001 — 防御：声明非 ASCII 时直接回落
            declared = ""
        if declared and declared not in ("utf-8", "utf8"):
            try:
                return content.decode(declared, errors="replace")
            except (LookupError, ValueError):
                logger.warning("ai cn batch: unknown prolog encoding %r", declared)
    return resp.text


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class AiCnBatchCrawler:
    """Sequentially crawl one batch of China AI industry-chain feeds.

    Mirrors :class:`EnFinBatchCrawler`. Unknown batch keys yield an
    empty crawl (defensive — a config typo must never crash the
    scheduler). A desktop browser User-Agent is mandatory: several
    outlets 403 plain curl-style UAs, and this UA string matches what
    the verification rounds in the sourcing reports used.
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
        rows = AI_CN_BATCHES.get(self._batch_key, [])
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
                            _decode_feed_body(resp),
                            source=feed.slug,  # source = slug 原样（显式裁决）
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ai cn batch %s: feed %s failed: %s",
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


async def crawl_ai_cn_batch(batch_key: str) -> dict:
    """Crawl one batch and return a summary dict.

    返回结构：``{"batch": batch_key, "feed_count": int,
    "article_count": int, "articles": list[RawArticle]}``。
    未知批次键返回零值摘要（不抛异常），与 crawler 的防御语义一致。
    """
    crawler = AiCnBatchCrawler(batch_key)
    articles = await crawler.fetch_recent()
    return {
        "batch": batch_key,
        "feed_count": len(crawler.feeds),
        "article_count": len(articles),
        "articles": articles,
    }
