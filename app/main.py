"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.scheduler import init_scheduler, shutdown_scheduler
from app.api.v1 import auth, etfs, pools, market_data, indicators, analysis, etl, scoring, screening, reports, stats, sector_rotation, etf_scanner, notifications, strategies, backtests, signals, attribution

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

# Serve frontend static files
web_dist = Path(__file__).parent.parent / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="static")


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    init_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    shutdown_scheduler()
