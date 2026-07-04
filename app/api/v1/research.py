"""AI Research API routes.

Endpoints for AI-generated research notes, sentiment analysis,
earnings analysis, and AI chat assistant.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import os

from app.api.deps import get_current_user, get_db
from app.models.etf import ETFInfo
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.research_service import ResearchService
from app.services.sentiment_service import SentimentService, SentimentFetchError

logger = logging.getLogger(__name__)

router = APIRouter()

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_AI_AVAILABLE: bool | None = None


def _ai_is_available() -> bool:
    """Check if AI features are available (cached per process)."""
    global _AI_AVAILABLE
    if _AI_AVAILABLE is None:
        _AI_AVAILABLE = bool(os.getenv("DEEPSEEK_API_KEY", ""))
    return _AI_AVAILABLE


def _require_ai():
    """Raise 503 if AI is not configured."""
    if not _ai_is_available():
        raise HTTPException(
            status_code=503,
            detail="AI 功能未配置。请在 .env 中设置 DEEPSEEK_API_KEY。"
                   "获取 Key: https://platform.deepseek.com/",
        )


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class AIStatusResponse(BaseModel):
    available: bool
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    setup_url: str = "https://platform.deepseek.com/"
    monthly_cost_estimate: str = "极低 (¥2/百万token)"


class GenerateNoteRequest(BaseModel):
    instrument_code: str


class NoteResponse(BaseModel):
    id: int
    instrument_code: str
    name: str | None = None
    name_zh: str | None = None
    note_type: str
    content: str
    summary: str | None = None
    sentiment: str | None = None
    confidence: int | None = None
    generated_at: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class SentimentResponse(BaseModel):
    instrument_code: str
    name: str | None = None
    name_zh: str | None = None
    avg_score: float
    label: str
    positive_count: int
    negative_count: int
    neutral_count: int
    total_articles: int
    period_days: int


class ChatSessionRequest(BaseModel):
    title: str | None = None


class ChatMessageRequest(BaseModel):
    content: str


class ChatSessionResponse(BaseModel):
    id: int
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: str | None = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# AI Status
# ------------------------------------------------------------------

@router.get("/ai/status", response_model=AIStatusResponse)
def get_ai_status():
    """Check whether AI features are available."""
    return AIStatusResponse(available=_ai_is_available())


# ------------------------------------------------------------------
# Research Notes
# ------------------------------------------------------------------

@router.post("/notes/generate", response_model=NoteResponse)
def generate_research_note(
    req: GenerateNoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI research note for an instrument."""
    _require_ai()
    service = ResearchService(db)
    result = service.generate_daily_note(req.instrument_code, user_id=current_user.id)
    if result.is_error:
        # LLM provider failure -> 503 so caller can retry
        if result.error_code == "LLM_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
            )
        # Other errors (INSTRUMENT_NOT_FOUND / INSUFFICIENT_DATA) -> 400
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": result.error_code,
                "error_message": result.error_message,
            },
        )
    instrument = db.query(ETFInfo).filter(ETFInfo.code == result.note.instrument_code).first()
    return _note_to_response(
        result.note,
        name=instrument.name if instrument else None,
        name_zh=instrument.name_zh if instrument else None,
    )


@router.get("/notes/{instrument_code}", response_model=list[NoteResponse])
def get_research_notes(
    instrument_code: str,
    note_type: str | None = Query(None),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get AI research notes for an instrument."""
    _require_ai()
    service = ResearchService(db)
    notes = service.get_notes(instrument_code=instrument_code, note_type=note_type, limit=limit, user_id=current_user.id)
    instrument = db.query(ETFInfo).filter(ETFInfo.code == instrument_code).first()
    name = instrument.name if instrument else None
    name_zh = instrument.name_zh if instrument else None
    return [_note_to_response(n, name=name, name_zh=name_zh) for n in notes]


# ------------------------------------------------------------------
# Sentiment Analysis
# ------------------------------------------------------------------

@router.get("/sentiment/{instrument_code}", response_model=SentimentResponse | None)
def get_sentiment(
    instrument_code: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregate sentiment for an instrument."""
    _require_ai()
    service = SentimentService(db)
    result = service.get_aggregate_sentiment(instrument_code, lookback_days=days)
    if not result:
        return None
    return result


@router.post("/sentiment/{instrument_code}/ingest")
def ingest_sentiment(
    instrument_code: str,
    days: int = Query(3, ge=1, le=7),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger news sentiment ingestion for an instrument."""
    _require_ai()
    service = SentimentService(db)
    try:
        count = service.ingest_finnhub_news(instrument_code, lookback_days=days)
    except SentimentFetchError as exc:
        # Provider failure: surface as 503 so the user knows it's not
        # "no data" but an actual upstream problem.
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "SENTIMENT_PROVIDER_UNAVAILABLE",
                "error_message": str(exc),
            },
        ) from exc
    return {"instrument_code": instrument_code, "articles_ingested": count}


# ------------------------------------------------------------------
# AI Chat
# ------------------------------------------------------------------

@router.post("/chat/sessions", response_model=ChatSessionResponse)
def create_chat_session(
    req: ChatSessionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new AI chat session."""
    _require_ai()
    service = ChatService(db)
    session = service.create_session(current_user.id, title=req.title if req else None)
    return _session_to_response(session)


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
def list_chat_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all AI chat sessions for the current user."""
    _require_ai()
    service = ChatService(db)
    sessions = service.get_sessions(current_user.id)
    return [_session_to_response(s) for s in sessions]


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat session."""
    _require_ai()
    service = ChatService(db)
    ok = service.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.post("/chat/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_chat_message(
    session_id: int,
    req: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message in an AI chat session. Returns the AI response."""
    _require_ai()
    service = ChatService(db)
    try:
        msg = service.send_message(session_id, req.content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _message_to_response(msg)


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
def get_chat_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all messages in a chat session."""
    _require_ai()
    service = ChatService(db)
    messages = service.get_messages(session_id)
    return [_message_to_response(m) for m in messages]


# ------------------------------------------------------------------
# AI Chat — streaming variant
# ------------------------------------------------------------------

# Chunk size (chars) and per-chunk delay used when the LLM provider does
# not expose true streaming. Tuned for an "AI-like" cadence: roughly
# 60-80 chars / second, ~20 ms pause between chunks.
_STREAM_CHUNK_SIZE = 4
_STREAM_CHUNK_DELAY_S = 0.02


def _sse(event: str, data: dict) -> str:
    """Format a single SSE frame with named ``event`` and JSON ``data``."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _chat_stream(
    session_id: int,
    content: str,
    db: Session,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames carrying the assistant reply in chunks.

    Strategy:
      1. Reuse ChatService.send_message to perform detection, context
         loading, LLM call, and message persistence (single source of truth).
      2. After persistence, fan the assistant content out as small text
         chunks so the frontend gets a true streaming experience without
         awaiting the full reply.

    Events:
      - ``meta``    -> {message_id, session_id, role, content_length}
      - ``delta``   -> {chunk: str} (multiple)
      - ``done``    -> {message_id} terminal success
      - ``error``   -> {error: str} on failure (also sent as done)
    """
    try:
        # Run synchronous LLM call + persistence in a worker thread so it
        # doesn't block the event loop while we stream chunks out.
        def _call() -> "AIChatMessage":
            svc = ChatService(db)
            return svc.send_message(session_id, content)

        msg = await asyncio.get_running_loop().run_in_executor(None, _call)
        text = msg.content or ""

        # Optional first frame: metadata about the persisted message.
        yield _sse(
            "meta",
            {
                "message_id": msg.id,
                "session_id": msg.session_id,
                "role": msg.role,
                "content_length": len(text),
            },
        )

        # Char-by-char chunked push (provider doesn't expose streaming).
        for i in range(0, len(text), _STREAM_CHUNK_SIZE):
            yield _sse("delta", {"chunk": text[i : i + _STREAM_CHUNK_SIZE]})
            await asyncio.sleep(_STREAM_CHUNK_DELAY_S)

        yield _sse("done", {"message_id": msg.id})
    except ValueError as exc:
        # Session not found (sent by ChatService).
        logger.info("Chat stream session-not-found: %s", exc)
        yield _sse("error", {"error": str(exc), "code": "SESSION_NOT_FOUND"})
        yield _sse("done", {"message_id": None})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Chat stream failure: %s", exc)
        yield _sse("error", {"error": str(exc), "code": "STREAM_ERROR"})
        yield _sse("done", {"message_id": None})


@router.post("/chat/sessions/{session_id}/messages/stream")
async def stream_chat_message(
    session_id: int,
    req: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message and stream the assistant reply as Server-Sent Events.

    Reuses ``ChatService.send_message`` so context detection, data loading,
    and message persistence stay in one place. The SSE feed then pushes the
    persisted reply out in small text chunks so the UI can render a
    typewriter animation as the response arrives.

    Frontend usage:

        const resp = await fetch(
          `${API}/research/chat/sessions/${id}/messages/stream`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ content }),
          },
        );
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        // Parse ``event: xxx\\ndata: {json}\\n\\n`` frames...
    """
    _require_ai()

    return StreamingResponse(
        _chat_stream(session_id, req.content, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _note_to_response(note, name: str | None = None, name_zh: str | None = None) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        instrument_code=note.instrument_code,
        name=name,
        name_zh=name_zh,
        note_type=note.note_type,
        content=note.content,
        summary=note.summary,
        sentiment=note.sentiment,
        confidence=note.confidence,
        generated_at=note.generated_at.isoformat() if note.generated_at else None,
        created_at=note.created_at.isoformat() if note.created_at else None,
    )


def _session_to_response(session) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at.isoformat() if session.created_at else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
    )


def _message_to_response(msg) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at.isoformat() if msg.created_at else None,
    )
