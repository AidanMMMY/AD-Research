"""AI Research API routes.

Endpoints for AI-generated research notes, sentiment analysis,
earnings analysis, and AI chat assistant.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.research_service import ResearchService
from app.services.sentiment_service import SentimentService

router = APIRouter()


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class GenerateNoteRequest(BaseModel):
    instrument_code: str


class NoteResponse(BaseModel):
    id: int
    instrument_code: str
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
# Research Notes
# ------------------------------------------------------------------

@router.post("/notes/generate", response_model=NoteResponse)
def generate_research_note(
    req: GenerateNoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI research note for an instrument."""
    service = ResearchService(db)
    note = service.generate_daily_note(req.instrument_code)
    if not note:
        raise HTTPException(
            status_code=400,
            detail=f"Could not generate note for {req.instrument_code}. "
                   "Check that the instrument has price data.",
        )
    return _note_to_response(note)


@router.get("/notes/{instrument_code}", response_model=list[NoteResponse])
def get_research_notes(
    instrument_code: str,
    note_type: str | None = Query(None),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get AI research notes for an instrument."""
    service = ResearchService(db)
    notes = service.get_notes(instrument_code=instrument_code, note_type=note_type, limit=limit)
    return [_note_to_response(n) for n in notes]


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
    service = SentimentService(db)
    count = service.ingest_finnhub_news(instrument_code, lookback_days=days)
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
    service = ChatService(db)
    session = service.create_session(current_user.id, title=req.title if req else None)
    return _session_to_response(session)


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
def list_chat_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all AI chat sessions for the current user."""
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
    service = ChatService(db)
    messages = service.get_messages(session_id)
    return [_message_to_response(m) for m in messages]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _note_to_response(note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        instrument_code=note.instrument_code,
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
