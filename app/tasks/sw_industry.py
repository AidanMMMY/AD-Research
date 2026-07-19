"""Celery tasks: SW industry index refresh (Phase 3 sector rotation).

Weekly refresh of the 31 申万2021 level-1 industry index returns
into ``sw_industry_index_return``. Schedule via scheduler
(CronTrigger weekly Monday 09:30 Asia/Shanghai) or dispatch manually:

    celery -A app.core.celery_app call \\
        app.tasks.sw_industry.refresh_sw_industry_returns
"""

import logging

from app.core.celery_app import celery_app
from app.data.pipelines.sw_industry_index import (
    SWIndustryIndexPipeline,
    run_once as _run_once,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="industry",
    # 31 个指数 × 6k+ 行/每个 = 大约 5min，加 2x headroom。
    soft_time_limit=600,
    time_limit=900,
)
def refresh_sw_industry_returns(self, lookback_days: int = 400) -> dict:
    """Refresh all 31 SW2021 level-1 industry index returns.

    Idempotent: UPSERTs on (sw_l1_code, trade_date). Safe to re-run.

    Args:
        lookback_days: AKShare 取全历史后本地 tail 多少天 (默认 400)。

    Returns:
        dict with ``codes_count`` / ``rows_written`` / ``errors`` keys.
    """
    try:
        result = _run_once(lookback_days=lookback_days)
    except Exception as exc:
        # 整批失败才重试；单条 industry 失败已被 pipeline 内部捕获。
        logger.exception("refresh_sw_industry_returns failed: %s", exc)
        raise self.retry(exc=exc)

    return {
        "codes_count": result.metadata.get("codes_count", 0),
        "rows_written": result.records_processed,
        "errors": result.errors,
        "warnings": result.warnings,
    }