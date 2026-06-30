"""Loader for the master ``news_article`` / ``news_article_symbol`` ORM models.

Why this exists
---------------
The file ``app/models/news.py`` defines the master news tables. There
is also a *package* ``app/models/news/`` (Xueqiu's tables) living
alongside it. Python's import machinery prefers the package, so a
plain ``from app.models.news import NewsArticle`` resolves to
``app/models/news/__init__.py`` (which re-exports Xueqiu classes, not
``NewsArticle``).

To avoid re-shaping the layout — that decision belongs to Agent A
which owns the package — we load ``app/models/news.py`` directly via
``importlib.util`` the first time we need it, and cache the resulting
module in ``sys.modules`` so subsequent imports are normal.

Public surface
--------------
``load_news_models()`` — returns the loaded module; idempotent.
``NewsArticle``, ``NewsArticleSymbol``, ``RedditCommentCache`` are
re-exported at module level for convenience.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models._news_article import (  # type: ignore[import-not-found]
        NewsArticle,
        NewsArticleSymbol,
        RedditCommentCache,
    )

_LOADED_KEY = "app.models._news_article"
_NEWS_FILE = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "models", "news.py",
    )
)


def _load_news_models_module() -> ModuleType:
    """Load ``app/models/news.py`` as a module and stash it in ``sys.modules``."""
    if _LOADED_KEY in sys.modules:
        return sys.modules[_LOADED_KEY]
    spec = importlib.util.spec_from_file_location(_LOADED_KEY, _NEWS_FILE)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not build import spec for news models at {_NEWS_FILE!r}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LOADED_KEY] = module
    spec.loader.exec_module(module)
    return module


def load_news_models() -> ModuleType:
    """Return the news-models module (load on first call, cache afterwards)."""
    return _load_news_models_module()


# Eagerly load at import time so callers can do::
#
#     from app.services.news._model_loader import NewsArticle
#
# even though that import would normally be a circular. The ``__getattr__``
# below routes attribute access through the loaded module.
class _NewsModelsProxy:
    """Lazily resolve attributes from the loaded news models module."""

    def __getattr__(self, name: str):
        return getattr(load_news_models(), name)


_proxy = _NewsModelsProxy()


def __getattr__(name: str):  # PEP 562 — module-level __getattr__
    if name in ("NewsArticle", "NewsArticleSymbol", "RedditCommentCache"):
        return getattr(load_news_models(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Touch the proxy at import time so the module is loaded — this makes
# the class instances addressable and lets ``isinstance`` checks work.
load_news_models()
