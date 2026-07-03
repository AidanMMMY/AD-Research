"""Service layer for futures contracts and daily bars.

Provides helpers that wrap the FuturesContract and FuturesDailyBar
ORM models behind the schemas consumed by the API layer. The heavy
ETL work is in ``app.data.pipelines.futures`` - this module is for
on-demand lookups used by the API.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.futures import (
    EXCHANGE_LABELS,
    PRODUCT_LABELS,
    FuturesContract,
    FuturesDailyBar,
)
from app.schemas.futures import (
    FuturesContractOut,
    FuturesDailyBarOut,
    FuturesDashboardResponse,
    FuturesDashboardSection,
    FuturesFilterParams,
    FuturesLeaderboardResponse,
    FuturesLeaderboardRow,
)

logger = logging.getLogger(__name__)


def _exchange_label(exchange: str | None) -> str | None:
    if not exchange:
        return None
    return EXCHANGE_LABELS.get(exchange, exchange)


def _product_label(product: str | None) -> str | None:
    if not product:
        return None
    return PRODUCT_LABELS.get(product, product)


def _contract_to_out(contract: FuturesContract) -> FuturesContractOut:
    return FuturesContractOut(
        code=contract.code,
        name=contract.name,
        exchange=contract.exchange,
        exchange_label=_exchange_label(contract.exchange),
        product=contract.product,
        underlying_instrument=contract.underlying_instrument,
        contract_size=contract.contract_size,
        price_unit=contract.price_unit,
        quote_unit=contract.quote_unit,
        is_main=bool(contract.is_main),
        list_date=contract.list_date,
        delist_date=contract.delist_date,
        last_seen_at=contract.last_seen_at,
    )


def _bar_to_out(bar: FuturesDailyBar, code: str | None = None, name: str | None = None) -> FuturesDailyBarOut:
    settle_change: float | None = None
    if bar.settle is not None and bar.pre_settle not in (None, 0):
        try:
            settle_change = (
                (float(bar.settle) - float(bar.pre_settle)) / float(bar.pre_settle)
            ) * 100.0
        except Exception:
            settle_change = None

    close_change: float | None = None
    # ``pre_close`` is not stored separately; for futures the canonical
    # daily percentage move is settle vs pre-settle. Reuse that value so
    # the frontend ``change_pct`` field is populated.
    if settle_change is not None:
        close_change = settle_change

    return FuturesDailyBarOut(
        code=code or bar.code,
        name=name,
        trade_date=bar.trade_date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        settle=bar.settle,
        pre_settle=bar.pre_settle,
        volume=bar.volume,
        open_interest=bar.open_interest,
        turnover=bar.turnover,
        warehouse_receipts=bar.warehouse_receipts,
        settle_change_pct=settle_change,
        change_pct=close_change,
    )


class FuturesService:
    """Read-only helpers for futures contracts and daily bars."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Contracts
    # ------------------------------------------------------------------

    def list_contracts(
        self, params: FuturesFilterParams
    ) -> tuple[list[FuturesContractOut], int]:
        """Paginated list of futures contracts."""
        stmt = select(FuturesContract)
        count_stmt = select(func.count(FuturesContract.id))

        conditions: list[Any] = []
        if params.exchange:
            conditions.append(FuturesContract.exchange == params.exchange.upper())
        if params.product:
            conditions.append(FuturesContract.product == params.product)
        if params.is_main is not None:
            conditions.append(FuturesContract.is_main == params.is_main)
        if params.search:
            like = f"%{params.search}%"
            conditions.append(
                or_(
                    FuturesContract.code.ilike(like),
                    FuturesContract.name.ilike(like),
                )
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = count_stmt.where(and_(*conditions))

        total = self.db.execute(count_stmt).scalar() or 0

        offset = (params.page - 1) * params.page_size
        stmt = (
            stmt.order_by(FuturesContract.exchange, FuturesContract.product, FuturesContract.code)
            .offset(offset)
            .limit(params.page_size)
        )
        rows = self.db.execute(stmt).scalars().all()
        return [_contract_to_out(r) for r in rows], int(total)

    def get_contract(self, code: str) -> FuturesContract | None:
        return self.db.query(FuturesContract).filter(FuturesContract.code == code).first()

    def upsert_contracts(self, records: list[dict[str, Any]]) -> int:
        """Insert or update contract rows from a list of dicts.

        Each dict should have at least: code, name, exchange, product,
        and optionally underlying_instrument, is_main.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not records:
            return 0

        # Build a copy without the SQLAlchemy ORM fields
        cleaned: list[dict[str, Any]] = []
        for r in records:
            cleaned.append(
                {
                    "code": r["code"],
                    "name": r["name"],
                    "exchange": r["exchange"],
                    "product": r["product"],
                    "is_main": r.get("is_main", True),
                    "underlying_instrument": r.get("underlying_instrument"),
                    "contract_size": r.get("contract_size"),
                    "price_unit": r.get("price_unit"),
                    "quote_unit": r.get("quote_unit"),
                    "list_date": r.get("list_date"),
                    "delist_date": r.get("delist_date"),
                    "source": r.get("source", "akshare"),
                    "last_seen_at": datetime.now(timezone.utc),
                }
            )

        stmt = pg_insert(FuturesContract).values(cleaned)
        update_cols = {
            "name": stmt.excluded.name,
            "exchange": stmt.excluded.exchange,
            "product": stmt.excluded.product,
            "is_main": stmt.excluded.is_main,
            "underlying_instrument": stmt.excluded.underlying_instrument,
            "contract_size": stmt.excluded.contract_size,
            "price_unit": stmt.excluded.price_unit,
            "quote_unit": stmt.excluded.quote_unit,
            "list_date": stmt.excluded.list_date,
            "delist_date": stmt.excluded.delist_date,
            "source": stmt.excluded.source,
            "last_seen_at": stmt.excluded.last_seen_at,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"], set_=update_cols
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(cleaned)

    # ------------------------------------------------------------------
    # Daily bars
    # ------------------------------------------------------------------

    def get_daily_bars(
        self,
        code: str | None,
        start: date | None = None,
        end: date | None = None,
        limit: int = 365,
    ) -> list[FuturesDailyBar]:
        stmt = select(FuturesDailyBar)
        conditions: list[Any] = []
        if code:
            conditions.append(FuturesDailyBar.code == code)
        if start:
            conditions.append(FuturesDailyBar.trade_date >= start)
        if end:
            conditions.append(FuturesDailyBar.trade_date <= end)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = (
            stmt.order_by(desc(FuturesDailyBar.trade_date))
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_bar(self, code: str) -> FuturesDailyBar | None:
        return (
            self.db.query(FuturesDailyBar)
            .filter(FuturesDailyBar.code == code)
            .order_by(desc(FuturesDailyBar.trade_date))
            .first()
        )

    def get_latest_bars_for_codes(
        self, codes: list[str]
    ) -> dict[str, FuturesDailyBar]:
        """Latest bar per code in a single pass.

        Returns a dict keyed by code. Codes with no data are omitted.
        """
        if not codes:
            return {}

        # Sub-select to get per-code max trade_date
        subq = (
            select(
                FuturesDailyBar.code,
                func.max(FuturesDailyBar.trade_date).label("max_date"),
            )
            .where(FuturesDailyBar.code.in_(codes))
            .group_by(FuturesDailyBar.code)
            .subquery()
        )

        stmt = select(FuturesDailyBar).join(
            subq,
            and_(
                FuturesDailyBar.code == subq.c.code,
                FuturesDailyBar.trade_date == subq.c.max_date,
            ),
        )
        rows = self.db.execute(stmt).scalars().all()
        return {row.code: row for row in rows}

    def upsert_daily_bars(self, records: list[dict[str, Any]]) -> int:
        """Upsert daily bars keyed on (code, trade_date)."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not records:
            return 0

        cleaned: list[dict[str, Any]] = []
        for r in records:
            cleaned.append(
                {
                    "code": r["code"],
                    "trade_date": r["trade_date"],
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "close": r.get("close"),
                    "settle": r.get("settle"),
                    "pre_settle": r.get("pre_settle"),
                    "volume": r.get("volume"),
                    "open_interest": r.get("open_interest"),
                    "turnover": r.get("turnover"),
                    "warehouse_receipts": r.get("warehouse_receipts"),
                    "source": r.get("source", "akshare"),
                }
            )

        stmt = pg_insert(FuturesDailyBar).values(cleaned)
        update_cols = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "settle": stmt.excluded.settle,
            "pre_settle": stmt.excluded.pre_settle,
            "volume": stmt.excluded.volume,
            "open_interest": stmt.excluded.open_interest,
            "turnover": stmt.excluded.turnover,
            "warehouse_receipts": stmt.excluded.warehouse_receipts,
            "source": stmt.excluded.source,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["code", "trade_date"], set_=update_cols
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(cleaned)

    # ------------------------------------------------------------------
    # Dashboard / leaderboard
    # ------------------------------------------------------------------

    def build_dashboard(self) -> FuturesDashboardResponse:
        """Group latest-day bars by product category for the home page."""
        contracts = (
            self.db.query(FuturesContract)
            .filter(FuturesContract.is_main == True)  # noqa: E712
            .all()
        )
        codes = [c.code for c in contracts]
        if not codes:
            return FuturesDashboardResponse(sections=[], trade_date=None, total_contracts=0)

        contract_by_code = {c.code: c for c in contracts}
        latest_by_code = self.get_latest_bars_for_codes(codes)
        if not latest_by_code:
            return FuturesDashboardResponse(sections=[], trade_date=None, total_contracts=len(codes))

        # Determine most-recent trade date across all latest bars
        trade_date = max(b.trade_date for b in latest_by_code.values())

        # Filter to bars on the most-recent trade date
        today_bars = {
            code: bar for code, bar in latest_by_code.items() if bar.trade_date == trade_date
        }
        if not today_bars:
            # Fall back to whatever was the latest available
            today_bars = latest_by_code

        sections: list[FuturesDashboardSection] = []
        from app.models.futures import PROD_AGRI, PROD_ENERGY, PROD_FINANCIAL, PROD_METAL

        for product_key in [PROD_METAL, PROD_ENERGY, PROD_AGRI, PROD_FINANCIAL]:
            items: list[FuturesDailyBarOut] = []
            for code, bar in today_bars.items():
                contract = contract_by_code.get(code)
                if not contract or contract.product != product_key:
                    continue
                items.append(_bar_to_out(bar, code=code, name=contract.name))

            if not items:
                continue

            # Sort by settle_change_pct desc to find best/worst
            ranked = sorted(
                items,
                key=lambda x: (x.settle_change_pct is None, -(x.settle_change_pct or 0.0)),
            )
            best = next(
                (it for it in ranked if it.settle_change_pct is not None),
                ranked[0] if ranked else None,
            )
            worst = next(
                (
                    it
                    for it in reversed(ranked)
                    if it.settle_change_pct is not None
                ),
                ranked[-1] if ranked else None,
            )
            sections.append(
                FuturesDashboardSection(
                    product=product_key,
                    product_label=_product_label(product_key),
                    items=items,
                    best_performer=best,
                    worst_performer=worst,
                    count=len(items),
                )
            )

        return FuturesDashboardResponse(
            sections=sections, trade_date=trade_date, total_contracts=len(contracts)
        )

    def build_leaderboard(
        self, exchange: str | None = None, direction: str = "gainers", top_n: int = 30
    ) -> FuturesLeaderboardResponse:
        """Sorted leaderboard by settle_change_pct for the latest trade date."""
        contracts_q = self.db.query(FuturesContract).filter(
            FuturesContract.is_main == True  # noqa: E712
        )
        if exchange:
            contracts_q = contracts_q.filter(FuturesContract.exchange == exchange.upper())
        contracts = contracts_q.all()
        if not contracts:
            return FuturesLeaderboardResponse(items=[], direction=direction, exchange=exchange)

        codes = [c.code for c in contracts]
        latest_by_code = self.get_latest_bars_for_codes(codes)
        if not latest_by_code:
            return FuturesLeaderboardResponse(items=[], direction=direction, exchange=exchange)

        trade_date = max(b.trade_date for b in latest_by_code.values())
        contract_by_code = {c.code: c for c in contracts}

        rows: list[FuturesLeaderboardRow] = []
        for code, bar in latest_by_code.items():
            contract = contract_by_code.get(code)
            if not contract:
                continue
            settle_change = None
            if bar.settle is not None and bar.pre_settle not in (None, 0):
                try:
                    settle_change = (
                        (float(bar.settle) - float(bar.pre_settle))
                        / float(bar.pre_settle)
                    ) * 100.0
                except Exception:
                    settle_change = None
            rows.append(
                FuturesLeaderboardRow(
                    code=code,
                    name=contract.name,
                    exchange=contract.exchange,
                    product=contract.product,
                    close=bar.close,
                    settle=bar.settle,
                    pre_settle=bar.pre_settle,
                    change_pct=settle_change,
                    volume=bar.volume,
                    open_interest=bar.open_interest,
                    turnover=bar.turnover,
                )
            )

        ranked = [r for r in rows if r.change_pct is not None]
        ranked.sort(key=lambda r: r.change_pct, reverse=(direction == "gainers"))
        top = ranked[:top_n]

        return FuturesLeaderboardResponse(
            items=top,
            direction=direction,
            exchange=(exchange.upper() if exchange else None),
            trade_date=trade_date,
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """High-level counts for diagnostics / ETL ops."""
        total_contracts = (
            self.db.query(func.count(FuturesContract.id))
            .filter(FuturesContract.is_main == True)  # noqa: E712
            .scalar()
            or 0
        )
        total_bars = self.db.query(func.count(FuturesDailyBar.id)).scalar() or 0
        latest_date = self.db.query(func.max(FuturesDailyBar.trade_date)).scalar()
        return {
            "total_contracts": int(total_contracts),
            "total_bars": int(total_bars),
            "latest_trade_date": latest_date.isoformat() if latest_date else None,
        }
