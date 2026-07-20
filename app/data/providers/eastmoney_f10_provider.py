"""Eastmoney fund F10 ETF top-10 holdings provider.

Background
----------
The stock-oriented F10 endpoint
``emweb.securities.eastmoney.com/PC_HSF10/PortfolioAllocation/PageAjax``
returns an *"无F10资料"* HTML stub for ETF codes — that view only exists
for individual equities. ETF (fund) holdings are disclosed through the
fund F10 feed instead:

    https://fundf10.eastmoney.com/FundArchivesDatas.aspx
        ?type=jjcc&code={code}&topline={n}&year={yyyy}&month=

This is the same 天天基金 disclosure feed that powers the public fund page
and Akshare's ``fund_portfolio_hold_em``. Calling it directly with
``requests`` (the backend already ships ``requests``; ``curl_cffi`` is only
in the agent image) plus retries, and selecting the newest disclosed
quarter across the current / previous calendar year, gives materially
higher and more reliable coverage than the Akshare wrapper, which times
out frequently from the ECS host.

The response body looks like::

    var apidata={ content:"<div ...>...tables...</div>",arryear:[2026,2025],curyear:2026};

``content`` is a double-quoted string of HTML (inner attributes use single
quotes, so no escaping collides with the delimiter). Each quarter is one
``boxitem`` block containing a ``截止至：<font>YYYY-MM-DD</font>`` marker and
a holdings ``<table>``. ``pandas.read_html`` yields one DataFrame per table
in document order, aligned with the disclosure dates.

Returned DataFrame (contract shared with the Tushare / Akshare providers)::

    etf_code, holding_code, holding_name, weight, shares,
    market_value, holdings_as_of_date, source
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
import time
from io import StringIO

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
SOURCE = "eastmoney_f10"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Referer": "https://fundf10.eastmoney.com/",
}
_TIMEOUT = 12
_RETRIES = 2

# ``content:"<html>",arryear:[...]`` — DOTALL so the HTML can span lines.
_CONTENT_RE = re.compile(r'content:"(.*)",arryear', re.S)
_DATE_RE = re.compile(r"截止至：<font[^>]*>([0-9]{4}-[0-9]{2}-[0-9]{2})</font>")

_OUT_COLS = [
    "etf_code",
    "holding_code",
    "holding_name",
    "weight",
    "shares",
    "market_value",
    "holdings_as_of_date",
    "source",
]


def _fetch_year(pure_code: str, year: int, topline: int) -> str | None:
    """GET one calendar year of the jjcc feed with retries.

    Returns the raw response text, or ``None`` when every attempt fails.
    """
    url = (
        f"{BASE_URL}?type=jjcc&code={pure_code}"
        f"&topline={topline}&year={year}&month="
    )
    for attempt in range(_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001 - network resilience
            if attempt < _RETRIES:
                time.sleep(0.5 * (attempt + 1))
            else:
                logger.warning(
                    "Eastmoney jjcc(%s, %s) failed after %d retries: %s",
                    pure_code, year, _RETRIES, exc,
                )
    return None


def _parse_quarters(text: str | None) -> dict[_dt.date, pd.DataFrame]:
    """Map each disclosed quarter-end date to its raw holdings table."""
    if not text:
        return {}
    match = _CONTENT_RE.search(text)
    if not match:
        return {}
    html = match.group(1)
    dates = _DATE_RE.findall(html)
    if not dates:
        return {}
    try:
        # ``converters={1: str}`` keeps 股票代码 (column index 1) as a
        # string so leading zeros (A-share 000001, HK 00700) survive
        # instead of being coerced to int.
        tables = pd.read_html(StringIO(html), converters={1: str})
    except ValueError:
        # read_html raises ValueError when it finds no table.
        return {}

    quarters: dict[_dt.date, pd.DataFrame] = {}
    for idx, table in enumerate(tables):
        if idx >= len(dates):
            break
        try:
            snapshot = _dt.date.fromisoformat(dates[idx])
        except ValueError:
            continue
        quarters[snapshot] = table
    return quarters


def _norm_code(value) -> str | None:
    """Normalise a raw underlying code cell to a clean string, or ``None``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in {"--", "-", "nan"}:
        return None
    # A trailing ``.0`` can slip in if a cell was ever coerced to float.
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _parse_pct(value) -> float | None:
    """Parse an ``'4.27%'`` weight cell into a decimal fraction (0.0427)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().rstrip("%").strip()
    if not text or text in {"--", "-"}:
        return None
    try:
        return float(text) / 100.0
    except ValueError:
        return None


def _find_col(columns, needle: str):
    """Return the first column whose name contains ``needle`` (spaces removed)."""
    for col in columns:
        if needle in str(col).replace(" ", ""):
            return col
    return None


def _normalize(
    table: pd.DataFrame, etf_code: str, snapshot: _dt.date, limit: int
) -> pd.DataFrame | None:
    """Reshape a raw jjcc holdings table into the shared provider contract."""
    code_col = _find_col(table.columns, "股票代码")
    name_col = _find_col(table.columns, "股票名称")
    weight_col = _find_col(table.columns, "占净值")
    shares_col = _find_col(table.columns, "持股数")
    mv_col = _find_col(table.columns, "持仓市值")

    if code_col is None or mv_col is None:
        return None

    out = pd.DataFrame()
    out["holding_code"] = table[code_col].map(_norm_code)
    out["holding_name"] = (
        table[name_col].astype(str).str.strip() if name_col is not None else None
    )
    out["weight"] = (
        table[weight_col].map(_parse_pct) if weight_col is not None else None
    )
    # Eastmoney's jjcc feed reports 持股数 in 万股 and 持仓市值 in 万元;
    # normalize to raw shares / yuan so rows match the Tushare source unit.
    out["shares"] = (
        pd.to_numeric(table[shares_col], errors="coerce") * 1e4
        if shares_col is not None
        else None
    )
    out["market_value"] = pd.to_numeric(table[mv_col], errors="coerce") * 1e4

    out = out[out["holding_code"].notna() & (out["holding_code"] != "")]
    out = out.dropna(subset=["market_value"])
    if out.empty:
        return None

    out = out.sort_values("market_value", ascending=False).head(limit)
    out["etf_code"] = etf_code
    out["holdings_as_of_date"] = snapshot
    out["source"] = SOURCE
    return out[_OUT_COLS].reset_index(drop=True)


def fetch_etf_holdings(code: str, limit: int = 10) -> pd.DataFrame | None:
    """Fetch the latest disclosed top-``limit`` ETF holdings from Eastmoney F10.

    ``code`` may be either a bare 6-digit fund code (``510300``) or the
    suffixed form used across the platform (``510300.SH`` / ``159919.SZ``);
    only the numeric part is sent to Eastmoney.

    Returns a DataFrame with columns
    ``etf_code, holding_code, holding_name, weight, shares, market_value,
    holdings_as_of_date, source`` — or ``None`` when Eastmoney has no stock
    holdings for the fund (e.g. bond / commodity / money-market ETFs) or
    every request failed.
    """
    pure = str(code).split(".")[0].strip()
    if not pure.isdigit():
        return None

    topline = max(limit, 10)
    this_year = _dt.date.today().year

    # The current calendar year already contains the newest disclosed
    # quarter; only reach back a year when it is empty (typical in
    # Jan–Mar before the Q4 report lands).
    quarters = _parse_quarters(_fetch_year(pure, this_year, topline))
    if not quarters:
        quarters = _parse_quarters(_fetch_year(pure, this_year - 1, topline))
    if not quarters:
        return None

    snapshot = max(quarters)
    df = _normalize(quarters[snapshot], str(code), snapshot, limit)
    if df is None or df.empty:
        return None
    return df
