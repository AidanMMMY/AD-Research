#!/usr/bin/env python3
"""Seed ``news_source_meta`` with the learning-center source tags.

学习中心（方案 B MVP，2026-08-02）的资讯源打标种子：把
``app/services/news/source_meta_seed.SOURCE_META_SEED`` 里
"深度分析/科普教育"源标签灌入 ``news_source_meta`` 表。幂等——
等价 INSERT ... ON CONFLICT DO NOTHING，重复执行只插缺失行，
不覆盖运营手改。

前置：先跑 alembic 迁移 ``w4x6y8z0a2b4`` 建表。

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 scripts/seed_news_source_meta.py

Dry-run (只打印分布，不写库):
    python3 scripts/seed_news_source_meta.py --dry-run
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

# 允许直接 `python3 scripts/seed_news_source_meta.py` 运行：
# 脚本目录会成为 sys.path[0]，需手动把仓库根目录加进来。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_news_source_meta")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed news_source_meta")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print seed distribution without writing",
    )
    args = parser.parse_args()

    from app.services.news.source_meta_seed import SOURCE_META_SEED

    by_type = Counter(r["content_type"] for r in SOURCE_META_SEED)
    by_topic = Counter(r["topic"] for r in SOURCE_META_SEED)
    logger.info("种子总数 %d（按 content_type: %s）", len(SOURCE_META_SEED), dict(by_type))
    logger.info("按 topic: %s", dict(by_topic))

    if args.dry_run:
        return 0

    from app.core.database import SessionLocal
    from app.services.news.source_meta_seed import seed_source_meta

    db = SessionLocal()
    try:
        inserted = seed_source_meta(db)
        logger.info("插入 %d 行（已存在的 %d 行跳过）", inserted, len(SOURCE_META_SEED) - inserted)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
