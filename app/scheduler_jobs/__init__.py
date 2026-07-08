"""Standalone scheduled job modules.

Each module in this package exposes a ``register(scheduler)`` function
that the central ``init_scheduler()`` in ``app.core.scheduler`` calls to
add jobs to the APScheduler instance. Keeping each job in its own module
makes it easy to add / remove / test jobs in isolation.
"""
