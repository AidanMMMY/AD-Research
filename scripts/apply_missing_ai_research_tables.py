"""One-off idempotent script to create the AI research tables.

Background
----------
The Alembic version in the database reports `e2f3a4b5c6d7` (merge_heads
phase 5/6/7/9), but the 4 tables that migration
`e5f6a7b8c9d0_add_ai_research_tables.py` is supposed to create
(research_note, sentiment_data, ai_chat_session, ai_chat_message) are
missing. The Sentiment Dashboard is therefore broken (B7).

This script issues the CREATE TABLE statements for the missing tables
only. It does NOT touch `alembic_version` — the existing row is treated
as authoritative.

The script is idempotent: each CREATE is wrapped in a check against
`to_regclass('public.<table>')`, so re-running it is safe.

Usage::

    poetry run python scripts/apply_missing_ai_research_tables.py

It reads `DATABASE_URL` from the environment (which `app.config.get_settings`
also picks up). The default points at the local Postgres dev instance
(`postgresql+psycopg2://etf:etf_research_password@localhost:5432/ad_research`).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


logger = logging.getLogger("apply_missing_ai_research_tables")


# Schema mirroring alembic/versions/e5f6a7b8c9d0_add_ai_research_tables.py
# (research_note must come before ai_chat_* because ai_chat_message depends
# on ai_chat_session, and research_note + sentiment_data reference etf_info).
# We deliberately do NOT include a stock_fundamental / etf_indicator etc.
# join — only the four tables the migration owns.
TABLE_DDL: dict[str, str] = {
    "research_note": """
        CREATE TABLE research_note (
            id              SERIAL PRIMARY KEY,
            instrument_code VARCHAR(20) NOT NULL
                REFERENCES etf_info(code) ON DELETE CASCADE,
            note_type       VARCHAR(50) NOT NULL,
            content         TEXT NOT NULL,
            summary         VARCHAR(500),
            sentiment       VARCHAR(20),
            confidence      INTEGER,
            source_data     JSON,
            generated_at    TIMESTAMP,
            created_at      TIMESTAMP DEFAULT now()
        )
    """,
    "sentiment_data": """
        CREATE TABLE sentiment_data (
            id               SERIAL PRIMARY KEY,
            instrument_code  VARCHAR(20)
                REFERENCES etf_info(code) ON DELETE CASCADE,
            source           VARCHAR(50) NOT NULL,
            title            VARCHAR(500),
            content          TEXT,
            url              VARCHAR(1000),
            sentiment_score  NUMERIC(5, 4),
            sentiment_label  VARCHAR(20),
            confidence       NUMERIC(5, 4),
            published_at     TIMESTAMP,
            ingested_at      TIMESTAMP DEFAULT now()
        )
    """,
    "ai_chat_session": """
        CREATE TABLE ai_chat_session (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            title       VARCHAR(200),
            created_at  TIMESTAMP DEFAULT now(),
            updated_at  TIMESTAMP DEFAULT now()
        )
    """,
    "ai_chat_message": """
        CREATE TABLE ai_chat_message (
            id          SERIAL PRIMARY KEY,
            session_id  INTEGER NOT NULL
                REFERENCES ai_chat_session(id) ON DELETE CASCADE,
            role        VARCHAR(20) NOT NULL,
            content     TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT now()
        )
    """,
}


def _engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Mirror the app default so this script works on a vanilla dev box.
        url = (
            "postgresql+psycopg2://etf:etf_research_password"
            "@localhost:5432/ad_research"
        )
    logger.info("Connecting to: %s", url)
    return create_engine(url, future=True)


def _existing_tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).fetchall()
    return {r[0] for r in rows}


def _alembic_version(engine: Engine) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


def apply_missing(engine: Engine) -> tuple[list[str], list[str]]:
    """Create tables that don't yet exist.

    Returns (created, skipped) table-name lists.
    """
    existing = _existing_tables(engine)
    created: list[str] = []
    skipped: list[str] = []
    with engine.begin() as conn:
        for name in ("research_note", "sentiment_data", "ai_chat_session", "ai_chat_message"):
            if name in existing:
                logger.info("SKIP   %s (already exists)", name)
                skipped.append(name)
                continue
            logger.info("CREATE %s", name)
            conn.execute(text(TABLE_DDL[name]))
            created.append(name)
    return created, skipped


def verify(engine: Engine, expected: Iterable[str]) -> list[str]:
    existing = _existing_tables(engine)
    missing = [t for t in expected if t not in existing]
    return missing


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    engine = _engine()

    pre_alembic = _alembic_version(engine)
    logger.info("Current alembic_version (read-only): %s", pre_alembic)

    created, skipped = apply_missing(engine)
    logger.info("Created: %s", created)
    logger.info("Skipped: %s", skipped)

    missing_after = verify(
        engine,
        ["research_note", "sentiment_data", "ai_chat_session", "ai_chat_message"],
    )
    if missing_after:
        logger.error("Verification FAILED — still missing: %s", missing_after)
        return 1

    post_alembic = _alembic_version(engine)
    if post_alembic != pre_alembic:
        logger.error(
            "alembbic_version changed unexpectedly: %s -> %s",
            pre_alembic,
            post_alembic,
        )
        return 2

    logger.info(
        "OK — 4 AI research tables verified; alembic_version still %s (untouched).",
        post_alembic,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())