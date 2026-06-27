"""Authentication API routes — login, refresh, logout, device management.

Token model:
  - access_token:  short-lived JWT (15 min), includes jti for revocation
  - refresh_token: long-lived opaque token (30 days), stored in DB as SHA-256 hash

Blacklist:
  - On logout, the access token's jti is written to Redis with TTL = remaining lifetime
  - get_current_user checks the blacklist on every authenticated request
"""

import hashlib
import secrets
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import auth_settings
from app.core.database import SessionLocal
from app.core.redis_client import blacklist_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.auth import (
    DeviceResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterDeviceRequest,
    UserResponse,
)

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


# ── Token creation / verification ──

def create_access_token(username: str, role: str, jti: str) -> str:
    """Create a short-lived JWT with a unique jti for revocation."""
    now = datetime.now(timezone.utc)
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
    return max(1, int(exp - datetime.now(timezone.utc).timestamp()))


# ── Endpoints ──

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(_get_db)):
    """Authenticate a user, return access + refresh tokens."""
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not _verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    # Generate tokens
    jti = _generate_jti()
    access_token = create_access_token(user.username, user.role, jti)

    raw_refresh = _generate_refresh_token()
    refresh_hash = _hash_token(raw_refresh)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    db.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user=UserResponse(username=user.username, role=user.role),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    """Return the current authenticated user."""
    return current_user


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

    if not stored or stored.expires_at < datetime.now(timezone.utc):
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
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    db.commit()

    # Get user for new access token
    user = db.query(User).filter(User.id == stored.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or deleted")

    jti = _generate_jti()
    access_token = create_access_token(user.username, user.role, jti)

    # Update device last_active
    if stored.device_id:
        (
            db.query(UserDevice)
            .filter(UserDevice.id == stored.device_id)
            .update({"last_active_at": datetime.now(timezone.utc)})
        )
        db.commit()

    return RefreshResponse(access_token=access_token)


@router.post("/logout")
def logout(
    current_user: UserResponse = Depends(get_current_user),
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
