"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.v1 import (
    admin_users,
    analysis,
    attribution,
    auth,
    backtests,
    etf_scanner,
    etfs,
    etl,
    favorites,
    indicators,
    market_data,
    notifications,
    pools,
    reports,
    scoring,
    screening,
    sector_rotation,
    signals,
    stats,
    strategies,
)
from app.config import get_settings
from app.core.scheduler import init_scheduler, shutdown_scheduler

settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}

# Include v1 routers
app.include_router(etfs.router, prefix=f"{settings.api_v1_prefix}/etfs", tags=["ETFs"])
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
    scoring.router, prefix=f"{settings.api_v1_prefix}/scores", tags=["Scoring"]
)
app.include_router(
    screening.router, prefix=f"{settings.api_v1_prefix}/screen", tags=["Screening"]
)
app.include_router(
    reports.router, prefix=f"{settings.api_v1_prefix}/reports", tags=["Reports"]
)
app.include_router(
    auth.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"]
)
app.include_router(
    admin_users.router,
    prefix=f"{settings.api_v1_prefix}/admin/users",
    tags=["Admin"],
)
app.include_router(
    stats.router, prefix=f"{settings.api_v1_prefix}/stats", tags=["Statistics"]
)
app.include_router(
    sector_rotation.router, prefix=f"{settings.api_v1_prefix}/analysis", tags=["Analysis"]
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

# Serve frontend static files with cache-control headers
web_dist = Path(__file__).parent.parent / "web" / "dist"


class CacheControlledStaticFiles(StaticFiles):
    """StaticFiles subclass that sets cache headers for hashed assets and HTML entry."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        request_path = scope.get("path", "/")

        if request_path in ("/", "/index.html") or request_path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif "/assets/" in request_path:
            # Hashed filenames change on every build, safe to cache forever
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return response


if web_dist.exists():
    app.mount(
        "/",
        CacheControlledStaticFiles(directory=str(web_dist), html=True),
        name="static",
    )


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    init_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    shutdown_scheduler()
