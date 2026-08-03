"""删除已成功转为 markdown 的 cninfo PDF 存档（B2，2026-08-03）.

md 提取管线全量重提完成后，``extracted_text``（DB 主存储）+ 盘上 md
存档已齐备，原始 PDF 体积巨大（全量约数百 GB），可安全删除以释放
/data 磁盘。

删除条件（全部满足）：

* ``extraction_status='extracted'`` —— 提取成功；
* ``extracted_format='md'`` —— 已升级为 markdown 产物；
* ``md_path NOT NULL`` —— md 存档文件已写盘；
* ``file_path NOT NULL`` —— 盘上确实还有 PDF。

删除 PDF 文件后把 ``file_path`` / ``file_size`` 置 NULL（``adjunct_url``
保留，必要时可从 cninfo 重新下载；届时走常规 download 任务即可）。

用法::

    # 预览（默认 dry-run，只打印将删数量/字节，不动任何数据）
    python scripts/delete_extracted_cninfo_pdfs.py

    # 真删
    python scripts/delete_extracted_cninfo_pdfs.py --execute
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_, select

from app.core.database import SessionLocal
from app.models.cninfo_report import CninfoReport

# 每 N 行提交一次，避免超长事务锁表。
_BATCH_COMMIT = 500


def find_candidates(db) -> list[CninfoReport]:
    """查出所有满足删除条件的行（按 id 排序，稳定可复现）。"""
    stmt = (
        select(CninfoReport)
        .where(
            and_(
                CninfoReport.extraction_status == "extracted",
                CninfoReport.extracted_format == "md",
                CninfoReport.md_path.isnot(None),
                CninfoReport.file_path.isnot(None),
            )
        )
        .order_by(CninfoReport.id)
    )
    return list(db.execute(stmt).scalars().all())


def purge(db, rows: list[CninfoReport], execute: bool) -> dict:
    """删除 PDF 并清空 file_path/file_size。dry-run 只统计字节数。"""
    counters = {
        "candidates": len(rows),
        "deleted": 0,
        "missing_file": 0,
        "bytes_freed": 0,
    }
    if not execute:
        # dry-run：用 DB 里的 file_size 估算（文件大小可能与实际有出入，
        # 但量级足够决策）；对 file_size 为 NULL 的行尝试 stat。
        for row in rows:
            if row.file_size:
                counters["bytes_freed"] += int(row.file_size)
            else:
                try:
                    counters["bytes_freed"] += os.path.getsize(row.file_path)
                except OSError:
                    counters["missing_file"] += 1
        return counters

    for idx, row in enumerate(rows, start=1):
        path = row.file_path
        try:
            size = int(row.file_size) if row.file_size else os.path.getsize(path)
        except OSError:
            size = 0
        try:
            os.remove(path)
            counters["deleted"] += 1
            counters["bytes_freed"] += size
        except FileNotFoundError:
            counters["missing_file"] += 1
        except OSError as exc:
            print(f"⚠️  remove failed id={row.id} path={path}: {exc}")
            continue

        # PDF 已删（或本就不在盘上）→ 清空路径字段。adjunct_url 保留，
        # 需要时可从 cninfo 重新下载。
        row.file_path = None
        row.file_size = None
        db.add(row)
        if idx % _BATCH_COMMIT == 0:
            db.commit()
            print(f"   ... committed {idx}/{len(rows)}")

    db.commit()
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真删（默认 dry-run 只打印统计）",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = find_candidates(db)
        counters = purge(db, rows, execute=args.execute)
    finally:
        db.close()

    freed_mb = counters["bytes_freed"] / (1024 * 1024)
    if args.execute:
        print(
            f"✅ Deleted {counters['deleted']} PDFs "
            f"(missing_file={counters['missing_file']}), freed {freed_mb:.1f} MB"
        )
    else:
        print(
            f"🔎 DRY-RUN: {counters['candidates']} PDFs eligible, "
            f"~{freed_mb:.1f} MB would be freed "
            f"(missing_file={counters['missing_file']}). "
            f"Re-run with --execute to delete."
        )


if __name__ == "__main__":
    main()
