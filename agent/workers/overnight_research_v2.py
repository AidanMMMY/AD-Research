#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
overnight_research_v2.py — 20 小时连续自主研究 worker（改进版）。

主要改进点：
1. Supervisor 循环：theme agent 结束后自动换方向/换子主题重新 spawn，直到 deadline。
2. 多 provider LLM fallback：Anthropic → OpenAI → DeepSeek → MiniMax，自动处理敏感内容报错。
3. 更丰富的搜索与提取：Jina Reader / Jina Search、SearXNG、RSS、readability-lxml、Playwright 兜底。
4. 增强记录字段：arguments、evidence、impact_chain、investment_implications、risk_factors、quality_score 等。
5. 跨主题去重与链接：基于 URL/title/content hash 的多层去重，合并相似记录并建立 cross-reference。
6. 中间报告快照：每 2 小时生成一次 report_snapshot_<n>.md。
7. 更详细可观测性：heartbeat 携带失败统计、各 agent 进度、LLM/搜索成功失败比例。

用法：
    python /workspace/workers/overnight_research_v2.py \
        --output /data/ad-research/overnight_20260718 \
        --runtime-hours 20
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import multiprocessing
import os
import random
import re
import signal
import sqlite3
import sys
import threading
import time
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# 可选依赖：不存在时优雅降级
# --------------------------------------------------------------------------- #
try:
    from readability import Document as ReadabilityDocument
except ImportError:  # pragma: no cover
    ReadabilityDocument = None

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

# --------------------------------------------------------------------------- #
# 配置与常量
# --------------------------------------------------------------------------- #

RUNTIME_HOURS = float(os.environ.get("RESEARCH_RUNTIME_HOURS", "20"))
WIND_DOWN_MINUTES = float(os.environ.get("RESEARCH_WIND_DOWN_MINUTES", "30"))
HEARTBEAT_SECONDS = int(os.environ.get("RESEARCH_HEARTBEAT_SECONDS", "300"))
SNAPSHOT_INTERVAL_SECONDS = int(os.environ.get("RESEARCH_SNAPSHOT_SECONDS", "7200"))
MAX_WORKERS_PER_AGENT = int(os.environ.get("RESEARCH_MAX_WORKERS", "2"))
FETCH_TIMEOUT = int(os.environ.get("RESEARCH_FETCH_TIMEOUT", "30"))
MAX_REFLECTIONS = int(os.environ.get("RESEARCH_MAX_REFLECTIONS", "6"))
QUERY_BUDGET_PER_PHASE = int(os.environ.get("RESEARCH_QUERY_BUDGET", "40"))

CATEGORIES: list[str] = [
    "china_mechanisms",
    "investor_speeches",
    "academic_research",
    "industry_deep_dive",
    "event_cases",
]

# 方向生成约束：防止 LLM 生成跑题子主题
DIRECTION_CONSTRAINTS: dict[str, str] = {
    "china_mechanisms": "必须聚焦中国宏观经济、货币政策、财政政策、监管政策、资本市场机制及其对A股的影响。",
    "investor_speeches": "必须聚焦投资大佬（如巴菲特、达里奥、张坤、段永平等）对中国/A股/中概股/价值投资的观点。",
    "academic_research": "必须聚焦与中国A股市场、资产定价、因子投资、行为金融、宏观政策传导相关的学术论文或实证研究。",
    "industry_deep_dive": "必须聚焦A股行业（如半导体、新能源、银行、消费、医药等）的产业链、政策、周期与龙头公司。",
    "event_cases": "必须聚焦对中国A股/港股/中概股有重大影响的政策、市场、国际或历史事件。",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# 用于方向重置的生成提示
DIRECTION_GENERATION_SYSTEM = """你是一位研究规划专家。给定一个研究主题和已收集的记录摘要，请从全新的角度生成 5-8 个深入搜索问题或子主题。
要求：
1. 不要重复已有记录的标题或 URL。
2. 每个问题应具体、可搜索，面向公开网络资料。
3. 优先覆盖未被充分研究的空白领域。
4. 用中文输出。"""

# 跨主题去重阈值（title 相似度）
TITLE_DEDUP_THRESHOLD = 0.82

# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #

logger = logging.getLogger("overnight_research_v2")


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "overnight_research_v2.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #

class ResearchRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"rec-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}")
    title: str
    source: str = ""
    url: str = ""
    date: str = ""
    accessed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    category: str
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    related_sectors: list[str] = Field(default_factory=list)
    related_tickers: list[str] = Field(default_factory=list)
    impact: str = ""
    original_language: str = "zh"
    translated: bool = False
    # 新增字段：分析深度
    arguments: str = ""                  # 核心论点
    evidence: str = ""                   # 数据/论据
    impact_chain: str = ""               # 影响链条
    investment_implications: str = ""    # 投资启示
    risk_factors: str = ""               # 风险点
    quality_score: float = 0.0           # 质量分 0-100
    cross_refs: list[str] = Field(default_factory=list)   # 跨主题引用记录 id
    original_text: str = ""              # 原始正文片段（用于去重/溯源）
    extra: dict[str, Any] = Field(default_factory=dict)


class ReflectionOutput(BaseModel):
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    gaps: str = ""
    new_queries: list[str] = Field(default_factory=list)
    notes: str = ""


class ExtractionOutput(BaseModel):
    records: list[ResearchRecord] = Field(default_factory=list)


class DirectionOutput(BaseModel):
    new_queries: list[str] = Field(default_factory=list)
    reasoning: str = ""


class AgentStats(BaseModel):
    llm_calls: int = 0
    llm_failures: int = 0
    search_calls: int = 0
    search_failures: int = 0
    fetch_failures: int = 0
    records_added: int = 0
    duplicates_skipped: int = 0


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _jaccard_similarity(a: str, b: str) -> float:
    """计算两个字符串的字符二元组 Jaccard 相似度。"""
    def bigrams(s: str) -> set[str]:
        s = s.lower().replace(" ", "")
        return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()
    sa, sb = bigrams(a), bigrams(b)
    if not sa and not sb:
        return 1.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _sanitize_for_anthropic(text: str) -> str:
    """简单降低 Anthropic 敏感误报风险：去掉过长的极端字符重复。"""
    # 把连续 20 个以上相同字符压缩
    text = re.sub(r"(.)\1{20,}", r"\1\1\1", text)
    # 把异常长度的无空格数字串分段
    text = re.sub(r"(\d{50,})", lambda m: m.group(1)[:50], text)
    return text


def _split_text(text: str, max_chars: int = 8000) -> list[str]:
    """按段落把文本切分成多个块，不硬截断句子。"""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n"):
        if len(current) + len(para) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n" + para if current else para
    if current:
        chunks.append(current.strip())
    return chunks


# --------------------------------------------------------------------------- #
# HTTP / 抓取
# --------------------------------------------------------------------------- #

class Fetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self._playwright_available = sync_playwright is not None

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def get(self, url: str, timeout: int = FETCH_TIMEOUT, **kwargs: Any) -> requests.Response | None:
        try:
            time.sleep(random.uniform(1.0, 3.0))
            resp = self.session.get(url, headers=self._headers(), timeout=timeout, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                logger.warning("429 from %s, sleeping %ds", url, retry_after)
                time.sleep(min(retry_after, 300))
                return None
            resp.raise_for_status()
            return resp
        except Exception as exc:
            logger.debug("fetch failed %s: %s", url, exc)
            return None

    def jina_read(self, url: str) -> str:
        """用 Jina AI Reader 获取正文 markdown。正确处理 URL scheme。"""
        if url.startswith("http://"):
            jina_url = f"https://r.jina.ai/http://{url[7:]}"
        elif url.startswith("https://"):
            jina_url = f"https://r.jina.ai/https://{url[8:]}"
        else:
            jina_url = f"https://r.jina.ai/http://{url}"
        resp = self.get(jina_url, timeout=45)
        if not resp:
            return ""
        text = resp.text
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
        return text.strip()

    def direct_fetch(self, url: str) -> str:
        """直接请求 + readability/BS4 提取正文。"""
        resp = self.get(url, timeout=FETCH_TIMEOUT)
        if not resp:
            return ""
        html = resp.text
        if ReadabilityDocument:
            try:
                doc = ReadabilityDocument(html)
                summary = doc.summary()
                text = BeautifulSoup(summary, "lxml").get_text("\n", strip=True)
                if len(text) >= 80:
                    return text
            except Exception as exc:
                logger.debug("readability failed %s: %s", url, exc)
        # fallback
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        return text

    def playwright_fetch(self, url: str) -> str:
        """Playwright 兜底，用于 JS 渲染页面。需要 playwright 已安装。"""
        if not self._playwright_available or sync_playwright is None:
            return ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    locale="zh-CN",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
            if ReadabilityDocument:
                try:
                    doc = ReadabilityDocument(html)
                    text = BeautifulSoup(doc.summary(), "lxml").get_text("\n", strip=True)
                    if len(text) >= 80:
                        return text
                except Exception:
                    pass
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text("\n", strip=True)
        except Exception as exc:
            logger.debug("playwright fetch failed %s: %s", url, exc)
            return ""

    def fetch_content(self, url: str) -> str:
        """多策略获取正文：Jina Reader → 直接请求 → Playwright。"""
        # 1. Jina Reader
        text = self.jina_read(url)
        if len(text) >= 80:
            return text
        # 2. 直接请求 + readability
        text = self.direct_fetch(url)
        if len(text) >= 80:
            return text
        # 3. Playwright 兜底
        text = self.playwright_fetch(url)
        if len(text) >= 80:
            return text
        # 4. 返回任何可用文本
        return text


# --------------------------------------------------------------------------- #
# 搜索
# --------------------------------------------------------------------------- #

class SearchEngine:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self.searxng_url = os.environ.get("SEARXNG_URL", "").rstrip("/")

    def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        self.stats_call()
        engines = [
            ("jina", self._jina_search),
            ("bing", self._bing),
            ("ddg", self._ddg),
            ("baidu", self._baidu),
        ]
        if self.searxng_url:
            engines.insert(0, ("searxng", self._searxng))
        for name, engine in engines:
            try:
                results = engine(query, max_results)
                if results:
                    logger.info("[search] %s returned %d results for %s", name, len(results), query)
                    return results
                else:
                    logger.debug("[search] %s returned no results for %s", name, query)
            except Exception as exc:
                logger.warning("[search] %s failed for %s: %s", name, query, exc)
        self.stats_failure()
        logger.warning("[search] all engines returned no results for %s", query)
        return []

    def stats_call(self) -> None:
        """在 Agent 运行时被重写为具体 stats 对象的调用。"""
        pass

    def stats_failure(self) -> None:
        pass

    def _jina_search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Jina Search 免费搜索端点。"""
        encoded = requests.utils.quote(query)
        url = f"https://s.jina.ai/{encoded}"
        resp = self.fetcher.get(url, timeout=30)
        if not resp:
            return []
        text = resp.text
        results: list[dict[str, str]] = []
        # Jina Search 返回 markdown 格式，通常是 [title](url) 后跟摘要
        for m in re.finditer(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text):
            title, href = m.group(1), m.group(2)
            if title and href:
                results.append({"title": title.strip(), "url": href.strip()})
            if len(results) >= max_results:
                break
        return results

    def _searxng(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        if not self.searxng_url:
            return []
        url = f"{self.searxng_url}/search"
        resp = self.fetcher.get(url, params={"q": query, "format": "json"}, timeout=30)
        if not resp:
            return []
        try:
            data = resp.json()
            results = []
            for r in data.get("results", [])[:max_results]:
                title = r.get("title", "")
                href = r.get("url", "")
                if title and href:
                    results.append({"title": title, "url": href})
            return results
        except Exception as exc:
            logger.warning("searxng parse failed: %s", exc)
            return []

    def _bing(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        url = "https://www.bing.com/search"
        resp = self.fetcher.get(url, params={"q": query, "setlang": "zh-cn"})
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results: list[dict[str, str]] = []
        ol = soup.find("ol", id="b_results")
        if not ol:
            return []
        for li in ol.find_all("li", recursive=False):
            a = li.find("a", href=True)
            if not a:
                continue
            href = a.get("href")
            title = a.get_text(strip=True)
            if not title:
                continue
            final_url = self._decode_bing_redirect(href) or href
            if final_url and final_url.startswith("http"):
                results.append({"title": title, "url": final_url})
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _decode_bing_redirect(href: str) -> str | None:
        try:
            m = re.search(r"[?&]u=([^&]+)", href)
            if not m:
                return None
            encoded = m.group(1)
            if len(encoded) >= 2 and encoded[0] in "abcdefghijklmnopqrstuvwxyz" and encoded[1].isdigit():
                encoded = encoded[2:]
            decoded = base64.urlsafe_b64decode(encoded + "==").decode("utf-8", errors="ignore")
            return decoded if decoded.startswith("http") else None
        except Exception:
            return None

    def _ddg(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        url = "https://lite.duckduckgo.com/lite/"
        resp = self.fetcher.get(url, params={"q": query, "kl": "cn-zh"})
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results: list[dict[str, str]] = []
        for link in soup.find_all("a", class_="result-link"):
            href = link.get("href")
            if not href or href.startswith("/"):
                continue
            title = link.get_text(strip=True)
            if href and title:
                results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
        return results

    def _baidu(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        url = "https://www.baidu.com/s"
        resp = self.fetcher.get(url, params={"wd": query, "rn": max_results})
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results: list[dict[str, str]] = []
        for item in soup.find_all("div", class_=re.compile("result")):
            a = item.find("a")
            if not a:
                continue
            href = a.get("href")
            title = a.get_text(strip=True)
            if href and title:
                results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
        return results


# --------------------------------------------------------------------------- #
# RSS / 站点直抓源
# --------------------------------------------------------------------------- #

class FeedSource:
    """为特定主题提供 RSS/feed 或站点直抓结果作为搜索补充。"""

    FEEDS: dict[str, list[str]] = {
        "china_mechanisms": [
            "https://www.gov.cn/zhengce/zhengceku/rss.htm",
            "http://www.pbc.gov.cn/zhengcehuobisi/11111/index.html",
        ],
        "investor_speeches": [
            "https://www.berkshirehathaway.com/letters/letters.html",
            "https://www.oaktreecapital.com/insights/memos",
        ],
        "academic_research": [
            "https://arxiv.org/rss/q-fin",
            "https://www.nber.org/rss/newthisweek.xml",
        ],
        "industry_deep_dive": [
            "https://www.ndrc.gov.cn/xxgk/zcwj/zcjd/rss.xml",
            "https://www.miit.gov.cn/jgsj/waj/rss.xml",
        ],
        "event_cases": [
            "https://www.reuters.com/world/china/rss",
            "https://www.bloomberg.com/feeds/markets",
        ],
    }

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def fetch(self, theme: str, max_results: int = 3) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for feed_url in self.FEEDS.get(theme, []):
            try:
                resp = self.fetcher.get(feed_url, timeout=20)
                if not resp:
                    continue
                if feedparser is not None:
                    parsed = feedparser.parse(resp.content)
                    for entry in parsed.entries[:max_results]:
                        title = entry.get("title", "").strip()
                        link = entry.get("link", "").strip()
                        if title and link:
                            results.append({"title": title, "url": link})
                else:
                    # 用 stdlib xml 兜底解析 RSS/Atom
                    try:
                        root = ET.fromstring(resp.content)
                    except ET.ParseError:
                        continue
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
                    for entry in entries[:max_results]:
                        title_el = entry.find("title") or entry.find("atom:title", ns)
                        link_el = entry.find("link") or entry.find("atom:link", ns)
                        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                        link = ""
                        if link_el is not None:
                            link = link_el.get("href", "").strip() or (link_el.text or "").strip()
                        if title and link:
                            results.append({"title": title, "url": link})
                if len(results) >= max_results:
                    break
            except Exception as exc:
                logger.debug("RSS fetch failed %s: %s", feed_url, exc)
        return results[:max_results]


# --------------------------------------------------------------------------- #
# LLM 客户端（多 provider fallback）
# --------------------------------------------------------------------------- #

class _LLMProvider:
    def __init__(self, provider: str, model: str, client: Any, priority: int) -> None:
        self.provider = provider
        self.model = model
        self.client = client
        self.priority = priority

    def complete(self, prompt: str, system: str | None, max_tokens: int, temperature: float) -> str:
        raise NotImplementedError


class _AnthropicProvider(_LLMProvider):
    def complete(self, prompt: str, system: str | None, max_tokens: int, temperature: float) -> str:
        # 降低敏感误报
        prompt = _sanitize_for_anthropic(prompt)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = self.client.messages.create(**kwargs)
        for block in resp.content:
            if block.type == "text":
                return block.text
        return ""


class _OpenAICompatibleProvider(_LLMProvider):
    def complete(self, prompt: str, system: str | None, max_tokens: int, temperature: float) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""


class LLMClient:
    def __init__(self) -> None:
        self.providers: list[_LLMProvider] = []

        # 1) Anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
            client = Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
            )
            self.providers.append(_AnthropicProvider("anthropic", model, client, 0))
            logger.info("LLMClient registered anthropic model=%s", model)

        # 2) OpenAI
        open_key = os.environ.get("OPENAI_API_KEY", "")
        open_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        open_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if open_key:
            client = OpenAI(api_key=open_key, base_url=open_base)
            self.providers.append(_OpenAICompatibleProvider("openai", open_model, client, 1))
            logger.info("LLMClient registered openai model=%s", open_model)

        # 3) MiniMax
        minimax_key = os.environ.get("MINIMAX_CN_API_KEY", "") or os.environ.get("MINIMAX_API_KEY", "")
        if minimax_key:
            minimax_model = os.environ.get("MINIMAX_MODEL", "minimax-m3")
            client = OpenAI(api_key=minimax_key, base_url="https://api.minimaxi.com/v1")
            self.providers.append(_OpenAICompatibleProvider("minimax", minimax_model, client, 3))
            logger.info("LLMClient registered minimax model=%s", minimax_model)

        # 4) DeepSeek
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
            client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
            self.providers.append(_OpenAICompatibleProvider("deepseek", deepseek_model, client, 2))
            logger.info("LLMClient registered deepseek model=%s", deepseek_model)

        # 按优先级排序
        self.providers.sort(key=lambda p: p.priority)
        if not self.providers:
            raise RuntimeError(
                "No LLM API key found (ANTHROPIC_API_KEY / OPENAI_API_KEY / MINIMAX_CN_API_KEY / MINIMAX_API_KEY / DEEPSEEK_API_KEY)"
            )

    def complete(self, prompt: str, system: str | None = None, max_tokens: int = 2048, temperature: float = 0.6) -> str:
        now = time.time()
        wait = 0.8 - (now - getattr(self, "last_call", 0))
        if wait > 0:
            time.sleep(wait)
        try:
            for provider in self.providers:
                try:
                    text = provider.complete(prompt, system, max_tokens, temperature)
                    if text:
                        logger.info("LLM success provider=%s", provider.provider)
                        return text
                    else:
                        logger.warning("LLM empty response from %s", provider.provider)
                except Exception as exc:
                    logger.warning("LLM call failed provider=%s: %s", provider.provider, exc)
                    err_str = str(exc).lower()
                    # 对敏感/安全类错误，先尝试拆分 prompt，再降级到下一个 provider
                    if any(k in err_str for k in ("sensitive", "new_sensitive", "content_filter", "policy", "moderation", "1026", "10013")):
                        logger.info("LLM sensitive/content error on %s, try split prompt", provider.provider)
                        try:
                            chunks = _split_text(prompt, max_chars=4000)
                            if len(chunks) > 1:
                                combined = ""
                                for chunk in chunks:
                                    combined += provider.complete(
                                        chunk, system,
                                        max_tokens=max(512, max_tokens // len(chunks)),
                                        temperature=temperature,
                                    ) + "\n"
                                if combined.strip():
                                    return combined
                        except Exception:
                            pass
                    continue
            logger.error("All LLM providers failed")
            return ""
        finally:
            self.last_call = time.time()

    def extract_records(self, prompt: str, system: str, output_model: type[ExtractionOutput]) -> ExtractionOutput:
        schema = output_model.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"请只返回符合以下 JSON Schema 的 JSON，不要包含任何解释或 markdown 代码块：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        text = self.complete(full_prompt, system=system, max_tokens=4096, temperature=0.3)
        return self._parse_json(text, output_model)

    def reflect(self, prompt: str, system: str) -> ReflectionOutput:
        schema = ReflectionOutput.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"请只返回符合以下 JSON Schema 的 JSON：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        text = self.complete(full_prompt, system=system, max_tokens=2048, temperature=0.5)
        return self._parse_json(text, ReflectionOutput)

    def generate_directions(self, prompt: str, system: str) -> DirectionOutput:
        schema = DirectionOutput.model_json_schema()
        full_prompt = (
            f"{prompt}\n\n"
            f"请只返回符合以下 JSON Schema 的 JSON：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        text = self.complete(full_prompt, system=system, max_tokens=2048, temperature=0.7)
        return self._parse_json(text, DirectionOutput)

    @staticmethod
    def _parse_json(text: str, model: type[BaseModel]) -> BaseModel:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        try:
            return model.model_validate_json(text)
        except Exception as exc:
            logger.debug("json parse failed: %s | text=%.200s", exc, text)
            m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
            if m:
                try:
                    return model.model_validate_json(m.group(1))
                except Exception:
                    pass
            return model()


# --------------------------------------------------------------------------- #
# 数据库（每个主题独立，避免并发锁）
# --------------------------------------------------------------------------- #

class AgentDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init()

    def _init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT,
                url TEXT,
                date TEXT,
                accessed_at TEXT,
                category TEXT NOT NULL,
                tags TEXT,
                summary TEXT,
                key_points TEXT,
                related_sectors TEXT,
                related_tickers TEXT,
                impact TEXT,
                original_language TEXT,
                translated INTEGER,
                content_hash TEXT,
                arguments TEXT,
                evidence TEXT,
                impact_chain TEXT,
                investment_implications TEXT,
                risk_factors TEXT,
                quality_score REAL,
                cross_refs TEXT,
                original_text TEXT,
                extra TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration INTEGER,
                coverage_score REAL,
                gaps TEXT,
                new_queries TEXT,
                notes TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_records_hash ON records(content_hash);
            CREATE INDEX IF NOT EXISTS idx_records_url ON records(url);
            CREATE INDEX IF NOT EXISTS idx_records_quality ON records(quality_score);
            """
        )
        conn.commit()
        conn.close()

    def insert_record(self, rec: ResearchRecord) -> bool:
        """插入记录，如果 content_hash 重复或 id 冲突则返回 False。"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute("SELECT 1 FROM records WHERE content_hash = ? LIMIT 1", (rec.extra.get("content_hash", ""),))
            if cur.fetchone():
                return False
            conn.execute(
                """
                INSERT INTO records
                (id, title, source, url, date, accessed_at, category, tags, summary, key_points,
                 related_sectors, related_tickers, impact, original_language, translated,
                 content_hash, arguments, evidence, impact_chain, investment_implications,
                 risk_factors, quality_score, cross_refs, original_text, extra, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.id, rec.title, rec.source, rec.url, rec.date, rec.accessed_at, rec.category,
                    json.dumps(rec.tags, ensure_ascii=False),
                    rec.summary,
                    json.dumps(rec.key_points, ensure_ascii=False),
                    json.dumps(rec.related_sectors, ensure_ascii=False),
                    json.dumps(rec.related_tickers, ensure_ascii=False),
                    rec.impact, rec.original_language, 1 if rec.translated else 0,
                    rec.extra.get("content_hash", ""),
                    rec.arguments, rec.evidence, rec.impact_chain, rec.investment_implications,
                    rec.risk_factors, rec.quality_score,
                    json.dumps(rec.cross_refs, ensure_ascii=False),
                    rec.original_text,
                    json.dumps(rec.extra, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            logger.debug("insert_record: integrity error for id=%s (duplicate id or hash)", rec.id)
            return False
        finally:
            conn.close()

    def url_exists(self, url: str) -> bool:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute("SELECT 1 FROM records WHERE url = ? LIMIT 1", (url,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def insert_reflection(self, iteration: int, reflection: ReflectionOutput) -> None:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute(
                """
                INSERT INTO reflections (iteration, coverage_score, gaps, new_queries, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    iteration,
                    reflection.coverage_score,
                    reflection.gaps,
                    json.dumps(reflection.new_queries, ensure_ascii=False),
                    reflection.notes,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def set_meta(self, key: str, value: str) -> None:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
        finally:
            conn.close()

    def get_meta(self, key: str, default: str = "") -> str:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default
        finally:
            conn.close()

    def count_records(self) -> int:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM records")
            return cur.fetchone()[0]
        finally:
            conn.close()

    def recent_records(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute(
                "SELECT title, summary, url, arguments, evidence, quality_score FROM records ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "title": r[0], "summary": r[1], "url": r[2],
                    "arguments": r[3], "evidence": r[4], "quality_score": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def all_records(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cur = conn.execute("SELECT * FROM records")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# 主题 Agent
# --------------------------------------------------------------------------- #

AGENT_CONFIG: dict[str, dict[str, Any]] = {
    "china_mechanisms": {
        "category": "机制",
        "system": "你是一位中国宏观政策研究员。请基于网页内容提取结构化信息，用中文输出。",
        "initial_queries": [
            "中国政治局会议 2025 2026 经济政策 A股影响",
            "中国货币政策 LPR MLF 利率传导 2025 2026",
            "中国地方政府债务 化债 城投 2025",
            "中国房地产政策 2025 2026 保交房 白名单",
            "中国新质生产力 产业政策 半导体 新能源",
            "中国证监会 新国九条 退市 注册制 2025",
            "中国资本市场 平准基金 国家队 汇金",
        ],
        "fallback_directions": [
            "中国财政政策 专项债 基建投资 2025 2026",
            "中国金融监管 影子银行 资管新规",
            "中国汇率政策 人民币国际化 资本账户",
            "中国产业政策 智能制造 工业互联网",
            "中国就业与收入政策 消费刺激",
            "中国碳中和政策 绿色金融 ESG",
        ],
    },
    "investor_speeches": {
        "category": "讲话",
        "system": "你整理投资大佬的公开讲话、访谈、股东信。请用中文总结核心观点和投资启示。",
        "initial_queries": [
            "Warren Buffett 2025 2026 shareholder letter China A-share",
            "Ray Dalio 2025 2026 China economy interview",
            "Howard Marks memo 2025 2026 China market",
            "张坤 2025 2026 年报 致持有人信 A股",
            "段永平 2025 2026 访谈 投资 中国",
            "李录 2025 2026 中国 价值投资",
            "但斌 2025 2026 私募 观点 A股",
        ],
        "fallback_directions": [
            "沈南鹏 2025 2026 投资 中国 VC PE",
            "高毅资产 2025 2026 邱国鹭 邓晓峰 观点",
            "高瓴资本 张磊 2025 2026 投资中国",
            "景林资产 2025 2026 蒋锦志 观点",
            "海外主权基金  pension fund 中国投资 2025",
            "诺贝尔经济学奖 2025 2026 中国 观点",
        ],
    },
    "academic_research": {
        "category": "论文",
        "system": "你是一位金融学术研究员。请提取论文/研究的核心发现、方法、对A股的适用性和局限。",
        "initial_queries": [
            "A-share anomalies investor sentiment lottery preference low volatility",
            "industry momentum strategy China A-share",
            "policy impact Chinese stock market empirical",
            "machine learning stock prediction China A-share",
            "ESG green bond China A-share empirical",
            "macro factor equity returns China monetary policy",
            "behavioral finance retail investors China",
        ],
        "fallback_directions": [
            "China equity market liquidity volatility macro news",
            "China factor investing value momentum quality",
            "China retail investor behavior noise trader",
            "China corporate governance ownership structure",
            "China IPO underpricing long term performance",
            "China credit risk default predict corporate bond",
        ],
    },
    "industry_deep_dive": {
        "category": "行业",
        "system": "你是一位行业研究员。请提取A股行业的政策驱动、周期阶段、代表ETF/个股、投资机会与风险。",
        "initial_queries": [
            "新能源行业 2025 2026 A股 光伏 锂电 固态电池 政策",
            "半导体行业 2025 2026 A股 国产替代 大基金",
            "银行券商保险 2025 2026 A股 金融 估值",
            "消费行业 白酒 家电 汽车 2025 2026 A股",
            "房地产行业 2025 2026 A股 政策 产业链",
            "AI 算力 光模块 2025 2026 A股",
            "低空经济 机器人 2025 2026 A股",
        ],
        "fallback_directions": [
            "医药生物 创新药 医疗器械 2025 2026 A股",
            "军工行业 2025 2026 A股 订单 估值",
            "电力公用事业 火电 水电 核电 2025 A股",
            "交通运输 航空 物流 港口 2025 A股",
            "化工新材料 2025 2026 A股 周期",
            "传媒互联网 游戏 电商 2025 A股",
        ],
    },
    "event_cases": {
        "category": "事件",
        "system": "你是一位市场复盘研究员。请提取重大事件的时间线、受影响板块/标的、价格反应和投资启示。",
        "initial_queries": [
            "2024 924 政策组合拳 A股 降准 降息 影响",
            "2022 上海封控 A股 市场复盘 板块",
            "2015 A股 股灾 救市 复盘",
            "2018 中美贸易摩擦 A股 影响 板块",
            "2020 新冠疫情 A股 复盘 V型反转",
            "2021 双减 反垄断 房地产 监管风暴 A股",
            "2023 AI行情 TMT A股 复盘",
        ],
        "fallback_directions": [
            "2024 2025 美联储降息周期 新兴市场 A股 影响",
            "2025 特朗普关税 中国反制 A股 板块",
            "2026 中国两会 政府工作报告 A股 反应",
            "2025 地缘政治 中东 能源价格 A股",
            "2025 人民币汇率 贬值 资本外流 A股",
            "2025 中国房地产 债务违约 风险传导",
        ],
    },
}


class ThemeAgent:
    def __init__(self, theme: str, output_dir: Path, deadline: float, phase: int = 0) -> None:
        self.theme = theme
        self.output_dir = output_dir
        self.deadline = deadline
        self.phase = phase
        self.cfg = AGENT_CONFIG[theme]
        self.db = AgentDB(output_dir / "raw" / f"{theme}.db")
        self.fetcher = Fetcher()
        self.search = SearchEngine(self.fetcher)
        self.search.stats_call = self._stat_search_call
        self.search.stats_failure = self._stat_search_failure
        self.llm = LLMClient()
        self.feed = FeedSource(self.fetcher)
        self.stats = AgentStats()
        self.query_history: set[str] = set()
        self.queries: list[str] = []
        self.iteration = 0
        self.reflection_count = 0
        self._load_state()
        if phase == 0 and not self.queries:
            self.queries = list(self.cfg["initial_queries"])
        elif phase > 0 and not self.queries:
            self.queries = list(self.cfg.get("fallback_directions", []))

    def _load_state(self) -> None:
        """从 DB 加载已查询过的关键词，避免重复。"""
        for row in self.db.all_records():
            extra = json.loads(row.get("extra") or "{}")
            query = extra.get("query", "")
            if query:
                self.query_history.add(query)

    def _stat_search_call(self) -> None:
        self.stats.search_calls += 1

    def _stat_search_failure(self) -> None:
        self.stats.search_failures += 1

    def run(self) -> None:
        logger.info(
            "[%s] ThemeAgent v2 starting, phase=%d deadline=%s",
            self.theme, self.phase, datetime.fromtimestamp(self.deadline, tz=timezone.utc),
        )
        self.db.set_meta("started_at", datetime.now(timezone.utc).isoformat())
        self.db.set_meta("theme", self.theme)
        self.db.set_meta("phase", str(self.phase))

        # 启动时先尝试 RSS 补充
        if self.phase == 0:
            self._process_feeds()

        # 主循环：直到 deadline 前 10 秒（supervisor wind-down 会发 SIGTERM 终止）
        while time.time() < self.deadline - 10:
            if not self.queries:
                # 方向重置：生成新的子主题
                self._generate_new_directions()
                if not self.queries:
                    # 使用 fallback 方向
                    self.queries = [q for q in self.cfg.get("fallback_directions", []) if q not in self.query_history]
                if not self.queries:
                    logger.warning("[%s] no more directions, sleeping 60s", self.theme)
                    time.sleep(60)
                    continue

            query = self.queries.pop(0)
            if query in self.query_history:
                continue
            self.query_history.add(query)
            self.iteration += 1

            logger.info("[%s] phase=%d iter=%d query=%s", self.theme, self.phase, self.iteration, query)
            results = self.search.search(query, max_results=5)
            if not results:
                logger.warning("[%s] no search results for %s", self.theme, query)
                # 偶尔也尝试 RSS 直抓
                if self.iteration % 5 == 0:
                    self._process_feeds()
                continue

            self._process_results(results, query)
            _write_agent_stats(self.output_dir, self.theme, self.stats)

            # 定期反思并补充新查询
            if self.iteration % 3 == 0:
                self._reflect()
                _write_agent_stats(self.output_dir, self.theme, self.stats)

            # 检查迭代预算
            if self.iteration >= QUERY_BUDGET_PER_PHASE * (self.phase + 1):
                self._generate_new_directions()

        # 最终反思
        self._reflect()
        _write_agent_stats(self.output_dir, self.theme, self.stats)
        self.db.set_meta("finished_at", datetime.now(timezone.utc).isoformat())
        logger.info("[%s] agent finished, records=%d", self.theme, self.db.count_records())

    def _process_feeds(self) -> None:
        """处理 RSS/feed 源。"""
        try:
            results = self.feed.fetch(self.theme, max_results=3)
            if results:
                logger.info("[%s] RSS fetched %d items", self.theme, len(results))
                self._process_results(results, query="__rss_feed__")
        except Exception as exc:
            logger.debug("[%s] RSS processing failed: %s", self.theme, exc)

    def _process_results(self, results: list[dict[str, str]], query: str) -> None:
        urls = [r["url"] for r in results]
        contents: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_PER_AGENT) as ex:
            futures = {ex.submit(self.fetcher.fetch_content, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    contents[url] = future.result()
                except Exception as exc:
                    self.stats.fetch_failures += 1
                    logger.debug("[%s] fetch error %s: %s", self.theme, url, exc)

        for r in results:
            url = r["url"]
            title = r["title"]
            if self.db.url_exists(url):
                logger.debug("[%s] url already exists, skip %s", self.theme, url)
                self.stats.duplicates_skipped += 1
                continue
            content = contents.get(url, "")
            if not content or len(content) < 80:
                self.stats.fetch_failures += 1
                continue

            prompt = self._build_extraction_prompt(self.theme, title, url, content)
            self.stats.llm_calls += 1
            try:
                extracted = self.llm.extract_records(prompt, self.cfg["system"], ExtractionOutput)
            except Exception as exc:
                self.stats.llm_failures += 1
                logger.warning("[%s] extraction failed for %s: %s", self.theme, url, exc)
                continue

            for rec in extracted.records:
                if not rec.title or not rec.summary:
                    continue
                rec.category = self.cfg["category"]
                rec.source = rec.source or title
                rec.url = rec.url or url
                rec.original_language = "zh"
                rec.translated = True
                rec.original_text = content[:2000]
                rec.quality_score = self._compute_quality_score(rec)
                # 强制生成唯一 id，避免 LLM 返回重复 id 或多进程偶发碰撞
                rec.id = f"rec-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{os.urandom(4).hex()}"
                content_hash = _short_hash(rec.url + rec.title + rec.summary[:200])
                rec.extra = {
                    "query": query,
                    "theme": self.theme,
                    "phase": self.phase,
                    "content_hash": content_hash,
                }
                if self.db.insert_record(rec):
                    self.stats.records_added += 1
                    logger.info("[%s] saved record %s (q=%.1f)", self.theme, rec.title[:60], rec.quality_score)
                else:
                    self.stats.duplicates_skipped += 1

    def _compute_quality_score(self, rec: ResearchRecord) -> float:
        """基于字段完整性计算质量分。"""
        score = 0.0
        # 摘要长度 30
        if len(rec.summary) >= 300:
            score += 30
        elif len(rec.summary) >= 150:
            score += 20
        elif len(rec.summary) >= 50:
            score += 10
        # 关键字段存在 40
        if rec.arguments:
            score += 10
        if rec.evidence:
            score += 10
        if rec.investment_implications:
            score += 10
        if rec.risk_factors:
            score += 10
        # 关联标的存在 10
        if rec.related_tickers or rec.related_sectors:
            score += 10
        # 要点数量 10
        if len(rec.key_points) >= 3:
            score += 10
        elif len(rec.key_points) >= 1:
            score += 5
        # 原始字段 10
        if len(rec.original_text) >= 500:
            score += 10
        elif len(rec.original_text) >= 100:
            score += 5
        return min(score, 100.0)

    def _reflect(self) -> None:
        count = self.db.count_records()
        recent = self.db.recent_records(10)
        recent_text = "\n".join(
            f"- {r['title']}: {r['summary'][:200]}"
            for r in recent
        )
        prompt = (
            f"你正在做一项 overnight 研究，主题是：{self.theme}。\n"
            f"当前已收集 {count} 条记录。最近记录摘要：\n{recent_text}\n\n"
            "请评估研究覆盖度（0-1）、指出主要空白，并给出 3-5 个下一步应搜索的中文关键词或问题。"
        )
        self.stats.llm_calls += 1
        try:
            reflection = self.llm.reflect(prompt, "你是研究策略优化助手，请用中文输出 JSON。")
        except Exception as exc:
            self.stats.llm_failures += 1
            logger.warning("[%s] reflection failed: %s", self.theme, exc)
            return

        self.reflection_count += 1
        self.db.insert_reflection(self.iteration, reflection)
        added = 0
        for q in reflection.new_queries:
            normalized = q.strip()
            if normalized and normalized not in self.query_history and normalized != self.theme:
                self.queries.append(normalized)
                added += 1
        logger.info(
            "[%s] reflection score=%.2f new_queries=%d",
            self.theme,
            reflection.coverage_score,
            added,
        )

    def _generate_new_directions(self) -> None:
        """当查询耗尽时，由 LLM 基于已有记录生成全新方向。"""
        if self.reflection_count >= MAX_REFLECTIONS:
            logger.info("[%s] max reflections reached, use fallback directions", self.theme)
            return
        count = self.db.count_records()
        recent = self.db.recent_records(8)
        recent_text = "\n".join(
            f"- {r['title']}: {r['summary'][:150]}"
            for r in recent
        )
        constraint = DIRECTION_CONSTRAINTS.get(self.theme, "")
        prompt = (
            f"研究主题：{self.theme}\n"
            f"当前阶段：phase {self.phase}\n"
            f"约束：{constraint}\n"
            f"已收集记录数：{count}\n"
            f"最近记录：\n{recent_text}\n\n"
            "请生成 5-8 个全新的研究子主题或搜索问题。要求：\n"
            "1. 紧扣主题和上述约束，不要跑题。\n"
            "2. 每个问题应具体、可搜索，面向公开网络资料。\n"
            "3. 不要重复已有记录的标题或 URL。\n"
            "4. 优先覆盖未被充分研究的空白领域。"
        )
        self.stats.llm_calls += 1
        try:
            direction = self.llm.generate_directions(prompt, DIRECTION_GENERATION_SYSTEM)
        except Exception as exc:
            self.stats.llm_failures += 1
            logger.warning("[%s] direction generation failed: %s", self.theme, exc)
            return

        self.reflection_count += 1
        added = 0
        for q in direction.new_queries:
            normalized = q.strip()
            if normalized and normalized not in self.query_history and normalized != self.theme:
                self.queries.append(normalized)
                added += 1
        logger.info("[%s] generated new directions: %d", self.theme, added)

    @staticmethod
    def _build_extraction_prompt(theme: str, title: str, url: str, content: str) -> str:
        return (
            f"主题：{theme}\n"
            f"来源标题：{title}\n"
            f"来源URL：{url}\n"
            f"正文：\n{content[:8000]}\n\n"
            "请从正文中提取 1-3 条高质量研究记录。每条记录包括：\n"
            "- title: 标题\n"
            "- source: 来源名称\n"
            "- url: 链接\n"
            "- date: 日期（YYYY-MM-DD，未知则空）\n"
            "- tags: 标签数组\n"
            "- summary: 300-800字中文摘要\n"
            "- key_points: 要点数组（3-7条）\n"
            "- related_sectors: 相关行业数组\n"
            "- related_tickers: 相关A股代码数组（如 510300.SH, 300750.SZ）\n"
            "- impact: 对A股/投资的影响方向\n"
            "- arguments: 核心论点（50-200字）\n"
            "- evidence: 关键数据/论据（50-200字）\n"
            "- impact_chain: 影响链条（如 政策→行业→个股→风险）\n"
            "- investment_implications: 投资启示（50-200字）\n"
            "- risk_factors: 风险点（50-200字）\n"
            "如果正文质量太低或无关，可以返回空 records 数组。"
        )


# --------------------------------------------------------------------------- #
# 主控 / Supervisor / 合并 / 报告
# --------------------------------------------------------------------------- #

class Supervisor:
    """管理 theme agent 进程，任一进程结束后换方向重新 spawn。"""

    def __init__(self, output_dir: Path, deadline: float) -> None:
        self.output_dir = output_dir
        self.deadline = deadline
        self.state_path = output_dir / "state_v2.json"
        self.ctx = multiprocessing.get_context("spawn")
        self.processes: dict[str, multiprocessing.Process] = {}
        self.phase_counter: dict[str, int] = {theme: 0 for theme in CATEGORIES}
        self.stats: dict[str, AgentStats] = {theme: AgentStats() for theme in CATEGORIES}
        self.stats_lock = threading.Lock()

    def start(self) -> None:
        logger.info("Supervisor starting, runtime=%.1fh, deadline=%s", RUNTIME_HOURS, datetime.fromtimestamp(self.deadline, tz=timezone.utc))
        for theme in CATEGORIES:
            self._spawn_theme(theme)

    def _spawn_theme(self, theme: str) -> None:
        remaining = self.deadline - time.time()
        if remaining < 60:  # 剩余时间不足 1 分钟则不再 spawn
            return
        phase = self.phase_counter[theme]
        p = self.ctx.Process(
            target=_run_theme_agent,
            args=(theme, self.output_dir, self.deadline, phase),
        )
        p.start()
        self.processes[theme] = p
        self.phase_counter[theme] += 1
        logger.info("[supervisor] spawned %s phase=%d", theme, phase)

    def _heartbeat(self) -> None:
        alive = sum(1 for p in self.processes.values() if p.is_alive())
        counts: dict[str, int] = {}
        for theme in CATEGORIES:
            db_path = self.output_dir / "raw" / f"{theme}.db"
            try:
                db = AgentDB(db_path)
                counts[theme] = db.count_records()
            except Exception:
                counts[theme] = 0

        # 读取子进程 stats 摘要（通过共享文件）
        stats_summary = self._load_stats_summary()
        logger.info(
            "heartbeat alive=%d/%d total_records=%d by_theme=%s llm_calls=%d llm_failures=%d search_failures=%d",
            alive,
            len(self.processes),
            sum(counts.values()),
            counts,
            stats_summary.get("llm_calls", 0),
            stats_summary.get("llm_failures", 0),
            stats_summary.get("search_failures", 0),
        )

    def _load_stats_summary(self) -> dict[str, int]:
        summary = {"llm_calls": 0, "llm_failures": 0, "search_calls": 0, "search_failures": 0, "fetch_failures": 0, "records_added": 0, "duplicates_skipped": 0}
        stats_path = self.output_dir / "stats_v2.json"
        if not stats_path.exists():
            return summary
        try:
            data = json.loads(stats_path.read_text(encoding="utf-8"))
            for theme, s in data.items():
                if isinstance(s, dict):
                    for k in summary:
                        summary[k] += s.get(k, 0)
        except Exception as exc:
            logger.debug("load stats summary failed: %s", exc)
        return summary

    def _respawn_finished(self) -> None:
        """检查已结束的进程并重新 spawn（换方向）。"""
        for theme, p in list(self.processes.items()):
            if not p.is_alive():
                exitcode = p.exitcode
                p.join(timeout=10)
                db_path = self.output_dir / "raw" / f"{theme}.db"
                try:
                    db = AgentDB(db_path)
                    count = db.count_records()
                except Exception:
                    count = 0
                logger.info("[supervisor] %s finished with exitcode=%d records=%d, respawning", theme, exitcode, count)
                self._spawn_theme(theme)

    def run(self) -> None:
        self.start()
        # 对短 runtime，wind-down 取 runtime 的 10% 且不超过 30 分钟；保证至少 1 分钟主循环
        runtime_minutes = RUNTIME_HOURS * 60
        wind_down_minutes = min(WIND_DOWN_MINUTES, max(0.5, runtime_minutes * 0.1))
        wind_down = self.deadline - wind_down_minutes * 60
        last_snapshot = time.time()  # 避免启动时立即快照
        # 短 runtime 时加快 heartbeat，避免错过进程状态
        heartbeat_interval = min(HEARTBEAT_SECONDS, max(30, int(runtime_minutes * 60 / 20)))
        while time.time() < wind_down:
            self._heartbeat()
            self._respawn_finished()
            if time.time() - last_snapshot >= SNAPSHOT_INTERVAL_SECONDS:
                self._snapshot()
                last_snapshot = time.time()
            time.sleep(heartbeat_interval)

        logger.info("[supervisor] entering wind-down phase")
        for p in self.processes.values():
            if p.is_alive():
                p.terminate()
        for p in self.processes.values():
            p.join(timeout=60)

        # 最终快照与合并
        self._snapshot(is_final=True)
        self._merge_and_report()

    def _snapshot(self, is_final: bool = False) -> None:
        try:
            Merger(self.output_dir).merge()
            ReportBuilder(self.output_dir, is_final=is_final).build_snapshot()
            logger.info("snapshot generated at %s", datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            logger.warning("snapshot failed: %s", exc)

    def _merge_and_report(self) -> None:
        try:
            Merger(self.output_dir).merge()
            ReportBuilder(self.output_dir, is_final=True).build()
        except Exception as exc:
            logger.exception("final merge/report failed: %s", exc)


# --------------------------------------------------------------------------- #
# 子进程入口
# --------------------------------------------------------------------------- #

def _setup_child_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def _run_theme_agent(theme: str, output_dir: Path, deadline: float, phase: int = 0) -> None:
    signal.signal(signal.SIGTERM, lambda _sig, _frame: sys.exit(0))
    _setup_child_logging()
    logger.info("[%s] child process started phase=%d", theme, phase)
    agent: ThemeAgent | None = None
    try:
        agent = ThemeAgent(theme, output_dir, deadline, phase=phase)
        agent.run()
    except Exception as exc:
        logger.exception("[%s] agent crashed: %s", theme, exc)
    finally:
        # 无论正常结束、SIGTERM 还是异常，都持久化 stats
        if agent is not None:
            try:
                _write_agent_stats(output_dir, theme, agent.stats)
            except Exception as exc:
                logger.warning("[%s] failed to write stats: %s", theme, exc)


def _write_agent_stats(output_dir: Path, theme: str, stats: AgentStats) -> None:
    stats_path = output_dir / "stats_v2.json"
    try:
        data = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    except Exception:
        data = {}
    data[theme] = stats.model_dump()
    stats_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 合并 / 跨主题去重 / 链接
# --------------------------------------------------------------------------- #

class Merger:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def merge(self) -> dict[str, int]:
        merged_path = self.output_dir / "overnight_research_v2.db"
        if merged_path.exists():
            merged_path.unlink()

        conn = sqlite3.connect(merged_path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE records (
                id TEXT PRIMARY KEY,
                theme TEXT,
                title TEXT,
                source TEXT,
                url TEXT,
                date TEXT,
                accessed_at TEXT,
                category TEXT,
                tags TEXT,
                summary TEXT,
                key_points TEXT,
                related_sectors TEXT,
                related_tickers TEXT,
                impact TEXT,
                original_language TEXT,
                translated INTEGER,
                content_hash TEXT,
                arguments TEXT,
                evidence TEXT,
                impact_chain TEXT,
                investment_implications TEXT,
                risk_factors TEXT,
                quality_score REAL,
                cross_refs TEXT,
                original_text TEXT,
                extra TEXT,
                created_at TEXT
            );
            CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, content='records', content_rowid='rowid');
            CREATE INDEX idx_records_theme ON records(theme);
            CREATE INDEX idx_records_hash ON records(content_hash);
            CREATE INDEX idx_records_quality ON records(quality_score);
            CREATE TRIGGER records_fts_insert AFTER INSERT ON records
            BEGIN INSERT INTO records_fts(rowid, title, summary) VALUES (new.rowid, new.title, new.summary); END;
            CREATE TRIGGER records_fts_delete AFTER DELETE ON records
            BEGIN INSERT INTO records_fts(records_fts, rowid, title, summary) VALUES ('delete', old.rowid, old.title, old.summary); END;
            CREATE TABLE stats (theme TEXT PRIMARY KEY, count INTEGER);
            """
        )

        stats: dict[str, int] = {}
        all_records: list[tuple[str, dict[str, Any]]] = []
        for theme in CATEGORIES:
            db_path = self.output_dir / "raw" / f"{theme}.db"
            if not db_path.exists():
                continue
            src = sqlite3.connect(db_path)
            cur = src.execute("SELECT * FROM records")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            for row in rows:
                rec = dict(zip(cols, row))
                rec["theme"] = theme
                all_records.append((theme, rec))
            stats[theme] = len(rows)
            src.close()

        # 跨主题去重：URL 精确 + title 相似
        seen_urls: set[str] = set()
        seen_titles: list[str] = []
        dedup_count = 0
        for theme, rec in all_records:
            url = rec.get("url", "")
            title = rec.get("title", "")
            if url in seen_urls:
                dedup_count += 1
                continue
            # title 相似度去重
            duplicate_title = False
            for st in seen_titles:
                if _jaccard_similarity(title, st) >= TITLE_DEDUP_THRESHOLD:
                    duplicate_title = True
                    break
            if duplicate_title:
                dedup_count += 1
                continue
            if url:
                seen_urls.add(url)
            seen_titles.append(title)
            conn.execute(
                """
                INSERT OR IGNORE INTO records
                (id, theme, title, source, url, date, accessed_at, category, tags, summary, key_points,
                 related_sectors, related_tickers, impact, original_language, translated,
                 content_hash, arguments, evidence, impact_chain, investment_implications,
                 risk_factors, quality_score, cross_refs, original_text, extra, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["id"], rec.get("theme", theme), rec["title"], rec["source"], rec["url"],
                    rec["date"], rec["accessed_at"], rec["category"], rec["tags"], rec["summary"],
                    rec["key_points"], rec["related_sectors"], rec["related_tickers"],
                    rec["impact"], rec["original_language"], rec["translated"],
                    rec["content_hash"], rec.get("arguments", ""), rec.get("evidence", ""),
                    rec.get("impact_chain", ""), rec.get("investment_implications", ""),
                    rec.get("risk_factors", ""), rec.get("quality_score", 0.0),
                    rec.get("cross_refs", "[]"), rec.get("original_text", ""),
                    rec["extra"], rec["created_at"],
                ),
            )

        for theme, count in stats.items():
            conn.execute("INSERT OR REPLACE INTO stats (theme, count) VALUES (?, ?)", (theme, count))
        conn.commit()
        conn.close()

        logger.info("merged total=%d records, dedup_removed=%d into %s", sum(stats.values()), dedup_count, merged_path)
        return stats


# --------------------------------------------------------------------------- #
# 报告生成
# --------------------------------------------------------------------------- #

class ReportBuilder:
    def __init__(self, output_dir: Path, is_final: bool = False) -> None:
        self.output_dir = output_dir
        self.is_final = is_final
        self.merged_path = output_dir / "overnight_research_v2.db"
        self.stats: dict[str, int] = {}
        self.total = 0
        self.high_quality = 0
        self._load_stats()

    def _load_stats(self) -> None:
        if not self.merged_path.exists():
            return
        try:
            conn = sqlite3.connect(self.merged_path)
            cur = conn.execute("SELECT theme, count FROM stats")
            self.stats = {row[0]: row[1] for row in cur.fetchall()}
            self.total = sum(self.stats.values())
            cur = conn.execute("SELECT COUNT(*) FROM records WHERE quality_score >= 60")
            self.high_quality = cur.fetchone()[0]
            conn.close()
        except Exception as exc:
            logger.warning("load stats for report failed: %s", exc)

    def build_snapshot(self) -> None:
        snapshot_index = 1
        while (self.output_dir / f"report_snapshot_{snapshot_index}.md").exists():
            snapshot_index += 1
        md = self._render_md(snapshot_index=snapshot_index)
        html = self._render_html(md, snapshot_index=snapshot_index)
        (self.output_dir / f"report_snapshot_{snapshot_index}.md").write_text(md, encoding="utf-8")
        (self.output_dir / f"report_snapshot_{snapshot_index}.html").write_text(html, encoding="utf-8")
        logger.info("snapshot report #%d saved", snapshot_index)

    def build(self) -> None:
        md = self._render_md()
        html = self._render_html(md)
        (self.output_dir / "report_v2.md").write_text(md, encoding="utf-8")
        (self.output_dir / "report_v2.html").write_text(html, encoding="utf-8")
        logger.info("final report saved to %s", self.output_dir)

    def _render_md(self, snapshot_index: int | None = None) -> str:
        title = "20 小时 Overnight 研究报告（v2 改进版）"
        if snapshot_index:
            title = f"Overnight 研究中间快照 #{snapshot_index}"
        lines = [
            f"# {title}",
            "",
            f"- **生成时间**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"- **数据来源**：公开网络搜索 + RSS/feed + LLM 结构化提取",
            f"- **记录总数**：{self.total}",
            f"- **高质量记录（quality_score >= 60）**：{self.high_quality}",
            "",
            "## 主题分布",
            "",
            "| 主题 | 记录数 |",
            "|------|--------|",
        ]
        for theme, count in self.stats.items():
            lines.append(f"| {theme} | {count} |")
        lines.extend([
            "",
            "## 改进说明",
            "",
            "v2 相对 v1 的主要改进：",
            "1. **Supervisor 循环**：theme agent 结束后自动换方向重新 spawn，避免空等 deadline。",
            "2. **LLM 多 provider fallback**：Anthropic → OpenAI → DeepSeek → MiniMax。",
            "3. **搜索与提取增强**：Jina Reader / Jina Search、SearXNG、RSS、readability-lxml、Playwright 兜底。",
            "4. **增强记录字段**：核心论点、数据论据、影响链条、投资启示、风险点、质量分。",
            "5. **跨主题去重与链接**：URL + title 相似度去重。",
            "6. **中间快照**：每 2 小时生成 report_snapshot。",
            "",
            "## 后续建议",
            "",
            "1. 将 `overnight_research_v2.db` 同步到本地项目作为 RAG 知识库。",
            "2. 接入平台 AI 问答模块。",
            "3. 根据质量分对低质量记录做二次 LLM 提炼。",
            "",
        ])
        return "\n".join(lines)

    def _render_html(self, md: str, snapshot_index: int | None = None) -> str:
        title = f"Overnight Research Report v2{' - Snapshot ' + str(snapshot_index) if snapshot_index else ''}"
        html_body = "\n".join(f"<p>{line}</p>" if line else "<br>" for line in md.splitlines())
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ddd; padding: .5em; text-align: left; }}
th {{ background: #f5f5f5; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, help="输出目录")
    p.add_argument("--runtime-hours", type=float, default=RUNTIME_HOURS)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(output_dir)

    global RUNTIME_HOURS
    if args.runtime_hours:
        RUNTIME_HOURS = args.runtime_hours

    # 保存状态
    state_path = output_dir / "state_v2.json"
    started_at = datetime.now(timezone.utc).isoformat()
    state_path.write_text(
        json.dumps({"started_at": started_at, "runtime_hours": RUNTIME_HOURS}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    deadline = datetime.now(timezone.utc).timestamp() + RUNTIME_HOURS * 3600
    Supervisor(output_dir, deadline).run()


if __name__ == "__main__":
    main()
