"""Celery application configuration.

Uses the existing Redis instance as both broker and result backend so that
long-running tasks (indicator calculation, cninfo backfill) can be executed
independent of the FastAPI / backend container lifecycle.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ad_research",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.indicator",
        "app.tasks.cninfo",
        "app.tasks.cninfo_pdf",
    ],
)

celery_app.conf.update(
    # Serialize task arguments as JSON for simplicity and inspectability.
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Results are useful for debugging/manual triggers but should expire quickly
    # to avoid filling Redis.
    result_expires=3600,
    # Use UTC internally; timestamps are converted by the client as needed.
    timezone="UTC",
    enable_utc=True,
    # Redis broker visibility_timeout: 指标任务可能跑 4-8 小时，必须大于最长任务
    # 运行时间，否则 Redis 会重复投递同一任务。
    broker_transport_options={"visibility_timeout": 43200},
    # Long-running tasks benefit from late ack: if the worker is killed mid-task,
    # the task is redelivered to another worker.  Downside is that tasks must be
    # idempotent, which our DB upserts guarantee.
    task_acks_late=True,
    # Do not prefetch more than one task per worker process; fair scheduling for
    # mixed-length jobs.
    worker_prefetch_multiplier=1,
    # Default queue name.
    task_default_queue="celery",
    # Track started state so callers can see "PENDING" vs "STARTED".
    task_track_started=True,
    # Route long-running tasks to dedicated queues so they don't block each
    # other on the default ``celery`` queue.  Workers listen to all three
    # queues (``-Q celery,indicator,cninfo``), but routing keeps indicator
    # calculation responsive even when a large cninfo backfill is in flight.
    task_routes={
        "app.tasks.indicator.*": {"queue": "indicator"},
        "app.tasks.cninfo.*": {"queue": "cninfo"},
        "app.tasks.cninfo_pdf.*": {"queue": "cninfo"},
    },
)

# Convenience alias used by scripts and the scheduler.
celery = celery_app
