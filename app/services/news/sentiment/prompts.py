"""Prompt template library for the sentiment LLM pipeline.

Four templates, each with a single ``.format(**kwargs)`` use site:

  - ``ENTITY_EXTRACTION_PROMPT``   - entity + classification (every article)
  - ``SENTIMENT_ANALYSIS_PROMPT``  - per-symbol sentiment (every article)
  - ``IMPACT_CHAIN_PROMPT``        - first/second-order impact (importance>=4)
  - ``RETAIL_AGGREGATION_PROMPT``  - retail chatter aggregation (every 30min)

System messages are kept short and English so the model does not waste
tokens re-deriving instructions.  The user prompts are in Chinese to
match the platform's analyst-facing content.
"""

# ---------------------------------------------------------------------------
# 1. Entity extraction + classification
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_SYSTEM = (
    "You are a financial text-analysis expert. Always reply with valid JSON only, "
    "no commentary, no markdown fences."
)

ENTITY_EXTRACTION_PROMPT = """你是一个金融文本分析专家。请从以下资讯中提取关键信息。

标题: {title}
正文: {body}

请输出 JSON:
{{
    "symbols": [
        {{"symbol": "AAPL", "market": "us", "confidence": 0.95}},
        {{"symbol": "600519.SH", "market": "cn_a", "confidence": 0.98}}
    ],
    "event_category": "earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor|other",
    "importance": 1-5,
    "reasoning": "简短说明为什么这个 importance 评级"
}}

importance 评级标准:
- 5: 重大事件(财报超预期/重大并购/政策变化/突发事件)
- 4: 重要事件(产品发布/重要人事变动/合作公告)
- 3: 一般关注(行业新闻/分析师观点/市场份额变化)
- 2: 噪音(重复信息/二手报道)
- 1: 几乎无关(社区讨论/个人看法)
"""


# ---------------------------------------------------------------------------
# 2. Per-symbol sentiment
# ---------------------------------------------------------------------------

SENTIMENT_ANALYSIS_SYSTEM = (
    "You are a financial-market sentiment expert. "
    "Always reply with valid JSON only, no commentary, no markdown fences."
)

SENTIMENT_ANALYSIS_PROMPT = """你是一个金融市场情绪分析专家。对以下资讯涉及的每个标的进行情绪打分。

标题: {title}
正文: {body}

涉及的标的: {symbols}

对每个标的输出:
{{
    "symbol": "AAPL",
    "score": -1.0 到 +1.0,
    "label": "negative|neutral|positive",
    "confidence": 0.0 到 1.0,
    "drivers": ["关键驱动因素 1", "驱动因素 2", ...],
    "time_horizon": "intraday|short_term|mid_term|long_term",
    "reasoning": "1-2 句话解释为什么这个情绪评分"
}}

注意:
- 区分短期情绪(受消息面刺激)和长期影响
- 同一事件对不同标的可能是相反情绪(如竞争对手利空)
- 公告类事件通常 confidence 较高,评论类较低

请用 JSON 数组返回,数组中每个元素是一个标的的情绪对象。
"""


# ---------------------------------------------------------------------------
# 3. Impact chain (only for importance >= 4)
# ---------------------------------------------------------------------------

IMPACT_CHAIN_SYSTEM = (
    "You are a buy-side strategist mapping cross-asset impact chains. "
    "Always reply with valid JSON only, no commentary, no markdown fences."
)

IMPACT_CHAIN_PROMPT = """针对以下重大事件(importance >= 4),分析其影响链。

事件: {event}
标的: {symbols}
当前情绪: {sentiment}

请分析:
{{
    "first_order": [
        {{"target": "标的或行业", "impact": "正面/负面/中性", "reason": "..."}}
    ],
    "second_order": [
        {{"target": "...", "impact": "...", "reason": "..."}}
    ],
    "time_dimension": {{
        "intraday": "预计影响...",
        "1_week": "...",
        "1_month": "...",
        "1_year": "..."
    }},
    "counter_argument": "看空/看多的反向观点是什么",
    "uncertainty": "主要不确定性来源"
}}
"""


# ---------------------------------------------------------------------------
# 4. Retail chatter aggregation
# ---------------------------------------------------------------------------

RETAIL_AGGREGATION_SYSTEM = (
    "You are a behavioural-finance analyst summarising retail trader "
    "discourse. Always reply with valid JSON only, no commentary, "
    "no markdown fences."
)

RETAIL_AGGREGATION_PROMPT = """以下是 {N} 条关于 {symbol} 的散户讨论(来自雪球/Reddit/Stocktwits):

{comments}

请输出:
{{
    "overall_sentiment": -1.0 到 1.0,
    "bull_bear_ratio": {{"bull": 65, "bear": 35}},
    "main_themes": [
        {{"theme": "看多主题", "percentage": 30}}
    ],
    "controversy_level": 0.0 到 1.0,
    "manipulation_signals": {{
        "coordinated_accounts": false,
        "sudden_consensus": false,
        "evidence": "..."
    }},
    "vs_smart_money": "散户情绪与机构观点是否背离",
    "summary": "2-3 句话总结散户整体看法"
}}
"""


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

ALL_PROMPTS = {
    "entity": (ENTITY_EXTRACTION_SYSTEM, ENTITY_EXTRACTION_PROMPT),
    "sentiment": (SENTIMENT_ANALYSIS_SYSTEM, SENTIMENT_ANALYSIS_PROMPT),
    "impact": (IMPACT_CHAIN_SYSTEM, IMPACT_CHAIN_PROMPT),
    "retail": (RETAIL_AGGREGATION_SYSTEM, RETAIL_AGGREGATION_PROMPT),
}

# Importance threshold for the more expensive impact-chain call.
IMPACT_CHAIN_IMPORTANCE_THRESHOLD = 4
