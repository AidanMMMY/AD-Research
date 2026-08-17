"""score_calculation / signal_generation 的 ETLLog wiring 测试（2026-08-17）。

背景：2026-08-06 全面审计发现这两个日终任务从未写 ``etl_log``——
运维面板（``app.api.v1.etl_status._TRACKED_JOBS`` 里有它们）永远显示
never_run，``cleanup_stuck_etl_jobs`` 也因为没有 ETLLog 行 / 锁映射
而无法定位它们的 Redis 锁。

本测试照 ``app/tests/digest/test_scheduler_wiring.py`` 的模式：
- ``_ETL_JOB_LOCK_MAP`` 含 score_calculation / signal_generation 映射
  （二者与 A 股日线共用 ``daily_pipeline`` 锁）；
- 锁内函数带 ``@record_etl`` 且 job_id 与 scheduler job id 一致；
- 功能级：锁内函数跑完后 etl_log 里确有对应 job_name 的行，
  状态 / records_count 符合 ``record_etl`` 的 dict 约定。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import app.core.scheduler as sched
from app.models.etl import ETLLog


# ---------------------------------------------------------------------------
# 静态 wiring
# ---------------------------------------------------------------------------

def test_lock_map_entries():
    assert sched._ETL_JOB_LOCK_MAP["score_calculation"] == "daily_pipeline"
    assert sched._ETL_JOB_LOCK_MAP["signal_generation"] == "daily_pipeline"


def test_run_functions_use_daily_pipeline_lock():
    """redis_lock 名必须与 _ETL_JOB_LOCK_MAP 一致（stuck 清理据此定位锁）。"""
    import inspect

    assert "redis_lock(_LOCK_DAILY_PIPELINE" in inspect.getsource(
        sched.run_score_calculation
    )
    assert "redis_lock(_LOCK_DAILY_PIPELINE" in inspect.getsource(
        sched.run_signal_generation
    )
    assert sched._LOCK_DAILY_PIPELINE == "daily_pipeline"


@pytest.mark.parametrize(
    ("fn_name", "job_id"),
    [
        ("_run_score_calculation_locked", "score_calculation"),
        ("_run_signal_generation_locked", "signal_generation"),
    ],
)
def test_record_etl_decorator_applied(fn_name, job_id):
    """锁内函数必须带 @record_etl("<job_id>")（闭包单元里能找到 job_id）。"""
    fn = getattr(sched, fn_name)
    assert fn.__name__ == fn_name
    cells = fn.__closure__ or ()
    values = [c.cell_contents for c in cells]
    assert job_id in values, (
        f"@record_etl 未生效或 job_id 不匹配（freevars={fn.__code__.co_freevars}）"
    )


def test_jobs_registered_with_matching_ids(monkeypatch):
    """scheduler 注册的 job id 必须与 ETLLog.job_name / 运维面板一致。"""

    class _FakeScheduler:
        def __init__(self):
            self.jobs: dict[str, dict] = {}

        def add_job(self, func, trigger=None, id=None, name=None,
                    replace_existing=False, max_instances=None, **kwargs):
            self.jobs[id] = {"func": func}

        def start(self):
            pass

        def __getattr__(self, _name):
            return lambda *a, **kw: None

    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)
    monkeypatch.setattr(sched, "cleanup_stuck_etl_jobs", lambda: 0)
    sched.init_scheduler()

    assert fake.jobs["score_calculation"]["func"] is sched.run_score_calculation
    assert fake.jobs["signal_generation"]["func"] is sched.run_signal_generation


# ---------------------------------------------------------------------------
# 功能级：锁内函数落 ETLLog
# ---------------------------------------------------------------------------

@pytest.fixture
def etl_db(db_session, monkeypatch):
    """把 scheduler / etl_log_helper 的 SessionLocal 都指到内存 SQLite。

    注意必须每次返回**新** session（共享同一 session 时，被测函数里
    ``with SessionLocal() as db:`` 退出会 close() 并把 start_log 的
    log_row 逐出 identity map，finish_log 的 UPDATE 就静默丢了——
    生产上每次 SessionLocal() 本来就是新 session，无此问题）。
    """
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(sched, "SessionLocal", factory)
    monkeypatch.setattr("app.core.database.SessionLocal", factory)
    return db_session


def test_score_calculation_writes_etl_log(etl_db, monkeypatch):
    class _FakeScoring:
        def __init__(self, db):
            pass

        def calculate_daily_scores(self, trade_date=None):
            return {1: 5, 2: 5}

    monkeypatch.setattr(sched, "ScoringService", _FakeScoring)

    result = sched._run_score_calculation_locked(target_date=date(2024, 8, 1))
    assert result["written"] == 10

    row = (
        etl_db.query(ETLLog)
        .filter(ETLLog.job_name == "score_calculation")
        .one()
    )
    assert row.status == "success"
    assert row.records_count == 10
    assert row.end_time is not None


def test_signal_generation_writes_etl_log(etl_db, monkeypatch):
    class _FakeSignalService:
        def __init__(self, db):
            pass

        def generate_signals(self, **kwargs):
            return [object()]  # 每个标的 1 条信号

    monkeypatch.setattr(sched, "SignalService", _FakeSignalService)

    strategies = [{"id": 1, "strategy_type": "unknown_type", "params": {}}]
    etfs = [SimpleNamespace(code="510300.SH"), SimpleNamespace(code="159915.SZ")]

    result = sched._run_signal_generation_locked(
        strategies, etfs, target_date=date(2024, 8, 1)
    )
    assert result["written"] == 2
    assert "failed" not in result

    row = (
        etl_db.query(ETLLog)
        .filter(ETLLog.job_name == "signal_generation")
        .one()
    )
    assert row.status == "success"
    assert row.records_count == 2


def test_signal_generation_partial_failure_recorded(etl_db, monkeypatch):
    """单标的失败不炸整轮，ETLLog 记 partial 且 failed 列表落 extra_data。"""
    class _FakeSignalService:
        def __init__(self, db):
            pass

        def generate_signals(self, *, etf_code, **kwargs):
            if etf_code == "BAD":
                raise RuntimeError("boom")
            return [object()]

    monkeypatch.setattr(sched, "SignalService", _FakeSignalService)

    strategies = [{"id": 1, "strategy_type": "unknown_type", "params": {}}]
    etfs = [SimpleNamespace(code="OK1"), SimpleNamespace(code="BAD")]

    result = sched._run_signal_generation_locked(
        strategies, etfs, target_date=date(2024, 8, 1)
    )
    assert result["written"] == 1
    assert result["failed"] == ["etf:BAD"]

    row = (
        etl_db.query(ETLLog)
        .filter(ETLLog.job_name == "signal_generation")
        .one()
    )
    assert row.status == "partial"
    assert row.records_count == 1
    assert (row.extra_data or {}).get("failed") == ["etf:BAD"]
