"""News sentiment LLM pipeline subpackage.

Async, batched LLM (MiniMax default) sentiment processing for news articles.
Reuses the shared ``app.services.llm`` providers; never instantiates
its own LLM client.

Exports
-------
SentimentPipeline   - high-level orchestrator
SentimentCache      - Redis-backed result cache
LLMPipelineMonitor  - cost / call / cache-hit accounting
prompts             - prompt template library
"""

from app.services.news.sentiment import prompts
from app.services.news.sentiment.cache import SentimentCache
from app.services.news.sentiment.monitor import LLMPipelineMonitor
from app.services.news.sentiment.sentiment_pipeline import (
    PipelineResult,
    SentimentPipeline,
)

__all__ = [
    "SentimentPipeline",
    "PipelineResult",
    "SentimentCache",
    "LLMPipelineMonitor",
    "prompts",
]
