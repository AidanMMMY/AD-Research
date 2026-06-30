"""Raw article data types emitted by crawlers.

These are the lingua franca between crawler implementations (one per
source) and the downstream persistence / dedup / NLP pipelines. Keep
the schema source-agnostic — anything source-specific belongs in
``extra``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RawArticle:
    """A single normalized news item produced by a crawler.

    Attributes
    ----------
    source:
        Stable identifier for the originating source, e.g.
        ``"xinhua_rss"``, ``"sec_edgar"``, ``"reddit_wsb"``.
    source_id:
        Native ID from the upstream platform. Optional because some
        sources (e.g. plain HTML scrape) lack one.
    url:
        Canonical link. Used for dedup and as a fallback
        ``source_id`` when the upstream ID is missing.
    title:
        Headline text. May include HTML entities — strip on ingest.
    body:
        Plain text body. At least one of ``body`` / ``body_html``
        should be populated.
    body_html:
        Raw HTML body, if available. Some downstream consumers
        prefer HTML for preserving structure.
    author:
        Author / reporter name when available.
    published_at:
        When the article was published. Must be timezone-aware UTC.
    language:
        ISO-ish language code: ``"zh"``, ``"en"``, ``"other"``.
    market:
        Market bucket: ``"cn_a"``, ``"us"``, ``"crypto"``.
    engagement:
        Engagement metrics as a dict, e.g.
        ``{"likes": 12, "comments": 4, "shares": 0, "views": 3800}``.
    extra:
        Source-specific free-form payload.
    """

    source: str
    url: str
    title: str
    published_at: datetime
    source_id: str | None = None
    body: str | None = None
    body_html: str | None = None
    author: str | None = None
    language: str = "zh"
    market: str = "cn_a"
    engagement: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize ``published_at`` to a UTC-aware datetime."""
        ts = self.published_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        self.published_at = ts

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data

    def to_json(self) -> str:
        """Return JSON string form of the article."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawArticle":
        """Build a RawArticle from a dict (inverse of ``to_dict``)."""
        payload = dict(data)
        raw_ts = payload.get("published_at")
        if isinstance(raw_ts, str):
            ts = datetime.fromisoformat(raw_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            payload["published_at"] = ts
        return cls(**payload)

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------
    def identity_key(self) -> str:
        """Stable key for dedup / upsert.

        Prefers ``source:source_id`` when available, else falls back
        to the URL.
        """
        if self.source_id:
            return f"{self.source}:{self.source_id}"
        return f"{self.source}:{self.url}"
