"""Self-service email registration domain logic (2026-10-25 design §3).

Layering: ``app/api/v1/auth.py`` owns HTTP concerns (status codes, rate
limits, token issuance); this module owns the verification-code state
machine, account creation and outbound emails.

Hard rule: the plaintext verification code never touches the logs or any
exception message — it exists only in the outgoing email body. Database
rows store the SHA-256 hash and comparisons are constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
from jose import jwt
from sqlalchemy.orm import Session

from app.config import auth_settings, get_settings
from app.core.log_sanitize import sanitize
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.services.transactional_email import send_email

logger = logging.getLogger(__name__)

# ── Policy constants ──

CODE_TTL_MINUTES = 10
MAX_CODE_ATTEMPTS = 5
MAGIC_LINK_MINUTES = 15
MAGIC_LINK_PURPOSE = "register_verify"

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

USERNAME_POLICY_HINT = "用户名需为 3-30 位字母、数字或下划线"
EMAIL_POLICY_HINT = "邮箱格式不正确"

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"

# Suffix pool for "username taken" suggestions (design §1: e.g. aidan_2026).
_SUGGESTION_SUFFIXES = ("2026", "01", "hq", "trader", "lab", "vip", "pro", "888")


# ── Exceptions (endpoint maps these to HTTP) ──


class CodeInvalidError(Exception):
    """Wrong code; ``remaining_attempts`` left before the row is voided."""

    def __init__(self, remaining_attempts: int):
        super().__init__("invalid code")
        self.remaining_attempts = remaining_attempts


class CodeExpiredError(Exception):
    """Code past its TTL or voided after MAX_CODE_ATTEMPTS failures."""


# ── Validation helpers ──


def validate_username(username: str) -> str | None:
    """Return a Chinese error message when the username breaks the rule."""
    if not username or not USERNAME_RE.match(username):
        return USERNAME_POLICY_HINT
    return None


def validate_email_format(email: str) -> str | None:
    """Return a Chinese error message when the email is not well-formed."""
    if not email or len(email) > 255 or not EMAIL_RE.match(email):
        return EMAIL_POLICY_HINT
    return None


def normalize_email(email: str) -> str:
    """Lowercase + strip so uniqueness checks are case-insensitive."""
    return (email or "").strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()


def username_taken(db: Session, username: str) -> bool:
    return db.query(User.id).filter(User.username == username).first() is not None


def suggest_usernames(db: Session, username: str) -> list[str]:
    """Three free alternatives built from the requested username."""
    base = username[:24]
    rng = secrets.SystemRandom()
    suffixes = list(_SUGGESTION_SUFFIXES)
    rng.shuffle(suffixes)
    suggestions: list[str] = []
    for suffix in suffixes:
        candidate = f"{base}_{suffix}"
        if len(candidate) > 30 or not USERNAME_RE.match(candidate):
            continue
        if not username_taken(db, candidate) and candidate not in suggestions:
            suggestions.append(candidate)
        if len(suggestions) == 3:
            return suggestions
    while len(suggestions) < 3:  # degenerate pool → random digits
        candidate = f"{base[:20]}_{rng.randrange(1000, 9999)}"
        if not username_taken(db, candidate) and candidate not in suggestions:
            suggestions.append(candidate)
    return suggestions


# ── Verification code state machine ──


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on DateTime(timezone=True); treat naive as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _generate_code() -> str:
    """6-digit numeric code from a CSPRNG (patched to a fixed value in tests)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def issue_verification_code(db: Session, user: User) -> tuple[str, str]:
    """Void pending codes and issue a fresh one.

    Caller owns the commit. Returns ``(code, magic_link)`` — the plaintext
    code must flow only into the email body.
    """
    now = _utcnow()
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)
    code = _generate_code()
    db.add(
        EmailVerification(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
            attempts=0,
        )
    )
    return code, build_magic_link(user)


def consume_verification_code(db: Session, user: User, code: str) -> None:
    """Verify one code attempt against the newest pending row.

    Success: mark the row consumed and the user's email verified (caller
    commits). Failure raises ``CodeExpiredError`` (TTL passed / row voided)
    or ``CodeInvalidError`` (wrong code — the attempts bump is flushed so
    the brute-force budget survives across requests; caller commits).
    """
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.user_id == user.id,
            EmailVerification.consumed_at.is_(None),
        )
        .order_by(EmailVerification.id.desc())
        .first()
    )
    if row is None:
        raise CodeInvalidError(0)
    if _as_utc(row.expires_at) <= _utcnow():
        raise CodeExpiredError
    if row.attempts >= MAX_CODE_ATTEMPTS:
        # Voided by failed attempts — same observable outcome as expiry.
        raise CodeExpiredError
    if not hmac.compare_digest(_hash_code(code), row.code_hash):
        row.attempts += 1
        db.flush()
        raise CodeInvalidError(max(0, MAX_CODE_ATTEMPTS - row.attempts))
    mark_email_verified(db, user)


def mark_email_verified(db: Session, user: User) -> None:
    """Set ``email_verified_at`` and void any pending codes (no commit)."""
    now = _utcnow()
    user.email_verified_at = now
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)


# ── Account creation ──


def create_registration(
    db: Session, *, email: str, username: str, password: str
) -> tuple[User, str, str]:
    """Create the unverified user row plus the first verification code.

    Caller owns the commit. Returns ``(user, code, magic_link)``.
    """
    user = User(
        username=username,
        password_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role="user",
        is_active=True,
        must_change_password=False,
        email=email,
        email_verified_at=None,
    )
    db.add(user)
    db.flush()  # populate user.id for the FK and the magic-link JWT
    code, magic_link = issue_verification_code(db, user)
    logger.info("registration_created: %s", sanitize(f"username={username}"))
    return user, code, magic_link


# ── Magic link (short-lived JWT, zero extra storage) ──


def create_magic_link_token(user_id: int) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "purpose": MAGIC_LINK_PURPOSE,
        "iat": now,
        "exp": now + timedelta(minutes=MAGIC_LINK_MINUTES),
    }
    return jwt.encode(payload, auth_settings.SECRET_KEY, algorithm="HS256")


def build_magic_link(user: User) -> str:
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/api/v1/auth/verify-link?token={create_magic_link_token(user.id)}"


# ── Outbound emails ──


def _render_template(name: str, **values: str) -> str:
    """Placeholder-replace renderer ({{key}}); values are code/link only."""
    template = (_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def send_verification_email(to: str, code: str, magic_link: str) -> bool:
    html = _render_template("verify_registration.html", code=code, magic_link=magic_link)
    text = (
        "AlloyResearch 邮箱验证 / Verify your email\n\n"
        f"点击链接完成验证（15 分钟内有效）/ Open this link to verify (valid 15 min):\n"
        f"{magic_link}\n\n"
        f"验证码（10 分钟内有效）/ Code (valid 10 min): {code}\n\n"
        "如果这不是你的操作，请忽略本邮件 / If this wasn't you, ignore this email.\n\n"
        "—— AlloyResearch"
    )
    return send_email(to, "AlloyResearch 邮箱验证 / Verify your email", html, text)


def send_already_registered_notice(to: str) -> bool:
    """Anti-enumeration notice for a registration attempt on an existing email."""
    base = get_settings().frontend_base_url.rstrip("/")
    html = _render_template("already_registered.html", login_link=f"{base}/login")
    text = (
        "AlloyResearch 账号提醒 / You already have an account\n\n"
        "刚才有人（可能是你）尝试用这个邮箱注册 AlloyResearch，但该邮箱已有账号。\n"
        "Someone (possibly you) tried to sign up with this email, but an account "
        "already exists.\n\n"
        "请直接用你的用户名登录 / Please sign in with your existing username.\n\n"
        "—— AlloyResearch"
    )
    return send_email(to, "AlloyResearch 账号提醒 / You already have an account", html, text)
