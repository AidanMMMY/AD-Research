"""Admin user management API routes."""

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.user import (
    PasswordResetRequest,
    UserAdminResponse,
    UserCreateRequest,
    UserUpdateRequest,
)

router = APIRouter()


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@router.get("", response_model=list[UserAdminResponse])
def list_users(
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """List all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.post("", response_model=UserAdminResponse, status_code=201)
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """Create a new user (admin only)."""
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=data.username,
        password_hash=_hash_password(data.password),
        role=data.role,
        is_active=data.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserAdminResponse)
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """Update user role and active status (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", response_model=dict)
def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """Reset a user's password (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = _hash_password(data.new_password)
    db.commit()
    return {"message": "Password reset successfully"}


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """Delete a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return None
