"""Futures daily ETL pipeline.

Fetches Chinese-domestic futures main contract metadata and daily bars
from akshare (Sina main contracts list + Sina/EM daily data) and
upserts them into the ``futures_contracts`` and ``futures_daily_bars``
tables.

The sina ``futures_main_sina(symbol="CU0")`` endpoint returns daily
OHLCV including settlement and open interest, which is what we need.
"""

import logging
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.base import DataProvider, ETFInfo, MarketHours
from app.models.futures import FuturesContract, FuturesDailyBar
from app.services.futures_service import FuturesService

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")


class _AkshareFuturesProvider(DataProvider):
    """Minimal DataProvider stub so futures pipelines fit the ETL base class.

    Futures data comes from akshare directly, not from a shared provider,
    but the base class still wants a provider for logging.
    """

    @property
    def name(self) -> str:
        return "akshare"

    def fetch_etf_list(self) -> list[ETFInfo]:
        return []

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        return pd.DataFrame()

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        return MarketHours()


# Number of concurrent workers when fetching daily bars for one contract per
# request. Sina throttles around 1 call/0.3s; with 3 workers we stay well
# inside that limit for 70+ contracts.
_MAX_WORKERS = 3

# Map sina exchange code -> our enum exchange code.
_SINA_EXCHANGE_MAP = {
    "shfe": "SHFE",
    "dce": "DCE",
    "czce": "CZCE",
    "cffex": "CFFEX",
    "ine": "INE",
    "gfex": "GFEX",
}

# Static product category per (exchange, symbol root). Built from a manual
# mapping of common Chinese commodity futures to keep the dashboard grouping
# deterministic instead of guessing from product names.
#
# Lookup order: exact symbol_root first, then exchange. Anything we don't
# recognise falls back to ``其他``.
_PRODUCT_MAP: dict[tuple[str, str], str] = {
    # ---- 上期所 (SHFE) ----
    ("SHFE", "CU"): "金属",
    ("SHFE", "AL"): "金属",
    ("SHFE", "ZN"): "金属",
    ("SHFE", "PB"): "金属",
    ("SHFE", "NI"): "金属",
    ("SHFE", "SN"): "金属",
    ("SHFE", "RB"): "金属",
    ("SHFE", "WR"): "金属",
    ("SHFE", "HC"): "金属",
    ("SHFE", "SS"): "金属",
    ("SHFE", "AU"): "金属",
    ("SHFE", "AG"): "金属",
    ("SHFE", "PT"): "金属",
    ("SHFE", "PD"): "金属",
    ("SHFE", "RU"): "能源化工",
    ("SHFE", "BU"): "能源化工",
    ("SHFE", "FU"): "能源化工",
    # ---- 大商所 (DCE) ----
    ("DCE", "I"): "能源化工",   # 铁矿石
    ("DCE", "J"): "能源化工",   # 焦炭
    ("DCE", "JM"): "能源化工",  # 焦煤
    ("DCE", "ZC"): "能源化工",  # 动力煤
    ("DCE", "M"): "农产品",     # 豆粕
    ("DCE", "Y"): "农产品",     # 豆油
    ("DCE", "A"): "农产品",     # 豆一
    ("DCE", "B"): "农产品",     # 豆二
    ("DCE", "P"): "农产品",     # 棕榈油
    ("DCE", "C"): "农产品",     # 玉米
    ("DCE", "CS"): "农产品",    # 玉米淀粉
    ("DCE", "JD"): "农产品",    # 鸡蛋
    ("DCE", "LH"): "农产品",    # 生猪
    ("DCE", "FB"): "农产品",    # 纤维板
    ("DCE", "BB"): "农产品",    # 胶合板
    ("DCE", "PP"): "能源化工",  # 聚丙烯
    ("DCE", "PVC"): "能源化工",  # PVC
    ("DCE", "L"): "能源化工",   # 塑料 (PE)
    ("DCE", "EG"): "能源化工",  # 乙二醇
    ("DCE", "EB"): "能源化工",  # 苯乙烯
    ("DCE", "V"): "能源化工",   # PVC (alt code)
    ("DCE", "RR"): "农产品",    # 粳米
    # ---- 郑商所 (CZCE) ----
    ("CZCE", "SR"): "农产品",   # 白糖
    ("CZCE", "CF"): "农产品",   # 棉花
    ("CZCE", "CY"): "农产品",   # 棉纱
    ("CZCE", "AP"): "农产品",   # 苹果
    ("CZCE", "CJ"): "农产品",   # 红枣
    ("CZCE", "PTA"): "能源化工",
    ("CZCE", "MA"): "能源化工",  # 甲醇
    ("CZCE", "FG"): "能源化工",  # 玻璃
    ("CZCE", "SA"): "能源化工",  # 纯碱
    ("CZCE", "UR"): "农产品",    # 尿素 (chemicals but CZCE groups with others)
    ("CZCE", "SH"): "能源化工",  # 烧碱
    ("CZCE", "SF"): "能源化工",  # 硅铁
    ("CZCE", "SM"): "能源化工",  # 锰硅
    ("CZCE", "RM"): "农产品",    # 菜粕
    ("CZCE", "OI"): "农产品",    # 菜油
    ("CZCE", "RS"): "农产品",    # 菜籽
    ("CZCE", "WH"): "农产品",    # 强麦
    ("CZCE", "PM"): "农产品",    # 普麦
    ("CZCE", "RI"): "农产品",    # 早籼稻
    ("CZCE", "LR"): "农产品",    # 晚籼稻
    ("CZCE", "JR"): "农产品",    # 粳稻
    ("CZCE", "TA"): "能源化工",  # PTA (alt code)
    ("CZCE", "ZC"): "能源化工",  # 动力煤 (alt)
    # ---- 中金所 (CFFEX) ----
    ("CFFEX", "IF"): "金融期货",
    ("CFFEX", "IH"): "金融期货",
    ("CFFEX", "IC"): "金融期货",
    ("CFFEX", "IM"): "金融期货",
    ("CFFEX", "T"): "金融期货",
    ("CFFEX", "TF"): "金融期货",
    ("CFFEX", "TS"): "金融期货",
    ("CFFEX", "TL"): "金融期货",
    # ---- 上海能源 (INE) ----
    ("INE", "SC"): "能源化工",  # 原油
    ("INE", "LU"): "能源化工",  # 低硫燃料油
    ("INE", "NR"): "能源化工",  # 20号胶
    ("INE", "BC"): "金属",      # 国际铜
    ("INE", "EC"): "金融期货",  # 集运指数 (often grouped under financial)
    # ---- 广期所 (GFEX) ----
    ("GFEX", "SI"): "金属",      # 工业硅
    ("GFEX", "LC"): "能源化工",  # 碳酸锂
}


def _classify_product(exchange: str, symbol_root: str) -> str:
    """Return one of 金属/能源化工/农产品/金融期货 for a given contract."""
    return _PRODUCT_MAP.get((exchange, symbol_root), "其他")


def _symbol_root(symbol: str) -> str:
    """Extract the alphabetic root from a continuous contract symbol like CU0/M0/IF0."""
    out = []
    for ch in symbol:
        if ch.isalpha():
            out.append(ch.upper())
        else:
            break
    return "".join(out)


def _coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


class FuturesContractDiscoveryPipeline(ETLPipeline):
    """Discovers main continuous contracts from sina via akshare.

    Calls ``ak.futures_display_main_sina()`` which returns a DataFrame
    of shape (82, 3) with columns [symbol, exchange, name]. Each row
    becomes a row in ``futures_contracts``.
    """

    job_name = "futures_contract_discovery"

    def __init__(self, db: Session) -> None:
        super().__init__(provider=_AkshareFuturesProvider(), db=db)

    def run(self) -> ETLResult:
        """Override base run() to skip OHLCV-specific validation.

        Discovery produces contract metadata, not price bars, so the
        standard four-layer validator does not apply.
        """
        result = ETLResult()
        self._create_log()

        try:
            data = self.extract()
            if data.empty:
                result.warnings.append("Extract returned empty DataFrame")

            loaded = self.load(data)
            result.records = loaded
            result.success = True
            self._update_log(status="success", records=loaded)
            logger.info(
                "FuturesContractDiscoveryPipeline: loaded %d contracts", loaded
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("FuturesContractDiscoveryPipeline failed: %s", error_msg)

        return result

    def extract(self) -> pd.DataFrame:
        try:
            df = ak.futures_display_main_sina()
        except Exception as exc:
            logger.exception("futures_display_main_sina failed: %s", exc)
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        rows: list[dict] = []
        for _, row in df.iterrows():
            symbol = str(row.get("symbol") or "").strip()
            exchange_raw = str(row.get("exchange") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            if not symbol or not exchange_raw or not name:
                continue
            exchange = _SINA_EXCHANGE_MAP.get(exchange_raw)
            if not exchange:
                # Skip unknown exchanges
                continue

            symbol_root = _symbol_root(symbol)
            product = _classify_product(exchange, symbol_root)

            rows.append(
                {
                    "code": symbol,
                    "name": name,
                    "exchange": exchange,
                    "product": product,
                    "is_main": True,
                    "source": "akshare",
                }
            )

        logger.info(
            "FuturesContractDiscovery: extracted %d main contracts", len(rows)
        )
        return pd.DataFrame(rows)

    def load(self, data: pd.DataFrame) -> int:
        if data.empty:
            return 0
        service = FuturesService(self.db)
        records = data.to_dict("records")
        return service.upsert_contracts(records)


class FuturesDailyPipeline(ETLPipeline):
    """ETL pipeline for futures main contract daily bars.

    For each active main contract in ``futures_contracts`` we pull
    ``ak.futures_main_sina(symbol="CU0")`` which returns columns:
        日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 持仓量, 动态结算价

    We persist the last ``history_days`` days (default 30) so the
    pipeline stays cheap and is meant to run daily as a snapshot.
    """

    job_name = "futures_daily_etl"

    def __init__(
        self,
        db: Session,
        target_date: date | None = None,
        history_days: int = 30,
    ) -> None:
        super().__init__(provider=_AkshareFuturesProvider(), db=db)
        self.target_date = target_date
        self.history_days = history_days

    def run(self) -> ETLResult:
        """Override base run() to skip the ETF-specific L2 validator.

        Futures markets have limit moves, settlement-driven opens and
        occasional historical data quirks that cause the shared
        four-layer validator (built for A-share/US ETF daily bars) to
        reject otherwise usable rows. We keep a light L1 check for the
        columns we need and then load directly.
        """
        result = ETLResult()
        self._create_log()

        try:
            data = self.extract()
            if data.empty:
                result.warnings.append("Extract returned empty DataFrame")

            # Light format check: ensure required columns exist.
            required = {"etf_code", "trade_date", "open", "high", "low", "close"}
            missing = required - set(data.columns)
            if missing:
                raise ValueError(f"Missing required columns: {sorted(missing)}")

            # Warn about rows with obvious bad prices but do not block the
            # entire batch; downstream loaders skip None/NaN values.
            bad_mask = (
                data["high"].isna()
                | data["low"].isna()
                | (data["high"] < data["low"])
            )
            bad_count = int(bad_mask.sum())
            if bad_count:
                result.warnings.append(
                    f"Dropping {bad_count} row(s) with invalid high/low"
                )
                data = data[~bad_mask]

            loaded = self.load(data)
            result.records = loaded
            result.success = True
            self._update_log(status="success", records=loaded)
            logger.info("FuturesDailyPipeline: loaded %d daily bars", loaded)
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("FuturesDailyPipeline failed: %s", error_msg)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_one(symbol: str) -> tuple[str, pd.DataFrame]:
        """Fetch one contract's daily history. Returns (symbol, df)."""
        try:
            df = ak.futures_main_sina(symbol=symbol)
        except Exception as exc:
            logger.warning("futures_main_sina(%s) failed: %s", symbol, exc)
            return symbol, pd.DataFrame()
        return symbol, df if df is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    def extract(self) -> pd.DataFrame:
        contracts = (
            self.db.query(FuturesContract)
            .filter(FuturesContract.is_main == True)  # noqa: E712
            .all()
        )
        if not contracts:
            logger.info("FuturesDailyPipeline: no contracts in futures_contracts; run discovery first")
            return pd.DataFrame()

        codes = [c.code for c in contracts]
        self._expected_codes = codes

        logger.info("FuturesDailyPipeline: fetching %d contracts", len(codes))

        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_one, code): code for code in codes
            }
            for fut in as_completed(futures):
                try:
                    symbol, df = fut.result(timeout=60)
                except Exception as exc:
                    logger.warning("worker failed for %s: %s", futures[fut], exc)
                    continue
                if df.empty:
                    continue
                df = df.copy()
                df["__code"] = symbol
                frames.append(df)

        if not frames:
            return pd.DataFrame()

        out = pd.concat(frames, ignore_index=True)

        # Normalize columns from sina's chinese headers to our internal names
        out = out.rename(
            columns={
                "日期": "trade_date",
                "开盘价": "open",
                "最高价": "high",
                "最低价": "low",
                "收盘价": "close",
                "成交量": "volume",
                "持仓量": "open_interest",
                "动态结算价": "settle_dynamic",
            }
        )
        # The sina endpoint sometimes includes a dynamic settlement column
        # that may not have a previous-settle column. We retain only the
        # fields we actually persist.
        out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
        for col in ["open", "high", "low", "close"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        for col in ["volume", "open_interest"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        if "settle_dynamic" in out.columns:
            out["settle"] = pd.to_numeric(out["settle_dynamic"], errors="coerce")
            out = out.drop(columns=["settle_dynamic"])

        # Keep only the requested history window (strictly > cutoff so that
        # ``history_days`` days are retained, not ``history_days + 1``).
        if self.target_date is None:
            cutoff = date.today() - timedelta(days=self.history_days)
        else:
            cutoff = self.target_date - timedelta(days=self.history_days)
        out = out[out["trade_date"] > cutoff]

        # Compute pre_settle = previous row's settle within each contract.
        # sina's main contract data always returns rows sorted ascending.
        out = out.sort_values(["__code", "trade_date"]).reset_index(drop=True)
        out["pre_settle"] = out.groupby("__code")["settle"].shift(1)

        # Use "etf_code" as the internal symbol column name so this pipeline
        # can still share the same light format check as other bar pipelines.
        out = out.rename(columns={"__code": "etf_code"})
        logger.info("FuturesDailyPipeline: extracted %d rows", len(out))
        return out

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, data: pd.DataFrame) -> int:
        if data.empty:
            return 0

        records = []
        for _, row in data.iterrows():
            rec = {
                "code": row.get("etf_code"),
                "trade_date": row.get("trade_date"),
                "open": _coerce_float(row.get("open")),
                "high": _coerce_float(row.get("high")),
                "low": _coerce_float(row.get("low")),
                "close": _coerce_float(row.get("close")),
                "settle": _coerce_float(row.get("settle")),
                "pre_settle": _coerce_float(row.get("pre_settle")),
                "volume": _coerce_int(row.get("volume")),
                "open_interest": _coerce_int(row.get("open_interest")),
                "turnover": None,
                "warehouse_receipts": None,
                "source": "akshare",
            }
            rec = {
                k: v
                for k, v in rec.items()
                if v is not None
                and not (isinstance(v, float) and pd.isna(v))
            }
            if not rec.get("code") or not rec.get("trade_date"):
                continue
            records.append(rec)

        if not records:
            return 0

        service = FuturesService(self.db)
        written = service.upsert_daily_bars(records)

        # Invalidate downstream caches that depend on bar data
        try:
            cache_invalidate_pattern("futures:*")
        except Exception:
            logger.exception("Failed to invalidate futures cache")

        return written
