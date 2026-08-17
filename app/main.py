"""FastAPI application entry point."""

import fcntl
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

# Import strategy modules so all built-in strategies self-register.
import app.strategies  # noqa: F401
from app.api.v1 import (
    admin_users,
    analysis,
    attribution,
    auth,
    backtests,
    cninfo_reports,
    crypto,
    deployments,
    digest,
    etf_holdings,
    etf_holdings_stats,
    etf_scanner,
    etfs,
    etl,
    etl_status,
    favorites,
    fund_flow,
    futures,
    indicators,
    internal,
    learning,
    listing_events,
    live_trading,
    macro,
    market_data,
    microstructure,
    news,
    notifications,
    paper_trading,
    pools,
    reports,
    research,
    research_reports,
    scoring,
    screening,
    search_trends,
    sec_filings,
    sector_rotation,
    signals,
    stats,
    stock_fundamentals,
    stocks,
    strategies,
    stream,
)
from app.config import get_settings
from app.core.scheduler import init_scheduler, scheduler, shutdown_scheduler

settings = get_settings()

# ── Version / build identity ──
# Bump __version__ per release. The git short SHA is read once at startup
# from the GIT_SHA env var (preferred — set by the build system / CI) and
# falls back to a subprocess call to `git rev-parse --short HEAD`. When
# neither is available we report "unknown" so the field is never empty.
__version__ = "0.1.0"


def _resolve_git_sha() -> str:
    """Return the current git short SHA, or 'unknown' when unavailable."""
    env_sha = os.environ.get("GIT_SHA", "").strip()
    if env_sha:
        return env_sha[:7]

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip() or "unknown"
    except Exception:  # noqa: BLE001 — git not installed / not a repo / etc.
        return "unknown"


GIT_SHA = _resolve_git_sha()

app = FastAPI(
    title=settings.project_name,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
# Origins are loaded from the CORS_ORIGINS env var (comma-separated).
# Defaults:
#   - APP_ENV=development  → http://localhost:5173, http://localhost:3000
#   - otherwise            → empty list (same-origin only)
# A bare "*" in CORS_ORIGINS is only honored when APP_ENV=development;
# credentials are then disabled (Fetch spec disallows the combination).
_origins = settings.cors_origins_list
_uses_wildcard = "*" in _origins
_allow_credentials = not _uses_wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
# ── Readiness probe (ops P1-13) ──
# Delegates every dependency check to ``app.core.health.readiness_check`` so
# each container concern (DB, Redis, scheduler heartbeat, data staleness) is
# reported per-component. The endpoint ALWAYS returns HTTP 200 — even when a
# dependency is degraded — and carries the machine-readable verdict in the
# body (``status`` = "ok" | "degraded"). This lets ECS / monitors / on-call
# read *which* concern is unhealthy without SSH-ing in to inspect logs.
# Consumers:
#   - scripts/post_deploy_check.sh
#   - update.sh's polling loop (inspects body ``status``/``db``)
#   - external monitors (UptimeRobot, Nagios, etc.)
@app.get("/health")
def health_check():
    from app.core.health import readiness_check

    report = readiness_check()
    components = report.get("components", {})

    payload = {
        "status": report.get("status", "degraded"),
        "ready": report.get("ready", False),
        "version": __version__,
        "git_sha": GIT_SHA,
        # Back-compat: flatten the two critical components to top-level
        # "ok" / "error: <Name>" strings that existing scripts already parse.
        "db": (
            "ok"
            if components.get("db", {}).get("status") == "ok"
            else f"error: {components.get('db', {}).get('detail', 'unknown')}"
        ),
        "redis": (
            "ok"
            if components.get("redis", {}).get("status") == "ok"
            else f"error: {components.get('redis', {}).get('detail', 'unknown')}"
        ),
        "checked_at": report.get("checked_at"),
        "components": components,
    }
    # Always 200 — the body carries the real verdict (constraint: report
    # per-component status even when DB is degraded).
    return JSONResponse(content=payload, status_code=200)

# Include v1 routers
app.include_router(etfs.router, prefix=f"{settings.api_v1_prefix}/etfs", tags=["ETFs"])
app.include_router(
    etf_holdings.router, prefix=f"{settings.api_v1_prefix}", tags=["ETF Holdings"]
)
# Coverage / stats / blacklist router — powers the dashboard card and
# the post-ETL alert log in ``etf_holdings_quarterly``.  Same prefix
# as the operational etf_holdings router so the four endpoints land
# under ``/api/v1/etf-holdings/{stats,coverage,unavailable}``.
app.include_router(
    etf_holdings_stats.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["ETF Holdings"],
)
app.include_router(pools.router, prefix=f"{settings.api_v1_prefix}/pools", tags=["Pools"])
app.include_router(
    market_data.router, prefix=f"{settings.api_v1_prefix}/market-data", tags=["Market Data"]
)
app.include_router(
    indicators.router, prefix=f"{settings.api_v1_prefix}/indicators", tags=["Indicators"]
)
app.include_router(
    analysis.router, prefix=f"{settings.api_v1_prefix}/analysis", tags=["Analysis"]
)
app.include_router(etl.router, prefix=f"{settings.api_v1_prefix}/etl", tags=["ETL"])
app.include_router(
    etl_status.router, prefix=f"{settings.api_v1_prefix}/etl", tags=["ETL"]
)
app.include_router(
    scoring.router, prefix=f"{settings.api_v1_prefix}/scores", tags=["Scoring"]
)
app.include_router(
    screening.router, prefix=f"{settings.api_v1_prefix}/screen", tags=["Screening"]
)
app.include_router(
    reports.router, prefix=f"{settings.api_v1_prefix}/reports", tags=["Reports"]
)
app.include_router(
    digest.router, prefix=f"{settings.api_v1_prefix}/digest", tags=["Digest"]
)
app.include_router(
    research_reports.router,
    prefix=f"{settings.api_v1_prefix}/research-reports",
    tags=["Research Reports"],
)
app.include_router(
    auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"]
)
app.include_router(
    cninfo_reports.router,
    prefix=f"{settings.api_v1_prefix}/cninfo-reports",
    tags=["CNINFO Reports"],
)
app.include_router(
    admin_users.router,
    prefix=f"{settings.api_v1_prefix}/admin/users",
    tags=["Admin"],
)
app.include_router(
    deployments.router,
    prefix=f"{settings.api_v1_prefix}/admin",
    tags=["Admin"],
)
app.include_router(
    stats.router, prefix=f"{settings.api_v1_prefix}/stats", tags=["Statistics"]
)
app.include_router(
    sector_rotation.router, prefix=f"{settings.api_v1_prefix}/analysis", tags=["Analysis"]
)
# Backward-compatible alias: expose the same sector-rotation endpoints
# at /api/v1/sector-rotation (and /api/v1/sector-rotation/sectors) so
# clients / docs that reference the documented shorter path still
# resolve. The router's own paths already start with "/sector-rotation",
# so the prefix here is just the API root.
app.include_router(
    sector_rotation.router, prefix=f"{settings.api_v1_prefix}", tags=["Sector Rotation"]
)
app.include_router(
    etf_scanner.router, prefix=f"{settings.api_v1_prefix}/etfs", tags=["ETF Scanner"]
)
app.include_router(
    notifications.router, prefix=f"{settings.api_v1_prefix}/notifications", tags=["Notifications"]
)
app.include_router(
    strategies.router, prefix=f"{settings.api_v1_prefix}/strategies", tags=["Strategies"]
)
app.include_router(
    backtests.router, prefix=f"{settings.api_v1_prefix}/backtests", tags=["Backtests"]
)
app.include_router(
    signals.router, prefix=f"{settings.api_v1_prefix}/signals", tags=["Signals"]
)
app.include_router(
    attribution.router, prefix=f"{settings.api_v1_prefix}/analysis", tags=["Analysis"]
)
app.include_router(
    favorites.router, prefix=f"{settings.api_v1_prefix}/favorites", tags=["Favorites"]
)
app.include_router(
    research.router,
    prefix=f"{settings.api_v1_prefix}/research",
    tags=["AI Research"],
)
app.include_router(
    crypto.router,
    prefix=f"{settings.api_v1_prefix}/crypto",
    tags=["Crypto"],
)
app.include_router(
    stream.router,
    prefix=f"{settings.api_v1_prefix}/stream",
    tags=["Stream"],
)
app.include_router(
    paper_trading.router,
    prefix=f"{settings.api_v1_prefix}/paper-trading",
    tags=["Paper Trading"],
)
app.include_router(
    live_trading.router,
    prefix=f"{settings.api_v1_prefix}/live-trading",
    tags=["Live Trading"],
)
app.include_router(
    listing_events.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["Listing Events"],
)
app.include_router(
    microstructure.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["Microstructure"],
)
app.include_router(
    fund_flow.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["Fund Flow"],
)
app.include_router(
    search_trends.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["Search Trends"],
)
app.include_router(
    sec_filings.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["SEC Filings"],
)
app.include_router(
    futures.router,
    prefix=f"{settings.api_v1_prefix}/futures",
    tags=["Futures"],
)
app.include_router(
    macro.router,
    prefix=f"{settings.api_v1_prefix}",
    tags=["Macro Indicators"],
)
app.include_router(
    stock_fundamentals.router,
    prefix=f"{settings.api_v1_prefix}/stock-fundamentals",
    tags=["Stock Fundamentals"],
)
app.include_router(
    stocks.router,
    prefix=f"{settings.api_v1_prefix}/stocks",
    tags=["Stocks"],
)
app.include_router(
    news.router,
    prefix=f"{settings.api_v1_prefix}/news",
    tags=["News"],
)
# 学习中心（方案 B MVP，2026-08-02）：知识 feed 按主题/内容类型过滤
app.include_router(
    learning.router,
    prefix=f"{settings.api_v1_prefix}/learning",
    tags=["Learning"],
)
# Internal/trusted-cron endpoints (machine-to-machine; not for user-auth).
# These live under /api/v1/internal/* and require INTERNAL_API_TOKEN.
app.include_router(
    internal.router,
    prefix=f"{settings.api_v1_prefix}/internal",
    tags=["Internal"],
)

# Serve frontend static files with cache-control headers
web_dist = Path(__file__).parent.parent / "web" / "dist"


# 这些路径属于后端 API/文档，绝不能 SPA fallback 到 index.html（否则不存在的
# API 端点会返回 HTML 而不是 JSON 404）。
_NON_SPA_PREFIXES = ("/api/", "/health", "/docs", "/redoc", "/openapi.json")

# 真正的静态资源扩展名。判断必须是白名单而不是"路径含点"——A 股带后缀
# 代码（如 /instruments/510300.SH）也会含点，黑名单式判断会把它们误判为
# 静态资源而不做 SPA fallback，导致详情页直达/刷新 404（2026-08-08 修复）。
_STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".map",
}


class CacheControlledStaticFiles(StaticFiles):
    """StaticFiles subclass that sets cache headers for hashed assets and HTML entry.

    2026-08-08（功能可用性审计）：补 SPA fallback —— 此前 uvicorn 直接服务时
    深层路由（/login、/dashboard 等）刷新/直达返回 404（生产靠 nginx try_files
    兜底，但后端直连端口会断）。非 API 路径文件不存在时回退 index.html。
    """

    async def get_response(self, path: str, scope: Scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and self._is_spa_path(scope):
                # SPA fallback：深层路由交给前端 router 渲染。
                index = await super().get_response("index.html", scope)
                index.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                index.headers["Pragma"] = "no-cache"
                index.headers["Expires"] = "0"
                return index
            raise

        request_path = scope.get("path", "/")
        if request_path in ("/", "/index.html") or request_path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif "/assets/" in request_path:
            # Hashed filenames change on every build, safe to cache forever
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return response

    @staticmethod
    def _is_spa_path(scope: Scope) -> bool:
        """True when a 404 should fall back to the SPA shell (not an API route)."""
        request_path = scope.get("path", "/")
        if any(request_path.startswith(p) for p in _NON_SPA_PREFIXES):
            return False
        # 白名单式判断：只有真正的静态资源扩展名才不 fallback，避免把
        # A 股带后缀代码（510300.SH）误判为文件。
        last = request_path.rsplit("/", 1)[-1]
        dot = last.rfind(".")
        if dot > 0:
            ext = last[dot:].lower()
            if ext in _STATIC_EXTENSIONS:
                return False
        return True


if web_dist.exists():
    app.mount(
        "/",
        CacheControlledStaticFiles(directory=str(web_dist), html=True),
        name="static",
    )


# Start the background scheduler from the ASGI startup event rather than at
# module import time. Module-level startup causes duplicate jobs when multiple
# workers import the same module.
#
# Multi-worker safety: APScheduler's BackgroundScheduler is a per-process
# object, but @app.on_event("startup") still fires once per Gunicorn worker.
# We use a file lock (flock on /tmp) plus an opt-in env flag (ENABLE_SCHEDULER)
# so that at most one worker actually runs the cron jobs. The other workers
# short-circuit cleanly and just serve HTTP traffic.
_SCHEDULER_LOCK_PATH = os.path.join(
    tempfile.gettempdir(), "ad_research_scheduler.lock"
)


def _try_acquire_scheduler_leadership() -> bool:
    """Attempt to become the worker that runs the scheduler.

    Uses a non-blocking flock on a temp file. The lock is held for the lifetime
    of the process; whoever holds it is the designated scheduler leader. We
    also honour ENABLE_SCHEDULER — when unset/false every worker skips the
    scheduler entirely, which is the safest default for multi-worker deploys
    where an external cron (or docker-compose command:) starts the job instead.
    """
    if os.environ.get("ENABLE_SCHEDULER", "").lower() not in {"1", "true", "yes"}:
        return False

    lock_fd = open(_SCHEDULER_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        return False

    # Stash the fd on the module so the OS keeps the lock until process exit.
    _SCHEDULER_LOCK_PATH_fd = lock_fd  # noqa: F841 (intentionally held)
    return True


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    if scheduler.running:
        return

    if not _try_acquire_scheduler_leadership():
        logging.getLogger(__name__).warning(
            "[Scheduler] Skipped on worker pid=%s "
            "(ENABLE_SCHEDULER not set, or another worker already holds the lock)",
            os.getpid(),
        )
        return

    try:
        init_scheduler()
        logging.getLogger(__name__).warning(
            "[Scheduler] Started on worker pid=%s", os.getpid()
        )
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "[Scheduler] Failed to start at startup: %s", exc
        )

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    shutdown_scheduler()
