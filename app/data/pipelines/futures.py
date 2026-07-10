"""Futures daily ETL pipeline.

Discovers Chinese-domestic futures main contracts and pulls daily bars
using akshare's **per-exchange** daily endpoints
(``ak.get_futures_daily(market=...)`` for SHFE / CZCE / CFFEX / INE /
GFEX, and ``ak.get_dce_daily(date)`` for DCE).

The previous implementation used ``ak.futures_display_main_sina()`` and
``ak.futures_main_sina(symbol=...)``, both of which are blocked from
the ECS IP (HTTP 456). The per-exchange endpoints use different
upstream sources and work fine from the same IP.

For each variety on each trade date we pick the contract with the
highest ``open_interest`` and treat that as the "main" contract. The
internal continuous code stays ``{variety}0`` (e.g. ``CU0``) so the
existing scheduler / dashboard / API code paths are unchanged.
"""

import logging
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Iterable

import akshare as ak
import numpy as np
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


# Number of concurrent workers when fetching per-exchange data.
# Each exchange needs at most one round-trip per (start, end) window,
# so 5 workers comfortably covers SHFE/CZCE/CFFEX/INE/GFEX in parallel.
_MAX_WORKERS = 5

# Exchanges reachable via ak.get_futures_daily(market=...).
# CFFEX (中金所) uses the literal arg name 'CFFEX' (akshare does NOT accept
# 'CCFX' — the function returns an empty DataFrame for unknown markets).
_FUTURES_DAILY_EXCHANGES: tuple[str, ...] = ("SHFE", "CZCE", "CFFEX", "INE", "GFEX")

# Chinese -> English column mapping used by ak.futures_main_sina(symbol=...).
# Used by the DCE fetcher since DCE has no working per-exchange endpoint.
_DCE_RENAME: dict[str, str] = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "持仓量": "open_interest",
    "动态结算价": "settle",
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
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        # numpy/pandas NaN check before int conversion (which would raise)
        if isinstance(value, (float, np.floating)) and np.isnan(value):
            return None
        result = int(float(value))
        return result
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


# ---------------------------------------------------------------------------
# Per-exchange data fetchers
# ---------------------------------------------------------------------------


def _format_yyyymmdd(value: date | datetime | str) -> str:
    """Normalise a date into the YYYYMMDD string akshare's daily endpoints expect."""
    if isinstance(value, str):
        # Accept either YYYYMMDD or YYYY-MM-DD; strip dashes.
        return value.replace("-", "")
    return value.strftime("%Y%m%d")


def _fetch_dce_day(d: date) -> pd.DataFrame:
    """Fetch one day's worth of DCE futures data via ``ak.get_dce_daily``.

    Returns an empty DataFrame on any error. DCE's endpoint takes a single
    ``date`` arg (not a range), so we loop one day at a time.

    NOTE: from the ECS IP this endpoint returns ``JSONDecodeError`` and is
    therefore broken. The pipeline now uses :func:`_fetch_dce_via_main_sina`
    instead, but this helper is kept around for completeness (it still works
    from other akshare routes / via a proxy) and is exercised by tests.
    """
    try:
        return ak.get_dce_daily(date=_format_yyyymmdd(d))
    except Exception as exc:
        logger.warning("get_dce_daily(%s) failed: %s", d, exc)
        return pd.DataFrame()


def _dce_main_contracts() -> list[str]:
    """Return DCE continuous main-contract symbols (``M0``, ``Y0``, ...).

    Uses ``ak.futures_display_main_sina`` which is the only working DCE
    discovery route from this ECS IP. The list is filtered to varieties
    that we actually classify in :data:`_PRODUCT_MAP` so we don't waste
    HTTP calls on symbols (e.g. ``BZ0``, ``LG0``) that aren't in the
    dashboard's product grouping.
    """
    try:
        contracts = ak.futures_display_main_sina()
    except Exception as exc:
        logger.warning("DCE futures_display_main_sina failed: %s", exc)
        return []
    if contracts is None or contracts.empty:
        return []

    dce = contracts[
        contracts["exchange"].astype(str).str.lower() == "dce"
    ]
    if dce.empty:
        return []

    tracked_roots = {root for ex, root in _PRODUCT_MAP if ex == "DCE"}
    out: list[str] = []
    for sym in dce["symbol"].tolist():
        s = str(sym).strip()
        if not s:
            continue
        root = _symbol_root(s)
        if not root or root not in tracked_roots:
            continue
        out.append(s)
    return out


def _fetch_one_dce_main(symbol: str) -> pd.DataFrame | None:
    """Fetch one DCE continuous contract's full rolled daily history.

    Wraps a single ``ak.futures_main_sina(symbol=...)`` call so the
    parallel scheduler in :func:`_fetch_dce_via_main_sina` can fan
    out per-variety.
    """
    try:
        df = ak.futures_main_sina(symbol=symbol)
    except Exception as exc:
        logger.warning("DCE futures_main_sina(%s) failed: %s", symbol, exc)
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df = df.rename(columns=_DCE_RENAME)
    df["symbol"] = symbol
    df["variety"] = _symbol_root(symbol)
    df["exchange"] = "DCE"
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    # ``pre_settle`` is not exposed by futures_main_sina; the daily pipeline
    # back-fills it from the previous row's settle in extract().
    if "pre_settle" not in df.columns:
        df["pre_settle"] = pd.NA
    return df


def _fetch_dce_via_main_sina(start_day: date, end_day: date) -> pd.DataFrame:
    """Fetch DCE daily bars via ``ak.futures_main_sina``.

    DCE's per-day endpoint (``ak.get_dce_daily``) and per-exchange
    ``ak.get_futures_daily(market='DCE')`` both return
    ``JSONDecodeError`` from this ECS IP — DCE blocks POST endpoints
    on this network and doesn't expose a JSON GET. The only working
    DCE source we have is the older sina-backed continuous-contract
    endpoint, which upstream still serves here (unlike SHFE/CZCE
    where the same endpoint is blocked).

    For each DCE variety we track (``M``, ``Y``, ``P``, ``C``,
    ``A``, ``I``, ``JD``, ``L``, ``PP``, ``V``, ``BB``, ``FB``,
    ``CS``, ``J``, ``JM``, ``EG``, ``EB``, ``RR``, ``PG``, ``LH``,
    ``B``) we fetch the rolled continuous-contract history and
    trim it to ``[start_day, end_day]``. Each variety's data is
    fetched in parallel so the 22 round-trips finish in ~1s.
    """
    symbols = _dce_main_contracts()
    if not symbols:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_symbol = {
            executor.submit(_fetch_one_dce_main, sym): sym for sym in symbols
        }
        for fut in as_completed(future_to_symbol):
            sym = future_to_symbol[fut]
            try:
                df = fut.result()
            except Exception as exc:
                logger.warning(
                    "DCE futures_main_sina worker crashed for %s: %s", sym, exc
                )
                continue
            if df is None or df.empty:
                continue
            if "date" in df.columns:
                df = df[df["date"].between(start_day, end_day)]
            if not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _fetch_market_range(exchange: str, start_day: date, end_day: date) -> pd.DataFrame:
    """Fetch a date range from one of the ak.get_futures_daily(market=...) endpoints."""
    try:
        df = ak.get_futures_daily(
            start_date=_format_yyyymmdd(start_day),
            end_date=_format_yyyymmdd(end_day),
            market=exchange,
        )
    except Exception as exc:
        logger.warning("get_futures_daily(%s, %s..%s) failed: %s", exchange, start_day, end_day, exc)
        return pd.DataFrame()
    return df if df is not None else pd.DataFrame()


def fetch_all_markets(
    start_day: date, end_day: date
) -> dict[str, pd.DataFrame]:
    """Fetch the per-exchange daily futures data for every supported exchange.

    Returns a dict keyed by exchange code (SHFE/CZCE/CFFEX/INE/GFEX/DCE).
    Each value is the raw per-contract DataFrame; an empty DataFrame means
    the fetch failed or the source returned no data.

    SHFE / CZCE / CFFEX / INE / GFEX are pulled in parallel via
    ``ak.get_futures_daily(market=...)``.

    DCE requires a different path because its per-day and per-exchange
    endpoints both fail (DCE blocks POST + some JSON GET routes from
    this network). We use ``ak.futures_main_sina(symbol=<continuous>)``
    per variety to fetch DCE daily bars; see
    :func:`_fetch_dce_via_main_sina`.
    """
    results: dict[str, pd.DataFrame] = {}

    # Parallel fetch for the 5 exchanges reachable via get_futures_daily.
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_market = {
            executor.submit(_fetch_market_range, ex, start_day, end_day): ex
            for ex in _FUTURES_DAILY_EXCHANGES
        }
        for fut in as_completed(future_to_market):
            ex = future_to_market[fut]
            try:
                df = fut.result()
                results[ex] = df if df is not None else pd.DataFrame()
            except Exception as exc:
                logger.warning("market fetch worker crashed for %s: %s", ex, exc)
                results[ex] = pd.DataFrame()

    # DCE: per-variety fetch via futures_main_sina (the only working DCE
    # source from this ECS IP; see _fetch_dce_via_main_sina).
    try:
        results["DCE"] = _fetch_dce_via_main_sina(start_day, end_day)
    except Exception as exc:
        logger.warning("DCE fetch failed: %s", exc)
        results["DCE"] = pd.DataFrame()

    for ex, df in results.items():
        logger.info(
            "fetch_all_markets: %s returned %d rows (%s..%s)",
            ex,
            len(df),
            start_day,
            end_day,
        )
    return results


def _normalise_market_df(exchange: str, df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a raw per-exchange frame into the canonical column set.

    Adds/renames ``exchange`` and ``variety`` columns so downstream code can
    treat every exchange uniformly. Returns the input unchanged if it's
    empty or missing the contract identifier.

    Also normalises the ``date`` column to a uniform
    ``datetime.date`` type. Each per-exchange endpoint returns dates in a
    different dtype (``int64`` epoch ms for CZCE, ``object`` of
    ``pd.Timestamp`` / ``datetime`` for SHFE/CFFEX/INE/GFEX, Python
    ``date`` for our DCE fetcher); concatenating them without coercion
    yields a heterogeneous ``object`` column that crashes ``sort_values``
    later in the pipeline.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # The newer akshare per-exchange endpoint already returns ``variety`` for
    # SHFE/CZCE/CFFEX/INE/GFEX. Older DCE responses may not, so we fall back
    # to deriving it from ``symbol``.
    if "variety" not in df.columns and "symbol" in df.columns:
        df["variety"] = df["symbol"].apply(
            lambda s: _symbol_root(str(s)) if pd.notna(s) else None
        )

    if "symbol" not in df.columns or "date" not in df.columns:
        logger.warning(
            "normalise_market_df(%s): missing symbol/date columns; got %s",
            exchange,
            list(df.columns),
        )
        return pd.DataFrame()

    # Normalise date to plain datetime.date (object dtype, but every cell
    # is comparable because all values are date objects).
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    df["exchange"] = exchange
    return df


def _pick_main_per_day(df: pd.DataFrame) -> pd.DataFrame:
    """Pick the highest-open_interest contract per (date, variety).

    Returns a frame with the same per-contract fields but at most one
    row per (date, variety). Ties (very rare) go to whichever contract
    appears first in the source.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    needed = {"date", "variety", "symbol", "open_interest"}
    missing = needed - set(df.columns)
    if missing:
        logger.warning(
            "_pick_main_per_day: missing columns %s; skipping frame",
            sorted(missing),
        )
        return pd.DataFrame()

    # Sort so the highest OI per group ends up at the top, then take the
    # first row per (date, variety). ``dropna`` ensures we never pick a
    # group whose top row has no OI.
    work = df.dropna(subset=["open_interest"]).copy()
    if work.empty:
        return pd.DataFrame()
    work = work.sort_values(
        ["date", "variety", "open_interest"], ascending=[True, True, False]
    )
    return work.drop_duplicates(subset=["date", "variety"], keep="first")


def _to_native(value) -> int | float | None:
    """Best-effort numpy/pandas scalar -> native Python int/float coercion.

    Used inside the record builders so we never hand ``numpy.int64`` /
    ``pandas.Timestamp`` etc. to psycopg2 via SQLAlchemy.
    """
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        if np.isnan(f):
            return None
        return f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


class FuturesContractDiscoveryPipeline(ETLPipeline):
    """Discovers main continuous contracts from akshare's per-exchange endpoints.

    Strategy:
      1. Pull per-exchange daily bars for the last few days.
      2. For each (date, variety) pick the highest-open_interest contract.
      3. Use the latest available trade date's picks as the current
         ``underlying_instrument`` for each variety.
      4. Upsert a row per (exchange, variety) into ``futures_contracts``,
         using ``code = variety + "0"`` (e.g. ``CU0``) so the rest of the
         app can keep treating these as continuous main contracts.
    """

    job_name = "futures_contract_discovery"

    # How many trailing calendar days to scan for the "current main" pick.
    _LOOKBACK_DAYS = 5

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
        end_day = date.today()
        start_day = end_day - timedelta(days=self._LOOKBACK_DAYS - 1)

        try:
            per_market = fetch_all_markets(start_day, end_day)
        except Exception as exc:
            logger.exception("FuturesContractDiscovery: fetch_all_markets crashed: %s", exc)
            return pd.DataFrame()
        normalised: list[pd.DataFrame] = []
        for ex, df in per_market.items():
            ndf = _normalise_market_df(ex, df)
            if not ndf.empty:
                normalised.append(ndf)

        if not normalised:
            logger.warning("FuturesContractDiscovery: no per-exchange data fetched")
            return pd.DataFrame()

        all_contracts = pd.concat(normalised, ignore_index=True)
        picks = _pick_main_per_day(all_contracts)
        if picks.empty:
            logger.warning(
                "FuturesContractDiscovery: no main-contract picks after OI ranking"
            )
            return pd.DataFrame()

        # Use the latest available trade date across all picks.
        picks["date"] = pd.to_datetime(picks["date"], errors="coerce")
        latest_date = picks["date"].max()
        latest = picks[picks["date"] == latest_date].copy()
        if latest.empty:
            return pd.DataFrame()

        rows: list[dict] = []
        for _, row in latest.iterrows():
            exchange = str(row.get("exchange") or "").strip().upper()
            variety = str(row.get("variety") or "").strip()
            symbol = str(row.get("symbol") or "").strip()
            if not exchange or not variety or not symbol:
                continue
            symbol_root = _symbol_root(variety)
            product = _classify_product(exchange, symbol_root)
            code = f"{symbol_root}0"
            rows.append(
                {
                    "code": code,
                    "name": f"{symbol_root}主力",
                    "exchange": exchange,
                    "product": product,
                    "is_main": True,
                    "underlying_instrument": symbol,
                    "source": "akshare",
                }
            )

        logger.info(
            "FuturesContractDiscovery: extracted %d main contracts (latest=%s)",
            len(rows),
            latest_date,
        )
        return pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last")

    def load(self, data: pd.DataFrame) -> int:
        if data.empty:
            return 0
        service = FuturesService(self.db)
        records = data.to_dict("records")
        return service.upsert_contracts(records)


class FuturesDailyPipeline(ETLPipeline):
    """ETL pipeline for futures main contract daily bars.

    For each market we call ``ak.get_futures_daily(market=...)`` once for
    the requested window, then for every (date, variety) we pick the
    contract with the highest ``open_interest`` and write that row under
    the canonical continuous code (``variety0``).

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
    # Extract
    # ------------------------------------------------------------------

    def _window(self) -> tuple[date, date]:
        end_day = self.target_date or date.today()
        # Pull a few extra days so the cutoff filter still leaves the
        # requested window after dropping non-trading days / weekends.
        start_day = end_day - timedelta(days=self.history_days + 7)
        return start_day, end_day

    def _active_main_codes(self) -> set[str]:
        codes: set[str] = set()
        for c in (
            self.db.query(FuturesContract)
            .filter(FuturesContract.is_main == True)  # noqa: E712
            .all()
        ):
            codes.add(c.code)
        return codes

    def extract(self) -> pd.DataFrame:
        start_day, end_day = self._window()

        try:
            per_market = fetch_all_markets(start_day, end_day)
        except Exception as exc:
            logger.exception("FuturesDailyPipeline: fetch_all_markets crashed: %s", exc)
            return pd.DataFrame()
        normalised: list[pd.DataFrame] = []
        for ex, df in per_market.items():
            ndf = _normalise_market_df(ex, df)
            if not ndf.empty:
                normalised.append(ndf)
        if not normalised:
            logger.info(
                "FuturesDailyPipeline: no per-exchange data fetched (%s..%s)",
                start_day,
                end_day,
            )
            return pd.DataFrame()

        all_contracts = pd.concat(normalised, ignore_index=True)
        picks = _pick_main_per_day(all_contracts)
        if picks.empty:
            logger.info("FuturesDailyPipeline: no main-contract picks after OI ranking")
            return pd.DataFrame()

        # Map each pick to its canonical continuous code (variety + "0").
        picks["__code"] = picks["variety"].astype(str).apply(
            lambda v: f"{_symbol_root(v)}0"
        )

        # Restrict to varieties that have an active main-contract row in the
        # DB. We still keep all rows in the frame so discovery can run in
        # any order, but the daily upsert only writes the contracts we
        # actually track.
        active = self._active_main_codes()
        if not active:
            logger.info(
                "FuturesDailyPipeline: no active main contracts in DB; run discovery first"
            )
            return pd.DataFrame()
        picks = picks[picks["__code"].isin(active)]

        # Normalise column names to match the historical sina-based schema
        # so load() and any downstream code keep working unchanged.
        rename = {
            "date": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "open_interest": "open_interest",
            "turnover": "turnover",
            "settle": "settle",
            "pre_settle": "pre_settle",
        }
        out = picks.rename(columns=rename).copy()

        out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
        for col in ["open", "high", "low", "close", "settle", "pre_settle", "turnover"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        for col in ["volume", "open_interest"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")

        # Keep only the requested history window (strictly > cutoff so that
        # ``history_days`` days are retained, not ``history_days + 1``).
        cutoff = end_day - timedelta(days=self.history_days)
        out = out[out["trade_date"] > cutoff]

        # Compute pre_settle = previous row's settle within each contract.
        # Per-exchange daily data may not arrive strictly sorted, so sort.
        out = out.sort_values(["__code", "trade_date"]).reset_index(drop=True)
        out["pre_settle"] = out.groupby("__code")["settle"].shift(1)

        # ``pre_settle`` was already supplied by upstream; our shift fills
        # the first row of each contract. Prefer the upstream value when
        # both are present.
        if "pre_settle" in picks.columns:
            upstream_pre = pd.to_numeric(
                picks["pre_settle"], errors="coerce"
            ).reset_index(drop=True)
            out["pre_settle"] = out["pre_settle"].where(
                out["pre_settle"].notna(), upstream_pre
            )

        # Use "etf_code" as the internal symbol column name so this pipeline
        # can still share the same light format check as other bar pipelines.
        out = out.rename(columns={"__code": "etf_code"})

        # Some exchanges (notably SHFE) return placeholder rows such as
        # ``<ROOT>_TAS<MMYY>`` alongside the real contract — both map to the
        # same ``etf_code`` via ``_symbol_root``. The placeholder rows have
        # zero OI / zero volume / NaN settle, so we drop them by preferring
        # the highest-open_interest row per ``(etf_code, trade_date)`` and
        # keeping the row with the most populated price set as tie-breaker.
        if not out.empty:
            oi_for_rank = pd.to_numeric(
                out.get("open_interest"), errors="coerce"
            ).fillna(0)
            non_null_prices = (
                pd.to_numeric(out["close"], errors="coerce").notna().astype(int)
                + pd.to_numeric(out["settle"], errors="coerce").notna().astype(int)
            )
            rank_score = oi_for_rank * 10 + non_null_prices
            out["__rank"] = rank_score
            out = (
                out.sort_values(["etf_code", "trade_date", "__rank"], ascending=[True, True, False])
                .drop_duplicates(subset=["etf_code", "trade_date"], keep="first")
                .drop(columns="__rank")
                .reset_index(drop=True)
            )

        # Also track the latest underlying instrument per code so we can
        # update ``futures_contracts.underlying_instrument`` in load().
        latest_picks = (
            picks.sort_values(["__code", "date"])
            .dropna(subset=["date"])
            .groupby("__code")
            .tail(1)[["__code", "symbol"]]
            .rename(columns={"__code": "etf_code", "symbol": "underlying_instrument"})
        )
        self._latest_underlying = latest_picks
        logger.info(
            "FuturesDailyPipeline: extracted %d rows (window=%s..%s, cutoff>%s)",
            len(out),
            start_day,
            end_day,
            cutoff,
        )
        return out

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, data: pd.DataFrame) -> int:
        if data.empty:
            return 0

        records: list[dict] = []
        for _, row in data.iterrows():
            rec: dict = {
                "code": _to_native(row.get("etf_code")),
                "trade_date": _coerce_date(row.get("trade_date")),
                "open": _coerce_float(row.get("open")),
                "high": _coerce_float(row.get("high")),
                "low": _coerce_float(row.get("low")),
                "close": _coerce_float(row.get("close")),
                "settle": _coerce_float(row.get("settle")),
                "pre_settle": _coerce_float(row.get("pre_settle")),
                "volume": _coerce_int(row.get("volume")),
                "open_interest": _coerce_int(row.get("open_interest")),
                "turnover": _coerce_float(row.get("turnover")),
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

        # Update ``underlying_instrument`` on each main contract so the
        # dashboard can surface which specific delivery-month contract is
        # currently the leader. Latest picks live in ``self._latest_underlying``.
        try:
            latest_df = getattr(self, "_latest_underlying", None)
            if latest_df is not None and not latest_df.empty:
                for _, r in latest_df.iterrows():
                    code = _to_native(r.get("etf_code"))
                    under = _to_native(r.get("underlying_instrument"))
                    if not code or not under:
                        continue
                    self.db.query(FuturesContract).filter(
                        FuturesContract.code == code
                    ).update({FuturesContract.underlying_instrument: str(under)})
                self.db.commit()
        except Exception:
            logger.exception("Failed to update underlying_instrument")

        # Invalidate downstream caches that depend on bar data
        try:
            cache_invalidate_pattern("futures:*")
        except Exception:
            logger.exception("Failed to invalidate futures cache")

        return written