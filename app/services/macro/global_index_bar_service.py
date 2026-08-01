"""全球速览指数日线 OHLCV 服务（详情页 Batch B 数据组装）.

封装 ``GlobalIndexDailyBar`` 的幂等写入与详情页聚合读取：

* ``upsert_bars`` — 按 (code, trade_date, source) 查重 upsert，
  幂等模式与 ``MacroDataService.upsert_observations`` 一致
  （通用 dialect：读已有键再 insert/update，SQLite 测试同样适用）。
* ``get_bars`` / ``has_bars`` — 单 code 的 bars 查询。
* ``get_detail`` — 详情页 API 契约的数据组装：有 bars 走 OHLC
  分支（latest/stats 由 bars 计算），无 bars 回退
  ``MacroDataService.get_series``（纯 DB 折线，FRED 序列走这里），
  两路皆空返回 None（API 层转 404）。

分类规则 ``_infer_category`` 与前端
``web/src/pages/GlobalMarkets/index.tsx`` 的 ``inferCategoryKey``
保持一致 —— 改动任何一侧都必须同步另一侧。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.global_index_bar import GlobalIndexDailyBar
from app.models.macro import MacroIndicator
from app.services.macro_service import MacroDataService

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> date | None:
    """Best-effort 把 str / date / datetime 转成 date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _infer_category(code: str) -> str:
    """按内部 code 推断分类，规则与前端 inferCategoryKey 逐条一致.

    顺序敏感：``us_dgs*`` / ``us_t10y*`` 必须先于 ``usd_*`` 前缀判断
    （us_dgs10 等利率代码也以 us_ 开头，不能落进 fx 桶）。
    """
    code_l = (code or "").lower()
    if code_l.startswith("us_dgs") or code_l.startswith("us_t10y"):
        return "rate"
    if code_l == "us_vix":
        return "vol"
    if code_l.startswith(("global_dxy", "global_usdjpy", "usd_")):
        return "fx"
    if code_l.startswith(("global_brent", "global_wti")):
        return "commodity"
    return "index"


def _meta_from_registries(code: str) -> dict[str, Any]:
    """从静态 registry 兜底元数据（macro_indicator 尚无该 code 的行时）.

    覆盖 yfinance 四个 registry + A 股 registry；FRED 序列的
    meta 总能从 macro_indicator 取到，不走这里。
    """
    from app.data.providers.yfinance_indices_provider import (
        GLOBAL_COMMODITY_REGISTRY,
        GLOBAL_FOREX_REGISTRY,
        GLOBAL_INDEX_REGISTRY,
        GLOBAL_RATES_REGISTRY,
    )
    from app.services.macro.global_indices_fetcher import A_SHARE_INDEX_REGISTRY

    for registry in (
        GLOBAL_INDEX_REGISTRY,
        GLOBAL_FOREX_REGISTRY,
        GLOBAL_RATES_REGISTRY,
        GLOBAL_COMMODITY_REGISTRY,
    ):
        for meta in registry:
            if meta.code == code:
                return {
                    "region": getattr(meta, "region", "global"),
                    "name_zh": meta.name_zh,
                    "name_en": meta.name_en,
                    "unit": meta.unit,
                    "source": "yfinance",
                }
    for entry in A_SHARE_INDEX_REGISTRY:
        if entry["code"] == code:
            return {
                "region": "global",
                "name_zh": entry["name_zh"],
                "name_en": None,
                "unit": "指数",
                "source": "akshare",
            }
    return {
        "region": "global",
        "name_zh": code,
        "name_en": None,
        "unit": "",
        "source": "",
    }


class GlobalIndexBarService:
    """全球指数日线 bars 的读写助手."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── write-side ───────────────────────────────────────────────

    def upsert_bars(self, bars: list[dict[str, Any]]) -> int:
        """按 (code, trade_date, source) 幂等 upsert 一批 bars.

        每个 bar dict 必须含 ``code`` / ``trade_date``（date 或
        ``YYYY-MM-DD`` 字符串）/ ``close``；``open`` / ``high`` /
        ``low`` / ``volume`` 可空；``source`` 缺省 ``"yfinance"``。
        已存在的行更新 O/H/L/C/V 与 fetched_at，不存在则插入。
        返回处理的行数（插入 + 更新合计）。
        """
        if not bars:
            return 0

        # 按 (code, source) 分组，批量预取已存在的 trade_date，
        # 避免逐行 SELECT（一次 3mo 刷新约 1200 行）。
        grouped: dict[tuple[str, str], list[tuple[dict, date]]] = defaultdict(list)
        for bar in bars:
            code = bar.get("code")
            trade_date = _parse_date(bar.get("trade_date"))
            close = bar.get("close")
            if not code or trade_date is None or close is None:
                continue
            source = bar.get("source") or "yfinance"
            grouped[(code, source)].append((bar, trade_date))

        processed = 0
        for (code, source), group in grouped.items():
            dates = [d for _, d in group]
            existing_rows = (
                self.db.query(GlobalIndexDailyBar)
                .filter(
                    GlobalIndexDailyBar.code == code,
                    GlobalIndexDailyBar.source == source,
                    GlobalIndexDailyBar.trade_date.in_(dates),
                )
                .all()
            )
            existing_map = {r.trade_date: r for r in existing_rows}
            for bar, trade_date in group:
                row = existing_map.get(trade_date)
                if row is None:
                    self.db.add(GlobalIndexDailyBar(
                        code=code,
                        trade_date=trade_date,
                        source=source,
                        open=bar.get("open"),
                        high=bar.get("high"),
                        low=bar.get("low"),
                        close=float(bar["close"]),
                        volume=bar.get("volume"),
                    ))
                else:
                    row.open = bar.get("open")
                    row.high = bar.get("high")
                    row.low = bar.get("low")
                    row.close = float(bar["close"])
                    row.volume = bar.get("volume")
                    row.fetched_at = datetime.utcnow()
                processed += 1
        self.db.commit()
        return processed

    # ── read-side ────────────────────────────────────────────────

    def get_bars(
        self,
        code: str,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        limit: int = 1500,
    ) -> list[GlobalIndexDailyBar]:
        """单 code 的 bars，日期升序；``limit`` 取最新 N 条.

        先按日期倒序取最新 ``limit`` 条，再反转为升序返回 —— 与
        ``MacroDataService.get_series`` 的窗口语义一致。
        """
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        stmt = select(GlobalIndexDailyBar).where(GlobalIndexDailyBar.code == code)
        if start:
            stmt = stmt.where(GlobalIndexDailyBar.trade_date >= start)
        if end:
            stmt = stmt.where(GlobalIndexDailyBar.trade_date <= end)
        stmt = stmt.order_by(GlobalIndexDailyBar.trade_date.desc()).limit(limit)
        return list(reversed(self.db.execute(stmt).scalars().all()))

    def has_bars(self, code: str) -> bool:
        """该 code 是否已有任意一条 bars（决定详情页走 K 线还是折线）."""
        row = (
            self.db.query(GlobalIndexDailyBar.code)
            .filter(GlobalIndexDailyBar.code == code)
            .first()
        )
        return row is not None

    def get_detail(
        self,
        code: str,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        limit: int = 1500,
    ) -> dict[str, Any] | None:
        """详情页聚合：OHLC 分支优先，macro_indicator 折线兜底.

        返回 dict 的结构与 ``GET /macro/indicators/{code}/detail``
        的响应契约一一对应；两路皆无数据时返回 None（→ 404）。
        """
        if self.has_bars(code):
            return self._detail_from_bars(code, start_date, end_date, limit)
        return self._detail_from_macro(code, start_date, end_date, limit)

    # ── 内部分支实现 ─────────────────────────────────────────────

    def _meta_for_code(self, code: str) -> dict[str, Any]:
        """元数据：优先 macro_indicator 最新行，registry 兜底."""
        row = (
            self.db.query(MacroIndicator)
            .filter(MacroIndicator.code == code)
            .order_by(MacroIndicator.period.desc())
            .first()
        )
        if row is not None:
            return {
                "region": row.region,
                "name_zh": row.name_zh,
                "name_en": row.name_en,
                "unit": row.unit or "",
                "source": row.source,
            }
        return _meta_from_registries(code)

    def _detail_from_bars(
        self,
        code: str,
        start_date: date | str | None,
        end_date: date | str | None,
        limit: int,
    ) -> dict[str, Any]:
        """OHLC 分支：latest / stats / ohlc 全部由 bars 计算."""
        meta = self._meta_for_code(code)

        # 窗口内 bars（响应的 ohlc 数组）
        window_bars = self.get_bars(code, start_date, end_date, limit)

        # latest：全量最新两条（不受请求窗口限制）
        latest_two = self.get_bars(code, limit=2)
        latest = None
        if latest_two:
            last = latest_two[-1]
            prev_close = latest_two[-2].close if len(latest_two) > 1 else None
            latest = {
                "period": last.trade_date.isoformat(),
                "value": float(last.close),
                "prev_value": float(prev_close) if prev_close is not None else None,
                "change_abs": None,
                "change_pct": None,
            }
            if prev_close not in (None, 0):
                latest["change_abs"] = round(float(last.close) - float(prev_close), 6)
                latest["change_pct"] = round(
                    (float(last.close) - float(prev_close)) / float(prev_close) * 100.0,
                    6,
                )

        # stats：first/last/count 基于全量；52 周高低基于近 365 天
        first_d, last_d, count = self.db.execute(
            select(
                func.min(GlobalIndexDailyBar.trade_date),
                func.max(GlobalIndexDailyBar.trade_date),
                func.count(),
            ).where(GlobalIndexDailyBar.code == code)
        ).one()
        high_52w, low_52w = self._window_high_low_52w(code, last_d)

        return {
            "code": code,
            "region": meta["region"],
            "name_zh": meta["name_zh"],
            "name_en": meta["name_en"],
            "unit": meta["unit"],
            "source": meta["source"],
            "category": _infer_category(code),
            "has_ohlc": True,
            "latest": latest,
            "stats": {
                "first_period": first_d.isoformat() if first_d else None,
                "last_period": last_d.isoformat() if last_d else None,
                "count": int(count or 0),
                "high_52w": high_52w,
                "low_52w": low_52w,
            },
            "ohlc": [
                {
                    "date": b.trade_date.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": float(b.close),
                    "volume": b.volume,
                }
                for b in window_bars
            ],
            # OHLC 分支下 points 契约允许为空数组
            "points": [],
        }

    def _window_high_low_52w(
        self, code: str, last_d: date | None
    ) -> tuple[float | None, float | None]:
        """近 365 天的最高/最低（high 缺失的行回退 close）."""
        if last_d is None:
            return None, None
        cutoff = last_d - timedelta(days=365)
        rows = (
            self.db.query(GlobalIndexDailyBar.high, GlobalIndexDailyBar.low,
                          GlobalIndexDailyBar.close)
            .filter(
                GlobalIndexDailyBar.code == code,
                GlobalIndexDailyBar.trade_date >= cutoff,
            )
            .all()
        )
        highs = [r.high if r.high is not None else r.close for r in rows]
        lows = [r.low if r.low is not None else r.close for r in rows]
        highs = [float(v) for v in highs if v is not None]
        lows = [float(v) for v in lows if v is not None]
        return (max(highs) if highs else None, min(lows) if lows else None)

    def _detail_from_macro(
        self,
        code: str,
        start_date: date | str | None,
        end_date: date | str | None,
        limit: int,
    ) -> dict[str, Any] | None:
        """折线分支：复用 MacroDataService.get_series（纯 DB）.

        FRED 序列（利率/波动率等无 OHLC 的代码）走这里。
        """
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        series = MacroDataService(self.db).get_series(
            code=code, start_date=start, end_date=end, limit=limit
        )
        if series is None:
            return None

        points = series["points"]
        latest = None
        if points:
            last_p = points[-1]
            prev_value = points[-2]["value"] if len(points) > 1 else None
            latest = {
                "period": last_p["period"].isoformat(),
                "value": float(last_p["value"]),
                "prev_value": float(prev_value) if prev_value is not None else None,
                "change_abs": None,
                "change_pct": None,
            }
            if prev_value not in (None, 0):
                latest["change_abs"] = round(
                    float(last_p["value"]) - float(prev_value), 6
                )
                latest["change_pct"] = round(
                    (float(last_p["value"]) - float(prev_value))
                    / float(prev_value) * 100.0,
                    6,
                )

        # stats 基于窗口内 points（折线分支没有全量聚合查询，
        # get_series 本身已按 limit 截断，与 OHLC 分支的全量语义
        # 略有差异但满足契约的 nullable 字段要求）
        high_52w, low_52w = None, None
        if points:
            last_period = points[-1]["period"]
            cutoff = last_period - timedelta(days=365)
            window_vals = [
                float(p["value"]) for p in points if p["period"] >= cutoff
            ]
            if window_vals:
                high_52w, low_52w = max(window_vals), min(window_vals)

        return {
            "code": series["code"],
            "region": series["region"],
            "name_zh": series["name_zh"],
            "name_en": series["name_en"],
            "unit": series["unit"],
            "source": series["source"],
            "category": _infer_category(code),
            "has_ohlc": False,
            "latest": latest,
            "stats": {
                "first_period": points[0]["period"].isoformat() if points else None,
                "last_period": points[-1]["period"].isoformat() if points else None,
                "count": len(points),
                "high_52w": high_52w,
                "low_52w": low_52w,
            },
            "ohlc": None,
            "points": [
                {"period": p["period"].isoformat(), "value": float(p["value"])}
                for p in points
            ],
        }
