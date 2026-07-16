"""Admin user management API routes."""

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import assert_would_keep_at_least_one_admin, get_db, require_admin
from app.core.audit import client_ip_from_headers, record_audit
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
    request: Request,
    db: Session = Depends(get_db),
    actor: UserResponse = Depends(require_admin),
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

    record_audit(
        db,
        action="POST /admin/users",
        actor_user_id=actor.id,
        actor_username=actor.username,
        target_type="user",
        target_id=user.id,
        payload={"username": user.username, "role": user.role, "is_active": user.is_active},
        ip=client_ip_from_headers(dict(request.headers)),
        status_code=201,
        detail=f"Created user '{user.username}'",
    )
    return user


@router.put("/{user_id}", response_model=UserAdminResponse)
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: UserResponse = Depends(require_admin),
):
    """Update user role and active status (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)

    # P0-2: last-admin protection — block writes that would leave zero
    # active admins in the system.
    assert_would_keep_at_least_one_admin(
        db,
        target_user_id=user.id,
        new_role=update_data.get("role"),
        new_is_active=update_data.get("is_active"),
    )

    for key, value in update_data.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)

    db.commit()
    db.refresh(user)

    record_audit(
        db,
        action="PUT /admin/users/{user_id}",
        actor_user_id=actor.id,
        actor_username=actor.username,
        target_type="user",
        target_id=user.id,
        payload=update_data,
        ip=client_ip_from_headers(dict(request.headers)),
        status_code=200,
        detail=f"Updated user '{user.username}'",
    )
    return user


@router.post("/{user_id}/reset-password", response_model=dict)
def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: UserResponse = Depends(require_admin),
):
    """Reset a user's password (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = _hash_password(data.new_password)
    db.commit()

    record_audit(
        db,
        action="POST /admin/users/{user_id}/reset-password",
        actor_user_id=actor.id,
        actor_username=actor.username,
        target_type="user",
        target_id=user.id,
        payload={"new_password": "***"},  # never log the actual password
        ip=client_ip_from_headers(dict(request.headers)),
        status_code=200,
        detail=f"Reset password for user '{user.username}'",
    )
    return {"message": "Password reset successfully"}


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: UserResponse = Depends(require_admin),
):
    """Delete a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # P0-2: last-admin protection — refuse to delete the final admin.
    assert_would_keep_at_least_one_admin(
        db,
        target_user_id=user.id,
        new_role=None,
        new_is_active=False,  # delete ⇒ not active anymore
    )

    deleted_username = user.username
    db.delete(user)
    db.commit()

    record_audit(
        db,
        action="DELETE /admin/users/{user_id}",
        actor_user_id=actor.id,
        actor_username=actor.username,
        target_type="user",
        target_id=user_id,
        payload={"username": deleted_username},
        ip=client_ip_from_headers(dict(request.headers)),
        status_code=204,
        detail=f"Deleted user '{deleted_username}'",
    )
    return None
