"""Authentication API routes — login, refresh, logout, device management.

Token model:
  - access_token:  short-lived JWT (15 min), includes jti for revocation
  - refresh_token: long-lived opaque token (30 days), stored in DB as SHA-256 hash

Blacklist:
  - On logout, the access token's jti is written to Redis with TTL = remaining lifetime
  - get_current_user checks the blacklist on every authenticated request

Self-registration (2026-10-25 design §3): /register, /verify-registration,
/resend-verification, /check-username, /verify-link plus an
unverified-email login gate. Gated by AUTH_REGISTRATION_ENABLED.
"""

import hashlib
import logging
import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_allow_password_change
from app.config import auth_settings, get_settings
from app.core.audit import client_ip_from_headers
from app.core.database import SessionLocal
from app.core.log_sanitize import sanitize
from app.core.rate_limit import (
    arm_resend_cooldown,
    check_login_rate_limit,
    check_register_rate_limit,
    check_verify_rate_limit,
    clear_login_attempts,
)
from app.core.redis_client import blacklist_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    CheckUsernameResponse,
    DeviceResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterDeviceRequest,
    RegisterRequest,
    ResendVerificationRequest,
    UserResponse,
    VerifyRegistrationRequest,
)
from app.services import registration_service
from app.services.password_policy import validate_password
from app.services.registration_service import CodeExpiredError, CodeInvalidError

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ──

ACCESS_TOKEN_MINUTES = 15  # short-lived
REFRESH_TOKEN_DAYS = 30


# ── DB helper ──


def _get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Crypto helpers ──


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    """SHA-256 for storing refresh tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_refresh_token() -> str:
    """Cryptographically random opaque token."""
    return secrets.token_urlsafe(64)


def _generate_jti() -> str:
    """Unique identifier for JWT revocation."""
    return uuid.uuid4().hex


def _client_ip(http_request: Request) -> str | None:
    """Resolve the caller IP the same way /login does (XFF first)."""
    return client_ip_from_headers(dict(http_request.headers)) or (
        http_request.client.host if http_request.client else None
    )


# ── Token creation / verification ──


def create_access_token(username: str, role: str, jti: str) -> str:
    """Create a short-lived JWT with a unique jti for revocation."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, auth_settings.SECRET_KEY, algorithm="HS256")


def _remaining_ttl(exp: int | float) -> int:
    """Seconds until a Unix timestamp. Minimum 1."""
    return max(1, int(exp - datetime.now(UTC).timestamp()))


def _issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    """Create an access token and persist a new refresh token.

    The caller owns the transaction/commit so token issuance can be atomic
    with login bookkeeping or a password change.
    """
    access_token = create_access_token(user.username, user.role, _generate_jti())
    raw_refresh = _generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    return access_token, raw_refresh


# ── Endpoints ──


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, http_request: Request, db: Session = Depends(_get_db)):
    """Authenticate a user, return access + refresh tokens.

    P0-5 (2026-07-16): rate-limited via Redis. 5 attempts / IP / minute
    and 20 / username / hour. Exceeding either window returns 429 with
    a ``Retry-After`` header.
    """
    client_ip = _client_ip(http_request)
    allowed, retry_after = check_login_rate_limit(client_ip, request.username)
    if not allowed:
        logger.warning(
            "Login rate-limited: %s",
            sanitize(f"username={request.username} ip={client_ip}"),
        )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.username == request.username).first()
    if not user or not _verify_password(request.password, user.password_hash):
        logger.warning(
            "Failed login attempt: %s",
            sanitize(f"username={request.username} ip={client_ip}"),
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    # Self-registration gate (2026-10-25): an account whose email has not
    # been verified yet cannot log in while registration is enabled. The
    # detail string is a frontend contract — it must stay distinct from
    # the must_change_password 403 ("请先修改密码后再访问") so clients can
    # route to the right page.
    if auth_settings.REGISTRATION_ENABLED and user.email and user.email_verified_at is None:
        logger.warning(
            "Login blocked, email not verified: %s",
            sanitize(f"username={request.username} ip={client_ip}"),
        )
        raise HTTPException(status_code=403, detail="email not verified")

    # Successful login — clear the per-user counter so the user doesn't
    # carry forward a near-limit count from earlier wrong-password tries.
    clear_login_attempts(user.username)

    # Generate tokens
    access_token, raw_refresh = _issue_token_pair(db, user)
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user=UserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            must_change_password=user.must_change_password,
        ),
    )


# ── Self-service registration (2026-10-25 design §3.2) ──
#
# API contract (shared with the web frontend; do not change unilaterally):
#   POST /register            201 {"detail":"verification email sent"}
#                             username taken → 400 "username already taken";
#                             email registered → same 201 (anti-enumeration)
#   POST /verify-registration 200 LoginResponse-shape (auto login)
#                             wrong code → 400 {"detail":"invalid code",
#                             "remaining_attempts":n}; expired/voided → 410
#   POST /resend-verification 202 {"detail":"resent"}; cooldown → 429
#                             {"detail":"cooldown"}; unknown email → 202
#   GET  /check-username      200 {"available":bool,"suggestions":[...]|null}
#   GET  /verify-link         302 → {FRONTEND_BASE}/register/verify?verified=…


@router.post("/register", status_code=201)
def register(body: RegisterRequest, http_request: Request, db: Session = Depends(_get_db)):
    """Create an unverified account and dispatch the verification email.

    The response is identical for new and already-registered emails
    (enumeration protection) — the latter instead gets a "you already
    have an account" notice. SMTP failures never fail the request: the
    frontend offers a resend flow.
    """
    if not auth_settings.REGISTRATION_ENABLED:
        logger.info(
            "registration_blocked: switch disabled %s",
            sanitize(f"ip={_client_ip(http_request)}"),
        )
        raise HTTPException(status_code=404, detail="registration disabled")

    email = registration_service.normalize_email(body.email)
    client_ip = _client_ip(http_request)
    allowed, retry_after = check_register_rate_limit(client_ip, email)
    if not allowed:
        logger.info("registration_blocked: rate limited %s", sanitize(f"ip={client_ip}"))
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )

    if error := registration_service.validate_email_format(body.email):
        raise HTTPException(status_code=422, detail=error)
    if error := registration_service.validate_username(body.username):
        raise HTTPException(status_code=422, detail=error)
    if error := validate_password(body.password):
        raise HTTPException(status_code=422, detail=error)

    if registration_service.username_taken(db, body.username):
        logger.info(
            "registration_blocked: username taken %s",
            sanitize(f"username={body.username} ip={client_ip}"),
        )
        raise HTTPException(status_code=400, detail="username already taken")

    existing = registration_service.get_user_by_email(db, email)
    if existing is not None:
        # Anti-enumeration: same 201, but nudge the real owner to sign in.
        registration_service.send_already_registered_notice(existing.email)
        logger.info(
            "registration_blocked: email already registered %s",
            sanitize(f"user_id={existing.id}"),
        )
        return {"detail": "verification email sent"}

    user, code, magic_link = registration_service.create_registration(
        db, email=email, username=body.username, password=body.password
    )
    db.commit()
    # Arm the 60s cooldown the moment the email goes out — the frontend
    # countdown starts right after this response.
    arm_resend_cooldown(user.email)
    registration_service.send_verification_email(user.email, code, magic_link)
    return {"detail": "verification email sent"}


@router.post("/verify-registration", response_model=LoginResponse)
def verify_registration(
    body: VerifyRegistrationRequest, http_request: Request, db: Session = Depends(_get_db)
):
    """Check the 6-digit code and sign the user in (access + refresh pair)."""
    email = registration_service.normalize_email(body.email)
    allowed, retry_after = check_verify_rate_limit(email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )

    user = registration_service.get_user_by_email(db, email)
    if user is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "invalid code", "remaining_attempts": 0},
        )

    try:
        registration_service.consume_verification_code(db, user, body.code.strip())
    except CodeExpiredError:
        db.rollback()
        return JSONResponse(status_code=410, content={"detail": "code expired"})
    except CodeInvalidError as exc:
        # Commit so the attempts bump survives across requests.
        db.commit()
        return JSONResponse(
            status_code=400,
            content={"detail": "invalid code", "remaining_attempts": exc.remaining_attempts},
        )

    access_token, raw_refresh = _issue_token_pair(db, user)
    db.commit()
    logger.info(
        "registration_verified: %s", sanitize(f"user_id={user.id} username={user.username}")
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user=UserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            must_change_password=user.must_change_password,
        ),
    )


@router.post("/resend-verification", status_code=202)
def resend_verification(
    body: ResendVerificationRequest, http_request: Request, db: Session = Depends(_get_db)
):
    """Re-issue the verification code (voids the previous one)."""
    email = registration_service.normalize_email(body.email)
    allowed, retry_after = check_register_rate_limit(_client_ip(http_request), email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )

    user = registration_service.get_user_by_email(db, email)
    if user is None or user.email_verified_at is not None:
        # Unknown / already-verified email: 202 without sending anything
        # (enumeration protection mirrors /register).
        return {"detail": "resent"}

    allowed, retry_after = arm_resend_cooldown(user.email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="cooldown",
            headers={"Retry-After": str(retry_after)},
        )

    code, magic_link = registration_service.issue_verification_code(db, user)
    db.commit()
    registration_service.send_verification_email(user.email, code, magic_link)
    logger.info("registration_verification_resent: %s", sanitize(f"user_id={user.id}"))
    return {"detail": "resent"}


@router.get("/check-username", response_model=CheckUsernameResponse)
def check_username(username: str, db: Session = Depends(_get_db)):
    """Availability check for the registration form (debounced client-side)."""
    username = (username or "").strip()
    if not registration_service.USERNAME_RE.match(username):
        return CheckUsernameResponse(available=False, suggestions=None)
    if registration_service.username_taken(db, username):
        return CheckUsernameResponse(
            available=False,
            suggestions=registration_service.suggest_usernames(db, username),
        )
    return CheckUsernameResponse(available=True, suggestions=None)


@router.get("/verify-link")
def verify_link(token: str, db: Session = Depends(_get_db)):
    """Magic-link endpoint: verify the email via JWT, then 302 to the app.

    Always redirects (never returns JSON) — the target page reads
    ``verified`` and ``reason`` from the query string. Failure modes are
    indistinguishable to the user except by reason code.
    """
    frontend = get_settings().frontend_base_url.rstrip("/")

    def _redirect(
        verified: str, reason: str | None = None, email: str | None = None
    ) -> RedirectResponse:
        params: dict[str, str] = {"verified": verified}
        if reason:
            params["reason"] = reason
        if email:
            params["email"] = email
        return RedirectResponse(f"{frontend}/register/verify?{urlencode(params)}", status_code=302)

    try:
        payload = jwt.decode(token, auth_settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != registration_service.MAGIC_LINK_PURPOSE:
            raise ValueError("wrong purpose")
        user = db.get(User, int(payload["sub"]))  # type: ignore[arg-type]
        if user is None:
            raise ValueError("unknown user")
    except jwt.ExpiredSignatureError:
        return _redirect("0", reason="expired")
    except (jwt.JWTError, ValueError, TypeError, KeyError):
        return _redirect("0", reason="invalid")

    if user.email_verified_at is None:
        registration_service.mark_email_verified(db, user)
        db.commit()
        logger.info(
            "registration_verified via magic link: %s",
            sanitize(f"user_id={user.id} username={user.username}"),
        )
    return _redirect("1", email=user.email)


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user_allow_password_change)):
    """Return the current authenticated user."""
    return current_user


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    http_request: Request,
    current_user: UserResponse = Depends(get_current_user_allow_password_change),
    db: Session = Depends(_get_db),
):
    """Change the current user's own password and rotate the session.

    Verifies the old password, enforces the shared password policy and
    clears ``must_change_password``. Every existing refresh token is
    revoked, then a fresh access/refresh pair is returned so the current
    session stays signed in while other devices must log in again.
    """
    client_ip = client_ip_from_headers(dict(http_request.headers)) or (
        http_request.client.host if http_request.client else None
    )
    allowed, retry_after = check_login_rate_limit(client_ip, current_user.username)
    if not allowed:
        logger.warning(
            "Password change rate-limited: %s",
            sanitize(f"username={current_user.username} ip={client_ip}"),
        )
        raise HTTPException(
            status_code=429,
            detail="修改密码尝试过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not _verify_password(request.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")

    error = validate_password(request.new_password)
    if error:
        raise HTTPException(status_code=422, detail=error)

    if request.new_password == request.old_password:
        raise HTTPException(status_code=422, detail="新密码不能与旧密码相同")

    user.password_hash = _hash_password(request.new_password)
    user.must_change_password = False

    # Revoke every existing refresh token, including this session's old
    # token. Issue a replacement pair below so the current browser does
    # not get logged out when its short-lived access token expires.
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .update({"revoked": True})
    )
    access_token, raw_refresh = _issue_token_pair(db, user)
    db.commit()
    # A successful change proves control of the old password; do not leave
    # the user carrying earlier near-limit failures into their next login.
    clear_login_attempts(user.username)

    logger.info(
        "User changed own password: %s",
        sanitize(f"user_id={user.id} username={user.username}"),
    )
    return ChangePasswordResponse(
        detail="密码修改成功",
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: RefreshRequest, db: Session = Depends(_get_db)):
    """Exchange a refresh token for a new access token (token rotation)."""
    token_hash = _hash_token(request.refresh_token)

    stored = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
        .first()
    )

    # SQLite drops tzinfo on DateTime(timezone=True); treat naive as UTC
    expires_at = stored.expires_at if stored else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if not stored or expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Revoke old refresh token (rotation)
    stored.revoked = True

    # Issue new refresh token
    raw_refresh = _generate_refresh_token()
    new_hash = _hash_token(raw_refresh)
    db.add(
        RefreshToken(
            user_id=stored.user_id,
            token_hash=new_hash,
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    db.commit()

    # Get user for new access token
    user = db.query(User).filter(User.id == stored.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or deleted")

    jti = _generate_jti()
    access_token = create_access_token(user.username, user.role, jti)

    # Update device last_active.
    # Scope the UPDATE by user_id as well as device_id so a tampered or
    # stolen refresh token cannot update another user's device row (defence
    # in depth — stored.device_id already belongs to this user in normal
    # flow, but the extra predicate prevents cross-user writes if the
    # device_id is ever leaked/reused).
    if stored.device_id:
        (
            db.query(UserDevice)
            .filter(
                UserDevice.id == stored.device_id,
                UserDevice.user_id == user.id,
            )
            .update({"last_active_at": datetime.now(UTC)})
        )
        db.commit()

    return RefreshResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/logout")
def logout(
    current_user: UserResponse = Depends(get_current_user_allow_password_change),
):
    """Logout: blacklist the current access token's jti in Redis.

    The jti is extracted in get_current_user and attached to the request
    via the internal `_current_jti` context variable.
    """
    from app.api.deps import _current_jti

    jti = _current_jti.get()
    if jti:
        # TTL is the remaining token lifetime; we use a safe upper bound
        blacklist_token(jti, ttl=ACCESS_TOKEN_MINUTES * 60)
    return {"detail": "Logged out"}


# ── Device management ──


@router.post("/devices", response_model=DeviceResponse, status_code=201)
def register_device(
    body: RegisterDeviceRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(_get_db),
):
    """Register a device for push notifications and multi-device tracking."""
    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    device = UserDevice(
        user_id=user.id,
        device_name=body.device_name,
        platform=body.platform,
        push_token=body.push_token,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/devices", response_model=list[DeviceResponse])
def list_devices(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(_get_db),
):
    """List all registered devices for the current user."""
    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return (
        db.query(UserDevice)
        .filter(UserDevice.user_id == user.id)
        .order_by(UserDevice.last_active_at.desc())
        .all()
    )


@router.delete("/devices/{device_id}")
def remove_device(
    device_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(_get_db),
):
    """Remove a device registration."""
    user = db.query(User).filter(User.username == current_user.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    device = (
        db.query(UserDevice)
        .filter(UserDevice.id == device_id, UserDevice.user_id == user.id)
        .first()
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    db.delete(device)
    db.commit()
    return {"detail": "Device removed"}
