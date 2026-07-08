#!/usr/bin/env python3
"""
gov_china.py - China official policy news worker.

Sources:
  - 中国政府网最新政策:  https://www.gov.cn/zhengce/index.htm
  - 中国人民银行新闻:   http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html
  - 证监会要闻:         http://www.csrc.gov.cn/csrc/c100028/common_list.shtml
  - 商务部新闻发布:     http://www.mofcom.gov.cn/xwfb/

Strategy:
  1. Scrape each agency's list page with BeautifulSoup to get title/URL/date.
  2. Fetch the article detail page (via jina.ai reader, fallback to direct HTML)
     to extract the full body and confirm the publish time.
  3. Drop navigation/portal noise using title/URL blacklists and a lightweight
     DeepSeek LLM classifier for edge cases.
  4. Output items with: title, url, published_at (ISO-8601 UTC), summary, content,
     agency, agency_name, source.

Usage:
  python gov_china.py                       # last 24h, all four sources
  python gov_china.py --hours 48
  python gov_china.py --sources pbc,csrc   # filter agencies
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CST,
    UTC,
    base_parser,
    http_get,
    make_session,
    parse_dt,
    setup_logger,
    utcnow,
    within_hours,
    write_json,
)

SOURCE = "gov_china"

SOURCES: dict[str, dict[str, Any]] = {
    "gov": {
        "name": "中国政府网",
        "homepage": "https://www.gov.cn/zhengce/index.htm",
        "homepage_fallback": "https://www.gov.cn/",
        "rss_candidates": [],
        "base_url": "https://www.gov.cn",
    },
    "pbc": {
        "name": "中国人民银行",
        "homepage": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        "homepage_fallback": "http://www.pbc.gov.cn/",
        "rss_candidates": [],
        "base_url": "http://www.pbc.gov.cn",
    },
    "csrc": {
        "name": "证监会",
        "homepage": "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
        "homepage_fallback": "http://www.csrc.gov.cn/csrc/c100028/c1001005/content.shtml",
        "rss_candidates": [],
        "base_url": "http://www.csrc.gov.cn",
    },
    "mofcom": {
        "name": "商务部",
        "homepage": "http://www.mofcom.gov.cn/xwfb/",
        "homepage_fallback": "http://www.mofcom.gov.cn/",
        "rss_candidates": [],
        "base_url": "http://www.mofcom.gov.cn",
    },
}

# ---------------------------------------------------------------------------
# Noise filters
# ---------------------------------------------------------------------------

# Hard title keywords: drop immediately if any substring matches.
NOISE_TITLE_KEYWORDS: set[str] = {
    "政务联播",
    "留言入口",
    "国务院部门",
    "政策解读",
    "专题",
    "首页",
    "返回",
    "更多",
    "网站地图",
    "联系我们",
    "关于我们",
    "常见问题",
    "更新日志",
    "RSS订阅",
    "English",
    "English Version",
    "手机用户",
    "无障碍浏览",
    "图文直播",
    "音频视频",
    "报告下载",
    "报刊年鉴",
    "网送文告",
    "办事大厅",
    "在线申报",
    "下载中心",
    "网上调查",
    "意见征集",
    "金融知识",
    "中国投资者网",
    "中国资本市场标准网",
    "京ICP备",
    "归档数据",
    "时政要闻",
    "新闻发布",
    "最新政策",
    "政府信息公开",
    "惠企助企政策集纳查询",
    "国务院政策文件库",
    "国务院组织机构",
    "国务院公报",
    "国家行政法规库",
    "国家规章库",
    "建言征集",
    "回应关切",
    "我要留言",
    "人民群众留言入口",
    "为民服务",
    "企业、个体户留言入口",
    "为企服务",
    "政务服务投诉与建议入口",
    "开办企业",
    "经营发展",
    "企业用工",
    "纳税缴费",
    "注销退出",
    "全国人大",
    "全国政协",
    "国家监察委员会",
    "最高人民法院",
    "最高人民检察院",
    "地方政府网站",
    "驻港澳机构网站",
    "驻外机构",
    "中国政府网",
    "机构概况",
    "政务信息",
    "办事服务",
    "互动交流",
    "统计信息",
    "热点专题",
    "政务公开",
    "工作通知",
    "政策发布",
    "政策图解",
    "国务院信息",
    "国务院文件",
    "出口商品技术指南",
    "新闻发布会",
    "例行新闻发布会",
    "专题新闻发布会",
    "部领导活动",
    "领导人活动",
    "新闻发言人谈话",
    "司局负责人发布",
    "日常新闻发布",
    "学习宣传贯彻",
    "国家层面海外综合服务平台",
    "2025年度网站工作年度报表",
    "外资企业问题诉求收集办理",
    "优化营商环境",
    "提振消费专项行动",
    "关于本网",
    "网站声明",
    "法律声明",
    "归档数据",
}

# Soft navigation keywords: trigger LLM review if any substring matches.
NAV_TITLE_KEYWORDS: set[str] = {
    "入口",
    "平台",
    "专栏",
    "频道",
    "服务",
    "大厅",
    "中心",
    "系统",
    "查询",
    "库",
    "专题",
    "首页",
    "返回",
    "更多",
    "导航",
    "地图",
    "关于",
    "联系",
    "English",
    "手机",
    "无障碍",
    "RSS",
    "直播",
    "下载",
    "调查",
    "征集",
    "常见问题",
    "网站声明",
    "关于本网",
}

# Exact URL paths or path fragments that are known portal pages.
NOISE_URL_PATHS: set[str] = {
    "/zhengwulianbo/",
    "/home/2023-03/29/content_5748953.htm",
    "/home/2023-03/29/content_5748954.htm",
    "/home/2023-03/29/content_5748955.htm",
    "/home/2023-03/29/content_5748956.htm",
    "/home/2014-02/18/content_5046260.htm",
    "/home/2016-05/11/content_5046257.htm",
    "/home/2014-02/23/content_5046258.htm",
    "/home/2014-02/23/content_5046259.htm",
}

# ---------------------------------------------------------------------------
# Date / content extraction helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"(?P<year>20\d{2})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})"
    r"(?:[\s\-](?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?)?"
)


def _load_deepseek_key(logger) -> str | None:
    """Read DEEPSEEK_API_KEY from env or common env files."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key and key not in ("", "placeholder"):
        return key
    # When running directly on the ECS host, fall back to known env files.
    for path in ["/opt/ad-research/deploy/aliyun-ecs/.env", "/root/.claude/.env"]:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        val = line.split("=", 1)[1].strip()
                        if val and val not in ("", "placeholder"):
                            return val
        except Exception as exc:
            logger.debug("could not read %s: %s", path, exc)
    return None


def _parse_date(value: str | None) -> datetime | None:
    """Best-effort parse into a CST-aware datetime."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    # gov.cn detail meta: "2026-07-08-11:19:00"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(\d{2}):(\d{2}):(\d{2})", value)
    if m:
        return datetime(
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
            int(m.group(5)),
            int(m.group(6)),
            tzinfo=CST,
        )

    # ISO / RFC fallback already normalizes to UTC
    dt = parse_dt(value)
    if dt:
        return dt

    # Plain regex fallback, assume China Standard Time
    m = _DATE_RE.search(value)
    if m:
        return datetime(
            int(m.group("year")),
            int(m.group("month")),
            int(m.group("day")),
            int(m.group("hour") or 0),
            int(m.group("minute") or 0),
            int(m.group("second") or 0),
            tzinfo=CST,
        )

    return None


def _format_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.astimezone(UTC).isoformat()


def _parse_date_from_url(url: str) -> datetime | None:
    """Try to infer a date from the URL path (e.g. /202607/ or /20260708151045/)."""
    if not url:
        return None
    # /202607/content_7074516.htm
    m = re.search(r"/(\d{4})(\d{2})/content_", url)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=CST)
    # /2026070815104519914/
    m = re.search(r"/(\d{4})(\d{2})(\d{2})\d{10}/", url)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=CST)
    return None


# ---------------------------------------------------------------------------
# HTML fetching
# ---------------------------------------------------------------------------

def _fetch_html(session, url: str, logger) -> str | None:
    resp = http_get(
        session,
        url,
        headers={"Referer": url, "Accept": "text/html,application/xhtml+xml"},
        timeout=25,
    )
    if resp is None or resp.status_code != 200:
        logger.warning("HTML fetch %s failed: %s", url, getattr(resp, "status_code", None))
        return None
    # Some Chinese government sites serve UTF-8 bodies without a charset in the
    # Content-Type header, so requests defaults to ISO-8859-1. Prefer the meta
    # charset or chardet's guess before falling back to UTF-8.
    if resp.encoding in (None, "ISO-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


# ---------------------------------------------------------------------------
# List-page scraping
# ---------------------------------------------------------------------------

def _looks_like_article_url(url: str) -> bool:
    if not url:
        return False
    path = urlparse(url).path.lower()
    if "/art/" in path:
        return True
    if "content_" in path:
        return True
    if path.endswith("/content.shtml"):
        return True
    # PBC timestamp directory: /2026070815104519914/
    if re.search(r"/\d{14,}/", path):
        return True
    return False


def _is_noise_url(url: str) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(("/index.html", "/index.htm", "/index.shtml", "/")):
        return True
    for p in NOISE_URL_PATHS:
        if p in path:
            return True
    return False


def _is_noise_title(title: str) -> bool:
    if not title:
        return True
    t = title.strip()
    if len(t) < 4:
        return True
    for kw in NOISE_TITLE_KEYWORDS:
        if kw in t:
            return True
    return False


def _title_looks_nav(title: str) -> bool:
    if not title:
        return True
    t = title.strip()
    for kw in NAV_TITLE_KEYWORDS:
        if kw in t:
            return True
    return False


def _extract_list_date(element: Any) -> str | None:
    """Look for a date in the element or its siblings."""
    if element is None:
        return None
    txt = element.get_text(" ", strip=True)
    m = _DATE_RE.search(txt)
    if m:
        return m.group(0)
    # Look at following sibling spans
    for sibling in element.next_siblings:
        if getattr(sibling, "name", None) in ("span", "div", "td"):
            m = _DATE_RE.search(sibling.get_text(" ", strip=True))
            if m:
                return m.group(0)
    return None


def _scrape_homepage(session, cfg: dict[str, Any], logger) -> list[dict]:
    homepage = cfg["homepage"]
    html = _fetch_html(session, homepage, logger)
    if not html:
        return []

    try:
        from bs4 import BeautifulSoup
    except Exception as exc:
        logger.warning("BeautifulSoup not available: %s", exc)
        return _scrape_homepage_regex(html, homepage, logger)

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"].strip()
        if not title or len(title) < 4 or len(title) > 200:
            continue
        if href.startswith(("javascript:", "#", "mailto:")):
            continue
        url = urljoin(homepage, href)
        if url in seen_urls:
            continue
        if not _looks_like_article_url(url):
            continue
        seen_urls.add(url)

        # Date: prefer the parent <li>/<td> text, then siblings.
        parent = a.find_parent(["li", "td", "dd", "div"])
        date = _extract_list_date(parent)

        items.append(
            {
                "title": title,
                "url": url,
                "published_at": date,
                "summary": None,
                "source_feed": homepage,
            }
        )

    logger.info("BS4 scrape %s yielded %d candidate links", homepage, len(items))
    return items[:60]


TITLE_LINK_RE = re.compile(
    r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>[^<]{4,200})</a>',
    re.IGNORECASE,
)


def _scrape_homepage_regex(html: str, homepage: str, logger) -> list[dict]:
    """Fallback regex scraper (used when BeautifulSoup is missing)."""
    out: list[dict] = []
    seen_urls: set[str] = set()
    for m in TITLE_LINK_RE.finditer(html):
        title = (m.group("title") or "").strip()
        href = (m.group("href") or "").strip()
        if not title or not href or len(title) < 4:
            continue
        if href.startswith(("javascript:", "#")):
            continue
        absolute = urljoin(homepage, href)
        if absolute in seen_urls:
            continue
        seen_urls.add(absolute)
        if not _looks_like_article_url(absolute) or _is_noise_url(absolute):
            continue
        snippet = html[max(0, m.start() - 200) : m.end() + 200]
        date_m = _DATE_RE.search(snippet)
        out.append(
            {
                "title": title,
                "url": absolute,
                "published_at": date_m.group(0) if date_m else None,
                "summary": None,
                "source_feed": homepage,
            }
        )
    logger.info("regex scrape %s yielded %d candidate links", homepage, len(out))
    return out[:60]


def _try_feedparser(session, candidates: list[str], logger) -> list[dict]:
    try:
        import feedparser  # type: ignore
    except ImportError:
        logger.debug("feedparser not available, skipping RSS path")
        return []
    for feed_url in candidates:
        resp = http_get(session, feed_url, timeout=20)
        if resp is None or resp.status_code != 200:
            continue
        try:
            parsed = feedparser.parse(resp.content)
        except Exception as exc:
            logger.debug("feedparser parse %s failed: %s", feed_url, exc)
            continue
        if not parsed.entries:
            continue
        out: list[dict] = []
        for e in parsed.entries:
            out.append(
                {
                    "title": getattr(e, "title", "").strip(),
                    "url": getattr(e, "link", ""),
                    "published_at": getattr(e, "published", None) or getattr(e, "updated", None),
                    "summary": getattr(e, "summary", ""),
                    "source_feed": feed_url,
                }
            )
        if out:
            logger.info("RSS %s returned %d entries", feed_url, len(out))
            return out
    return []


# ---------------------------------------------------------------------------
# Detail-page extraction
# ---------------------------------------------------------------------------

def _clean_jina_content(text: str) -> str:
    """Remove navigation-only markdown lines from jina.ai output."""
    footer_kws = {
        "主办单位",
        "版权所有",
        "网站标识码",
        "京ICP备",
        "京公网安备",
        "国务院客户端",
        "中国政府网运行中心",
        "中文域名",
        "相关稿件",
        "链接：",
        "我要纠错",
        "责任编辑",
        "扫一扫在手机打开当前页",
    }
    nav_only_tokens = {
        "登录",
        "注册",
        "×",
        "收藏",
        "留言",
        "打印",
        "字号：默认 大 超大|打印",
        "|",
        "EN",
        "首页",
        "无障碍",
        "长者版",
    }
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # image-link lines: [![Image N](url)](url) or nested variants
        if re.match(r"^!?\[\s*!?\[[^\]]*\]\([^)]*\)\s*\]\([^)]*\)$", stripped):
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]*\)$", stripped):
            continue
        # empty bullet separators: "*   |", "*   -", "*"
        if re.match(r"^[\*\-•]\s*[|\-—\s]*$", stripped):
            continue
        # standalone markdown link or bullet link
        if re.match(r"^(\*\s*)?\[[^\]]+\]\([^)]+\)$", stripped):
            continue
        # bullet containing only a single nav link
        if re.match(r"^[\*\-•]\s+\[[^\]]+\]\([^)]+\)\s*$", stripped):
            continue
        # breadcrumb-like nav lines made of links separated by > or | or -
        if re.match(r"^(\[[^\]]+\]\([^)]+\)\s*[>|\-/]\s*)+\[[^\]]+\]\([^)]+\)$", stripped):
            continue
        # "链接：" repeated bullet list
        if re.match(r"^[\*\-•]\s*链接[:：]?\s*$", stripped):
            continue
        # footer / boilerplate lines
        if any(stripped.startswith(kw) for kw in footer_kws):
            continue
        # standalone site URL
        if stripped in (
            "https://www.gov.cn/",
            "http://www.gov.cn/",
            "http://www.pbc.gov.cn/",
            "http://www.csrc.gov.cn/",
            "http://www.mofcom.gov.cn/",
        ):
            continue
        # utility / nav-only buttons
        if stripped in nav_only_tokens:
            continue
        # social-share tooltips / titles: [](url 'title') or [](url "title")
        if re.match(r"^\[\]\([^)]+\s+['\"][^'\"]+['\"]\)\s*$", stripped):
            continue
        # bare number list like "1." or "2." (rare in body)
        if re.match(r"^\d+\.\s*$", stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _dedupe_body(text: str) -> str:
    """If the article body is repeated (gov.cn jina render sometimes does this),
    keep only the first occurrence of each long Chinese paragraph.
    """
    if not text:
        return text
    matches = list(
        re.finditer(r"[一-鿿][一-鿿\w\s，。、；：？！「」『』（）《》()【】…—\-]{80,}", text)
    )
    if len(matches) < 2:
        return text
    seen: set[str] = set()
    keep_parts: list[str] = []
    last_end = 0
    for m in matches:
        snippet = m.group(0)
        if snippet in seen:
            continue
        seen.add(snippet)
        if m.start() > last_end:
            keep_parts.append(text[last_end : m.start()])
        keep_parts.append(snippet)
        last_end = m.end()
    if last_end < len(text):
        keep_parts.append(text[last_end:])
    return "".join(keep_parts).strip()


def _extract_clean_paragraph(text: str, min_len: int = 40) -> str:
    """Find the first non-trivial Chinese paragraph in cleaned markdown.

    Used to build a useful ``summary`` that is not the nav/header cruft.
    """
    if not text:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Skip markdown image / link / bullet nav
        if re.match(r"^!?\[[^\]]*\]\([^)]*\)$", line):
            continue
        if re.match(r"^[\*\-•]\s*[|\-—\s]*$", line):
            continue
        if re.match(r"^[\*\-•]\s+\[[^\]]+\]\([^)]+\)\s*$", line):
            continue
        if re.match(r"^(\[[^\]]+\]\([^)]+\)\s*[>|\-/]\s*)+\[[^\]]+\]\([^)]+\)$", line):
            continue
        # Skip pure metadata lines like "**索 引 号：**..."
        if re.match(r"^\*\*[^*]+\*\*[:：]?$", line):
            continue
        # Strip residual markdown emphasis / link wrappers
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"^#+\s*", "", cleaned)
        cleaned = cleaned.strip()
        # Count CJK characters
        cjk = sum(1 for c in cleaned if "一" <= c <= "鿿")
        if len(cleaned) >= min_len and cjk >= 15:
            return cleaned
    # Fallback: return the longest non-trivial line we saw.
    fallback = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^!?\[[^\]]*\]\([^)]*\)$", line):
            continue
        if re.match(r"^(\[[^\]]+\]\([^)]+\)\s*[>|\-/]\s*)+\[[^\]]+\]\([^)]+\)$", line):
            continue
        cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"^#+\s*", "", cleaned)
        cleaned = cleaned.strip()
        cjk = sum(1 for c in cleaned if "一" <= c <= "鿿")
        if cjk >= 20 and len(cleaned) > len(fallback):
            fallback = cleaned
    return fallback


def _extract_article_jina(session, url: str, logger) -> dict[str, Any]:
    """Use jina.ai reader to fetch title, date and cleaned markdown body."""
    jina_url = f"https://r.jina.ai/{url}"
    resp = http_get(session, jina_url, headers={"Accept": "text/plain"}, timeout=40)
    if resp is None or resp.status_code != 200:
        logger.debug("jina.ai fetch failed for %s: %s", url, getattr(resp, "status_code", None))
        return {}
    text = resp.text
    out: dict[str, Any] = {}

    m = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["title"] = m.group(1).strip()

    m = re.search(r"^URL Source:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["url"] = m.group(1).strip()

    m = re.search(r"^Published Time:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["published_at"] = m.group(1).strip()

    m = re.search(r"Markdown Content:\s*\n(.*)", text, re.DOTALL)
    if m:
        out["content"] = _clean_jina_content(m.group(1))

    return out


_DETAIL_DATE_PATTERNS = [
    r'<meta[^>]+name=["\']firstpublishedtime["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+name=["\']createDate["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+name=["\']PublishDate["\'][^>]+content=["\']([^"\']+)',
    r'<span[^>]+class=["\']pages-date["\'][^>]*>([^<]+)',
    r'<span[^>]+class=["\']date["\'][^>]*>([^<]+)',
    r'<span[^>]+class=["\']hui12["\'][^>]*>([^<]+)',
    r'<p[^>]+class=["\']fl["\'][^>]*>日期：\s*([^<]+)',
]

_CONTENT_SELECTORS = [
    # gov.cn detail
    "div.pages_content",
    "div#UCAP-CONTENT",
    "div.b12c",
    # mofcom detail
    "div.art-con",
    "div.wms-con",
    # pbc detail
    "div#zoom",
    "div.article-content",
    "div.TRS_Editor",
    # csrc detail
    "div.detail-content",
    "div.main-content",
    # generic
    "div.content",
    "td.content",
    "div.article",
    "section.content",
    "div.detail",
    "div.main",
]


def _extract_article_html(session, url: str, logger) -> dict[str, Any]:
    """Fallback direct HTML extraction using BeautifulSoup."""
    html = _fetch_html(session, url, logger)
    if not html:
        return {}

    out: dict[str, Any] = {}

    # Date
    for pat in _DETAIL_DATE_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            out["published_at"] = m.group(1).strip()
            break

    # Content
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for sel in _CONTENT_SELECTORS:
            el = soup.select_one(sel)
            if el:
                # Drop nested script/style nodes
                for bad in el.find_all(["script", "style", "noscript"]):
                    bad.decompose()
                text = el.get_text("\n", strip=True)
                if len(text) > 100:
                    out["content"] = text
                    break
    except Exception as exc:
        logger.debug("BS4 detail extraction failed for %s: %s", url, exc)

    return out


def _extract_article(session, url: str, logger) -> dict[str, Any]:
    """Try jina.ai first, then direct HTML fallback for missing date/content."""
    detail = _extract_article_jina(session, url, logger)
    if not detail.get("published_at") or not detail.get("content"):
        html_detail = _extract_article_html(session, url, logger)
        if html_detail.get("published_at") and not detail.get("published_at"):
            detail["published_at"] = html_detail["published_at"]
        if html_detail.get("content") and not detail.get("content"):
            detail["content"] = html_detail["content"]
    # De-duplicate repeated article bodies (gov.cn jina sometimes renders twice).
    if detail.get("content"):
        detail["content"] = _dedupe_body(detail["content"])
    return detail


# ---------------------------------------------------------------------------
# LLM noise classification
# ---------------------------------------------------------------------------

LLM_API_URL = "https://api.deepseek.com/chat/completions"
LLM_MODEL = "deepseek-chat"


def _llm_classify(title: str, url: str, content: str, api_key: str, logger) -> bool:
    """Return True if the item is a real policy/news/announcement."""
    prompt = (
        "判断以下中国政府网站条目是否属于「真实政策/新闻/公告」资讯，而不是导航入口、"
        "板块索引、服务入口或功能页面。只回答 yes 或 no，不要解释。\n\n"
        f"标题：{title}\n"
        f"URL：{url}\n"
        f"正文：{content[:600]}\n\n"
        "是否真实资讯？"
    )
    try:
        import requests

        resp = requests.post(
            LLM_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("LLM classify failed for %s: %s", title, resp.status_code)
            return True  # fail open
        data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip().lower()
        return "yes" in answer or "是" in answer
    except Exception as exc:
        logger.warning("LLM classify exception for %s: %s", title, exc)
        return True  # fail open


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def fetch_one(session, key: str, cfg: dict[str, Any], logger, llm_key: str | None) -> list[dict]:
    items = _try_feedparser(session, cfg.get("rss_candidates", []), logger)
    if not items:
        items = _scrape_homepage(session, cfg, logger)
    if not items and cfg.get("homepage_fallback"):
        fallback_cfg = {**cfg, "homepage": cfg["homepage_fallback"]}
        items = _scrape_homepage(session, fallback_cfg, logger)

    out: list[dict] = []
    for it in items:
        it["agency"] = key
        it["agency_name"] = cfg["name"]
        it["source"] = "gov_china"

        # Hard noise filters
        title = it.get("title", "")
        url = it.get("url", "")
        if _is_noise_title(title) or _is_noise_url(url):
            logger.debug("hard-filtered noise: %s", title)
            continue

        # Fetch detail content and confirm date
        detail = _extract_article(session, url, logger)

        # Content
        content = (detail.get("content") or "").strip()
        if not content:
            logger.debug("dropped empty-content item: %s", title)
            continue
        it["content"] = content
        # Build a cleaner summary: first non-trivial paragraph (skip nav header).
        first_para = _extract_clean_paragraph(content, min_len=60)
        if first_para:
            it["summary"] = first_para[:400] if len(first_para) <= 400 else first_para[:400] + "..."
        else:
            it["summary"] = content[:400] if len(content) <= 400 else content[:400] + "..."

        # Date: prefer detail page, then list page, then URL inference
        list_dt = _parse_date(it.get("published_at"))
        detail_dt = _parse_date(detail.get("published_at"))
        dt = detail_dt or list_dt or _parse_date_from_url(url)
        it["published_at"] = _format_iso(dt)

        # LLM review for short/suspicious items
        if len(content) < 50 or _title_looks_nav(title):
            if llm_key:
                if not _llm_classify(title, url, content, llm_key, logger):
                    logger.debug("llm-filtered noise: %s", title)
                    continue
            else:
                # No LLM available: drop definitely-short items, keep others
                if len(content) < 50:
                    logger.debug("dropped short-content item without LLM: %s", title)
                    continue

        out.append(it)

    return out


def filter_by_hours(items: list[dict], hours: int) -> list[dict]:
    if hours <= 0:
        return items
    out = []
    for it in items:
        dt = parse_dt(it.get("published_at"))
        if within_hours(dt, hours):
            out.append(it)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("China official policy news worker (gov / PBOC / CSRC / MOFCOM)")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(SOURCES.keys()),
        help=f"Comma-separated agency keys. Available: {','.join(SOURCES.keys())}",
    )
    args = parser.parse_args(argv)

    logger = setup_logger(SOURCE, level="DEBUG" if args.verbose else "INFO")
    session = make_session()
    selected = [s.strip() for s in args.sources.split(",") if s.strip() in SOURCES]
    llm_key = _load_deepseek_key(logger)
    if llm_key:
        logger.info("DeepSeek API key loaded; LLM noise filter enabled")
    else:
        logger.warning("DeepSeek API key not found; LLM noise filter disabled")

    all_items: list[dict] = []
    for key in selected:
        cfg = SOURCES[key]
        try:
            items = fetch_one(session, key, cfg, logger, llm_key)
        except Exception as exc:
            logger.warning("source %s raised: %s", key, exc)
            continue
        all_items.extend(items)

    all_items = filter_by_hours(all_items, args.hours)
    if args.limit > 0:
        all_items = all_items[: args.limit]

    if not all_items:
        all_items = [
            {
                "type": "empty",
                "reason": "no real policy/news items returned after filtering",
                "sources_attempted": selected,
            }
        ]

    write_json(
        all_items,
        source=SOURCE,
        out_path=args.output,
        data_root=args.data_root,
        limit=args.limit,
        logger=logger,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
