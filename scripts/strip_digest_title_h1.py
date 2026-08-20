#!/usr/bin/env python3
"""Strip the baked-in ``# {title}`` H1 from historical daily_digest rows.

Background (2026-08-21): before the generator fix, ``content_md`` was
assembled as ``# {title}`` + 6 ``##`` sections, while every consumer
(web hero card / email header / Telegram first message / macOS app)
already renders the ``title`` column separately — the report title was
displayed twice in all four channels. The generator no longer embeds
the H1; this script cleans the rows already persisted.

Safety: only strips leading lines at the very start of the document that
look like an H1 (``# ...``) plus following blank lines — the exact shape
``_strip_leading_heading`` handles in the generator. Section bodies are
untouched (they never occur before the first ``##`` in these rows).

Usage (inside backend container):
    cd /app && PYTHONPATH=/app python3 scripts/strip_digest_title_h1.py --dry-run
    cd /app && PYTHONPATH=/app python3 scripts/strip_digest_title_h1.py --apply
"""

import argparse
import logging
import re
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("strip_digest_title_h1")

# 文档开头的 H1 行（`# 标题`，非 `##`）+ 其后空行。digest 的 content_md
# 合法内容不会以 H1 开头（标题在 title 列），所以开头出现 H1 必是要剥的。
_LEADING_H1_RE = re.compile(r"^(?:#[^#\n]*\n(?:[ \t]*\n)*)+")


def strip_leading_h1(content: str) -> str:
    """剥掉 content_md 开头残留的 `# 标题` H1 行（含后续空行）。"""
    return _LEADING_H1_RE.sub("", content.lstrip("\n"), count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run: report only)",
    )
    args = parser.parse_args()

    from app.core.database import SessionLocal
    from app.models.digest import DailyDigest

    db = SessionLocal()
    try:
        rows = db.query(DailyDigest).order_by(DailyDigest.report_date).all()
        changed = 0
        for row in rows:
            content = (row.content_md or "").strip()
            if not content.startswith("# "):
                continue
            new_content = strip_leading_h1(content)
            if new_content == content:
                continue
            logger.info(
                "%s: strip leading H1 (%d -> %d chars, head: %.40s)",
                row.report_date,
                len(content),
                len(new_content),
                content.splitlines()[0],
            )
            changed += 1
            if args.apply:
                row.content_md = new_content
        if args.apply:
            db.commit()
            logger.info("APPLIED: %d rows updated", changed)
        else:
            logger.info("DRY-RUN: %d/%d rows would be updated", changed, len(rows))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
