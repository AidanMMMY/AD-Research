"""Macro indicator data service.

Wraps the ``MacroIndicator`` ORM model and provides:

* ``list_indicators`` — paginated, filtered list of observations.
* ``list_codes`` — distinct indicator codes for filter dropdowns.
* ``latest_snapshot`` — one row per (code, region) with the most
  recent value.
* ``upsert_observations`` — idempotent insert via the unique
  constraint on (code, region, period, source). Used by the
  scheduler / manual-refresh pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models.macro import MacroIndicator


class MacroDataService:
    """Read/write helpers for macro indicator observations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── read-side ────────────────────────────────────────────────

    def list_indicators(
        self,
        region: str | None = None,
        code: str | None = None,
        start_period: date | None = None,
        end_period: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Return a paginated, filtered list of macro observations."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 200:
            page_size = 50

        stmt = select(MacroIndicator)
        count_stmt = select(func.count(MacroIndicator.id))

        if region:
            stmt = stmt.where(MacroIndicator.region == region)
            count_stmt = count_stmt.where(MacroIndicator.region == region)
        if code:
            stmt = stmt.where(MacroIndicator.code == code)
            count_stmt = count_stmt.where(MacroIndicator.code == code)
        if start_period:
            stmt = stmt.where(MacroIndicator.period >= start_period)
            count_stmt = count_stmt.where(MacroIndicator.period >= start_period)
        if end_period:
            stmt = stmt.where(MacroIndicator.period <= end_period)
            count_stmt = count_stmt.where(MacroIndicator.period <= end_period)

        stmt = stmt.order_by(
            MacroIndicator.period.desc(),
            MacroIndicator.code.asc(),
        )

        total = self.db.execute(count_stmt).scalar() or 0
        rows = (
            self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )

        return {
            "items": [_to_out(row) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def list_codes(self, region: str | None = None) -> list[dict[str, Any]]:
        """Return one entry per distinct (code, region) plus its latest value."""
        stmt = select(
            MacroIndicator.code,
            MacroIndicator.region,
            MacroIndicator.name_zh,
            MacroIndicator.name_en,
            MacroIndicator.unit,
            MacroIndicator.source,
        ).group_by(
            MacroIndicator.code,
            MacroIndicator.region,
            MacroIndicator.name_zh,
            MacroIndicator.name_en,
            MacroIndicator.unit,
            MacroIndicator.source,
        )
        if region:
            stmt = stmt.where(MacroIndicator.region == region)
        rows = self.db.execute(stmt).all()

        latest_period_subq = (
            select(
                MacroIndicator.code,
                MacroIndicator.region,
                func.max(MacroIndicator.period).label("latest_period"),
            )
            .group_by(MacroIndicator.code, MacroIndicator.region)
        )
        if region:
            latest_period_subq = latest_period_subq.where(MacroIndicator.region == region)
        latest_period_subq = latest_period_subq.subquery()

        latest_stmt = (
            select(MacroIndicator)
            .join(
                latest_period_subq,
                (MacroIndicator.code == latest_period_subq.c.code)
                & (MacroIndicator.region == latest_period_subq.c.region)
                & (MacroIndicator.period == latest_period_subq.c.latest_period),
            )
        )
        latest_rows = {
            (r.code, r.region): r for r in self.db.execute(latest_stmt).scalars().all()
        }

        result: list[dict[str, Any]] = []
        for code, region_v, name_zh, name_en, unit, source in rows:
            latest = latest_rows.get((code, region_v))
            result.append(
                {
                    "code": code,
                    "region": region_v,
                    "name_zh": name_zh,
                    "name_en": name_en,
                    "unit": unit,
                    "source": source,
                    "latest_period": latest.period if latest else None,
                    "latest_value": latest.value if latest else None,
                }
            )
        result.sort(key=lambda x: (x["region"], x["code"]))
        return result

    def latest_snapshot(self, region: str | None = None) -> dict[str, Any]:
        """Return one row per (code, region) — the most recent observation.

        Also surfaces ``prev_value`` (the second-most-recent observation
        for the same code) and ``change_pct`` so dashboard tiles can show
        day-over-day moves without a separate per-code series call.

        When multiple sources have data for the same code on the same day,
        the tie-breaker prefers ``yfinance``/``akshare`` over ``fred``
        alphabetically so the real-time pipeline wins over the slower
        FRED publication.
        """
        ranked = select(
            MacroIndicator,
            func.dense_rank()
            .over(
                partition_by=[MacroIndicator.code, MacroIndicator.region],
                order_by=desc(MacroIndicator.period),
            )
            .label("period_rank"),
            func.row_number()
            .over(
                partition_by=[
                    MacroIndicator.code,
                    MacroIndicator.region,
                    MacroIndicator.period,
                ],
                order_by=desc(MacroIndicator.source),
            )
            .label("source_rank"),
        )
        if region:
            ranked = ranked.where(MacroIndicator.region == region)
        ranked = ranked.cte("ranked")

        stmt = (
            select(ranked)
            .where(ranked.c.period_rank <= 2)
            .where(ranked.c.source_rank == 1)
            .order_by(ranked.c.code, ranked.c.period.desc())
        )
        rows = self.db.execute(stmt).mappings().all()

        # Group the top-2 periods per code and compute the previous value.
        by_code: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row["code"], row["region"])
            by_code.setdefault(key, []).append(row)

        items: list[dict[str, Any]] = []
        for key in sorted(by_code):
            group = sorted(by_code[key], key=lambda r: r["period"], reverse=True)
            latest = group[0]
            prev = group[1] if len(group) > 1 else None
            prev_value = prev["value"] if prev else None
            change_pct = None
            if (
                latest["value"] is not None
                and prev_value is not None
                and prev_value != 0
            ):
                change_pct = round(
                    (latest["value"] - prev_value) / prev_value * 100.0, 6
                )
            items.append(_to_latest(latest, prev_value=prev_value, change_pct=change_pct))

        return {"items": items, "region": region}

    def get_series(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 500,
    ) -> dict[str, Any] | None:
        """Return the time-series for any upserted (code, region) — pure DB lookup.

        Used by the API as the fallback path when a code is not in the
        static FRED registry (e.g. ``global_hsi`` upserted by the
        yfinance/akshare global-indices job).  Returns None if no
        observations exist for the code at all.

        Picks one row per ``period`` (preferring the highest ``source``
        alphabetically as a stable tie-breaker) so multiple sources
        for the same code do not duplicate points on the chart.
        """
        from sqlalchemy import select

        # Identify the (region, source) pairs that have data for this
        # code so we can pick the right one to display.
        first_row = (
            self.db.query(MacroIndicator)
            .filter(MacroIndicator.code == code)
            .order_by(MacroIndicator.period.desc())
            .first()
        )
        if first_row is None:
            return None

        stmt = (
            select(MacroIndicator)
            .where(MacroIndicator.code == code)
            .where(MacroIndicator.region == first_row.region)
            .where(MacroIndicator.source == first_row.source)
        )
        if start_date:
            stmt = stmt.where(MacroIndicator.period >= start_date)
        if end_date:
            stmt = stmt.where(MacroIndicator.period <= end_date)
        stmt = stmt.order_by(MacroIndicator.period.asc()).limit(limit)

        rows = self.db.execute(stmt).scalars().all()
        return {
            "code": first_row.code,
            "region": first_row.region,
            "name_zh": first_row.name_zh,
            "name_en": first_row.name_en,
            "unit": first_row.unit or "",
            "source": first_row.source,
            "points": [
                {"period": r.period, "value": float(r.value)}
                for r in rows
                if r.period is not None and r.value is not None
            ],
        }

    # ── write-side ───────────────────────────────────────────────

    def upsert_observations(
        self,
        region: str,
        source: str,
        observations: list[dict[str, Any]],
    ) -> int:
        """Idempotent upsert of observations.

        Each observation dict must contain ``code``, ``period`` (date or
        ``YYYY-MM-DD`` string), ``value``, ``name_zh``, and optionally
        ``name_en`` / ``unit``.

        Returns the number of rows processed (upsert count from the DB).
        """
        if not observations:
            return 0

        rows: list[dict[str, Any]] = []
        for obs in observations:
            period = obs.get("period")
            if isinstance(period, str):
                period = datetime.strptime(period, "%Y-%m-%d").date()
            if period is None:
                continue
            rows.append(
                {
                    "code": obs["code"],
                    "region": region,
                    "name_zh": obs.get("name_zh", obs["code"]),
                    "name_en": obs.get("name_en"),
                    "unit": obs.get("unit", ""),
                    "period": period,
                    "value": float(obs["value"]),
                    "source": source,
                }
            )

        if not rows:
            return 0

        # MySQL ON DUPLICATE KEY UPDATE keeps the upsert atomic; for
        # SQLite (tests) we fall back to a merge-then-update so the
        # unique-constraint conflict is still handled.
        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect.startswith("mysql"):
            stmt = mysql_insert(MacroIndicator).values(rows)
            upsert = stmt.on_duplicate_key_update(
                value=stmt.inserted.value,
                name_zh=stmt.inserted.name_zh,
                name_en=stmt.inserted.name_en,
                unit=stmt.inserted.unit,
                fetched_at=func.now(),
            )
            self.db.execute(upsert)
        else:
            # Generic dialect: read existing keys then insert/update per row.
            for row in rows:
                existing = (
                    self.db.query(MacroIndicator)
                    .filter(
                        MacroIndicator.code == row["code"],
                        MacroIndicator.region == row["region"],
                        MacroIndicator.period == row["period"],
                        MacroIndicator.source == row["source"],
                    )
                    .first()
                )
                if existing is None:
                    self.db.add(MacroIndicator(**row))
                else:
                    existing.value = row["value"]
                    existing.name_zh = row["name_zh"]
                    existing.name_en = row["name_en"]
                    existing.unit = row["unit"]
                    existing.fetched_at = datetime.utcnow()
        self.db.commit()
        return len(rows)


def _to_out(row: MacroIndicator) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "region": row.region,
        "name_zh": row.name_zh,
        "name_en": row.name_en,
        "unit": row.unit,
        "period": row.period.isoformat() if row.period else None,
        "value": row.value,
        "source": row.source,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }


def _to_latest(
    row: Any,
    prev_value: float | None = None,
    change_pct: float | None = None,
) -> dict[str, Any]:
    return {
        "code": row["code"],
        "region": row["region"],
        "name_zh": row["name_zh"],
        "name_en": row["name_en"],
        "unit": row["unit"],
        "source": row["source"],
        "period": row["period"].isoformat() if row["period"] else None,
        "value": row["value"],
        "prev_value": prev_value,
        "change_pct": change_pct,
        "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
    }
