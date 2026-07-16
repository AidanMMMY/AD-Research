"""Log sanitization helper (ops P1-3).

Redacts secrets and PII from strings *before* they reach the logging
subsystem so that access logs, error logs, and audit trails never leak:

* Bearer tokens          — ``Authorization: Bearer <jwt>``
* Raw JWTs               — ``xxxxx.yyyyy.zzzzz`` triple-segment tokens
* Passwords              — ``password=...`` / ``"password": "..."`` shapes
* Chinese mobile numbers — ``1[3-9]xxxxxxxxx``
* Email addresses        — ``user@example.com``

The single public entry point is :func:`sanitize`. It is deliberately
defensive: any input type is coerced to ``str`` and a failure inside a
regex substitution can never propagate (a log call must not crash the
request it is describing).

Usage::

    from app.core.log_sanitize import sanitize

    logger.warning("Failed login for %s", sanitize(raw_detail))
"""

from __future__ import annotations

import re

__all__ = ["sanitize"]

# Order matters. We redact the most specific / most sensitive shapes
# first so a later, broader pattern cannot partially reveal a secret that
# an earlier pattern would have fully masked.
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # 1) Authorization: Bearer <token>  →  keep the scheme, drop the token.
    (
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*"),
        "Bearer [REDACTED]",
    ),
    # 2) Standalone JWT (three base64url segments joined by dots).
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
        ),
        "[REDACTED_JWT]",
    ),
    # 3) password / passwd / pwd / secret / token = value  (json or kv form).
    (
        re.compile(
            r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_-]?key)\b"
            r"(\"?\s*[:=]\s*\"?)"
            r"[^\s\"',}&]+"
        ),
        r"\1\2[REDACTED]",
    ),
    # 4) Email addresses.
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    # 5) Chinese mobile numbers (11 digits, 1[3-9] prefix). Bounded by
    #    non-digits so we don't chew into longer numeric ids.
    (
        re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
]


def sanitize(value: object) -> str:
    """Return a copy of ``value`` (coerced to ``str``) with secrets redacted.

    Never raises: on any internal error the original text is returned as a
    best effort so the caller's log statement still emits *something*.
    """
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:  # pragma: no cover — extremely defensive
        return "[UNSTRINGIFIABLE]"

    try:
        for pattern, replacement in _REDACTIONS:
            text = pattern.sub(replacement, text)
    except Exception:  # pragma: no cover — a bad regction must not crash logging
        return text
    return text
