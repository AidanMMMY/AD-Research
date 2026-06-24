"""AI research note generation service.

Generates research notes for instruments using LLM-powered analysis
of price data, technical indicators, and composite scores.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo
from app.models.research import ResearchNote
from app.models.scoring import ETFScore
from app.services.llm import DeepSeekProvider, LLMService

logger = logging.getLogger(__name__)

# Number of trading days to include in the prompt context
_CONTEXT_DAYS = 30


class ResearchService:
    """AI research note generator."""

    def __init__(self, db: Session) -> None:
        self.db = db
        provider = DeepSeekProvider()
        self.llm = LLMService(provider)

    # ------------------------------------------------------------------
    # Daily Note
    # ------------------------------------------------------------------

    def generate_daily_note(self, instrument_code: str) -> ResearchNote | None:
        """Generate a daily research note for a single instrument.

        Fetches the last 30 days of price data, latest indicators, and
        composite score, then prompts the LLM to write a concise
        research summary in Chinese.
        """
        # 1. Fetch instrument info
        instrument = (
            self.db.query(ETFInfo).filter(ETFInfo.code == instrument_code).first()
        )
        if not instrument:
            return None

        # 2. Fetch recent daily bars
        start = date.today() - timedelta(days=_CONTEXT_DAYS + 5)
        bars = (
            self.db.query(ETFDailyBar)
            .filter(ETFDailyBar.etf_code == instrument_code)
            .filter(ETFDailyBar.trade_date >= start)
            .order_by(ETFDailyBar.trade_date.asc())
            .all()
        )
        if len(bars) < 5:
            return None

        # 3. Fetch latest indicator
        indicator = (
            self.db.query(ETFIndicator)
            .filter(ETFIndicator.etf_code == instrument_code)
            .order_by(ETFIndicator.trade_date.desc())
            .first()
        )

        # 4. Fetch latest composite score
        score = (
            self.db.query(ETFScore)
            .filter(ETFScore.etf_code == instrument_code)
            .order_by(ETFScore.trade_date.desc())
            .first()
        )

        # 5. Build data context
        price_summary = self._build_price_summary(instrument, bars)
        indicator_text = self._build_indicator_text(indicator)
        score_text = self._build_score_text(score)

        # 6. Build prompt
        prompt = f"""分析以下标的的近况并撰写一份简短的研究笔记（2-3段，中文）：

**基本信息：**
- 代码: {instrument.code}
- 名称: {instrument.name}
- 类型: {instrument.instrument_type or 'ETF'}
- 市场: US

**近30个交易日价格走势：**
{price_summary}

**最新技术指标：**
{indicator_text}

**综合评分：**
{score_text}

请以专业卖方分析师的口吻撰写。包含：
1. 近期价格走势总结
2. 关键技术信号分析（RSI、MACD、均线等）
3. 风险提示
4. 一句话投资观点

以JSON格式输出：
{{"summary": "一句话摘要", "content": "完整研报(markdown)", "sentiment": "bullish或bearish或neutral", "confidence": 1-10}}
"""
        try:
            result = self.llm.complete_with_cache(
                prompt=prompt,
                system=self.llm.RESEARCH_ANALYST_SYSTEM,
                max_tokens=800,
                temperature=0.5,
            )
        except Exception as exc:
            logger.error("Failed to generate note for %s: %s", instrument_code, exc)
            return None

        # 7. Parse response
        parsed = self._parse_json_response(result)

        # 8. Store in DB
        note = ResearchNote(
            instrument_code=instrument_code,
            note_type="daily_summary",
            content=parsed.get("content", result),
            summary=parsed.get("summary", ""),
            sentiment=parsed.get("sentiment", "neutral"),
            confidence=parsed.get("confidence", 5),
            source_data={
                "latest_close": float(bars[-1].close) if bars[-1].close else 0,
                "latest_date": bars[-1].trade_date.isoformat() if bars[-1].trade_date else "",
                "num_bars": len(bars),
                "rsi14": float(indicator.rsi14) if indicator and indicator.rsi14 else None,
                "composite_score": float(score.composite_score) if score and score.composite_score else None,
            },
            generated_at=datetime.now(),
        )
        self.db.add(note)
        self.db.commit()

        logger.info("Generated research note for %s: %s", instrument_code, note.summary)
        return note

    # ------------------------------------------------------------------
    # Pool Weekly Review
    # ------------------------------------------------------------------

    def generate_pool_review(self, pool_id: int, instrument_codes: list[str]) -> ResearchNote | None:
        """Generate a weekly review for all instruments in a pool."""
        if not instrument_codes:
            return None

        summaries = []
        for code in instrument_codes[:10]:  # Limit to 10 to manage prompt size
            latest_note = (
                self.db.query(ResearchNote)
                .filter(ResearchNote.instrument_code == code)
                .order_by(ResearchNote.created_at.desc())
                .first()
            )
            if latest_note:
                summaries.append(f"- {code}: {latest_note.summary}")

        if not summaries:
            return None

        prompt = f"""以下是标的池中各项标的的最新研究摘要：

{chr(10).join(summaries)}

请撰写一份池综合周报（2-3段，中文），涵盖：
1. 整体表现回顾
2. 值得关注的标的（提及具体代码）
3. 未来一周关注要点

以JSON格式输出：
{{"summary": "一句话摘要", "content": "完整周报(markdown)", "sentiment": "bullish或bearish或neutral"}}
"""
        try:
            result = self.llm.complete_with_cache(
                prompt=prompt,
                system=self.llm.RESEARCH_ANALYST_SYSTEM,
                max_tokens=600,
                temperature=0.5,
            )
        except Exception as exc:
            logger.error("Failed to generate pool review: %s", exc)
            return None

        parsed = self._parse_json_response(result)

        note = ResearchNote(
            instrument_code="__pool__",  # Sentinel for pool-level notes
            note_type="weekly_review",
            content=parsed.get("content", result),
            summary=parsed.get("summary", ""),
            sentiment=parsed.get("sentiment", "neutral"),
            source_data={"pool_id": pool_id, "instruments": instrument_codes},
            generated_at=datetime.now(),
        )
        self.db.add(note)
        self.db.commit()
        return note

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_notes(
        self,
        instrument_code: str | None = None,
        note_type: str | None = None,
        limit: int = 20,
    ) -> list[ResearchNote]:
        """Query research notes with optional filtering."""
        q = self.db.query(ResearchNote)
        if instrument_code:
            q = q.filter(ResearchNote.instrument_code == instrument_code)
        if note_type:
            q = q.filter(ResearchNote.note_type == note_type)
        return q.order_by(ResearchNote.created_at.desc()).limit(limit).all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_price_summary(self, instrument: ETFInfo, bars: list[ETFDailyBar]) -> str:
        if not bars:
            return "无数据"

        closes = [float(b.close) for b in bars if b.close]
        if len(closes) < 2:
            return "数据不足"

        first = closes[0]
        last = closes[-1]
        change = (last - first) / first * 100 if first else 0
        high = max(closes)
        low = min(closes)

        lines = [
            f"期初: {first:.2f} | 最新: {last:.2f} | 区间涨跌: {change:+.2f}%",
            f"区间最高: {high:.2f} | 区间最低: {low:.2f}",
        ]

        # Add last 5 daily closes
        recent = closes[-5:]
        dates = [b.trade_date.isoformat() for b in bars[-5:] if b.trade_date]
        for i, (d, c) in enumerate(zip(dates, recent, strict=False)):
            chg = (c - closes[-6 + i]) / closes[-6 + i] * 100 if i > 0 else 0
            sign = "+" if chg >= 0 else ""
            lines.append(f"  {d}: {c:.2f} ({sign}{chg:.2f}%)")

        return "\n".join(lines)

    def _build_indicator_text(self, indicator: ETFIndicator | None) -> str:
        if not indicator:
            return "无指标数据"

        parts = []
        if indicator.rsi14 is not None:
            rsi = float(indicator.rsi14)
            level = "超买" if rsi > 70 else ("超卖" if rsi < 30 else "中性")
            parts.append(f"RSI(14): {rsi:.1f} ({level})")
        if indicator.ma20 is not None:
            parts.append(f"MA20: {float(indicator.ma20):.2f}")
        if indicator.ma60 is not None:
            parts.append(f"MA60: {float(indicator.ma60):.2f}")
        if indicator.volatility_20d is not None:
            parts.append(f"20日波动率: {float(indicator.volatility_20d):.2f}%")
        if indicator.sharpe_1y is not None:
            parts.append(f"1年夏普: {float(indicator.sharpe_1y):.2f}")
        if indicator.return_1m is not None:
            parts.append(f"1月收益: {float(indicator.return_1m):+.2f}%")
        if indicator.return_3m is not None:
            parts.append(f"3月收益: {float(indicator.return_3m):+.2f}%")
        return "\n".join(parts) if parts else "无指标数据"

    def _build_score_text(self, score: ETFScore | None) -> str:
        if not score:
            return "无评分数据"
        parts = [f"综合评分: {float(score.composite_score or 0):.1f}"]
        if score.return_score is not None:
            parts.append(f"  收益: {float(score.return_score):.1f}")
        if score.risk_score is not None:
            parts.append(f"  风险: {float(score.risk_score):.1f}")
        if score.trend_score is not None:
            parts.append(f"  趋势: {float(score.trend_score):.1f}")
        return "\n".join(parts)

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract JSON from LLM response. Falls back to raw text."""
        text = text.strip()
        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to extract JSON block from markdown
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass
        # Try braces
        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {"content": text}
