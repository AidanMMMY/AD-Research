"""Authentication API routes."""

from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import auth_settings
from app.core.database import SessionLocal
from app.models.user import User

router = APIRouter()
security = HTTPBearer()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    username: str
    role: str


def _get_db() -> Session:
    """Return a fresh database session for auth lookups."""
    return SessionLocal()


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def create_access_token(username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=auth_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, auth_settings.SECRET_KEY, algorithm="HS256")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserResponse:
    try:
        payload = jwt.decode(credentials.credentials, auth_settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        role = payload.get("role", "user")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return UserResponse(username=username, role=role)
    except JWTError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Authenticate a user and return a JWT.

    First tries to validate against the database users table. If the users
    table is empty (not seeded yet), falls back to the legacy plaintext
    USERS config one time and logs a warning.
    """
    db = _get_db()
    try:
        user = db.query(User).filter(User.username == request.username).first()
        if user:
            if not user.is_active:
                raise HTTPException(status_code=401, detail="User is inactive")
            if _verify_password(request.password, user.password_hash):
                token = create_access_token(user.username, user.role)
                return LoginResponse(
                    token=token,
                    user={"username": user.username, "role": user.role},
                )
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Legacy fallback: if no users table has been seeded yet, allow one
        # last plaintext verification from config and warn.
        expected_password = auth_settings.USERS.get(request.username)
        if expected_password and request.password == expected_password:
            print(
                "[AUTH WARNING] User table is empty. Falling back to plaintext "
                "config. Please run scripts/seed_users.py to migrate accounts."
            )
            role = "admin" if request.username == "admin" else "user"
            token = create_access_token(request.username, role)
            return LoginResponse(token=token, user={"username": request.username, "role": role})

        raise HTTPException(status_code=401, detail="Invalid credentials")
    finally:
        db.close()


@router.get("/me", response_model=UserResponse)
def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
