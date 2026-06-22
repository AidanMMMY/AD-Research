"""Data normalization module for standardizing ETF data from various sources."""

import pandas as pd

COLUMN_MAP: dict[str, str] = {
    # Chinese column names
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "change_pct",
    "换手率": "turnover_rate",
    # English column names
    "Date": "trade_date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    # Generic / common aliases
    "etf_code": "etf_code",
    "code": "etf_code",
    "pre_close": "pre_close",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to unified standard names."""
    df = df.copy()
    rename_map = {col: COLUMN_MAP[col] for col in df.columns if col in COLUMN_MAP}
    df = df.rename(columns=rename_map)
    return df


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert columns to appropriate data types."""
    df = df.copy()

    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    for col in ["open", "high", "low", "close", "pre_close", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

    if "change_pct" in df.columns:
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")

    if "turnover_rate" in df.columns:
        df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce")

    return df


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Run full normalization: rename columns and convert types."""
    df = normalize_columns(df)
    df = normalize_types(df)
    return df
