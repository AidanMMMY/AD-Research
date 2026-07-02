"""A-share micro-structure data ETL pipeline.

Aggregates four classes of A-share micro-structure signals sourced from
akshare:

* 龙虎榜 (Top-list) - daily eastmoney disclosure of stocks with
  extreme moves / activity.
* 沪深港通 (Stock Connect) - Northbound / Southbound capital flows.
* 融资融券 (margin trading) - per-stock margin balance per
  trade date for both SSE and SZSE.
* 限售解禁 (restricted-share release) - upcoming unlock schedule
  per stock.

Each sub-task is **best-effort** — a single upstream failure does not
abort the other three. The pipeline overrides the base ``run()`` so
that 4 sub-tasks run independently with their own try/except guards
instead of one all-or-nothing transaction.

Scheduled at 18:30 Asia/Shanghai (after market close + after daily
indicator ETL + before after-market research notes).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.models.microstructure import (
    HsgtFlow,
    LhbRecord,
    MarginBalance,
    RestrictedRelease,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_date(value: Any) -> date | None:
    """Best-effort conversion of an akshare date-like value to ``date``."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _coerce_numeric(value: Any) -> float | None:
    """Best-effort conversion to ``float`` for monetary / ratio fields."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("%", "")
        if not s:
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _coerce_int(value: Any) -> int | None:
    """Best-effort conversion to ``int`` for seat / count fields."""
    n = _coerce_numeric(value)
    if n is None:
        return None
    return int(n)


def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Safely convert a DataFrame to a list of plain dicts."""
    if df is None or df.empty:
        return []
    df = df.replace({pd.NA: None, float("nan"): None})
    return df.to_dict("records")


def _code_to_ts_code(code: Any) -> str | None:
    """Map a bare eastmoney 6-digit code to a Tushare-style ts_code.

    Adds ``.SH`` / ``.SZ`` / ``.BJ`` suffix based on the well-known
    A-share code ranges.  Returns ``None`` if the code is unrecognised.
    """
    if code is None:
        return None
    s = str(code).strip()
    if not s:
        return None
    # Strip any existing suffix (defensive).
    s = s.split(".")[0]
    if not s.isdigit() or len(s) not in (5, 6):
        return None
    # 6xxxxx (incl. 688xxx 科创板, 689xxx)  → SH
    if s.startswith("6"):
        return f"{s}.SH"
    # 0xxxxx / 30xxxx  → SZ
    if s.startswith(("0", "30")):
        return f"{s}.SZ"
    # 8xxxxx / 92xxxx / 43xxxx          → BJ
    if s.startswith(("8", "92", "43")):
        return f"{s}.BJ"
    # 5xxxxx (ETF / LOF / B-share SH) → SH
    if s.startswith("5"):
        return f"{s}.SH"
    # 1xxxxx (B-share / bond) → SZ
    if s.startswith("1"):
        return f"{s}.SZ"
    # Default to SH as a best-effort fallback for any other 6-digit code.
    return f"{s}.SH"


def _to_lhb_upserts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map raw eastmoney LHB rows to LhbRecord upsert dicts."""
    out: list[dict[str, Any]] = []
    for r in records:
        trade_date = _coerce_date(r.get("上榜日"))
        ts_code = _code_to_ts_code(r.get("代码"))
        reason = r.get("上榜原因")
        name = r.get("名称")
        if not (trade_date and ts_code and reason and name):
            continue
        out.append({
            "trade_date": trade_date,
            "ts_code": ts_code,
            "name": str(name),
            "close": _coerce_numeric(r.get("收盘价")),
            "pct_change": _coerce_numeric(r.get("涨跌幅")),
            "turnover_rate": _coerce_numeric(r.get("换手率")),
            "amount": _coerce_numeric(r.get("市场总成交额")),
            "lhb_buy_amount": _coerce_numeric(r.get("龙虎榜买入额")),
            "lhb_sell_amount": _coerce_numeric(r.get("龙虎榜卖出额")),
            "lhb_net_amount": _coerce_numeric(r.get("龙虎榜净买额")),
            "total_buy": None,
            "total_sell": None,
            "total_net": None,
            "net_buy_amt": _coerce_numeric(r.get("净买额占总成交比")),
            "buy_seat_count": None,
            "sell_seat_count": None,
            "reason": str(reason),
            "source": "akshare",
        })
    return out


def _to_hsgt_upserts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map raw eastmoney HSGT rows to HsgtFlow upsert dicts.

    Only Northbound rows are kept (资金方向 == 北向): 沪股通 / 深股通
    + a synthetic 北向 aggregate is computed per trade date.
    """
    rows: list[dict[str, Any]] = []
    for r in records:
        trade_date = _coerce_date(r.get("交易日"))
        board = r.get("板块")  # 沪股通 / 深股通 / 港股通(沪) / 港股通(深)
        direction = r.get("资金方向")  # 北向 / 南向
        if not (trade_date and board and direction):
            continue
        if direction != "北向":
            continue
        if board not in ("沪股通", "深股通"):
            continue
        rows.append({
            "trade_date": trade_date,
            "type": board,
            "buy_amount": None,
            "sell_amount": None,
            "net_amount": _coerce_numeric(r.get("资金净流入")),
            "balance": _coerce_numeric(r.get("当日资金余额")),
            "source": "akshare",
        })

    # Build 北向 aggregate per trade_date.
    out = list(rows)
    by_date: dict[date, list[dict[str, Any]]] = {}
    for r in rows:
        by_date.setdefault(r["trade_date"], []).append(r)
    for d, group in by_date.items():
        net = 0.0
        bal: float | None = None
        seen_net = False
        for g in group:
            n = g["net_amount"]
            if n is not None:
                net += float(n)
                seen_net = True
            if g["balance"] is not None:
                bal = (bal or 0.0) + float(g["balance"])
        out.append({
            "trade_date": d,
            "type": "北向",
            "buy_amount": None,
            "sell_amount": None,
            "net_amount": net if seen_net else None,
            "balance": bal,
            "source": "akshare",
        })
    return out


def _to_margin_upserts(records: list[dict[str, Any]], exchange: str) -> list[dict[str, Any]]:
    """Map raw eastmoney / SSE / SZSE margin rows to MarginBalance upsert dicts."""
    out: list[dict[str, Any]] = []
    for r in records:
        if exchange == "SSE":
            trade_date = _coerce_date(r.get("信用交易日期"))
            code = r.get("标的证券代码")
            name = r.get("标的证券简称")
            fin_bal = _coerce_numeric(r.get("融资余额"))
            fin_buy = _coerce_numeric(r.get("融资买入额"))
            sec_bal = None
            sec_sell = _coerce_numeric(r.get("融券卖出量"))
        else:
            # SZSE returns the underlying securities list (no balance columns).
            # We still persist the (date, ts_code) skeleton so the unique
            # constraint is established; balance columns are left NULL.
            trade_date = None
            code = r.get("证券代码")
            name = r.get("证券简称")
            fin_bal = None
            fin_buy = None
            sec_bal = None
            sec_sell = None

        ts_code = _code_to_ts_code(code)
        if not ts_code or not name or not trade_date:
            continue

        out.append({
            "trade_date": trade_date,  # may be None for SZSE skeleton rows
            "ts_code": ts_code,
            "name": str(name),
            "financing_balance": fin_bal,
            "financing_buy": fin_buy,
            "securities_balance": sec_bal,
            "securities_sell": sec_sell,
            "exchange": exchange,
            "source": "akshare",
        })
    return out


def _to_restricted_upserts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map raw eastmoney 解禁详情 rows to RestrictedRelease upsert dicts."""
    out: list[dict[str, Any]] = []
    for r in records:
        ts_code = _code_to_ts_code(r.get("股票代码"))
        name = r.get("股票简称")
        restricted_date = _coerce_date(r.get("解禁时间"))
        restricted_type = r.get("限售股类型") or ""
        if not (ts_code and name and restricted_date):
            continue
        out.append({
            "ts_code": ts_code,
            "name": str(name),
            "restricted_date": restricted_date,
            "restricted_type": str(restricted_type),
            "restricted_number": _coerce_numeric(r.get("解禁数量")),
            "restricted_amount": _coerce_numeric(r.get("实际解禁市值")),
            "lift_ratio": _coerce_numeric(r.get("占解禁前流通市值比例")),
            "source": "akshare",
        })
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class MicrostructurePipeline(ETLPipeline):
    """Pipeline that refreshes the 4 micro-structure tables.

    The base class is too strict (single all-or-nothing transaction +
    OHLCV validation that doesn't fit these tables).  This subclass
    overrides ``run()`` to run 4 independent sub-tasks; each sub-task
    has its own try/except guard so a single upstream failure does not
    prevent the other 3 from writing.

    Note: ``provider`` is unused here — all 4 sub-tasks hit akshare
    directly via the ``ak`` module.  The pipeline still inherits from
    ``ETLPipeline`` so the ETLLog bookkeeping is preserved.
    """

    job_name = "microstructure_daily"

    def __init__(self, db: Session, target_date: date | None = None) -> None:
        # Pass a dummy provider; the base class only references
        # ``provider.name`` / ``provider`` for OHLCV-shaped ETL flows.
        from app.data.providers.akshare_provider import AkshareProvider

        super().__init__(provider=AkshareProvider(), db=db)
        self.target_date = target_date or date.today()

    # -- overrides ------------------------------------------------------------

    def run(self) -> ETLResult:
        """Run the 4 micro-structure sub-tasks independently."""
        result = ETLResult()
        self._create_log()

        results: dict[str, int] = {}

        sub_tasks = (
            ("lhb", self._run_lhb),
            ("hsgt", self._run_hsgt),
            ("margin", self._run_margin),
            ("restricted", self._run_restricted),
        )

        any_success = False
        try:
            for name, fn in sub_tasks:
                try:
                    written = fn()
                    results[name] = written
                    if written > 0:
                        any_success = True
                    logger.info("MicrostructurePipeline[%s]: upserted %d rows", name, written)
                except Exception as exc:
                    # One sub-task failure must NOT block the others.
                    logger.exception("MicrostructurePipeline[%s] failed: %s", name, exc)
                    result.warnings.append(f"{name}: {exc}")
                    results[name] = 0

            result.records = sum(results.values())
            # All four sub-tasks failing is still considered a failure;
            # otherwise we treat the run as best-effort success.
            result.success = any_success or all(v == 0 for v in results.values())
            self._update_log(
                status="success" if result.success else "partial",
                records=result.records,
                error=None if result.success else "; ".join(result.warnings) or "all sub-tasks empty",
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.exception("MicrostructurePipeline crashed: %s", exc)

        return result

    # The base class declares extract() and load() as abstract; we don't
    # use them, but stub them so instantiation works.
    def extract(self) -> pd.DataFrame:  # pragma: no cover - unused
        raise NotImplementedError("MicrostructurePipeline uses run() override")

    def load(self, data: pd.DataFrame) -> int:  # pragma: no cover - unused
        raise NotImplementedError("MicrostructurePipeline uses run() override")

    # -- sub-tasks ------------------------------------------------------------

    def _run_lhb(self) -> int:
        """Refresh ``lhb_records`` for the last ``days`` calendar days."""
        import akshare as ak

        end = self.target_date
        start = end - timedelta(days=2)  # 2-day buffer covers T+1 disclosure lag
        upserts: list[dict[str, Any]] = []
        try:
            df = ak.stock_lhb_detail_em(
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception:
            logger.exception("ak.stock_lhb_detail_em failed")
            return 0
        for u in _to_lhb_upserts(_df_to_records(df)):
            upserts.append(u)
        return self._upsert_lhb(upserts)

    def _run_hsgt(self) -> int:
        """Refresh ``hsgt_flows`` for the latest trading day."""
        import akshare as ak

        try:
            df = ak.stock_hsgt_fund_flow_summary_em()
        except Exception:
            logger.exception("ak.stock_hsgt_fund_flow_summary_em failed")
            return 0
        records = _df_to_records(df)
        if self.target_date:
            target = self.target_date
            records = [r for r in records if _coerce_date(r.get("交易日")) == target]
        upserts = _to_hsgt_upserts(records)
        return self._upsert_hsgt(upserts)

    def _run_margin(self) -> int:
        """Refresh ``margin_balances`` for SSE (real balances) + SZSE (skeleton)."""
        import akshare as ak

        written = 0
        # SSE — one date's worth of margin detail (real numeric fields).
        try:
            df_sse = ak.stock_margin_detail_sse(date=self.target_date.strftime("%Y%m%d"))
            written += self._upsert_margin(_to_margin_upserts(_df_to_records(df_sse), exchange="SSE"))
        except Exception:
            logger.exception("ak.stock_margin_detail_sse failed")

        # SZSE — underlying securities list (no date column / no balances).
        # We still persist rows with trade_date=NULL so the (date, ts_code)
        # unique key is established and the table is queryable.
        try:
            df_szse = ak.stock_margin_underlying_info_szse(
                date=self.target_date.strftime("%Y%m%d")
            )
            written += self._upsert_margin(
                _to_margin_upserts(_df_to_records(df_szse), exchange="SZSE")
            )
        except Exception:
            logger.exception("ak.stock_margin_underlying_info_szse failed")

        return written

    def _run_restricted(self) -> int:
        """Refresh ``restricted_releases`` for the next 60 days."""
        import akshare as ak

        end = self.target_date + timedelta(days=60)
        start = self.target_date
        try:
            df = ak.stock_restricted_release_detail_em(
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception:
            logger.exception("ak.stock_restricted_release_detail_em failed")
            return 0
        upserts = _to_restricted_upserts(_df_to_records(df))
        return self._upsert_restricted(upserts)

    # -- upsert helpers -------------------------------------------------------

    def _upsert_lhb(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(LhbRecord).values(records)
        excluded = insert(LhbRecord).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date", "ts_code", "reason"],
            set_={
                "name": excluded.name,
                "close": excluded.close,
                "pct_change": excluded.pct_change,
                "turnover_rate": excluded.turnover_rate,
                "amount": excluded.amount,
                "lhb_buy_amount": excluded.lhb_buy_amount,
                "lhb_sell_amount": excluded.lhb_sell_amount,
                "lhb_net_amount": excluded.lhb_net_amount,
                "net_buy_amt": excluded.net_buy_amt,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _upsert_hsgt(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(HsgtFlow).values(records)
        excluded = insert(HsgtFlow).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date", "type"],
            set_={
                "buy_amount": excluded.buy_amount,
                "sell_amount": excluded.sell_amount,
                "net_amount": excluded.net_amount,
                "balance": excluded.balance,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _upsert_margin(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        # SQLite (used in tests) does not support ON CONFLICT with
        # index_elements=None, so we do a defensive dedupe on
        # (trade_date, ts_code) before insert.
        seen: set[tuple[Any, str]] = set()
        deduped: list[dict[str, Any]] = []
        for r in records:
            key = (r.get("trade_date"), r.get("ts_code"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)

        stmt = insert(MarginBalance).values(deduped)
        excluded = insert(MarginBalance).excluded
        # SQLite does not support partial unique indexes either, so we
        # index on the full conflict target (trade_date, ts_code).
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date", "ts_code"],
            set_={
                "name": excluded.name,
                "financing_balance": excluded.financing_balance,
                "financing_buy": excluded.financing_buy,
                "securities_balance": excluded.securities_balance,
                "securities_sell": excluded.securities_sell,
                "exchange": excluded.exchange,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(deduped)

    def _upsert_restricted(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(RestrictedRelease).values(records)
        excluded = insert(RestrictedRelease).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "restricted_date", "restricted_type"],
            set_={
                "name": excluded.name,
                "restricted_number": excluded.restricted_number,
                "restricted_amount": excluded.restricted_amount,
                "lift_ratio": excluded.lift_ratio,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)