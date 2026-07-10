"""单个 batch 的 IR 页面发现代理。

用法:
    python app/data/discovery_agent.py <offset> <limit> <output_json>

示例:
    python app/data/discovery_agent.py 0 50 batch_0000.json

对给定 batch 内的每家公司，使用 web search 发现其官网 IR 页面 URL。
结果写入 JSON 文件，每个条目包含 {code, name, ir_url, method, notes}。
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import SessionLocal
from app.models.disclosure_route import CompanyDisclosureRoute
from sqlalchemy import select, func


def get_batch(offset: int, limit: int) -> list[dict]:
    """读取指定 offset/limit 的公司列表（按市值排名的前 N 优先）。"""
    db = SessionLocal()
    rows = db.execute(
        select(CompanyDisclosureRoute.code, CompanyDisclosureRoute.name)
        .order_by(CompanyDisclosureRoute.market_cap_rank.asc().nullslast())
        .offset(offset)
        .limit(limit)
    ).all()
    db.close()
    return [{"code": r.code, "name": r.name} for r in rows]


def main():
    if len(sys.argv) < 3:
        print("Usage: python discovery_agent.py <offset> <limit> [output_json]")
        sys.exit(1)

    offset = int(sys.argv[1])
    limit = int(sys.argv[2])
    output_file = sys.argv[3] if len(sys.argv) > 3 else f"batch_{offset:04d}.json"

    companies = get_batch(offset, limit)
    print(f"Batch offset={offset} limit={limit}: loaded {len(companies)} companies")
    print(f"Output: {output_file}")

    # 公司列表以 JSON 格式输出，供后续 agent 处理
    payload = {
        "offset": offset,
        "limit": limit,
        "count": len(companies),
        "companies": companies,
    }

    with open(output_file, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(companies)} companies to {output_file}")


if __name__ == "__main__":
    main()
