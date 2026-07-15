"""Academic research collector.

Fetches recent finance/econ papers from arXiv RSS (no external RSS lib).
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from research.agents.base import save_raw, save_note, safe_get

logger = logging.getLogger("research.agents.academic")

ARXIV_FEEDS = [
    "http://export.arxiv.org/rss/q-fin",
    "http://export.arxiv.org/rss/econ",
]


def _parse_arxiv_feed(url: str) -> list[dict]:
    resp = safe_get(url, timeout=30)
    if not resp:
        return []
    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    # arXiv RSS uses <item> elements
    for item in root.findall(".//item")[:20]:
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        summary = item.findtext("description", default="")
        published = item.findtext("pubDate", default="")
        items.append({
            "title": title.strip() if title else "",
            "link": link.strip() if link else "",
            "summary": summary.strip() if summary else "",
            "published": published.strip() if published else "",
        })
    return items


def run_academic_agent(data_dir: str, agent_name: str = "academic") -> None:
    logging.basicConfig(level=logging.INFO)
    root = Path(data_dir)
    logger.info("Starting %s agent", agent_name)

    all_items = []
    for url in ARXIV_FEEDS:
        try:
            items = _parse_arxiv_feed(url)
            all_items.extend({"source": "arxiv", **it} for it in items)
            logger.info("arXiv feed fetched %d items", len(items))
        except Exception as exc:  # noqa: BLE001
            logger.exception("arXiv feed failed: %s", exc)

    save_raw(root, agent_name, "recent_papers", all_items)

    if all_items:
        top = all_items[:20]
        note_body = "\n\n".join(
            f"- **{it['source']}**: [{it['title']}]({it['link']})" for it in top
        )
        save_note(root, agent_name, "近期学术论文摘要", note_body)

    logger.info("%s agent finished; collected %d papers", agent_name, len(all_items))
