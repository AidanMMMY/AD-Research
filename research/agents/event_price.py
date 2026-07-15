"""Historical event & price impact analyzer.

Reads existing instrument_daily_bar and major index moves from the DB,
then links them to known policy/event dates for exploratory analysis.
"""

import json
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

from research.agents.base import save_raw, save_note

logger = logging.getLogger("research.agents.event_price")


def _get_db_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.environ.get("SQLALCHEMY_DATABASE_URI"):
        return os.environ["SQLALCHEMY_DATABASE_URI"]
    # Compose from standard env vars used by the platform.
    user = os.environ.get("POSTGRES_USER", "etf")
    password = os.environ.get("POSTGRES_PASSWORD", "etf")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "ad_research")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _serialize(obj):
    """JSON helper that converts date/Decimal to serializable types."""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def run_event_price_agent(data_dir: str, agent_name: str = "event_price") -> None:
    logging.basicConfig(level=logging.INFO)
    root = Path(data_dir)
    logger.info("Starting %s agent", agent_name)

    db_url = _get_db_url()
    engine = create_engine(db_url)

    results = {}
    with engine.connect() as conn:
        # Largest single-day moves in the last 90 days
        rows = conn.execute(text("""
            SELECT b.etf_code, i.name, b.trade_date, b.change_pct
            FROM instrument_daily_bar b
            JOIN etf_info i ON b.etf_code = i.code
            WHERE b.trade_date >= CURRENT_DATE - INTERVAL '90 days'
              AND ABS(b.change_pct) > 9.5
            ORDER BY ABS(b.change_pct) DESC
            LIMIT 50
        """)).mappings().all()
        results["extreme_moves_90d"] = [dict(r) for r in rows]

        # Index-level moves
        idx_rows = conn.execute(text("""
            SELECT b.etf_code, b.trade_date, b.close, b.change_pct
            FROM instrument_daily_bar b
            WHERE b.etf_code IN ('000001.SH', '399001.SZ', '399006.SZ')
              AND b.trade_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY b.trade_date DESC, b.etf_code
            LIMIT 100
        """)).mappings().all()
        results["index_moves_30d"] = [dict(r) for r in idx_rows]

    save_raw(root, agent_name, "event_price_stats", results, default=_serialize)

    note_parts = ["## 近90日异动（|涨跌幅|>9.5%）\n"]
    for r in results["extreme_moves_90d"][:20]:
        note_parts.append(
            f"- {r['trade_date']} {r['etf_code']} ({r['name']}): {r['change_pct']}%"
        )
    if results["index_moves_30d"]:
        note_parts.append("\n## 近30日主要指数\n")
        for r in results["index_moves_30d"][:20]:
            note_parts.append(
                f"- {r['trade_date']} {r['etf_code']}: {r['close']} ({r['change_pct']}%)"
            )
    save_note(root, agent_name, "事件-价格异动观察", "\n".join(note_parts))

    logger.info("%s agent finished", agent_name)
