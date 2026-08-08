"""Macro-indicator services (FRED, NBS, PBOC)."""

from app.services.macro.fred_service import SERIES_REGISTRY, FredService

__all__ = ["FredService", "SERIES_REGISTRY"]
