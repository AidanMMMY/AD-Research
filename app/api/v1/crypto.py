"""Cryptocurrency API routes.

Provides endpoints for listing, detail, price history, indicators,
scores, signals, research, and backtest data specifically for
cryptocurrency instruments (market="CRYPTO").

Reuses the existing ETFService, IndicatorService, ScoringService,
SignalService, MarketDataService, and ResearchService so that no
dedicated crypto service is needed — all downstream systems are
already instrument-agnostic.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_etf_service,
    get_indicator_service,
    get_market_data_service,
    get_scoring_service,
    get_signal_service,
)
from app.data.providers.binance_provider import BinanceProvider
from app.schemas.crypto import (
    CryptoDetailOut,
    CryptoInfoOut,
    CryptoListResponse,
    DailyBarOut,
    IndicatorHistoryOut,
    IndicatorOut,
)
from app.schemas.etf import ETFInfoResponse, ETFFilterParams
from app.services.etf_service import ETFService
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MarketDataService
from app.services.research_service import ResearchService
from app.services.scoring_service import ScoringService
from app.services.signal_service import SignalService

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper – enrich ETFInfoResponse with live price from Binance
# ---------------------------------------------------------------------------

def _enrich_with_realtime(
    items: list[ETFInfoResponse],
) -> list[CryptoInfoOut]:
    """Attach latest Binance 24hr ticker data to a list of instrument rows.

    If the Binance API is unreachable the rows are returned with price
    fields set to None — the caller still gets the instrument list.
    """
    codes = [i.code for i in items]
    try:
        provider = BinanceProvider()
        quotes_df = provider.fetch_realtime_quotes(codes)
        quotes = {}
        if not quotes_df.empty:
            for _, row in quotes_df.iterrows():
                quotes[row["etf_code"]] = row
    except Exception:
        quotes = {}

    enriched: list[CryptoInfoOut] = []
    for item in items:
        q = quotes.get(item.code, {}) if quotes else {}
        enriched.append(
            CryptoInfoOut(
                code=item.code,
                name=item.name,
                exchange=item.exchange,
                market=item.market,
                category=item.category,
                currency=item.currency,
                instrument_type=item.instrument_type,
                status=item.status,
                price=q.get("price"),
                change_24h=q.get("price_change_pct"),
                volume_24h=q.get("volume"),
            )
        )
    return enriched


# ---------------------------------------------------------------------------
# Instrument list & detail
# ---------------------------------------------------------------------------


@router.get("", response_model=CryptoListResponse)
def list_crypto(
    market: str = Query("CRYPTO"),
    exchange: str = Query(None),
    category: str = Query(None),
    search: str = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: ETFService = Depends(get_etf_service),
):
    """List cryptocurrency instruments with optional filtering.

    Enriched with live 24hr price data from Binance when available.
    """
    params = ETFFilterParams(
        market=market,
        category=category,
        search=search,
        page=page,
        page_size=page_size,
    )
    response = service.list_etfs(params)
    return CryptoListResponse(
        items=_enrich_with_realtime(response.items),
        total=response.total,
        page=response.page,
        page_size=response.page_size,
    )


@router.get("/{code}", response_model=CryptoDetailOut)
def get_crypto(
    code: str,
    service: ETFService = Depends(get_etf_service),
    indicator_service: IndicatorService = Depends(get_indicator_service),
):
    """Full detail for a single cryptocurrency instrument.

    Includes basic info, live price, and latest technical indicators.
    """
    etf = service.get_etf(code)
    if not etf:
        raise HTTPException(status_code=404, detail=f"Instrument {code} not found")

    # Live price
    price = None
    change_24h = None
    high_24h = None
    low_24h = None
    volume_24h = None
    amount_24h = None
    try:
        provider = BinanceProvider()
        quotes_df = provider.fetch_realtime_quotes([code])
        if not quotes_df.empty:
            row = quotes_df.iloc[0]
            price = row.get("price")
            change_24h = row.get("price_change_pct")
            high_24h = row.get("high")
            low_24h = row.get("low")
            volume_24h = row.get("volume")
            amount_24h = row.get("amount")
    except Exception:
        pass

    # Latest indicator
    latest_indicator = None
    try:
        ind = indicator_service.get_latest(code)
        if ind:
            latest_indicator = IndicatorOut.model_validate(ind)
    except Exception:
        pass

    return CryptoDetailOut(
        code=etf.code,
        name=etf.name,
        exchange=etf.exchange,
        market=etf.market,
        category=etf.category,
        currency=etf.currency,
        instrument_type=etf.instrument_type,
        status=etf.status,
        price=price,
        change_24h=change_24h,
        high_24h=high_24h,
        low_24h=low_24h,
        volume_24h=volume_24h,
        amount_24h=amount_24h,
        latest_indicator=latest_indicator,
    )


# ---------------------------------------------------------------------------
# Price history (OHLCV)
# ---------------------------------------------------------------------------


@router.get("/{code}/history", response_model=list[DailyBarOut])
def get_crypto_history(
    code: str,
    start_date: date = Query(None),
    end_date: date = Query(None),
    limit: int = Query(365, ge=1, le=2000),
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Historical daily OHLCV bars for a cryptocurrency.

    Falls back to Binance provider when no local data exists yet.
    """
    bars = service.get_daily_bars(code, start=start_date, end=end_date, limit=limit)
    if bars:
        return [DailyBarOut.model_validate(b) for b in bars]

    # Fallback: fetch from Binance directly
    try:
        provider = BinanceProvider()
        s = start_date or date.today().replace(year=date.today().year - 1)
        e = end_date or date.today()
        df = provider.fetch_daily_bars([code], s, e)
        if df.empty:
            return []
        df = df.sort_values("trade_date").tail(limit)
        return [
            DailyBarOut(
                trade_date=row["trade_date"],
                open=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("close"),
                volume=row.get("volume"),
                amount=row.get("amount"),
                change_pct=row.get("change_pct"),
            )
            for _, row in df.iterrows()
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


@router.get("/{code}/indicators", response_model=IndicatorOut)
def get_crypto_indicators(
    code: str,
    service: IndicatorService = Depends(get_indicator_service),
):
    """Latest technical indicators for a cryptocurrency."""
    result = service.get_latest(code)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"No indicators found for {code}"
        )
    return IndicatorOut.model_validate(result)


@router.get("/{code}/indicators/history", response_model=IndicatorHistoryOut)
def get_crypto_indicator_history(
    code: str,
    start_date: date = Query(None, alias="start"),
    end_date: date = Query(None, alias="end"),
    limit: int = Query(365, ge=1, le=2000),
    service: IndicatorService = Depends(get_indicator_service),
):
    """Historical technical indicators for a cryptocurrency."""
    items = service.get_history(
        code, start=start_date, end=end_date, limit=limit
    )
    return IndicatorHistoryOut(
        items=[IndicatorOut.model_validate(i) for i in items],
        count=len(items),
    )


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


@router.get("/{code}/score")
def get_crypto_score(
    code: str,
    service: ScoringService = Depends(get_scoring_service),
):
    """Latest composite score for a cryptocurrency."""
    result = service.get_latest_score(code)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"No score found for {code}"
        )
    return result


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


@router.get("/{code}/signals")
def get_crypto_signals(
    code: str,
    limit: int = Query(20, ge=1, le=200),
    service: SignalService = Depends(get_signal_service),
):
    """Recent trading signals for a cryptocurrency."""
    return service.get_signals_for_etf(code, limit=limit)


# ---------------------------------------------------------------------------
# Research / AI note
# ---------------------------------------------------------------------------


@router.get("/{code}/research")
def get_crypto_research(
    code: str,
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Recent AI-generated research notes for a cryptocurrency."""
    service = ResearchService(db)
    notes = service.get_notes(instrument_code=code, limit=limit)
    return [
        {
            "id": n.id,
            "note_type": n.note_type,
            "summary": n.summary,
            "content": n.content,
            "sentiment": n.sentiment,
            "confidence": n.confidence,
            "generated_at": n.generated_at.isoformat() if n.generated_at else None,
        }
        for n in notes
    ]


# ---------------------------------------------------------------------------
# Market list
# ---------------------------------------------------------------------------


@router.get("/markets/list")
def list_crypto_markets(service: ETFService = Depends(get_etf_service)):
    """List distinct market labels available for crypto (always ["CRYPTO"])."""
    return {"markets": ["CRYPTO"]}
