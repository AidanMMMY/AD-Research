"""Eastmoney research-report provider.

Wraps akshare's ``stock_research_report_em(symbol)`` function. Akshare
hits Eastmoney's public ``data.eastmoney.com/report/stock.jshtml`` JSON
endpoint and returns a per-instrument list of analyst reports — no auth
required.

Field mapping (akshare -> provider):
  股票代码       -> stock_code
  股票简称       -> stock_name
  报告名称       -> title
  机构           -> org_name
  行业           -> industry
  东财评级       -> rating
  日期           -> publish_date
  报告PDF链接    -> pdf_url

The provider exposes two methods:

* :meth:`fetch_for_stock` — single-symbol fetch (used by the API
  ``POST /research-reports/{id}/summarize`` path and the on-demand
  per-stock scheduler).
* :meth:`fetch_for_codes` — batch fetch for a list of plain (non-ts)
  A-share codes.  Used by the daily pipeline.
"""

import logging
from datetime import date, datetime
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _to_iso_date(value: Any) -> date | None:
    """Coerce akshare's mixed date types into a ``date``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(value[:10].replace("/", "-"), fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _serialize_row(row: Any) -> dict[str, Any]:
    """Convert a row to dict, serializing date/datetime objects to ISO strings."""
    if hasattr(row, "to_dict"):
        d = row.to_dict()
    else:
        d = dict(row)
    result = {}
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _to_ts_code(symbol: str) -> str:
    """Convert a plain A-share code like ``600519`` to ``600519.SH``.

    SH/SZ/BJ heuristic:
      * code starts with 6/9 -> SH (Shanghai main + 科创板 B-share)
      * code starts with 0/3/2 -> SZ (Shenzhen main + 创业板 + B-share)
      * code starts with 4/8  -> BJ (Beijing exchange)
      * code starts with 5   -> SH (funds, ETFs; safe default)
      * fallback             -> SH
    """
    if not symbol:
        return ""
    s = symbol.strip()
    if "." in s:
        return s  # already ts-style
    head = s[0]
    if head in {"6", "9", "5"}:
        suffix = "SH"
    elif head in {"0", "2", "3"}:
        suffix = "SZ"
    elif head in {"4", "8"}:
        suffix = "BJ"
    else:
        suffix = "SH"
    return f"{s}.{suffix}"


class EastMoneyResearchProvider:
    """Thin wrapper around ``ak.stock_research_report_em``.

    Akshare is imported lazily so the rest of the app can import this
    provider without the heavy dep being available in unit tests.
    """

    name = "eastmoney"

    def __init__(self) -> None:
        self._ak = None  # populated on first use

    def _get_ak(self):
        if self._ak is None:
            import akshare as ak  # local import — keeps tests light

            self._ak = ak
        return self._ak

    def fetch_for_stock(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch research reports for a single A-share code.

        ``symbol`` may be either ``600519`` or ``600519.SH``. Returns a
        list of normalized dicts (one per report) ready for the
        pipeline's ``transform`` step. Returns ``[]`` on any error so
        the pipeline can keep running for other stocks.
        """
        try:
            ak = self._get_ak()
            df = ak.stock_research_report_em(symbol=symbol)
        except Exception as exc:  # pragma: no cover - network/upstream
            logger.warning(
                "EastMoneyResearchProvider: fetch failed for %s: %s", symbol, exc
            )
            return []
        if df is None or df.empty:
            return []
        return [_normalize_row(row) for _, row in df.iterrows()]

    def fetch_for_codes(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        """Batch fetch research reports for multiple A-share codes.

        Failures for individual symbols are logged and skipped so a
        single bad symbol does not abort the whole batch.
        """
        results: list[dict[str, Any]] = []
        for code in codes:
            for record in self.fetch_for_stock(code):
                results.append(record)
        return results


def _normalize_row(row: Any) -> dict[str, Any]:
    """Map one akshare row to the provider's normalized schema.

    The output dict is what the pipeline's ``transform`` step expects.
    Fields are deliberately permissive (``Any``) — the pipeline is
    responsible for strict validation and DB-level coercion.
    """
    raw_code = row.get("股票代码")
    symbol = str(raw_code).strip() if raw_code is not None else ""
    ts_code = _to_ts_code(symbol)
    name = row.get("股票简称")
    title = row.get("报告名称")
    org_name = row.get("机构")
    industry = row.get("行业")
    rating = row.get("东财评级")
    publish_date = _to_iso_date(row.get("日期"))
    pdf_url = row.get("报告PDF链接")

    return {
        "ts_code": ts_code,
        "symbol": symbol,
        "name": str(name).strip() if name is not None else None,
        "title": str(title).strip() if title is not None else None,
        "org_name": str(org_name).strip() if org_name is not None else None,
        "industry": str(industry).strip() if industry is not None else None,
        "rating": str(rating).strip() if rating is not None else None,
        "publish_date": publish_date,
        "pdf_url": str(pdf_url).strip() if pdf_url is not None else None,
        "raw": _serialize_row(row),
    }
