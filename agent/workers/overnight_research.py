#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
overnight_research.py — 20 小时连续自主研究 worker。

设计目标：
- 在 ECS agent worker 容器内连续跑约 20 小时。
- 5 个主题子进程并行（宏观/机制、投资大佬讲话、学术研究、行业深度、历史事件）。
- 每个子进程内部循环：搜索 → 抓取 → LLM 结构化 → 反思/调整方向 → 继续搜索。
- 最终合并所有主题数据库，生成中文 report.md + report.html。

用法（由 run_worker.sh 调用）：
    python /workspace/workers/overnight_research.py \
        --output /data/ad-research/overnight_20260718
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
import time
import traceback
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
# 配置与常量
# --------------------------------------------------------------------------- #

RUNTIME_HOURS = float(os.environ.get("RESEARCH_RUNTIME_HOURS", "20"))
WIND_DOWN_MINUTES = float(os.environ.get("RESEARCH_WIND_DOWN_MINUTES", "30"))
HEARTBEAT_SECONDS = int(os.environ.get("RESEARCH_HEARTBEAT_SECONDS", "300"))
MAX_WORKERS_PER_AGENT = int(os.environ.get("RESEARCH_MAX_WORKERS", "2"))
FETCH_TIMEOUT = int(os.environ.get("RESEARCH_FETCH_TIMEOUT", "30"))

CATEGORIES: list[str] = [
    "china_mechanisms",
    "investor_speeches",
    "academic_research",
    "industry_deep_dive",
    "event_cases",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #

logger = logging.getLogger("overnight_research")


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "overnight_research.log"
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
    extra: dict[str, Any] = Field(default_factory=dict)


class ReflectionOutput(BaseModel):
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    gaps: str = ""
    new_queries: list[str] = Field(default_factory=list)
    notes: str = ""


class ExtractionOutput(BaseModel):
    records: list[ResearchRecord] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# HTTP / 搜索 / 抓取
# --------------------------------------------------------------------------- #

class Fetcher:
    def __init__(self) -> None:
        self.session = requests.Session()

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
            time.sleep(random.uniform(1.5, 4.0))
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
        """用 Jina AI reader 获取正文 markdown。"""
        jina_url = f"https://r.jina.ai/http://{url}"
        resp = self.get(jina_url, timeout=45)
        if not resp:
            return ""
        text = resp.text
        # 去掉可能的 think 标签
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
        return text.strip()


class SearchEngine:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        engines = [("bing", self._bing), ("ddg", self._ddg), ("baidu", self._baidu)]
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
        logger.warning("[search] all engines returned no results for %s", query)
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
        # Bing 重定向链接：/ck/a?...&u=a1<base64>
        try:
            m = re.search(r"[?&]u=([^&]+)", href)
            if not m:
                return None
            encoded = m.group(1)
            # 常见前缀 a1 / a2 等，去掉前两个字符
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
# LLM 客户端（优先 Anthropic/OpenAI，兼容 MiniMax/DeepSeek）
# --------------------------------------------------------------------------- #

class LLMClient:
    def __init__(self) -> None:
        self.provider = "minimax"
        self.model = os.environ.get("MINIMAX_MODEL", "minimax-m3")
        self.client: OpenAI | Anthropic | None = None
        ant_len = len(os.environ.get("ANTHROPIC_API_KEY", ""))
        open_len = len(os.environ.get("OPENAI_API_KEY", ""))
        logger.info("LLMClient env check ant=%d open=%d minimax=%d", ant_len, open_len, len(os.environ.get("MINIMAX_CN_API_KEY", "")))

        # 1) Anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.provider = "anthropic"
            self.model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
            self.client = Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
            )
            logger.info("LLMClient using anthropic model=%s", self.model)
            return

        # 2) OpenAI / OpenAI-compatible
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.provider = "openai"

        # 3) MiniMax
        if not api_key:
            api_key = os.environ.get("MINIMAX_CN_API_KEY", "") or os.environ.get("MINIMAX_API_KEY", "")
            base_url = "https://api.minimaxi.com/v1"
            model = os.environ.get("MINIMAX_MODEL", "minimax-m3")
            self.provider = "minimax"

        # 4) DeepSeek
        if not api_key:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = "https://api.deepseek.com"
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
            self.provider = "deepseek"

        if not api_key:
            raise RuntimeError(
                "No LLM API key found (ANTHROPIC_API_KEY / OPENAI_API_KEY / MINIMAX_CN_API_KEY / MINIMAX_API_KEY / DEEPSEEK_API_KEY)"
            )
        self.model = model
        logger.warning("LLMClient provider=%s model=%s", self.provider, self.model)
        if self.provider == "anthropic":
            self.client = Anthropic(api_key=api_key, base_url=base_url or None)
        else:
            self.client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, prompt: str, system: str | None = None, max_tokens: int = 2048, temperature: float = 0.6) -> str:
        # 简单限流
        now = time.time()
        wait = 0.8 - (now - getattr(self, "last_call", 0))
        if wait > 0:
            time.sleep(wait)
        try:
            if self.provider == "anthropic":
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
            else:
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
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
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

    @staticmethod
    def _parse_json(text: str, model: type[BaseModel]) -> BaseModel:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        try:
            return model.model_validate_json(text)
        except Exception as exc:
            logger.debug("json parse failed: %s | text=%.200s", exc, text)
            # 尝试正则提取第一个 {} 或 []
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
            """
        )
        conn.commit()
        conn.close()

    def insert_record(self, rec: ResearchRecord) -> None:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO records
                (id, title, source, url, date, accessed_at, category, tags, summary, key_points,
                 related_sectors, related_tickers, impact, original_language, translated,
                 content_hash, extra, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.id, rec.title, rec.source, rec.url, rec.date, rec.accessed_at, rec.category,
                    json.dumps(rec.tags, ensure_ascii=False),
                    rec.summary,
                    json.dumps(rec.key_points, ensure_ascii=False),
                    json.dumps(rec.related_sectors, ensure_ascii=False),
                    json.dumps(rec.related_tickers, ensure_ascii=False),
                    rec.impact, rec.original_language, 1 if rec.translated else 0,
                    self._hash(rec.url + rec.title + rec.summary[:200]),
                    json.dumps(rec.extra, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
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
                "SELECT title, summary, url FROM records ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
            return [{"title": r[0], "summary": r[1], "url": r[2]} for r in rows]
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
    },
}


class ThemeAgent:
    def __init__(self, theme: str, output_dir: Path, deadline: float) -> None:
        self.theme = theme
        self.output_dir = output_dir
        self.deadline = deadline
        self.cfg = AGENT_CONFIG[theme]
        self.db = AgentDB(output_dir / "raw" / f"{theme}.db")
        self.fetcher = Fetcher()
        self.search = SearchEngine(self.fetcher)
        self.llm = LLMClient()
        self.queries: list[str] = list(self.cfg["initial_queries"])
        self.iteration = 0
        self.query_history: set[str] = set()

    def run(self) -> None:
        logger.info("[%s] ThemeAgent.run starting, deadline=%s", self.theme, datetime.fromtimestamp(self.deadline, tz=timezone.utc))
        self.db.set_meta("started_at", datetime.now(timezone.utc).isoformat())
        self.db.set_meta("theme", self.theme)

        while time.time() < self.deadline - 300 and self.queries:
            query = self.queries.pop(0)
            if query in self.query_history:
                continue
            self.query_history.add(query)
            self.iteration += 1

            logger.info("[%s] iter=%d query=%s", self.theme, self.iteration, query)
            results = self.search.search(query, max_results=5)
            if not results:
                logger.warning("[%s] no search results for %s", self.theme, query)
                continue

            self._process_results(results, query)

            # 定期反思并补充新查询
            if self.iteration % 3 == 0:
                self._reflect()

        # 最终反思
        self._reflect()
        self.db.set_meta("finished_at", datetime.now(timezone.utc).isoformat())
        logger.info("[%s] agent finished, records=%d", self.theme, self.db.count_records())

    def _process_results(self, results: list[dict[str, str]], query: str) -> None:
        urls = [r["url"] for r in results]
        contents: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_PER_AGENT) as ex:
            futures = {ex.submit(self.fetcher.jina_read, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    contents[url] = future.result()
                except Exception as exc:
                    logger.debug("[%s] fetch error %s: %s", self.theme, url, exc)

        for r in results:
            url = r["url"]
            title = r["title"]
            content = contents.get(url, "")
            if not content or len(content) < 80:
                continue

            prompt = self._build_extraction_prompt(self.theme, title, url, content)
            try:
                extracted = self.llm.extract_records(prompt, self.cfg["system"], ExtractionOutput)
            except Exception as exc:
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
                rec.extra = {"query": query, "theme": self.theme}
                self.db.insert_record(rec)
                logger.info("[%s] saved record %s", self.theme, rec.title[:60])

    def _reflect(self) -> None:
        count = self.db.count_records()
        recent = self.db.recent_records(10)
        recent_text = "\n".join(
            f"- {r['title']}: {r['summary'][:200]}" for r in recent
        )
        prompt = (
            f"你正在做一项 overnight 研究，主题是：{self.theme}。\n"
            f"当前已收集 {count} 条记录。最近记录摘要：\n{recent_text}\n\n"
            "请评估研究覆盖度（0-1）、指出主要空白，并给出 3-5 个下一步应搜索的中文关键词或问题。"
        )
        try:
            reflection = self.llm.reflect(prompt, "你是研究策略优化助手，请用中文输出 JSON。")
        except Exception as exc:
            logger.warning("[%s] reflection failed: %s", self.theme, exc)
            return

        self.db.insert_reflection(self.iteration, reflection)
        for q in reflection.new_queries:
            normalized = q.strip()
            if normalized and normalized not in self.query_history:
                self.queries.append(normalized)
        logger.info(
            "[%s] reflection score=%.2f new_queries=%d",
            self.theme,
            reflection.coverage_score,
            len(reflection.new_queries),
        )

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
            "- key_points: 要点数组\n"
            "- related_sectors: 相关行业数组\n"
            "- related_tickers: 相关A股代码数组（如 510300.SH, 300750.SZ）\n"
            "- impact: 对A股/投资的影响方向\n"
            "如果正文质量太低或无关，可以返回空 records 数组。"
        )


# --------------------------------------------------------------------------- #
# 主控 / 合并 / 报告
# --------------------------------------------------------------------------- #

class Orchestrator:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.state_path = output_dir / "state.json"
        self.deadline = self._compute_deadline()
        self.processes: dict[str, multiprocessing.Process] = {}

    def _compute_deadline(self) -> float:
        now = time.time()
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                started_at = state.get("started_at")
                if started_at:
                    started_ts = datetime.fromisoformat(started_at).timestamp()
                    planned_end = started_ts + RUNTIME_HOURS * 3600
                    if planned_end > now:
                        logger.info("resuming previous run, remaining=%.1fh", (planned_end - now) / 3600)
                        return planned_end
            except Exception as exc:
                logger.warning("failed to read state: %s", exc)
        started_at = datetime.now(timezone.utc).isoformat()
        self.state_path.write_text(
            json.dumps({"started_at": started_at, "runtime_hours": RUNTIME_HOURS}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return now + RUNTIME_HOURS * 3600

    def run(self) -> None:
        logger.info("orchestrator started, runtime=%.1fh, deadline=%s", RUNTIME_HOURS, datetime.fromtimestamp(self.deadline, tz=timezone.utc))

        ctx = multiprocessing.get_context("spawn")
        for theme in CATEGORIES:
            p = ctx.Process(target=_run_theme_agent, args=(theme, self.output_dir, self.deadline))
            p.start()
            self.processes[theme] = p

        wind_down = self.deadline - WIND_DOWN_MINUTES * 60
        while time.time() < wind_down:
            self._heartbeat()
            time.sleep(HEARTBEAT_SECONDS)

        logger.info("entering wind-down phase")
        for p in self.processes.values():
            if p.is_alive():
                p.terminate()
        for p in self.processes.values():
            p.join(timeout=60)

        self._merge_and_report()

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
        logger.info(
            "heartbeat alive=%d/%d total_records=%d by_theme=%s",
            alive,
            len(self.processes),
            sum(counts.values()),
            counts,
        )

    def _merge_and_report(self) -> None:
        logger.info("merging theme databases")
        merged_path = self.output_dir / "overnight_research.db"
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
                extra TEXT,
                created_at TEXT
            );
            CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, content='records', content_rowid='rowid');
            CREATE INDEX idx_records_theme ON records(theme);
            CREATE TRIGGER records_fts_insert AFTER INSERT ON records
            BEGIN INSERT INTO records_fts(rowid, title, summary) VALUES (new.rowid, new.title, new.summary); END;
            CREATE TRIGGER records_fts_delete AFTER DELETE ON records
            BEGIN INSERT INTO records_fts(records_fts, rowid, title, summary) VALUES ('delete', old.rowid, old.title, old.summary); END;
            CREATE TABLE stats (theme TEXT PRIMARY KEY, count INTEGER);
            """
        )

        stats: dict[str, int] = {}
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
                conn.execute(
                    """
                    INSERT OR IGNORE INTO records
                    (id, theme, title, source, url, date, accessed_at, category, tags, summary, key_points,
                     related_sectors, related_tickers, impact, original_language, translated,
                     content_hash, extra, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec["id"], rec.get("theme", theme), rec["title"], rec["source"], rec["url"],
                        rec["date"], rec["accessed_at"], rec["category"], rec["tags"], rec["summary"],
                        rec["key_points"], rec["related_sectors"], rec["related_tickers"],
                        rec["impact"], rec["original_language"], rec["translated"],
                        rec["content_hash"], rec["extra"], rec["created_at"],
                    ),
                )
            stats[theme] = len(rows)
            src.close()

        for theme, count in stats.items():
            conn.execute("INSERT OR REPLACE INTO stats (theme, count) VALUES (?, ?)", (theme, count))
        conn.commit()
        conn.close()

        logger.info("merged total=%d records into %s", sum(stats.values()), merged_path)
        ReportBuilder(self.output_dir, stats).build()


# --------------------------------------------------------------------------- #
# 子进程入口
# --------------------------------------------------------------------------- #

def _setup_child_logging() -> None:
    """在子进程中启用 INFO 级别 stdout 日志。"""
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def _run_theme_agent(theme: str, output_dir: Path, deadline: float) -> None:
    # 子进程忽略 SIGTERM 以便主进程 terminate 后能尽快退出循环
    signal.signal(signal.SIGTERM, lambda _sig, _frame: sys.exit(0))
    _setup_child_logging()
    logger.info("[%s] child process started, ant=%d open=%d", theme, len(os.environ.get("ANTHROPIC_API_KEY", "")), len(os.environ.get("OPENAI_API_KEY", "")))
    try:
        agent = ThemeAgent(theme, output_dir, deadline)
        agent.run()
    except Exception as exc:
        logger.exception("[%s] agent crashed: %s", theme, exc)


# --------------------------------------------------------------------------- #
# 报告生成
# --------------------------------------------------------------------------- #

class ReportBuilder:
    def __init__(self, output_dir: Path, stats: dict[str, int]) -> None:
        self.output_dir = output_dir
        self.stats = stats
        self.total = sum(stats.values())

    def build(self) -> None:
        md = self._render_md()
        html = self._render_html(md)
        (self.output_dir / "report.md").write_text(md, encoding="utf-8")
        (self.output_dir / "report.html").write_text(html, encoding="utf-8")
        logger.info("report saved to %s", self.output_dir)

    def _render_md(self) -> str:
        lines = [
            f"# 20 小时 Overnight 研究报告（ECS agent worker）",
            "",
            f"- **生成时间**：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"- **数据来源**：公开网络搜索 + LLM 结构化提取",
            f"- **记录总数**：{self.total}",
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
            "## 说明",
            "",
            "本报告由部署在 ECS 的 `overnight_research.py` worker 连续运行约 20 小时后自动生成。",
            "原始结构化数据保存在同目录 `overnight_research.db`，支持 FTS5 全文检索。",
            "",
            "## 后续建议",
            "",
            "1. 将 `overnight_research.db` 同步到本地项目 `docs/research/` 下。",
            "2. 接入平台 AI 问答模块作为 RAG 知识库。",
            "3. 定期重新跑该 worker 更新资料。",
            "",
        ])
        return "\n".join(lines)

    def _render_html(self, md: str) -> str:
        # 非常简单的 markdown-to-html 转换
        html_body = "\n".join(f"<p>{line}</p>" if line else "<br>" for line in md.splitlines())
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Overnight Research Report</title>
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

    # 允许全局覆盖
    global RUNTIME_HOURS
    if args.runtime_hours:
        RUNTIME_HOURS = args.runtime_hours

    Orchestrator(output_dir).run()


if __name__ == "__main__":
    main()
