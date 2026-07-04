"""AI research and chat ORM models.

Tables for AI-generated research notes, sentiment data, and
AI chat conversations.
"""

from sqlalchemy import (
    DECIMAL,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ResearchNote(Base):
    """AI-generated research notes for instruments."""

    __tablename__ = "research_note"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    instrument_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="Instrument code",
    )
    note_type = Column(
        String(50),
        nullable=False,
        comment="Note type: daily_summary, weekly_review, earnings_reaction, earnings_preview, manual",
    )
    content = Column(Text, nullable=False, comment="Full research note (markdown)")
    summary = Column(String(500), comment="One-line summary")
    sentiment = Column(String(20), comment="bullish, bearish, neutral")
    confidence = Column(Integer, comment="Confidence score 1-10")
    source_data = Column(JSON, comment="Snapshot of indicator/price data used")
    generated_at = Column(DateTime, comment="When this note was generated")
    created_at = Column(DateTime, server_default=func.now(), comment="Creation time")

    instrument = relationship("ETFInfo", backref="research_notes")


class SentimentData(Base):
    """Multi-source sentiment data for instruments."""

    __tablename__ = "sentiment_data"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    instrument_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        comment="Instrument code (NULL for market-wide)",
    )
    source = Column(
        String(50),
        nullable=False,
        comment="Source: finnhub_news, gdelt, earnings_call",
    )
    title = Column(String(500), comment="Article/headline title")
    content = Column(Text, comment="Article/content text")
    url = Column(String(1000), comment="Source URL")
    sentiment_score = Column(
        DECIMAL(5, 4), comment="Sentiment score: -1.0 (bearish) to 1.0 (bullish)"
    )
    sentiment_label = Column(
        String(20), comment="positive, negative, neutral"
    )
    confidence = Column(DECIMAL(5, 4), comment="Model confidence 0-1")
    published_at = Column(DateTime, comment="Original publication time")
    ingested_at = Column(
        DateTime, server_default=func.now(), comment="Ingestion time"
    )

    instrument = relationship("ETFInfo", backref="sentiment_data")


class AIChatSession(Base):
    """AI chat conversation sessions."""

    __tablename__ = "ai_chat_session"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID",
    )
    title = Column(String(200), comment="Auto-generated session title")
    created_at = Column(DateTime, server_default=func.now(), comment="Creation time")
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="Update time"
    )

    messages = relationship(
        "AIChatMessage", back_populates="session", order_by="AIChatMessage.created_at"
    )


class AIChatMessage(Base):
    """Individual messages in an AI chat session."""

    __tablename__ = "ai_chat_message"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    session_id = Column(
        Integer,
        ForeignKey("ai_chat_session.id", ondelete="CASCADE"),
        nullable=False,
        comment="Session ID",
    )
    role = Column(
        String(20), nullable=False, comment="Role: user or assistant"
    )
    content = Column(Text, nullable=False, comment="Message content (markdown)")
    created_at = Column(DateTime, server_default=func.now(), comment="Creation time")

    session = relationship("AIChatSession", back_populates="messages")
