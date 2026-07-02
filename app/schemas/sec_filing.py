"""SEC EDGAR filing Pydantic schemas.

Used by the API layer to serialize ORM rows for SEC EDGAR filings
(10-K, 10-Q, 20-F, etc.) into JSON responses.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Base + Out
# ---------------------------------------------------------------------------


class SecFilingBase(BaseModel):
    """Fields common to all SEC filing schemas."""

    cik: str = Field(..., description="SEC 10-digit CIK")
    ticker: str = Field(..., description="Primary US ticker")
    company_name: str | None = None
    form_type: str = Field(..., description="Filing form (10-K, 10-Q, 8-K, 20-F)")
    filing_date: date = Field(..., description="Date filed with SEC")
    report_period: date | None = Field(None, description="Period the filing reports on")
    accession_number: str = Field(..., description="SEC accession number (unique filing id)")
    primary_document: str | None = None
    filing_url: str | None = None


class SecFilingOut(SecFilingBase):
    """SEC filing as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    extraction_status: str
    source: str
    extracted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SecFilingDetail(SecFilingOut):
    """Detail view including the raw XBRL-extracted metrics payload."""

    extracted_metrics: dict[str, Any] | None = None
    xbrl_file_path: str | None = None


# ---------------------------------------------------------------------------
# List response + params
# ---------------------------------------------------------------------------


class SecFilingListResponse(BaseModel):
    """Paginated SEC filing list response."""

    items: list[SecFilingOut]
    total: int
    page: int
    page_size: int


class SecFilingListParams(BaseModel):
    """Query parameters for the SEC filings list endpoint."""

    page: int = 1
    page_size: int = 20
    ticker: str | None = None
    cik: str | None = None
    form_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    q: str | None = None
    sort_by: str = "filing_date"
    sort_dir: str = "desc"


# ---------------------------------------------------------------------------
# Coverage summary
# ---------------------------------------------------------------------------


class SecFilingCoverageResponse(BaseModel):
    """Coverage stats: which tickers we track, how many filings we have."""

    total_filings: int = Field(..., description="Total rows in sec_filings table")
    tracked_tickers: int = Field(..., description="Distinct tickers")
    by_form_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count of filings grouped by form_type (10-K / 10-Q / 20-F)",
    )
    latest_filing_date: date | None = None
    extractions_completed: int = Field(..., description="Rows with extraction_status=success")
    extractions_failed: int = Field(..., description="Rows with extraction_status=failed")
    extractions_pending: int = Field(..., description="Rows with extraction_status=pending")