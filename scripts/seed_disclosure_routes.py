#!/usr/bin/env python3
"""Seed company_disclosure_route with every active A-share stock.

Walks ``etf_info`` for ``instrument_type=STOCK`` + ``market='A股'`` +
``status='active'`` and upserts one ``company_disclosure_route`` row per
code via ``app.data.disclosure_routes.upsert_batch``.

Each row carries the SSE / SZSE / BSE disclosure URL (whichever is
appropriate for the numeric code prefix), the cninfo URL is filled in
by ``build_cninfo_org_id_map.py`` (separate flow).  IR URLs are left
``NULL`` for the operator-scheduled discovery pass.

Run::

    cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform
    poetry run python scripts/seed_disclosure_routes.py

The script is idempotent: the underlying ``upsert_batch`` uses
``ON CONFLICT (code) DO UPDATE`` so re-running just refreshes the
exchange URLs / names.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.config import get_settings
from app.core.database import SessionLocal
from app.data.disclosure_routes import build_seed_routes


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("seed_disclosure_routes")


def _count_a_share_stocks() -> int:
    """Return how many A-share STOCK rows exist (sanity check)."""
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM etf_info
                WHERE instrument_type = 'STOCK'
                  AND market = 'A股'
                  AND status = 'active'
                """
            )
        ).one()
        return int(row[0])


def main() -> None:
    expected = _count_a_share_stocks()
    log.info("etf_info 中预期写入 %d 条 A 股 STOCK 记录", expected)

    db = SessionLocal()
    try:
        written = build_seed_routes(db)
        log.info("已写入 %d 条路由记录", written)
    finally:
        db.close()

    if expected and written < expected:
        log.warning(
            "实际写入 %d 条，少于 etf_info 中 A 股 STOCK 总数 %d — "
            "可能部分代码前缀不在 SSE/SZSE/BSE 规则中",
            written,
            expected,
        )


if __name__ == "__main__":
    main()
