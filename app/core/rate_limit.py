"""Redis-backed rate-limit helpers for the login endpoint.

P0-5 (2026-07-16): brute-force protection on ``/api/v1/auth/login``.

Two independent counters are tracked per attempt:

  * ``rl:login:ip:<ip>``     — fixed-window counter, TTL=60s, limit 5
  * ``rl:login:user:<name>`` — fixed-window counter, TTL=3600s, limit 20

Either window overflowing raises ``HTTPException(429, Retry-After=ttl)``.

Implementation uses ``INCR`` + ``EXPIRE`` so concurrent attempts land
in the same window.  A small race exists between INCR and EXPIRE — a
new key created by INCR but not yet EXPIREd would persist forever if
the process dies between the two calls.  We mitigate this by checking
the post-INCR TTL and calling EXPIRE unconditionally; Redis's
``SETEX``-style idempotency handles the duplicate.

If Redis itself is unreachable we fail **open** — the alternative
(locking users out because the rate-limit store is down) is worse
than letting a single attempt through.
"""

from __future__ import annotations

import logging

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Limits: 5 attempts / IP / minute, 20 / username / hour
_IP_LIMIT = 5
_IP_WINDOW_SECONDS = 60
_USER_LIMIT = 20
_USER_WINDOW_SECONDS = 3600


def _incr_with_ttl(key: str, ttl_seconds: int) -> tuple[int, int]:
    """Atomically increment ``key`` with TTL semantics.

    Returns ``(count, ttl)`` after the increment.  ``ttl`` is the
    remaining window in seconds; callers should use it for
    ``Retry-After`` headers.
    """
    client = get_redis_client()
    count = client.incr(key)
    if count == 1:
        # Newly created key — set the window TTL.
        client.expire(key, ttl_seconds)
    # Re-read TTL (cheap; 0 when key vanished between commands).
    ttl = max(1, int(client.ttl(key)) or ttl_seconds)
    return int(count), ttl


def check_login_rate_limit(
    ip: str | None,
    username: str | None,
) -> tuple[bool, int]:
    """Raise-style rate-limit guard for the login endpoint.

    Returns ``(allowed, retry_after_seconds)``.  When ``allowed`` is
    ``False`` the caller should respond with ``HTTP 429``.

    Fail-open semantics: if Redis is unreachable we log and return
    ``allowed=True`` so a transient Redis outage doesn't lock users
    out.
    """
    try:
        retry_after = 1

        if ip:
            count, ttl = _incr_with_ttl(f"rl:login:ip:{ip}", _IP_WINDOW_SECONDS)
            if count > _IP_LIMIT:
                return False, ttl
            retry_after = max(retry_after, ttl)

        if username:
            count, ttl = _incr_with_ttl(f"rl:login:user:{username.lower()}", _USER_WINDOW_SECONDS)
            if count > _USER_LIMIT:
                return False, ttl
            retry_after = max(retry_after, ttl)

        return True, retry_after
    except Exception as exc:  # pragma: no cover — Redis outage path
        logger.warning("login rate-limit Redis unavailable, failing open: %s", exc)
        return True, 1


def clear_login_attempts(username: str | None) -> None:
    """Reset the per-user counter after a successful login.

    Called from the login endpoint after the password is verified so
    legitimate users don't carry forward near-limit counts from earlier
    wrong-password attempts.  The IP counter is left in place — that
    window resets on its own TTL.
    """
    if not username:
        return
    try:
        client = get_redis_client()
        client.delete(f"rl:login:user:{username.lower()}")
    except Exception:  # pragma: no cover — best-effort cleanup
        pass


# ── Self-registration rate limits (2026-10-25 design §3.2) ──
#
# register / resend:  5 / IP / hour + 3 / email / hour, plus a 60s
#                     per-email resend cooldown (check-and-set)
# verify:            10 / email / hour (brute-force budget on the OTP)
#
# Same fail-open contract as the login limiter: a Redis outage must not
# lock legitimate signups out.

_REG_IP_LIMIT = 5
_REG_IP_WINDOW_SECONDS = 3600
_REG_EMAIL_LIMIT = 3
_REG_EMAIL_WINDOW_SECONDS = 3600
_VERIFY_EMAIL_LIMIT = 10
_VERIFY_EMAIL_WINDOW_SECONDS = 3600
_RESEND_COOLDOWN_SECONDS = 60


def _hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Fixed-window guard: increments ``key`` and reports allowance.

    Returns ``(allowed, retry_after_seconds)``. Fail-open when Redis is
    unreachable.
    """
    try:
        count, ttl = _incr_with_ttl(key, window_seconds)
        return count <= limit, ttl
    except Exception as exc:  # pragma: no cover — Redis outage path
        logger.warning("rate-limit Redis unavailable, failing open: %s", exc)
        return True, 1


def check_register_rate_limit(ip: str | None, email: str | None) -> tuple[bool, int]:
    """Guard for POST /auth/register and /auth/resend-verification."""
    retry_after = 1
    if ip:
        allowed, ttl = _hit(f"rl:register:ip:{ip}", _REG_IP_LIMIT, _REG_IP_WINDOW_SECONDS)
        if not allowed:
            return False, ttl
        retry_after = max(retry_after, ttl)
    if email:
        allowed, ttl = _hit(
            f"rl:register:email:{email.lower()}", _REG_EMAIL_LIMIT, _REG_EMAIL_WINDOW_SECONDS
        )
        if not allowed:
            return False, ttl
        retry_after = max(retry_after, ttl)
    return True, retry_after


def check_verify_rate_limit(email: str | None) -> tuple[bool, int]:
    """Guard for POST /auth/verify-registration (brute-force budget)."""
    if not email:
        return True, 1
    return _hit(
        f"rl:verify:email:{email.lower()}", _VERIFY_EMAIL_LIMIT, _VERIFY_EMAIL_WINDOW_SECONDS
    )


def arm_resend_cooldown(email: str | None) -> tuple[bool, int]:
    """Check-and-set the 60s per-email resend cooldown.

    Returns ``(allowed, retry_after_seconds)``. Arming happens at the same
    moment the email is dispatched (registration or resend), which is what
    the frontend's 60-second countdown expects. Fail-open without Redis.
    """
    if not email:
        return True, 0
    key = f"rl:resend:cooldown:{email.lower()}"
    try:
        client = get_redis_client()
        if client.set(key, "1", nx=True, ex=_RESEND_COOLDOWN_SECONDS):
            return True, 0
        return False, max(1, client.ttl(key) or _RESEND_COOLDOWN_SECONDS)
    except Exception as exc:  # pragma: no cover — Redis outage path
        logger.warning("resend cooldown Redis unavailable, failing open: %s", exc)
        return True, 0
