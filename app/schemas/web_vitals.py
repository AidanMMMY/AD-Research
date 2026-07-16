"""Web Vitals ingestion schemas.

Pydantic payload shape mirrors what the frontend's ``web-vitals`` library
sends over ``navigator.sendBeacon`` — see web/src/lib/web-vitals.ts.

Validation is intentionally permissive:
* ``rating`` is typed ``str`` because web-vitals may introduce new buckets;
  we just persist whatever comes in.
* ``id`` / ``navigationType`` / ``page`` are optional — the JS layer only
  sets them when it has context.
* ``name`` is restricted to the 5 vitals we care about so we don't fill the
  table with garbage if a stale library version ships a new metric.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


# Whitelist of Core Web Vitals names. Adding a new metric here requires
# bumping the column comment in app/models/web_vitals.py and re-checking
# the summary aggregation in app/api/v1/stats.py.
_VITAL_NAMES = ("LCP", "INP", "CLS", "FCP", "TTFB")


class WebVitalsPayload(BaseModel):
    """Single Web Vitals observation from the browser."""

    model_config = ConfigDict(extra="ignore")

    name: Literal["LCP", "INP", "CLS", "FCP", "TTFB"]
    value: float
    rating: str
    id: str | None = None
    navigationType: str | None = None
    page: str | None = None


__all__ = ["WebVitalsPayload", "_VITAL_NAMES"]