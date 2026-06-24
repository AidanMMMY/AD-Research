"""Authentication API routes."""

from collections.abc import Generator
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import auth_settings
from app.core.database import SessionLocal
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


def _get_db() -> Generator[Session, None, None]:
    """Yield a fresh database session for auth lookups."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=auth_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, auth_settings.SECRET_KEY, algorithm="HS256")


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(_get_db)):
    """Authenticate a user and return a JWT."""
    user = db.query(User).filter(User.username == request.username).first()

    if not user or not _verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    token = create_access_token(user.username, user.role)
    return LoginResponse(
        token=token,
        user={"username": user.username, "role": user.role},
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
