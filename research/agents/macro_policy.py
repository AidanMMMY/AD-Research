"""Macro & policy news collector.

Targets publicly available Chinese policy/news pages and RSS feeds.
"""

import logging
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from research.agents.base import save_raw, save_note, safe_get

logger = logging.getLogger("research.agents.macro_policy")

SOURCES = [
    {
        "name": "新华社_时政",
        "url": "http://www.xinhuanet.com/politics/news_politics.xml",
        "kind": "rss",
    },
    {
        "name": "中国政府网_政策",
        "url": "https://www.gov.cn/zhengce/zhengceku/",
        "kind": "html_list",
    },
    {
        "name": "新浪财经_国内财经",
        "url": "https://finance.sina.com.cn/china/",
        "kind": "html_list",
    },
]


def _fetch_html_list(url: str) -> list[dict]:
    resp = safe_get(url, timeout=20)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text or len(text) < 8:
            continue
        items.append({"title": text, "href": a["href"]})
        if len(items) >= 50:
            break
    return items


def _fetch_rss(url: str) -> list[dict]:
    resp = safe_get(url, timeout=20)
    if not resp:
        return []
    import xml.etree.ElementTree as ET

    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item")[:30]:
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        pub_date = item.findtext("pubDate", default="")
        items.append({"title": title.strip(), "href": link.strip(), "published": pub_date.strip()})
    return items


def run_macro_policy_agent(data_dir: str, agent_name: str = "macro_policy") -> None:
    logging.basicConfig(level=logging.INFO)
    root = Path(data_dir)
    logger.info("Starting %s agent", agent_name)

    all_items = []
    for src in SOURCES:
        try:
            if src["kind"] == "rss":
                items = _fetch_rss(src["url"])
            else:
                items = _fetch_html_list(src["url"])
            all_items.extend({"source": src["name"], **it} for it in items)
            logger.info("%s fetched %d items", src["name"], len(items))
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s failed: %s", src["name"], exc)
        time.sleep(2)

    save_raw(root, agent_name, "policy_headlines", all_items)

    if all_items:
        top = all_items[:30]
        note_body = "\n\n".join(
            f"- **{it['source']}**: [{it['title']}]({it['href']})" for it in top
        )
        save_note(root, agent_name, "宏观政策要闻摘要", note_body)

    logger.info("%s agent finished; collected %d items", agent_name, len(all_items))
