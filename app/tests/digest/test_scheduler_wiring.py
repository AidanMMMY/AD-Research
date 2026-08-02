"""Daily Digest 调度 wiring 测试（2026-08-03，B4）。

照 ``app/tests/news/test_expansion_wave_wiring.py`` 的模式：不真跑
scheduler（``init_scheduler()`` 会触达 DB / Redis），而是用 fake
scheduler 捕获 ``add_job`` 注册参数，断言：

- ``daily_digest`` job 已注册，函数指向 ``run_daily_digest``；
- cron 表达式为每天 06:30 Asia/Shanghai；
- replace_existing=True + max_instances=1；
- ``_ETL_JOB_LOCK_MAP`` 含 daily_digest 映射（健康页靠它定位锁）。
"""

from __future__ import annotations

import app.core.scheduler as sched


class _FakeScheduler:
    """捕获 add_job 注册参数的最小替身（init_scheduler 只用到这些方法）。"""

    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def add_job(self, func, trigger=None, id=None, name=None,
                replace_existing=False, max_instances=None, **kwargs):
        self.jobs[id] = {
            "func": func,
            "trigger": trigger,
            "name": name,
            "replace_existing": replace_existing,
            "max_instances": max_instances,
        }

    def start(self):
        pass

    def __getattr__(self, _name):
        # init_scheduler 里其他辅助调用（如 remove_job）一律 no-op
        return lambda *a, **kw: None


def _register_all(monkeypatch) -> dict[str, dict]:
    fake = _FakeScheduler()
    monkeypatch.setattr(sched, "scheduler", fake)
    monkeypatch.setattr(sched, "cleanup_stuck_etl_jobs", lambda: 0)
    sched.init_scheduler()
    return fake.jobs


def test_daily_digest_job_registered(monkeypatch):
    jobs = _register_all(monkeypatch)
    job = jobs.get("daily_digest")
    assert job is not None, "daily_digest job 未注册到 scheduler"
    assert job["func"] is sched.run_daily_digest
    assert job["replace_existing"] is True
    assert job["max_instances"] == 1


def test_daily_digest_cron_expression(monkeypatch):
    jobs = _register_all(monkeypatch)
    trigger = jobs["daily_digest"]["trigger"]
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == "6"
    assert fields["minute"] == "30"
    assert "Shanghai" in str(trigger.timezone)


def test_daily_digest_lock_map_entry():
    assert sched._ETL_JOB_LOCK_MAP["daily_digest"] == "daily_digest"


def test_run_daily_digest_uses_matching_lock():
    """redis_lock 名必须与 _ETL_JOB_LOCK_MAP 一致（健康页据此判 stuck）。"""
    import inspect

    source = inspect.getsource(sched.run_daily_digest)
    assert 'redis_lock("daily_digest"' in source


def test_record_etl_decorator_applied():
    """_run_daily_digest_locked 必须带 @record_etl("daily_digest")。

    装饰器用 functools.wraps，包一层后 __wrapped__ 指向原函数；
    这里通过闭包单元里的 job_id 常量验证装饰器确实生效。
    """
    fn = sched._run_daily_digest_locked
    assert fn.__name__ == "_run_daily_digest_locked"
    # record_etl 返回 wrapper(*args, **kwargs)，其闭包引用 start_log 时
    # 会用到 job_id="daily_digest"；直接检查 wrapper 的自由变量包含它。
    free_vars = fn.__code__.co_freevars
    cells = fn.__closure__ or ()
    values = [c.cell_contents for c in cells]
    assert "daily_digest" in values, (
        f"@record_etl 未生效或 job_id 不匹配（freevars={free_vars}）"
    )
