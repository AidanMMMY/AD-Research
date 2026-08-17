"""SSE (Server-Sent Events) real-time price streaming endpoint.

GET /api/v1/stream/prices?codes=510300.SH,159915.SZ

Authenticated via Bearer token in the Authorization header (optional, allows
anonymous access for public data).
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal

# anyio 随 FastAPI/Starlette 传递安装（fastapi 强依赖 starlette→anyio），
# to_thread.run_sync 与 FastAPI 内部共用同一线程池。
import anyio.to_thread
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter()
logger = logging.getLogger(__name__)

# Interval between price updates (seconds)
STREAM_INTERVAL = 3
# Max connection lifetime (seconds)
STREAM_TIMEOUT = 300


def _candidate_codes(code: str) -> list[str]:
    """Build a list of candidate code forms to try for lookup.

    Accepts both ``510300.SH`` and bare ``510300`` styles from the client.
    The DB stores codes WITH the market suffix (``510300.SH``, ``SPY.US``,
    ``BTC.US`` …), but historical/legacy rows may only have the bare
    numeric form. We try multiple shapes so that the SSE stream keeps
    working regardless of which side reformatted the symbol.
    """
    code = (code or "").strip()
    if not code:
        return []

    base = code.split(".", 1)[0] if "." in code else code
    has_suffix = "." in code

    candidates: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    # 1) Exact match as given by the client (with or without suffix).
    _push(code)

    # 2) If a suffix was provided, try the bare numeric/alphanumeric base.
    if has_suffix:
        _push(base)

    # 3) If the code has NO suffix, try common market suffixes so we can
    #    locate rows that always store the suffix in the DB.
    if not has_suffix:
        if base.isdigit():
            # A-share heuristic: 6xxxxx / 9xxxxx => SH, 0xxxxx / 2xxxxx / 3xxxxx => SZ
            if base.startswith(("5", "6", "9")):
                _push(f"{base}.SH")
            elif base.startswith(("0", "1", "2", "3")):
                _push(f"{base}.SZ")
        elif base.isalpha() and base.isupper() and len(base) <= 5:
            # Likely US-listed ticker or crypto symbol.
            _push(f"{base}.US")
            _push(f"{base}.HK")

    # 4) If a suffix was provided but no row matched, fall back to the
    #    bare form + the same heuristic (e.g. client sent ``SPY.HK`` by
    #    mistake — try ``SPY`` and ``SPY.US``).
    if has_suffix:
        if base.isdigit():
            if base.startswith(("5", "6", "9")):
                _push(f"{base}.SH")
            elif base.startswith(("0", "1", "2", "3")):
                _push(f"{base}.SZ")
        elif base.isalpha() and base.isupper():
            _push(f"{base}.US")
            _push(f"{base}.HK")

    return candidates


def _resolve_matches(
    db: Session, codes: list[str]
) -> dict[str, tuple[str, "object | None"]]:
    """Map each requested code to ``(matched_db_code, ETFInfo | None)``.

    批量版（2026-08-17）：原先逐 code、逐 candidate 的循环查询在每 3s 的
    SSE tick 里会放大成 N×M 次round-trip，这里改成两次 IN 批量查询
    （ETFInfo 一次、InstrumentDailyBar 存在性一次），LIKE 模糊兜底仅对
    仍未命中的 code 逐个执行（正常路径不会走到）。

    Candidate 优先级语义保持不变：每个请求 code 仍按
    :func:`_candidate_codes` 的顺序取第一个在库中存在的形态。
    """
    from app.models.etf import ETFInfo, InstrumentDailyBar

    cand_map: dict[str, list[str]] = {c: _candidate_codes(c) for c in codes}
    all_cands = {cand for cands in cand_map.values() for cand in cands}
    if not all_cands:
        return {}

    matched: dict[str, tuple[str, object | None]] = {}

    # 1) ETFInfo 批量 IN 查询（取代逐 candidate 循环）。
    instruments = {
        inst.code: inst
        for inst in db.query(ETFInfo).filter(ETFInfo.code.in_(all_cands)).all()
    }
    for code in codes:
        for cand in cand_map[code]:
            if cand in instruments:
                matched[code] = (instruments[cand].code, instruments[cand])
                break

    # 2) ETFInfo 未命中者的 LIKE 兜底（与旧逻辑一致，逐 code 但极少触发）。
    def _base(code: str) -> str:
        return code.split(".", 1)[0] if "." in code else code

    for code in codes:
        if code in matched:
            continue
        base = _base(code)
        if not base:
            continue
        inst = (
            db.query(ETFInfo)
            .filter(ETFInfo.code.like(f"{base}%"))
            .first()
        )
        if inst is not None:
            matched[code] = (inst.code, inst)

    # 3) 仍未命中：InstrumentDailyBar 存在性批量 IN（股票等非 ETF 行）。
    remaining = [c for c in codes if c not in matched]
    if remaining:
        rem_cands = {cand for c in remaining for cand in cand_map[c]}
        bar_codes: set[str] = set()
        if rem_cands:
            bar_codes = {
                row[0]
                for row in db.query(InstrumentDailyBar.etf_code)
                .filter(InstrumentDailyBar.etf_code.in_(rem_cands))
                .distinct()
                .all()
            }
        for code in remaining:
            for cand in cand_map[code]:
                if cand in bar_codes:
                    matched[code] = (cand, None)
                    break

        # 4) LIKE 兜底（旧逻辑的 last-resort 分支，仅对彻底未命中者）。
        for code in [c for c in remaining if c not in matched]:
            base = _base(code)
            if not base:
                continue
            row = (
                db.query(InstrumentDailyBar.etf_code)
                .filter(InstrumentDailyBar.etf_code.like(f"{base}%"))
                .first()
            )
            if row is not None:
                matched[code] = (row[0], None)

    return matched


def _fetch_latest_two_bars(db: Session, matched_codes: set[str]) -> dict:
    """批量取每个 code 最新两根 bar：``{code: {1: latest_row, 2: prev_row}}``。

    row_number 窗口一次查询取代逐 code 的 latest/prev 两次查询
    （PostgreSQL / SQLite 均支持窗口函数）。
    """
    from app.models.etf import InstrumentDailyBar

    if not matched_codes:
        return {}

    rn = func.row_number().over(
        partition_by=InstrumentDailyBar.etf_code,
        order_by=InstrumentDailyBar.trade_date.desc(),
    ).label("rn")
    sub = (
        db.query(
            InstrumentDailyBar.etf_code.label("etf_code"),
            InstrumentDailyBar.close.label("close"),
            InstrumentDailyBar.volume.label("volume"),
            InstrumentDailyBar.trade_date.label("trade_date"),
            rn,
        )
        .filter(InstrumentDailyBar.etf_code.in_(matched_codes))
        .subquery()
    )
    bars: dict[str, dict[int, object]] = {}
    for row in db.query(sub).filter(sub.c.rn <= 2).all():
        bars.setdefault(row.etf_code, {})[row.rn] = row
    return bars


def _build_snapshot(
    matched_code: str,
    instrument: "object | None",
    latest,
    prev,
) -> dict:
    """由最新/前一根 bar 组装 SSE 载荷（与旧 _fetch_snapshot 输出一致）。"""
    latest_close = latest.close or Decimal("0")
    prev_close = prev.close if prev else None

    change_pct = Decimal("0")
    if prev_close and prev_close != 0:
        change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

    trade_date = latest.trade_date
    if isinstance(trade_date, datetime):
        ts_seconds = trade_date.timestamp()
    elif trade_date is not None:
        # ``trade_date`` is often a ``datetime.date`` (no tz, no time component).
        ts_seconds = datetime.combine(trade_date, datetime.min.time()).timestamp()
    else:
        ts_seconds = 0.0

    return {
        "code": matched_code,
        "name": instrument.name if instrument is not None else matched_code,
        "market": instrument.market if instrument is not None else None,
        "price": float(latest_close) if latest_close else 0.0,
        "change_pct": float(change_pct),
        "volume": latest.volume or 0,
        "timestamp": int(ts_seconds * 1000),
    }


def _collect_payload(codes: list[str]) -> dict | None:
    """Fetch all snapshots in one short-lived session.

    The session is fully closed (returning its pooled connection)
    BEFORE this function returns, so the SSE generator never holds a
    database connection while suspended at a ``yield`` waiting on the
    client. Previously the connection stayed checked out across the
    ``yield`` and the network flush, which piled up under slow or
    zombie SSE clients and contributed to pool exhaustion.

    本函数是纯同步实现，由 async 生成器经 ``anyio.to_thread.run_sync``
    丢到线程池执行，避免同步 SQLAlchemy 查询阻塞 uvicorn 事件循环
    （2026-08-17 审计 HIGH）。session 每轮迭代新建并关闭，不跨线程共享。
    """
    db = SessionLocal()
    try:
        matched = _resolve_matches(db, codes)
        bars = _fetch_latest_two_bars(
            db, {mc for mc, _ in matched.values()}
        )

        snapshots = []
        unknown: list[str] = []
        seen_codes: set[str] = set()
        for code in codes:
            entry = matched.get(code)
            bar_pair = bars.get(entry[0]) if entry else None
            latest = bar_pair.get(1) if bar_pair else None
            if entry is None or latest is None:
                if entry is not None:
                    logger.debug(
                        "SSE snapshot: matched %s but no InstrumentDailyBar rows",
                        entry[0],
                    )
                else:
                    logger.debug("SSE snapshot: no match for code=%s", code)
                unknown.append(code)
                continue
            snap = _build_snapshot(
                entry[0], entry[1], latest, bar_pair.get(2)
            )
            if snap["code"] not in seen_codes:
                snapshots.append(snap)
                seen_codes.add(snap["code"])

        if snapshots or unknown:
            return {"data": snapshots, "unknown": unknown}
        return None
    finally:
        db.close()


async def _price_stream(
    codes: list[str],
) -> AsyncGenerator[str, None]:
    """Yield SSE price events at an interval."""
    deadline = asyncio.get_event_loop().time() + STREAM_TIMEOUT

    while asyncio.get_event_loop().time() < deadline:
        try:
            # 同步 DB 查询丢线程池，避免阻塞事件循环（2026-08-17 审计 HIGH）。
            payload = await anyio.to_thread.run_sync(_collect_payload, codes)
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        else:
            if payload is not None:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        await asyncio.sleep(STREAM_INTERVAL)


@router.get("/prices")
async def price_stream(
    codes: str = Query(..., description="Comma-separated instrument codes, e.g. 510300.SH,159915.SZ"),
):
    """Stream real-time price updates via SSE."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    return StreamingResponse(
        _price_stream(code_list),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
