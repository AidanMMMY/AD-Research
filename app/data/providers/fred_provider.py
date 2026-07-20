"""FRED (Federal Reserve Economic Data) API provider.

Free public data source for ~800,000 US economic time series.  We
typically only consume the ~30 indicators registered in
``app.services.macro.fred_service``.

Free-tier limits (per FRED docs):
  - 120 requests / minute
  - No daily quota

Endpoint reference: https://fred.stlouisfed.org/docs/api/fred/
"""

import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests

from app.config import get_settings
from app.core.exceptions import DataProviderError

logger = logging.getLogger(__name__)


# Default request timeout.  FRED is rarely slow but we cap at 15s so a
# stuck connection does not block the scheduler thread.
_REQUEST_TIMEOUT_SECONDS = 15

# Free-tier rate limit: 120 req/min.  We sleep between calls to stay
# safely below this even with a full registry of ~30 series.
_MIN_INTERVAL_SECONDS = 0.6  # ~100 req/min — leaves headroom

# Retry policy on 429 (rate limit) or 5xx.
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0


def _redact_api_key(message: object) -> str:
    """Mask API-key query params in URLs embedded in error messages.

    ``requests`` exceptions include the full request URL, and the FRED key
    travels as an ``api_key=`` query param — never log or propagate it raw.
    """
    return re.sub(r"(?i)(token|apikey|api_key)=[^&\s]+", r"\1=***", str(message))


class FredProvider:
    """FRED API client used by the macro refresh pipeline.

    Pulls settings.fred_api_key lazily so unit tests can stub it.  All
    network failures are converted into ``DataProviderError`` so the
    scheduler can log them and continue with the next series.
    """

    BASE_URL = "https://api.stlouisfed.org"

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = (api_key if api_key is not None else settings.fred_api_key).strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_series(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch observations for a single FRED series.

        Args:
            series_id: FRED series id (e.g. ``CPIAUCSL``).
            start_date: ISO date ``YYYY-MM-DD`` (inclusive).  Optional.
            end_date: ISO date ``YYYY-MM-DD`` (inclusive).  Optional.

        Returns:
            A list of ``{"date": "YYYY-MM-DD", "value": float}`` dicts.
            Rows where FRED reports "." (missing) are skipped.

        Raises:
            DataProviderError: when the API key is missing, the request
                fails, or the response cannot be parsed.
        """
        if not self.api_key:
            raise DataProviderError(
                "FRED_API_KEY not configured. Set it in .env or as an env var "
                "(get a free key at https://fred.stlouisfed.org/docs/api/api_key.html)."
            )

        params: dict[str, str] = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date

        url = f"{self.BASE_URL}/fred/series/observations?{urlencode(params)}"
        payload = self._get_json(url)

        observations = payload.get("observations") or []
        out: list[dict[str, Any]] = []
        for obs in observations:
            raw_value = obs.get("value")
            # FRED marks missing observations with a literal "." — skip
            # rather than fail the whole series.
            if raw_value is None or raw_value == "." or raw_value == "":
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                logger.warning(
                    "FRED %s: skipping non-numeric value %r at %s",
                    series_id, raw_value, obs.get("date"),
                )
                continue

            date_str = obs.get("date")
            if not date_str:
                continue
            out.append({"date": date_str, "value": value})

        return out

    def get_series_info(self, series_id: str) -> dict[str, Any] | None:
        """Fetch metadata (title, units, frequency, seasonal adjustment).

        Returns ``None`` if the API key is missing or the request fails;
        callers treat metadata as a best-effort enrichment.
        """
        if not self.api_key:
            return None

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
        }
        url = f"{self.BASE_URL}/fred/series?{urlencode(params)}"

        try:
            payload = self._get_json(url)
        except DataProviderError as exc:
            logger.warning("FRED series info %s failed: %s", series_id, exc)
            return None

        series_list = payload.get("seriess") or []
        if not series_list:
            return None
        s = series_list[0]
        return {
            "id": s.get("id"),
            "title": s.get("title"),
            "units": s.get("units"),
            "frequency": s.get("frequency"),
            "seasonal_adjustment": s.get("seasonal_adjustment"),
            "last_updated": s.get("last_updated"),
        }

    def list_categories(self) -> list[dict[str, Any]]:
        """Optional: list FRED top-level categories. Not used by MVP."""
        if not self.api_key:
            return []
        url = (
            f"{self.BASE_URL}/fred/categories?{urlencode({'api_key': self.api_key, 'file_type': 'json'})}"
        )
        try:
            payload = self._get_json(url)
        except DataProviderError:
            return []
        return payload.get("categories") or []

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_json(self, url: str) -> dict[str, Any]:
        """GET ``url`` and return parsed JSON, retrying on 429 / 5xx."""
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = requests.get(url, timeout=_REQUEST_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "FRED request failed (attempt %d/%d): %s",
                    attempt + 1, _MAX_RETRIES, _redact_api_key(exc),
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            if resp.status_code == 429:
                # Rate limited — honour Retry-After if present.
                retry_after = float(resp.headers.get("Retry-After", _RETRY_BACKOFF_SECONDS))
                logger.warning(
                    "FRED 429 rate-limited; sleeping %.1fs (attempt %d/%d)",
                    retry_after, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(retry_after)
                continue

            if 500 <= resp.status_code < 600:
                last_error = DataProviderError(
                    f"FRED HTTP {resp.status_code}: {resp.text[:200]}"
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                raise DataProviderError(
                    f"FRED HTTP {resp.status_code}: {resp.text[:200]}"
                ) from exc

            try:
                return resp.json()
            except ValueError as exc:
                raise DataProviderError(
                    f"FRED response was not valid JSON: {exc}"
                ) from exc

        raise DataProviderError(
            f"FRED request failed after {_MAX_RETRIES} attempts: "
            f"{_redact_api_key(last_error)}"
        )

    def rate_limit_sleep(self) -> None:
        """Sleep a short interval to respect FRED free-tier rate limits.

        Call between series in a batched refresh.  Not enforced inside
        ``get_series`` because callers that fetch a single series in
        parallel don't need it.
        """
        time.sleep(_MIN_INTERVAL_SECONDS)