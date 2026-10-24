"""Celery tasks for indicator calculation.

These tasks offload CPU/DB-heavy indicator recalculation from the backend
container to dedicated celery workers.
"""

import json
import logging
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client
from app.data.indicators.calculator import (
    batch_calculate_indicators,
    etl_job_name_for_market,
)
from app.models.etf import ETFIndicator, ETFInfo
from app.models.etl import ETLLog

logger = logging.getLogger(__name__)

# ── Indicator completion marker (P0-1, 2026-10-25) ─────────────────────────
#
# 背景：docs/dev-notes/20261025-backend-health-survey.md P0-1。调度器把
# ``calculate_indicators.delay(...)`` 投递出去后 with 块结束即释放
# ``daily_pipeline`` 锁，但指标任务本身在 Celery 里还要跑 4-6h（SQL 后端
# 逐 chunk 渐进 commit）。下游的评分(08:30)/信号(09:00) 只等锁，等于在
# 半宇宙指标集上算横截面。
#
# 本任务成功 / 最终失败时向 Redis 写**完成标记**，下游凭标记（而不是凭
# 锁的释放）判断指标集是否完整。key 按 market 作用域区分：A股 跑法写
# ``ad:indicator:done:A股:{date}``，全市场跑法（market_filter=None）写
# ``ad:indicator:done:ALL:{date}``——A股 标记绝不放行全市场门控（反之
# 亦然）。
INDICATOR_DONE_KEY_PREFIX = "ad:indicator:done"
# TTL 8 天：覆盖周末 + 周一重试窗口，又不至于在 Redis 里无限累积
# （每日 3 个市场 key，量级极小）。
INDICATOR_DONE_TTL_SECONDS = 8 * 24 * 3600

# 下游门控的最低覆盖率阈值。低于此值说明指标集明显不完整（如两个 A 股
# 日线 ETL 之一失败），横截面百分位会系统性失真，宁可跳过重试。
INDICATOR_MIN_COVERAGE = 0.95


def indicator_done_key(market_filter: str | None, target_date: date) -> str:
    """Return the Redis completion-marker key for a market-scoped run.

    ``market_filter=None``（全市场跑法）使用 ``ALL`` 作用域——与任何单市场
    的 key 都不同，防止 A 股标记误放行全市场门控（survey P0-1 要求 c）。
    """
    scope = market_filter if market_filter else "ALL"
    return f"{INDICATOR_DONE_KEY_PREFIX}:{scope}:{target_date.isoformat()}"


def write_indicator_completion_marker(
    db: Session,
    *,
    market_filter: str | None,
    target_date: date,
    status: str,
    error: BaseException | str | None = None,
) -> dict:
    """Write the Redis completion marker for one indicator run.

    ``universe_count`` / ``indicator_rows`` 都从 DB 实时统计（同一把尺子）：
    universe = 该市场 active 标的数；rows = 这些标的中 ``trade_date =
    target_date`` 已有指标行的数量。coverage = rows / universe。

    标记只反映 DB 现状——失败路径同样统计（半途 rows 就是当时的落库量），
    绝不静默。任何异常都被吞掉并记日志：标记写入失败不能让任务本身报错。
    """
    payload: dict = {}
    try:
        universe = (
            db.execute(
                select(func.count())
                .select_from(ETFInfo)
                .where(ETFInfo.status == "active", ETFInfo.market == market_filter)
            ).scalar()
            or 0
        )
        rows = (
            db.execute(
                select(func.count())
                .select_from(ETFIndicator)
                .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
                .where(
                    ETFInfo.status == "active",
                    ETFInfo.market == market_filter,
                    ETFIndicator.trade_date == target_date,
                )
            ).scalar()
            or 0
        )
        payload = {
            "status": status,
            "completed_at": datetime.now(UTC).isoformat(),
            "target_date": target_date.isoformat(),
            "market": market_filter if market_filter else "ALL",
            "universe_count": universe,
            "indicator_rows": rows,
            "coverage": (rows / universe) if universe > 0 else 1.0,
        }
        if error is not None:
            payload["error"] = str(error)[:500]
        get_redis_client().set(
            indicator_done_key(market_filter, target_date),
            json.dumps(payload),
            ex=INDICATOR_DONE_TTL_SECONDS,
        )
        logger.info(
            "indicator completion marker written: market=%s date=%s status=%s "
            "coverage=%s (%d/%d)",
            payload["market"],
            target_date,
            status,
            f"{payload['coverage']:.1%}",
            rows,
            universe,
        )
    except Exception:
        # 标记失败不能阻塞任务结果上报；下游门控会把「无标记」当作未完成，
        # 语义上安全（宁可跳过评分也不在半宇宙上算横截面）。
        logger.exception(
            "Failed to write indicator completion marker " "(market=%s date=%s status=%s)",
            market_filter,
            target_date,
            status,
        )
    return payload


def _latest_etl_status(db: Session, market_filter: str | None) -> str | None:
    """Read back the terminal status of the run we just executed.

    ``batch_calculate_indicators`` 只在收尾时写终态 ETLLog 行（success /
    partial）；读最新一行即可拿到 partial 语义。查不到（例如 batch 被
    monkeypatch / 极早返回）则返回 None，由调用方按 success 处理。
    """
    try:
        row = (
            db.query(ETLLog)
            .filter(ETLLog.job_name == etl_job_name_for_market(market_filter))
            .order_by(ETLLog.created_at.desc())
            .first()
        )
        return row.status if row else None
    except Exception:
        logger.exception("Failed to read back ETLLog status for market=%s", market_filter)
        return None


def _write_completion_marker_for_run(
    db: Session,
    *,
    target_date: date | None,
    market_filter: str | None,
    instrument_type_filter: str | None,
    code_prefix: str | list[str] | None,
    status_override: str | None = None,
    error: BaseException | str | None = None,
) -> None:
    """Dispatch marker writing for one ``calculate_indicators`` invocation.

    只有 whole-market 运行（无 code_prefix / instrument_type 分片、带显式
    target_date）才写标记：分片任务共享同一 (market, date) key，逐片覆写会
    互相污染；而门控只关心调度器投递的市场级跑法（A股 08:00/17:00、US
    05:30、CRYPTO 08:30 都带显式日期）。跳过时记 info 日志，绝不无痕。
    """
    if target_date is None:
        logger.info(
            "indicator completion marker skipped: no explicit target_date " "(market=%s)",
            market_filter,
        )
        return
    if code_prefix is not None or instrument_type_filter is not None:
        logger.info(
            "indicator completion marker skipped: sharded run "
            "(market=%s code_prefix=%s instrument_type=%s)",
            market_filter,
            code_prefix,
            instrument_type_filter,
        )
        return
    status = status_override or _latest_etl_status(db, market_filter) or "success"
    write_indicator_completion_marker(
        db,
        market_filter=market_filter,
        target_date=target_date,
        status=status,
        error=error,
    )


def _release_indicator_date_lock(target_date: date | None, full_history: bool) -> None:
    """释放调度器预定的指标日期锁（2026-08-08 循环/断点审计）。

    调度侧 ``_acquire_indicator_date_lock`` 只预定不释放；若任务失败，
    17:00 兜底会连续多日被同一把锁挡住。任务成功或最终失败后在此释放。
    """
    if target_date is None:
        return
    try:
        client = get_redis_client()
        lock_key = f"ad_research:indicator:a_share:{target_date.isoformat()}" f":fh={full_history}"
        client.delete(lock_key)
    except Exception:
        # 释放失败不阻塞任务结果上报；锁有 6h TTL 兜底。
        pass


def _parse_date(value: date | str | None) -> date | None:
    """Accept either a date object or an ISO date string."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="indicator",
    # 防止任务无限挂起、触发 Redis 重复投递；先给 4h 软超时报警，6h 强制终止。
    soft_time_limit=4 * 3600,
    time_limit=6 * 3600,
)
def calculate_indicators(
    self,
    target_date: date | str | None = None,
    full_history: bool = False,
    market_filter: str = "A股",
    instrument_type_filter: str | None = None,
    code_prefix: str | list[str] | None = None,
) -> int:
    """Calculate technical/risk indicators for all active instruments in a market.

    Args:
        target_date: Only compute indicators up to and including this date.
            Accepts ``datetime.date`` or ISO string ``"YYYY-MM-DD"``.
        full_history: If True, compute every historical trade date instead of
            only the latest day.
        market_filter: Market to filter by, e.g. ``"A股"``, ``"US"``,
            ``"CRYPTO"``.
        instrument_type_filter: Optional secondary filter on
            ``etf_info.instrument_type`` — pass ``"ETF"`` or ``"STOCK"`` to
            narrow the universe. Defaults to ``None`` which keeps the
            original behaviour where ``market_filter='A股'`` already covers
            every active A-share code in a single pass.
        code_prefix: Optional prefix filter on ``etf_info.code``. Used to
            shard a large universe (e.g. A-share stocks) across multiple
            workers without code duplication.

    Returns:
        Number of indicator records written.

    成功 / 最终失败都会写 Redis 完成标记（P0-1，见模块头注释）：下游
    评分 / 信号以标记为准判断指标集完整性，而不是依赖调度器早已释放的
    ``daily_pipeline`` 锁。中间态重试不写标记——此时结论未定，残留旧
    标记（或无标记）会让下游继续等待，语义正确。
    """
    effective_date = _parse_date(target_date)
    db = SessionLocal()
    try:
        count = batch_calculate_indicators(
            db,
            target_date=effective_date,
            full_history=full_history,
            market_filter=market_filter,
            instrument_type_filter=instrument_type_filter,
            code_prefix=code_prefix,
        )
        # 成功即释放调度侧日期锁，让 17:00 兜底 / 次日主跑不受残留锁阻塞。
        _release_indicator_date_lock(effective_date, full_history)
        _write_completion_marker_for_run(
            db,
            target_date=effective_date,
            market_filter=market_filter,
            instrument_type_filter=instrument_type_filter,
            code_prefix=code_prefix,
        )
        return count
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # 重试耗尽（最终失败）：释放锁，避免后续兜底被永久挡住；
            # 并写 failed 完成标记，让下游门控明确拒绝（绝不静默）。
            _release_indicator_date_lock(effective_date, full_history)
            _write_completion_marker_for_run(
                db,
                target_date=effective_date,
                market_filter=market_filter,
                instrument_type_filter=instrument_type_filter,
                code_prefix=code_prefix,
                status_override="failed",
                error=exc,
            )
        # Retry on transient DB/lock errors; permanent errors will raise after
        # max_retries.
        raise self.retry(exc=exc)
    finally:
        db.close()
