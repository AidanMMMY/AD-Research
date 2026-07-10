"""上市公司信息披露路由发现与验证。

该模块提供：
1. ``build_seed_routes`` — 基于 etf_info 构建交易所 + 巨潮 URL 种子数据
2. ``discover_company_ir`` — 利用 web search 发现公司官网 IR 页面
3. ``verify_route`` — 轻量验证已知 URL 是否仍有效
4. ``upsert_batch`` — 批量写入/更新路由记录
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.models.disclosure_route import CompanyDisclosureRoute

logger = logging.getLogger(__name__)

# ── 交易所代码 → 公告列表页 URL 模板 ──────────────────────────
# SSE：60xxxx → 上交所
# SZSE：00xxxx / 30xxxx → 深交所
# BSE：83xxxx / 87xxxx / 88xxxx / 92xxxx → 北交所

SSE_DISCLOSURE = (
    "https://www.sse.com.cn/assortment/stock/list/info/announcement/"
    "index.shtml?COMPANY_CODE={code}"
)
SZSE_DISCLOSURE = (
    "https://www.szse.cn/certificate/individual/index.html?code={code}"
)
CNINFO_DISCLOSURE = (
    "https://www.cninfo.com.cn/new/disclosure/stock?stockCode={code}&orgId={org_id}"
)


def _exchange_for(code: str) -> str | None:
    """根据 A 股代码推断交易所。"""
    if code.startswith("60"):
        return "SSE"
    if code.startswith(("00", "30")):
        return "SZSE"
    if code.startswith(("83", "87", "88", "92", "43", "4")):
        return "BSE"
    if code.startswith("68"):
        return "SSE"  # 科创板
    return None


def build_seed_routes(db: Session, *, dry_run: bool = False) -> int:
    """从 etf_info 中提取全量 A 股个股，生成交易所+巨潮种子路由。

    返回写入的记录数。
    """
    rows = db.execute(
        select(
            ETFInfo.code,
            ETFInfo.name,
            ETFInfo.exchange,
            ETFInfo.market_cap,
        ).where(
            ETFInfo.instrument_type == "STOCK",
            ETFInfo.market == "A股",
            ETFInfo.status == "active",
        )
    ).all()

    if not rows:
        logger.warning("build_seed_routes: 未找到 A 股个股记录")
        return 0

    records: list[dict] = []
    for r in rows:
        raw_code = r.code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        exchange = _exchange_for(raw_code)
        if not exchange:
            continue

        rec = {
            "code": raw_code,
            "name": r.name,
            "exchange_code": exchange,
            "sse_disclosure_url": SSE_DISCLOSURE.format(code=raw_code) if exchange == "SSE" else None,
            "szse_disclosure_url": SZSE_DISCLOSURE.format(code=raw_code) if exchange == "SZSE" else None,
            "cninfo_disclosure_url": None,  # 需要 orgId，由后续 pass 填充
            "ir_website_url": None,
            "ir_discovery_method": None,
            "last_verified_at": None,
            "verification_status": "pending",
            "verification_notes": "seed — 待验证",
            "market_cap_rank": None,
        }
        records.append(rec)

    if dry_run:
        logger.info("build_seed_routes[dry_run]: 将写入 %d 条记录", len(records))
        return len(records)

    return upsert_batch(db, records)


def upsert_batch(db: Session, records: list[dict]) -> int:
    """批量 UPSERT 路由记录。

    返回成功写入的记录数。
    """
    if not records:
        return 0

    stmt = insert(CompanyDisclosureRoute).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "exchange_code": stmt.excluded.exchange_code,
            "sse_disclosure_url": stmt.excluded.sse_disclosure_url,
            "szse_disclosure_url": stmt.excluded.szse_disclosure_url,
            "cninfo_disclosure_url": stmt.excluded.cninfo_disclosure_url,
            "ir_website_url": stmt.excluded.ir_website_url,
            "ir_discovery_method": stmt.excluded.ir_discovery_method,
            "last_verified_at": stmt.excluded.last_verified_at,
            "verification_status": stmt.excluded.verification_status,
            "verification_notes": stmt.excluded.verification_notes,
            "market_cap_rank": stmt.excluded.market_cap_rank,
            "updated_at": func.now(),
        },
    )

    db.execute(stmt)
    db.commit()
    logger.info("upsert_batch: %d 条记录已写入", len(records))
    return len(records)


def update_ir_url(
    db: Session,
    code: str,
    ir_url: str,
    method: str = "web_search",
) -> None:
    """更新单条记录的公司 IR 页面 URL。"""
    db.execute(
        insert(CompanyDisclosureRoute).values(
            code=code,
            name="",
            exchange_code="SSE",
            ir_website_url=ir_url,
            ir_discovery_method=method,
            verification_status="verified",
            last_verified_at=datetime.now(timezone.utc),
            verification_notes="agent 发现",
        ).on_conflict_do_update(
            index_elements=["code"],
            set_={
                "ir_website_url": ir_url,
                "ir_discovery_method": method,
                "verification_status": "verified",
                "last_verified_at": datetime.now(timezone.utc),
                "verification_notes": "agent 发现",
            },
        )
    )
    db.commit()


def update_verification(
    db: Session,
    code: str,
    status: str,
    notes: str = "",
) -> None:
    """更新单条记录的验证状态。"""
    db.execute(
        insert(CompanyDisclosureRoute).values(
            code=code,
            name="",
            exchange_code="SSE",
            verification_status=status,
            last_verified_at=datetime.now(timezone.utc),
            verification_notes=notes,
        ).on_conflict_do_update(
            index_elements=["code"],
            set_={
                "verification_status": status,
                "last_verified_at": datetime.now(timezone.utc),
                "verification_notes": notes,
            },
        )
    )
    db.commit()


def get_pending_batch(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """获取待发现 IR 页面的公司列表（优先市值最大的）。

    返回 [{code, name, exchange_code, ...}, ...]
    """
    rows = db.execute(
        select(CompanyDisclosureRoute)
        .where(CompanyDisclosureRoute.ir_website_url.is_(None))
        .order_by(CompanyDisclosureRoute.market_cap_rank.asc().nullslast())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [
        {
            "code": r.code,
            "name": r.name,
            "exchange_code": r.exchange_code,
        }
        for r in rows
    ]


def stats(db: Session) -> dict:
    """返回路由知识库的统计信息。"""
    from sqlalchemy import func as f

    total = db.scalar(select(f.count(CompanyDisclosureRoute.id)))
    with_ir = db.scalar(
        select(f.count(CompanyDisclosureRoute.id)).where(
            CompanyDisclosureRoute.ir_website_url.isnot(None)
        )
    )
    verified = db.scalar(
        select(f.count(CompanyDisclosureRoute.id)).where(
            CompanyDisclosureRoute.verification_status == "verified"
        )
    )

    return {
        "total": total or 0,
        "with_ir_url": with_ir or 0,
        "verified": verified or 0,
        "ir_coverage_pct": round((with_ir or 0) / (total or 1) * 100, 1),
    }
