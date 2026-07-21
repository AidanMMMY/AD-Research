"""Regression test: etl_log timestamps must be timezone-aware UTC.

Production issue (2026-07-21): ``ETLPipeline._create_log`` / ``_update_log``
used naive ``datetime.now()``, so local wall-clock time (Asia/Shanghai) was
stored into ``timestamptz`` columns as if it were UTC, shifting displayed
times by +8 hours.  The news jobs were unaffected because they go through
``app.core.etl_log_helper`` which already used ``datetime.now(timezone.utc)``.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd

from app.data.indicators.calculator import _log_etl
from app.data.pipelines.base import ETLPipeline
from app.models.etl import ETLLog


class _DummyPipeline(ETLPipeline):
    @property
    def job_name(self) -> str:
        return "dummy_job"

    def extract(self) -> pd.DataFrame:
        return pd.DataFrame()

    def load(self, data: pd.DataFrame) -> int:
        return 0


def _assert_utc(dt) -> None:
    assert dt is not None
    assert dt.tzinfo is not None, "timestamp must be timezone-aware"
    assert dt.utcoffset() == timedelta(0), "timestamp must be UTC"


def test_pipeline_create_log_writes_utc_start_time():
    db = MagicMock()
    pipeline = _DummyPipeline(provider=MagicMock(name="akshare"), db=db)
    pipeline.provider.name = "akshare"

    log = pipeline._create_log()

    assert isinstance(log, ETLLog)
    _assert_utc(log.start_time)


def test_pipeline_update_log_writes_utc_end_time():
    db = MagicMock()
    pipeline = _DummyPipeline(provider=MagicMock(), db=db)
    pipeline._log = ETLLog(job_name="dummy_job", status="running")

    pipeline._update_log("success", records=1)

    _assert_utc(pipeline._log.end_time)


def test_indicator_calculator_log_etl_writes_utc_end_time():
    db = MagicMock()
    from datetime import datetime, timezone

    start = datetime.now(timezone.utc)
    _log_etl(db, "indicator_calc", "success", 10, start, None)

    log = db.add.call_args[0][0]
    _assert_utc(log.start_time)
    _assert_utc(log.end_time)
