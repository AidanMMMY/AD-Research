"""AI research chat service.

Provides data-aware conversational AI for investment research.
Each chat session maintains context; new messages fetch the latest
indicator/score data for instruments mentioned in the conversation.

Uses AnthropicProvider with data pre-loading for grounded responses.
"""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo
from app.models.research import AIChatMessage, AIChatSession
from app.models.scoring import ETFScore
from app.services.llm import get_llm_provider, LLMService

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """你是投资研究助手，可以访问平台的ETF筛选、技术指标和评分数据。
回答需简洁、数据驱动，使用中文。
当讨论具体标的时，优先引用提供的实时数据。
如果数据不足以做出判断，明确说明。
你的回答应包含：
1. 数据分析（引用具体数值）
2. 技术面解读（RSI、均线、MACD等）
3. 风险提示
4. 可操作建议（如适用）

回复格式：使用Markdown，可以包含表格、列表和加粗文字。"""


class ChatService:
    """AI research chat assistant."""

    def __init__(self, db: Session) -> None:
        self.db = db
        provider = get_llm_provider()
        self.llm = LLMService(provider)

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def create_session(self, user_id: int, title: str | None = None) -> AIChatSession:
        session = AIChatSession(
            user_id=user_id,
            title=title or "新对话",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_sessions(self, user_id: int) -> list[AIChatSession]:
        return (
            self.db.query(AIChatSession)
            .filter(AIChatSession.user_id == user_id)
            .order_by(AIChatSession.updated_at.desc())
            .all()
        )

    def get_session(
        self, session_id: int, user_id: int | None = None
    ) -> AIChatSession | None:
        """Fetch a chat session, optionally scoped to a user.

        When ``user_id`` is given, sessions owned by another user are treated
        as not found (404 semantics) so pool existence/ownership is not leaked
        (IDOR fix, 2026-08-06).
        """
        query = self.db.query(AIChatSession).filter(AIChatSession.id == session_id)
        if user_id is not None:
            query = query.filter(AIChatSession.user_id == user_id)
        return query.first()

    def delete_session(self, session_id: int, user_id: int | None = None) -> bool:
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return False
        self.db.delete(session)
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(
        self, session_id: int, content: str, user_id: int | None = None
    ) -> AIChatMessage:
        """Send a user message and get AI response.

        ``user_id`` scopes the operation to the session owner (IDOR fix) —
        a message sent into another user's session raises ``ValueError``.

        1. Save user message
        2. Detect instrument codes in message
        3. Fetch current data for those instruments
        4. Build context-enhanced system prompt
        5. Get LLM response
        6. Save and return AI message
        """
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # 1. Save user message
        user_msg = AIChatMessage(
            session_id=session_id,
            role="user",
            content=content,
        )
        self.db.add(user_msg)
        self.db.commit()

        # 2. Detect instrument codes mentioned
        codes = self._extract_codes(content)

        # 3. Fetch context data
        context = self._build_data_context(codes) if codes else ""

        # 4. Build conversation history.
        # NOTE: history already includes the user message persisted in
        # step 1 (we committed before calling _get_history), so we use it
        # directly as the LLM message list — appending another user message
        # here would duplicate it (previously did so, wasting tokens and
        # confusing the model).
        messages = self._get_history(session_id)

        # 5. Build system prompt with context
        system = CHAT_SYSTEM_PROMPT
        if context:
            system += f"\n\n**当前可用的真实数据：**\n{context}"

        # 6. Get LLM response
        try:
            response_text = self.llm.chat_with_cache(
                messages=messages,
                system=system,
                max_tokens=1024,
                temperature=0.6,
            )
        except Exception as exc:
            logger.error("Chat LLM call failed: %s", exc)
            response_text = f"抱歉，AI服务暂时不可用。错误: {exc}"

        # 7. Save AI message
        ai_msg = AIChatMessage(
            session_id=session_id,
            role="assistant",
            content=response_text,
        )
        self.db.add(ai_msg)

        # 8. Update session timestamp and auto-title
        session.updated_at = datetime.now()
        if session.title == "新对话" and len(content) > 2:
            session.title = content[:50] + ("..." if len(content) > 50 else "")

        self.db.commit()
        self.db.refresh(ai_msg)
        return ai_msg

    def get_messages(
        self, session_id: int, user_id: int | None = None
    ) -> list[AIChatMessage]:
        """Return messages for a session, scoped to the owner (IDOR fix)."""
        if self.get_session(session_id, user_id=user_id) is None:
            return []
        return (
            self.db.query(AIChatMessage)
            .filter(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at.asc())
            .all()
        )

    # ------------------------------------------------------------------
    # Context Building
    # ------------------------------------------------------------------

    def _extract_codes(self, text: str) -> list[str]:
        """Extract instrument codes from user message.

        Matches patterns like AAPL.US, SPY.US, 510050.SH, etc.
        """
        import re
        pattern = r'\b([A-Z0-9]+)\.(US|SH|SZ|HK|JP)\b'
        matches = re.findall(pattern, text.upper())
        return [f"{m[0]}.{m[1]}" for m in matches]

    def _build_data_context(self, codes: list[str]) -> str:
        """Build a text summary of current data for given codes."""
        if not codes:
            return ""

        codes = codes[:5]  # Limit to 5 instruments

        # Batch all lookups into 3 IN queries (perf audit 2026-08-06) —
        # previously this issued 3 SELECTs per code on every chat message.
        instruments = {
            i.code: i
            for i in (
                self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
            )
        }

        def _latest_by_code(model) -> dict[str, Any]:
            latest_subq = (
                self.db.query(
                    model.etf_code,
                    func.max(model.trade_date).label("latest_date"),
                )
                .filter(model.etf_code.in_(codes))
                .group_by(model.etf_code)
                .subquery()
            )
            rows = (
                self.db.query(model)
                .join(
                    latest_subq,
                    (model.etf_code == latest_subq.c.etf_code)
                    & (model.trade_date == latest_subq.c.latest_date),
                )
                .all()
            )
            return {r.etf_code: r for r in rows}

        indicators = _latest_by_code(ETFIndicator)
        scores = _latest_by_code(ETFScore)

        parts = []
        for code in codes:
            instrument = instruments.get(code)
            if not instrument:
                continue
            indicator = indicators.get(code)
            score = scores.get(code)

            info_lines = [f"**{code}** ({instrument.name})"]
            if indicator:
                if indicator.rsi14 is not None:
                    info_lines.append(f"  RSI(14): {float(indicator.rsi14):.1f}")
                if indicator.return_1m is not None:
                    # Stored as decimal; multiply by 100 for percentage display.
                    info_lines.append(f"  1月收益: {float(indicator.return_1m) * 100:+.2f}%")
                if indicator.return_3m is not None:
                    info_lines.append(f"  3月收益: {float(indicator.return_3m) * 100:+.2f}%")
                if indicator.volatility_20d is not None:
                    info_lines.append(f"  20日波动率: {float(indicator.volatility_20d) * 100:.2f}%")
                if indicator.sharpe_1y is not None:
                    info_lines.append(f"  1年夏普: {float(indicator.sharpe_1y):.2f}")
            if score and score.composite_score is not None:
                info_lines.append(f"  综合评分: {float(score.composite_score):.1f}")

            parts.append("\n".join(info_lines))

        return "\n\n".join(parts)

    def _get_history(
        self, session_id: int, user_id: int | None = None
    ) -> list[dict[str, str]]:
        """Get recent chat history for context (owner-scoped)."""
        if self.get_session(session_id, user_id=user_id) is None:
            return []
        messages = (
            self.db.query(AIChatMessage)
            .filter(AIChatMessage.session_id == session_id)
            .order_by(AIChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        # Return in chronological order
        return [
            {"role": m.role, "content": m.content}
            for m in reversed(messages)
        ]
