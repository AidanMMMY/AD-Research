#!/usr/bin/env python3
"""存量繁体中文 → 简体中文回填（news_article）。

背景：2026-07 起接入的台湾/香港中文源（zhb_technews 科技新报、
zhb_ithometw、zhb_blocktempo 動區動趨、zhx_* 播客 shownotes、部分
wechat_ 号）正文为繁体。新文章已在入库链路（NewsNormalizer +
ContentFetcher，2026-08-01）统一转简体；本脚本回填存量数据。

特性：
* **幂等** —— 只处理检出繁体特征（``zh_convert.has_traditional``）的
  行；转换后的行再次扫描时不再命中，可反复执行。
* **分批** —— 按主键 id 游标分页，每批一个事务，默认 500 行/批，
  不会长时间持锁；中断后重跑自动续扫。
* **语言门控** —— 仅 ``language`` 为中文变体（zh/cn/zh-*）的行。
* 转换字段：title / summary / body / body_html / full_content。
  （title_zh / translated_zh / summary_zh 是 AI 翻译产物，本来就是
  简体，不在范围内。）

Usage（在 ECS backend 容器内）：
    cd /app && PYTHONPATH=/app python3 scripts/backfill_zh_traditional_to_simplified.py

Dry-run（只统计不写库，建议先跑一遍看规模）：
    python3 scripts/backfill_zh_traditional_to_simplified.py --dry-run

调整批大小 / 限批数：
    python3 scripts/backfill_zh_traditional_to_simplified.py --batch-size 200 --max-batches 10
"""

import argparse
import logging

from sqlalchemy import or_, select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_zh_t2s")

# 与 app.services.news.translation_service._CHINESE_LANGUAGE_CODES 保持一致。
# SQL 预过滤用 like 匹配 zh*，外加 "cn"。
_FIELDS = ("title", "summary", "body", "body_html", "full_content")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill traditional → simplified Chinese")
    parser.add_argument(
        "--batch-size", type=int, default=500, help="rows per batch (default: 500)"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="stop after N batches (default: unlimited)",
    )
    parser.add_argument("--dry-run", action="store_true", help="count only, no writes")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from app.core.database import SessionLocal
    from app.services.news._model_loader import NewsArticle
    from app.services.news.zh_convert import to_simplified_if_traditional

    db = SessionLocal()
    last_id = 0
    scanned = converted_rows = converted_fields = 0
    batches = 0
    try:
        while True:
            rows = (
                db.execute(
                    select(NewsArticle)
                    .where(NewsArticle.id > last_id)
                    .where(
                        or_(
                            NewsArticle.language.like("zh%"),
                            NewsArticle.language == "cn",
                        )
                    )
                    .order_by(NewsArticle.id)
                    .limit(args.batch_size)
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            batches += 1
            batch_changed = 0
            for row in rows:
                scanned += 1
                row_changed = False
                for field in _FIELDS:
                    original = getattr(row, field)
                    converted = to_simplified_if_traditional(original)
                    if converted != original:
                        converted_fields += 1
                        row_changed = True
                        if not args.dry_run:
                            setattr(row, field, converted)
                if row_changed:
                    converted_rows += 1
                    batch_changed += 1
            last_id = rows[-1].id
            if not args.dry_run:
                db.commit()
            logger.info(
                "batch %d done (id<=%d): scanned=%d converted_rows=%d converted_fields=%d",
                batches,
                last_id,
                len(rows),
                batch_changed,
                converted_fields,
            )
            if args.max_batches is not None and batches >= args.max_batches:
                logger.info("stopping after --max-batches=%d", args.max_batches)
                break
    finally:
        db.close()

    logger.info(
        "%s complete: scanned=%d zh rows, converted_rows=%d, converted_fields=%d",
        "DRY-RUN" if args.dry_run else "backfill",
        scanned,
        converted_rows,
        converted_fields,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
