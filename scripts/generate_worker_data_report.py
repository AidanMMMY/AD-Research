#!/usr/bin/env python3
"""
Generate an HTML report from the 8-worker ad-research crawler data on ECS.
Reads JSON files via SSH and writes a standalone HTML document.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ECS_HOST = "ad-research"
ECS_BASE_DIR = "/data/ad-research"

SOURCES = [
    ("cls", "财联社", "published_at"),
    ("eastmoney_news", "东方财富公告", "published_at"),
    ("gov_china", "中国政府网", "published_at"),
    ("fed_intl", "Fed/ECB/BIS", "published_at"),
    ("stocktwits", "美股散户 (StockTwits)", "created_at"),
    ("xueqiu_playwright", "雪球", "published_at"),
    ("x", "X/Twitter", "created_at"),
    ("reddit_curl_cffi", "Reddit", "created_at"),
]


def ssh_cat(path: str) -> str | None:
    """Return the contents of a remote file via SSH, or None if missing/empty."""
    try:
        result = subprocess.run(
            ["ssh", ECS_HOST, f"cat {path}"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return text if text else None
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        # ssh not installed locally
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Best-effort parse a variety of timestamp strings."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None

    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "n/a"):
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a %b %d %H:%M:%S %z %Y",
        "%a %b %d %H:%M:%S +0000 %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Try ISO8601 with Python's own parser as a fallback
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_source(slug: str, _label: str, _time_field: str) -> dict[str, Any]:
    """Load one source's today.json from the remote server."""
    raw = ssh_cat(f"{ECS_BASE_DIR}/{slug}/today.json")
    if raw is None:
        return {"source": slug, "error": "file not found or empty", "items": []}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"source": slug, "error": f"invalid JSON: {exc}", "items": []}

    # Some files are a bare list, others are an object with an `items` key.
    if isinstance(data, list):
        return {"source": slug, "items": data}

    return data


def format_time(value: Any) -> str:
    dt = parse_datetime(value)
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def sort_key(item: dict[str, Any], time_field: str) -> datetime:
    dt = parse_datetime(item.get(time_field)) or parse_datetime(item.get("published_at")) or parse_datetime(item.get("created_at")) or parse_datetime(item.get("timestamp"))
    if dt is None:
        # Push undated items to the end so they don't block dated items.
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt


def escape_html(text: str | None) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(data_sources: list[tuple[str, str, str, dict[str, Any]]]) -> str:
    total_items = sum(
        len(s[3].get("items", [])) if isinstance(s[3].get("items"), list) else 0
        for s in data_sources
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Header / summary
    header = f"""
    <header class="page-header">
      <h1>8-Worker 爬虫数据日报</h1>
      <p class="meta">生成时间：{generated} &nbsp;|&nbsp; 总条目：{total_items}</p>
      <div class="summary-grid">
"""
    for slug, label, _time_field, data in data_sources:
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        error = data.get("error")
        fetched_at = data.get("fetched_at")
        status_class = "ok" if items else ("error" if error else "empty")
        status_text = f"{len(items)} 条" if items else ("采集错误" if error else "无数据")
        header += f"""
        <div class="summary-card {status_class}">
          <div class="source-name">{label}</div>
          <div class="source-count">{status_text}</div>
          {"<div class='source-error'>" + escape_html(error) + "</div>" if error else ""}
          {"<div class='source-time'>更新：" + escape_html(fetched_at) + "</div>" if fetched_at else ""}
        </div>
"""
    header += """      </div>
    </header>
"""

    # Sections
    sections = []
    for slug, label, time_field, data in data_sources:
        items = data.get("items", []) if isinstance(data.get("items", list), list) else []
        error = data.get("error")
        fetched_at = data.get("fetched_at")

        if error and not items:
            sections.append(
                f"""
    <section class="source-section" id="{slug}">
      <h2>{label} <span class="badge error">错误</span></h2>
      <p class="empty">{escape_html(error)}</p>
    </section>
"""
            )
            continue

        sorted_items = sorted(items, key=lambda it: sort_key(it, time_field), reverse=True)

        cards = []
        for item in sorted_items:
            # Determine title / body for this source type.
            title = item.get("title") or item.get("author_name") or item.get("user") or "(无标题)"
            body = item.get("summary") or item.get("body") or item.get("text") or ""
            url = item.get("url") or ""
            time_value = (
                item.get(time_field)
                or item.get("published_at")
                or item.get("created_at")
                or item.get("timestamp")
            )
            source_meta = item.get("source") or item.get("source_api") or item.get("agency_name") or label

            extra_meta = []
            if item.get("username"):
                extra_meta.append(f"用户: {item['username']}")
            if item.get("symbol"):
                extra_meta.append(f"标的: {item['symbol']}")
            if item.get("sentiment"):
                extra_meta.append(f"情绪: {item['sentiment']}")
            if item.get("author_handle"):
                extra_meta.append(f"@{item['author_handle']}")
            if item.get("tags"):
                tags = item["tags"]
                if isinstance(tags, list):
                    extra_meta.append(", ".join(tags))
            if item.get("engagement") and isinstance(item["engagement"], dict):
                eg = item["engagement"]
                parts = [f"{k}: {v}" for k, v in eg.items() if v is not None]
                if parts:
                    extra_meta.append(" | ".join(parts))
            if item.get("stock_symbols"):
                ss = item["stock_symbols"]
                if isinstance(ss, list) and ss:
                    extra_meta.append("股票: " + ", ".join(str(s) for s in ss))

            extra_line = " &nbsp;|&nbsp; ".join(extra_meta) if extra_meta else ""

            title_link = f'<a href="{escape_html(url)}" target="_blank" rel="noopener">{escape_html(title)}</a>' if url else escape_html(title)
            body_html = f'<p class="body">{escape_html(body)}</p>' if body else ""
            meta_html = f'<div class="meta-line">来源: {escape_html(source_meta)} &nbsp;|&nbsp; 时间: {format_time(time_value)}'
            if extra_line:
                meta_html += f" &nbsp;|&nbsp; {extra_line}"
            meta_html += "</div>"

            cards.append(
                f"""
        <article class="item-card">
          <h3 class="item-title">{title_link}</h3>
          {body_html}
          {meta_html}
        </article>
"""
            )

        if not cards:
            cards_html = '<p class="empty">该数据源暂无今日数据。</p>'
        else:
            cards_html = "\n".join(cards)

        header_meta = f"<span class='meta-fetched'>更新: {escape_html(fetched_at)}</span>" if fetched_at else ""
        sections.append(
            f"""
    <section class="source-section" id="{slug}">
      <h2>{label} <span class="badge">{len(items)} 条</span> {header_meta}</h2>
      {cards_html}
    </section>
"""
        )

    css = """
    :root {
      --bg: #f8f9fa;
      --card-bg: #ffffff;
      --text: #1a1a1a;
      --muted: #6b7280;
      --border: #e5e7eb;
      --accent: #2563eb;
      --accent-light: #eff6ff;
      --error: #dc2626;
      --error-bg: #fef2f2;
      --empty: #9ca3af;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      margin: 0;
      padding: 0 1rem 3rem;
    }
    .container { max-width: 960px; margin: 0 auto; }
    .page-header { padding: 2rem 0 1rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
    .page-header h1 { margin: 0 0 0.25rem; font-size: 1.75rem; font-weight: 700; }
    .meta { color: var(--muted); font-size: 0.9rem; margin: 0; }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.25rem; }
    .summary-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
    .summary-card.ok { border-left: 4px solid #16a34a; }
    .summary-card.empty { border-left: 4px solid var(--empty); }
    .summary-card.error { border-left: 4px solid var(--error); background: var(--error-bg); }
    .source-name { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
    .source-count { font-size: 1.25rem; font-weight: 700; color: var(--text); }
    .source-error { color: var(--error); font-size: 0.8rem; margin-top: 0.25rem; }
    .source-time { color: var(--muted); font-size: 0.75rem; margin-top: 0.25rem; }
    .source-section { margin-bottom: 2.5rem; }
    .source-section h2 { font-size: 1.25rem; font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin: 0 0 1rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .badge { font-size: 0.75rem; font-weight: 600; color: var(--accent); background: var(--accent-light); padding: 0.15rem 0.5rem; border-radius: 9999px; }
    .badge.error { color: #fff; background: var(--error); }
    .meta-fetched { font-size: 0.75rem; color: var(--muted); font-weight: 400; margin-left: auto; }
    .item-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; margin-bottom: 0.75rem; box-shadow: 0 1px 2px rgba(0,0,0,0.03); transition: box-shadow 0.15s ease; }
    .item-card:hover { box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .item-title { font-size: 1rem; font-weight: 600; margin: 0 0 0.5rem; color: var(--text); }
    .item-title a { color: var(--accent); text-decoration: none; }
    .item-title a:hover { text-decoration: underline; }
    .body { color: var(--text); font-size: 0.92rem; margin: 0 0 0.75rem; }
    .meta-line { color: var(--muted); font-size: 0.82rem; margin: 0; }
    .empty { color: var(--muted); font-style: italic; }
    @media (max-width: 640px) {
      .page-header h1 { font-size: 1.4rem; }
      .summary-grid { grid-template-columns: 1fr; }
    }
"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>8-Worker 爬虫数据日报 - {generated.split(" ")[0]}</title>
  <style>
{css}
  </style>
</head>
<body>
  <div class="container">
{header}
{''.join(sections)}
  </div>
</body>
</html>
"""
    return html


def main() -> int:
    loaded = [(slug, label, time_field, load_source(slug, label, time_field)) for slug, label, time_field in SOURCES]
    html = build_html(loaded)

    output_path = Path("/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/docs/dev-notes/20260708-worker-data-report-20260708.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"Report written to: {output_path}")
    print("\nSource counts:")
    for slug, label, _time_field, data in loaded:
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        error = data.get("error")
        if error:
            print(f"  {label:25} error: {error}")
        else:
            print(f"  {label:25} {len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
