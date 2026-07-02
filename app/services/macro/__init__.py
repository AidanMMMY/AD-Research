"""Macro-indicator services (FRED, NBS, PBOC)."""

from app.services.macro.fred_service import FredService, SERIES_REGISTRY

__all__ = ["FredService", "SERIES_REGISTRY"]