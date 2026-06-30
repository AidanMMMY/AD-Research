"""News / social-sentiment ORM models.

These tables are owned by the Xueqiu crawler (and future agents that
ingest Reddit / Stocktwits / etc). Sentiment scoring tables will live
in a separate file once the scoring service lands.

Sibling file ``../news.py`` (Agent-B-owned) defines the master
``news_article`` / ``news_article_symbol`` / ``reddit_comment_cache``
tables. It cannot be imported via ``from app.models.news import ...``
because Python resolves that to this package first. Downstream
consumers should import it via
``app.services.news._model_loader.load_news_models()`` which uses
``importlib`` to load the file by absolute path.
"""

from app.models.news.xueqiu import XueqiuFetchState, XueqiuUserCache

__all__ = ["XueqiuUserCache", "XueqiuFetchState"]
