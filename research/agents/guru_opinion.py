"""Investment guru opinion collector (v1).

Public speeches/interviews of well-known investors are scattered across
podcasts, shareholder letters, and social platforms.  v1 records a plan
and fetches a couple of publicly available pages without authentication.
"""

import logging
from pathlib import Path

from research.agents.base import save_raw, save_note, safe_get

logger = logging.getLogger("research.agents.guru_opinion")

GURU_SOURCES = [
    {"name": "Berkshire_Hathaway_letters", "url": "https://www.berkshirehathaway.com/letters/letters.html"},
    {"name": "Bridgewater_Research", "url": "https://www.bridgewater.com/research-and-insights"},
]


def run_guru_opinion_agent(data_dir: str, agent_name: str = "guru_opinion") -> None:
    logging.basicConfig(level=logging.INFO)
    root = Path(data_dir)
    logger.info("Starting %s agent", agent_name)

    fetched = []
    for src in GURU_SOURCES:
        resp = safe_get(src["url"], timeout=15)
        fetched.append({
            "source": src["name"],
            "url": src["url"],
            "status": resp.status_code if resp else None,
            "len": len(resp.text) if resp else 0,
        })

    save_raw(root, agent_name, "guru_source_status", fetched)

    plan = """## 投资大佬公开观点采集规划（v1）

当前版本先建立可扩展框架。后续迭代可接入：
1. 巴菲特致股东信（Berkshire Hathaway letters）文本解析与主题提取。
2. 桥水研究观点（Bridgewater research）RSS/文章抓取。
3. 国内私募大佬（但斌、林园、张坤等）公开路演/采访的音频转文本摘要。
4. 雪球/东方财富热门专栏作者观点聚合（需登录，放到 v2）。

本次仅记录数据源可访问性，避免一开始就过度抓取导致 IP/账号受限。
"""
    save_note(root, agent_name, "投资大佬观点采集规划", plan)

    logger.info("%s agent finished", agent_name)
