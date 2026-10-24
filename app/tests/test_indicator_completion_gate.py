"""P0-1 评分/信号与指标计算的跨进程竞态——完成标记门控测试（2026-10-25）。

背景见 docs/dev-notes/20261025-backend-health-survey.md P0-1：
08:00 指标任务经 ``calculate_indicators.delay(...)`` 投递后，调度器 with
块结束即释放 ``daily_pipeline`` 锁；指标任务在 Celery worker 里跑 4-6h
（SQL 后端逐 chunk ``db.commit()`` 渐进落库）。08:30 评分 / 09:00 信号
只等锁——等到的锁早已释放 → 在半宇宙指标集上算横截面百分位并落库，
错误分数持续一整天。

本文件锁定修复后的硬语义：

1. Celery 指标任务成功 / 最终失败必须写 Redis 完成标记
   （``ad:indicator:done:{market}:{date}``，值含 completed_at /
   universe_count / indicator_rows / coverage），失败路径绝不静默；
2. 评分 / 信号入口在标记缺失、status=failed 或覆盖率 <95% 时必须跳过
   本轮（ScoringService / SignalService 不得被调用），log warning，
   并安排 30 分钟一次的延时重试（当日 20:00 Asia/Shanghai 后放弃并
   log error）；
3. 标记按 market 作用域区分——A股 标记不能放行全市场门控（反之亦然）。

另含两个 P1 的回归测试：

* stuck-ETL 清理按 job 分级阈值（指标 6h / 信号 4h / adj_factor 4h /
  其余默认 2h，见 survey P1-1）；
* 调度循环 ``except: continue`` 的可观测性（warning 日志 + 带日期的
  Redis 失败计数器，见 survey P1-3）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app.core.scheduler as sched
import app.tasks.indicator as indicator_tasks
from app.core.redis_client import get_redis_client
from app.models.etf import ETFIndicator, ETFInfo, InstrumentDailyBar
from app.models.etl import ETLLog, StrategyConfig
from app.models.pool import ETFPools

TARGET = date(2026, 10, 23)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeScheduler:
    """Record add_job calls without running anything."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def add_job(
        self,
        func,
        trigger=None,
        id=None,
        name=None,
        replace_existing=False,
        max_instances=None,
        **kwargs,
    ):
        self.jobs[id] = {"func": func, "trigger": trigger, "kwargs": kwargs}

    def get_jobs(self):
        return []

    def __getattr__(self, _name):
        return lambda *a, **kw: None


@pytest.fixture
def gate_db(db_session, monkeypatch):
    """把 scheduler / tasks.indicator / etl_log_helper 的 SessionLocal
    都指到内存 SQLite（照 test_score_signal_etl_wiring.etl_db 的模式）。"""
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(sched, "SessionLocal", factory)
    monkeypatch.setattr("app.core.database.SessionLocal", factory)
    monkeypatch.setattr(indicator_tasks, "SessionLocal", factory)
    return db_session


def _seed_a_share_universe(
    db,
    *,
    n_codes: int = 10,
    n_indicators: int | None = None,
    bars_date: date = TARGET,
    indicator_date: date = TARGET,
) -> list[str]:
    """Seed active A股 instruments + one daily bar（供 target date 解析）
    + 部分/全部指标行。"""
    if n_indicators is None:
        n_indicators = n_codes
    codes = []
    for i in range(n_codes):
        code = f"5{i:05d}.SH"
        codes.append(code)
        db.add(ETFInfo(code=code, name=f"ETF{i}", market="A股", status="active"))
    db.commit()
    db.add(InstrumentDailyBar(etf_code=codes[0], trade_date=bars_date, close=1.0))
    db.commit()
    for code in codes[:n_indicators]:
        db.add(ETFIndicator(etf_code=code, trade_date=indicator_date, ma5=1.0))
    db.commit()
    return codes


def _make_scoring_stub(calls: list):
    class _StubScoringService:
        def __init__(self, db):
            pass

        def calculate_daily_scores(self, trade_date=None):
            calls.append(trade_date)
            return {1: 5}

    return _StubScoringService


def _marker_key(market: str | None, d: date) -> str:
    from app.tasks.indicator import indicator_done_key

    return indicator_done_key(market, d)


# ---------------------------------------------------------------------------
# 任务 1a：Celery 指标任务写完成标记
# ---------------------------------------------------------------------------


def test_indicator_done_key_separates_market_scopes():
    """A股标记 ≠ 全市场(ALL)标记 ≠ US 标记 ≠ 其他日期（P0-1 要求 c）。"""
    from app.tasks.indicator import indicator_done_key

    keys = {
        indicator_done_key("A股", TARGET),
        indicator_done_key(None, TARGET),
        indicator_done_key("US", TARGET),
        indicator_done_key("A股", TARGET + timedelta(days=1)),
    }
    assert len(keys) == 4
    assert indicator_done_key("A股", TARGET).endswith(f"A股:{TARGET.isoformat()}")
    assert indicator_done_key(None, TARGET).endswith(f"ALL:{TARGET.isoformat()}")


def test_indicator_task_writes_success_marker(gate_db, monkeypatch):
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    monkeypatch.setattr(
        indicator_tasks,
        "batch_calculate_indicators",
        lambda db, **kw: 10,
    )

    result = indicator_tasks.calculate_indicators(
        target_date=TARGET.isoformat(),
        full_history=False,
        market_filter="A股",
    )
    assert result == 10

    raw = get_redis_client().get(_marker_key("A股", TARGET))
    assert raw is not None, "指标任务成功后必须写完成标记"
    payload = json.loads(raw)
    assert payload["status"] == "success"
    assert payload["universe_count"] == 10
    assert payload["indicator_rows"] == 10
    assert payload["coverage"] == 1.0
    assert payload["completed_at"]
    assert payload["target_date"] == TARGET.isoformat()

    # 集成：写完标记后门控直接放行
    ok, reason = sched.check_indicator_completion("A股", TARGET)
    assert ok, reason


def test_indicator_task_writes_failed_marker_on_final_failure(gate_db, monkeypatch):
    def _boom(db, **kw):
        raise RuntimeError("chunk exploded")

    monkeypatch.setattr(indicator_tasks, "batch_calculate_indicators", _boom)
    task = indicator_tasks.calculate_indicators
    # 直接调用 + push_request(retries=max) 模拟重试耗尽后的最终失败分支
    task.push_request(retries=task.max_retries)
    try:
        with pytest.raises(RuntimeError):
            task(target_date=TARGET.isoformat(), market_filter="A股")
    finally:
        task.pop_request()

    raw = get_redis_client().get(_marker_key("A股", TARGET))
    assert raw is not None, "最终失败路径也必须写标记（绝不静默）"
    payload = json.loads(raw)
    assert payload["status"] == "failed"
    assert "chunk exploded" in (payload.get("error") or "")

    ok, _reason = sched.check_indicator_completion("A股", TARGET)
    assert not ok, "failed 标记不得放行评分"


def test_partial_marker_with_sufficient_coverage_releases_gate(gate_db):
    """partial（个别标的失败）但覆盖率达标 → 放行；覆盖率检查兜底质量。"""
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter="A股", target_date=TARGET, status="partial"
    )
    ok, reason = sched.check_indicator_completion("A股", TARGET)
    assert ok, reason


# ---------------------------------------------------------------------------
# 任务 1b：评分 / 信号入口门控
# ---------------------------------------------------------------------------


def test_score_skipped_when_lock_released_but_marker_missing(gate_db, monkeypatch, caplog):
    """红测复现 P0-1：daily_pipeline 锁早已释放（无竞争），但完成标记
    缺失（指标任务仍在 Celery 里跑）→ 评分必须跳过并安排重试。"""
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    calls: list = []
    monkeypatch.setattr(sched, "ScoringService", _make_scoring_stub(calls))
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)

    with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
        sched.run_score_calculation()

    assert calls == [], "完成标记缺失时绝不能算分（哪怕锁是空闲的）"
    assert any(
        k.startswith("indicator_gate_retry:score_calculation") for k in fake.jobs
    ), "跳过时必须安排延时重试"
    assert any(
        "Score calculation deferred" in r.getMessage() for r in caplog.records
    ), "跳过必须留 warning 日志"


def test_score_skipped_when_coverage_insufficient(gate_db, monkeypatch, caplog):
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=5)  # 50% 覆盖
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter="A股", target_date=TARGET, status="success"
    )
    calls: list = []
    monkeypatch.setattr(sched, "ScoringService", _make_scoring_stub(calls))
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)

    with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
        sched.run_score_calculation()

    assert calls == [], "覆盖率 <95% 时必须跳过"
    assert any("Score calculation deferred" in r.getMessage() for r in caplog.records)
    deferred = [
        r.getMessage() for r in caplog.records if "Score calculation deferred" in r.getMessage()
    ]
    assert "coverage" in deferred[0], "日志必须携带覆盖率不足的原因"


def test_score_runs_when_marker_ready(gate_db, monkeypatch):
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter="A股", target_date=TARGET, status="success"
    )
    calls: list = []
    monkeypatch.setattr(sched, "ScoringService", _make_scoring_stub(calls))

    result = sched.run_score_calculation()

    assert calls == [None], "门控通过后评分照常执行（trade_date 语义不变）"
    assert result is not None and result.get("written") == 5


def test_score_skips_when_no_a_share_bars(gate_db, monkeypatch):
    """无 A 股 bar（target date 无法解析）→ 显式跳过，不炸。"""
    calls: list = []
    monkeypatch.setattr(sched, "ScoringService", _make_scoring_stub(calls))
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)
    sched.run_score_calculation()
    assert calls == []
    assert fake.jobs == {}, "无法解析日期时不应安排重试（等次日调度）"


def test_score_retry_chain_runs_after_marker_appears(gate_db, monkeypatch):
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    calls: list = []
    monkeypatch.setattr(sched, "ScoringService", _make_scoring_stub(calls))
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)

    sched.run_score_calculation()
    assert calls == []

    # 指标任务完成、标记出现后，重试链一次性 job 补跑评分
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter="A股", target_date=TARGET, status="success"
    )
    retry_fn = fake.jobs[f"indicator_gate_retry:score_calculation:{TARGET.isoformat()}"]["func"]
    retry_fn()
    assert calls == [None]


def test_signal_skipped_when_marker_missing(gate_db, monkeypatch, caplog):
    _seed_a_share_universe(gate_db, n_codes=2, n_indicators=2)
    constructed: list = []

    class _StubSignalService:
        def __init__(self, db):
            constructed.append(db)

        def generate_signals(self, **kw):
            return []

        def generate_signals_universe(self, **kw):
            return []

    monkeypatch.setattr(sched, "SignalService", _StubSignalService)
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)

    with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
        sched.run_signal_generation()

    assert constructed == [], "完成标记缺失时绝不能生成信号"
    assert any(k.startswith("indicator_gate_retry:signal_generation") for k in fake.jobs)
    assert any("Signal generation deferred" in r.getMessage() for r in caplog.records)


def test_signal_runs_when_marker_ready(gate_db, monkeypatch):
    _seed_a_share_universe(gate_db, n_codes=2, n_indicators=2)
    gate_db.add(
        StrategyConfig(
            user_id=1,
            name="t",
            strategy_type="momentum",
            params={},
            is_active=True,
        )
    )
    gate_db.commit()
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter="A股", target_date=TARGET, status="success"
    )

    class _StubSignalService:
        def __init__(self, db):
            pass

        def generate_signals(self, **kw):
            return [object()]

    monkeypatch.setattr(sched, "SignalService", _StubSignalService)

    result = sched.run_signal_generation()

    assert result is not None
    assert result["written"] == 2  # 2 active instruments × 1 signal


def test_all_scope_marker_does_not_release_a_share_gate(gate_db):
    """P0-1 要求 c：全市场跑法写的 ALL 标记不得放行 A 股门控。"""
    _seed_a_share_universe(gate_db, n_codes=10, n_indicators=10)
    indicator_tasks.write_indicator_completion_marker(
        gate_db, market_filter=None, target_date=TARGET, status="success"
    )
    ok, reason = sched.check_indicator_completion("A股", TARGET)
    assert not ok
    assert "missing" in (reason or "")


# ---------------------------------------------------------------------------
# 任务 1b（续）：重试调度链——30 分钟一次、20:00 截止
# ---------------------------------------------------------------------------


def test_gate_retry_schedules_30min_one_shot(monkeypatch):
    from apscheduler.triggers.date import DateTrigger

    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 10, 23, 10, 0, tzinfo=tz)

    scheduled = sched._schedule_indicator_gate_retry(
        job_label="score_calculation",
        target_date=TARGET,
        attempt=0,
        retry_fn=lambda: None,
        now=now,
    )

    assert scheduled is True
    job = fake.jobs[f"indicator_gate_retry:score_calculation:{TARGET.isoformat()}"]
    assert isinstance(job["trigger"], DateTrigger)
    assert job["trigger"].run_date == now + timedelta(minutes=30)


def test_gate_retry_gives_up_after_daily_deadline(monkeypatch, caplog):
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)
    tz = ZoneInfo("Asia/Shanghai")

    with caplog.at_level(logging.ERROR, logger="app.core.scheduler"):
        scheduled = sched._schedule_indicator_gate_retry(
            job_label="score_calculation",
            target_date=TARGET,
            attempt=4,
            retry_fn=lambda: None,
            now=datetime(2026, 10, 23, 20, 30, tzinfo=tz),
        )

    assert scheduled is False
    assert fake.jobs == {}
    assert any(
        "giving up" in r.getMessage() for r in caplog.records
    ), "放弃时必须 log error，绝不无痕"


# ---------------------------------------------------------------------------
# 任务 2：stuck-ETL 清理按 job 分级阈值（survey P1-1）
# ---------------------------------------------------------------------------


def _seed_running_etl(db, job_name: str, started_minutes_ago: float) -> None:
    db.add(
        ETLLog(
            job_name=job_name,
            status="running",
            start_time=datetime.now(UTC) - timedelta(minutes=started_minutes_ago),
        )
    )
    db.commit()


def test_stuck_cleanup_spares_long_legit_signal_run(gate_db):
    """信号生成合法运行可到 4h（锁 TTL min(14400, ...)）——3h 不得误清。"""
    _seed_running_etl(gate_db, "signal_generation", 180)
    get_redis_client().set("lock:daily_pipeline", "alive-token")

    cleaned = sched.cleanup_stuck_etl_jobs()

    assert cleaned == 0
    row = gate_db.query(ETLLog).filter_by(job_name="signal_generation").one()
    assert row.status == "running", "未超过该 job 阈值的 running 行不得标 failed"
    assert (
        get_redis_client().get("lock:daily_pipeline") == "alive-token"
    ), "不得删除仍在被合法持有的活锁"


def test_stuck_cleanup_kills_signal_run_beyond_threshold(gate_db):
    _seed_running_etl(gate_db, "signal_generation", 300)  # 5h > 4h 阈值
    get_redis_client().set("lock:daily_pipeline", "alive-token")

    cleaned = sched.cleanup_stuck_etl_jobs()

    assert cleaned == 1
    row = gate_db.query(ETLLog).filter_by(job_name="signal_generation").one()
    assert row.status == "failed"
    assert get_redis_client().get("lock:daily_pipeline") is None


def test_stuck_cleanup_default_threshold_unchanged_for_ordinary_jobs(gate_db):
    _seed_running_etl(gate_db, "a_share_daily_etl", 150)  # 2.5h > 默认 2h
    assert sched.cleanup_stuck_etl_jobs() == 1
    _seed_running_etl(gate_db, "a_share_daily_etl", 90)  # 1.5h < 默认 2h
    assert sched.cleanup_stuck_etl_jobs() == 0


def test_stuck_cleanup_spares_indicator_calc_within_6h(gate_db):
    """指标 Celery 任务硬限 6h——5h 的 running 行不得误清。"""
    _seed_running_etl(gate_db, "indicator_calculation", 300)
    assert sched.cleanup_stuck_etl_jobs() == 0
    _seed_running_etl(gate_db, "indicator_calculation", 380)  # 6h20m > 6h
    assert sched.cleanup_stuck_etl_jobs() == 1


def test_stuck_cleanup_adj_factor_backfill_4h_threshold(gate_db):
    """adj_factor 回填锁 4h（redis_lock expire_seconds=14400）。"""
    _seed_running_etl(gate_db, "a_share_adj_factor_backfill", 210)  # 3.5h
    assert sched.cleanup_stuck_etl_jobs() == 0
    _seed_running_etl(gate_db, "a_share_adj_factor_backfill", 270)  # 4.5h
    assert sched.cleanup_stuck_etl_jobs() == 1


# ---------------------------------------------------------------------------
# 任务 3：调度循环失败可观测（survey P1-3）
# ---------------------------------------------------------------------------


def test_paper_trade_auto_failure_logged_and_counted(gate_db, monkeypatch, caplog):
    import app.services.paper_trading_service as pts

    class _FakePTS:
        def __init__(self, db):
            pass

        def get_accounts(self):
            return [SimpleNamespace(id=11), SimpleNamespace(id=12)]

        def auto_trade_from_signals(self, account_id):
            if account_id == 11:
                raise RuntimeError("quote timeout")
            return []

    monkeypatch.setattr(pts, "PaperTradingService", _FakePTS)

    with caplog.at_level(logging.WARNING, logger="app.core.scheduler"):
        sched.run_paper_trade_auto()

    key = f"ad:scheduler:loop_failure:paper_trade_auto:{date.today().isoformat()}"
    assert int(get_redis_client().get(key) or 0) == 1
    assert any("account:11" in r.getMessage() for r in caplog.records), "失败日志必须带账户上下文"


def test_signal_generation_per_item_failure_counted(gate_db, monkeypatch):
    gate_db.add(
        StrategyConfig(
            user_id=1,
            name="t",
            strategy_type="momentum",
            params={},
            is_active=True,
        )
    )
    gate_db.commit()
    etfs = [
        SimpleNamespace(code="OK1"),
        SimpleNamespace(code="BAD"),
    ]

    class _StubSignalService:
        def __init__(self, db):
            pass

        def generate_signals(self, *, etf_code, **kw):
            if etf_code == "BAD":
                raise RuntimeError("no indicator rows")
            return [object()]

    monkeypatch.setattr(sched, "SignalService", _StubSignalService)

    result = sched._run_signal_generation_locked(
        [{"id": 1, "strategy_type": "momentum", "params": {}}],
        etfs,
        target_date=TARGET,
    )

    assert result["failed"] == ["etf:BAD"]
    key = f"ad:scheduler:loop_failure:signal_generation:{date.today().isoformat()}"
    assert int(get_redis_client().get(key) or 0) == 1


def test_weekly_pool_report_failure_counted(gate_db, monkeypatch):
    gate_db.add(ETFPools(name="p1"))
    gate_db.commit()

    class _BoomReportService:
        def __init__(self, db):
            pass

        def generate_pool_report(self, **kw):
            raise RuntimeError("template missing")

    monkeypatch.setattr(sched, "ReportService", _BoomReportService)
    # pool_ids 查询用 scheduler 的 SessionLocal（gate_db 已 patch）
    sched.run_weekly_pool_reports()

    key = f"ad:scheduler:loop_failure:weekly_pool_reports:{date.today().isoformat()}"
    assert int(get_redis_client().get(key) or 0) == 1
