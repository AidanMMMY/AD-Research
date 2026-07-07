#!/usr/bin/env python3
"""本地生成 A 股 ETF adj_factor CSV，用于导入 ECS 数据库。

背景
----
ECS 上 Akshare 连接不稳定，因此在本地（Akshare 可达）拉取每只 ETF 的 raw/qfq
行情，计算 adj_factor = qfq_close / raw_close，输出 CSV 后上传到 ECS 用 psql
COPY 导入并 UPDATE instrument_daily_bar。

用法
----
    python scripts/generate_etf_adj_factor_csv.py \
        --bars-csv /tmp/etf_backfill_bars.csv \
        --output /tmp/etf_adj_factor_updates.csv \
        --progress-file /tmp/generate_etf_adj_factor_progress.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

import akshare as ak
import numpy as np
import pandas as pd

logger = logging.getLogger("generate_etf_adj_factor_csv")

_AK_DELAY = 0.6
_MAX_WORKERS = 2
_PROGRESS_FILE_DEFAULT = "/tmp/generate_etf_adj_factor_progress.json"
_lock = threading.Lock()


def _coerce_date(value) -> date | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _load_progress(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ("completed_codes", "failed_codes"):
                if key not in data:
                    data[key] = []
            for key in ("total_rows",):
                if key not in data:
                    data[key] = 0
            return data
        except Exception as exc:
            logger.warning("进度文件读取失败，将重建: %s", exc)
    return {
        "completed_codes": [],
        "failed_codes": [],
        "total_rows": 0,
        "start_time": pd.Timestamp.now().isoformat(),
        "last_updated": None,
    }


def _save_progress(path: str | Path, progress: dict[str, Any]) -> None:
    path = Path(path)
    progress["last_updated"] = pd.Timestamp.now().isoformat()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


class _RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.monotonic()
            self._last = now


_limiter = _RateLimiter(_AK_DELAY)


def _fetch_bars(pure_code: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    _limiter.acquire()
    df = ak.fund_etf_hist_em(
        symbol=pure_code,
        period="daily",
        start_date=start_str,
        end_date=end_str,
        adjust=adjust,
    )
    if df.empty:
        return df
    col_close = "raw_close" if adjust == "" else "qfq_close"
    df = df.rename(columns={"日期": "trade_date", "收盘": col_close})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df[col_close] = pd.to_numeric(df[col_close], errors="coerce")
    return df[["trade_date", col_close]]


def _process_one_etf(
    etf_code: str,
    bars_df: pd.DataFrame,
    progress_file: str,
) -> dict[str, Any]:
    pure_code = etf_code.split(".")[0]
    start_date = bars_df["trade_date"].min()
    end_date = bars_df["trade_date"].max()
    result = {"etf_code": etf_code, "rows": 0, "error": None}

    try:
        qfq_df = _fetch_bars(pure_code, start_date, end_date, "qfq")
        raw_df = _fetch_bars(pure_code, start_date, end_date, "")

        if qfq_df.empty or raw_df.empty:
            result["error"] = "empty qfq or raw"
            return result

        merged = bars_df[["trade_date", "close"]].merge(qfq_df, on="trade_date", how="left")
        merged = merged.merge(raw_df, on="trade_date", how="left")

        with np.errstate(invalid="ignore", divide="ignore"):
            merged["adj_factor"] = np.where(
                (merged["raw_close"].notna()) & (merged["raw_close"] != 0) & (merged["qfq_close"].notna()),
                merged["qfq_close"] / merged["raw_close"],
                np.nan,
            )

        valid = merged.dropna(subset=["adj_factor"])
        valid = valid[np.isfinite(valid["adj_factor"])]
        valid["adj_factor"] = valid["adj_factor"].astype(float)
        valid = valid[["trade_date", "adj_factor"]].copy()
        valid["etf_code"] = etf_code

        result["rows"] = len(valid)
        result["df"] = valid
        return result
    except Exception as exc:
        result["error"] = f"{exc}\n{traceback.format_exc()}"
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars-csv", required=True, help="输入的 bars CSV (etf_code, trade_date, close)")
    parser.add_argument("--output", required=True, help="输出的 adj_factor CSV")
    parser.add_argument("--progress-file", default=_PROGRESS_FILE_DEFAULT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=_MAX_WORKERS)
    parser.add_argument("--ak-delay", type=float, default=_AK_DELAY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    _limiter.min_interval = args.ak_delay

    progress = _load_progress(args.progress_file) if args.resume else {
        "completed_codes": [],
        "failed_codes": [],
        "total_rows": 0,
        "start_time": pd.Timestamp.now().isoformat(),
        "last_updated": None,
    }
    completed = set(progress.get("completed_codes", []))
    failed = set(progress.get("failed_codes", []))

    logger.info("读取 bars CSV: %s", args.bars_csv)
    bars = pd.read_csv(args.bars_csv)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"]).dt.date
    bars["close"] = pd.to_numeric(bars["close"], errors="coerce")

    grouped = [(code, group) for code, group in bars.groupby("etf_code")]
    if args.limit:
        grouped = grouped[:args.limit]

    if args.resume:
        before = len(grouped)
        grouped = [(c, g) for c, g in grouped if c not in completed]
        logger.info("resume: 跳过 %d 只已完成，本次处理 %d 只", before - len(grouped), len(grouped))

    output_path = Path(args.output)
    write_header = not output_path.exists()

    total_rows = progress.get("total_rows", 0)
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_process_one_etf, code, group, args.progress_file): code
            for code, group in grouped
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                res = future.result(timeout=120)
                results.append(res)
                if res["error"]:
                    logger.warning("%s 失败: %s", code, res["error"][:200])
                    failed.add(code)
                    completed.discard(code)
                else:
                    logger.info("%s OK rows=%d", code, res["rows"])
                    if res["rows"] > 0 and "df" in res:
                        res["df"][["etf_code", "trade_date", "adj_factor"]].to_csv(
                            output_path, mode="a", index=False, header=write_header
                        )
                        write_header = False
                    completed.add(code)
                    failed.discard(code)
                    total_rows += res["rows"]

                progress["completed_codes"] = sorted(completed)
                progress["failed_codes"] = sorted(failed)
                progress["total_rows"] = total_rows
                _save_progress(args.progress_file, progress)
            except Exception as exc:
                logger.exception("%s 未捕获异常", code)
                failed.add(code)
                progress["failed_codes"] = sorted(failed)
                _save_progress(args.progress_file, progress)

    summary = {
        "total_etfs": len(results),
        "completed": len(completed),
        "failed": len(failed),
        "total_rows": total_rows,
        "failed_codes": sorted(failed),
    }
    logger.info("完成: %s", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
