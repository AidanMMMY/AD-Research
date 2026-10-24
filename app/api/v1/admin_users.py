"""Admin user management API routes."""

import logging

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import assert_would_keep_at_least_one_admin, get_db, require_admin
from app.core.audit import client_ip_from_headers, record_audit
from app.core.log_sanitize import sanitize
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.user import (
    PasswordResetRequest,
    UserAdminResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserUpdateRequest,
)
from app.services.password_policy import generate_random_password, validate_password

logger = logging.getLogger(__name__)

router = APIRouter()


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _resolve_initial_password(raw: str | None) -> str:
    """Validate an explicit password or generate a random one.

    Returns the plaintext to be hashed and echoed once in the response.
    Raises 422 with a Chinese detail when the explicit password violates
    the shared policy (see app.services.password_policy).
    """
    if raw is None or raw == "":
        return generate_random_password()
    error = validate_password(raw)
    if error:
        raise HTTPException(status_code=422, detail=error)
    return raw


def _revoke_all_refresh_tokens(db: Session, user_id: int) -> None:
    """Revoke every active refresh token of a user (password changed)."""
    (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .update({"revoked": True})
    )


@router.get("", response_model=list[UserAdminResponse])
def list_users(
    db: Session = Depends(get_db),
    _: UserResponse = Depends(require_admin),
):
    """List all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.post("", response_model=UserCreateResponse, status_code=201)
def create_user(
    data: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: UserResponse = Depends(require_admin),
):
    """Create a new user (admin only).

    Password is optional: when omitted a random one is generated. Either
    way the user is flagged ``must_change_password=True`` so the first
    login forces a password change. The plaintext initial password is
    returned once in ``initial_password`` and never stored or logged.
    """
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    initial_password = _resolve_initial_password(data.password)

    user = User(
        username=data.username,
        password_hash=_hash_password(initial_password),
        role=data.role,
        is_active=data.is_active,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(
        "Admin %s created user: %s",
        sanitize(actor.username),
        sanitize(
            f"username={user.username} role={user.role} "
            f"password_generated={data.password in (None, '')}"
        ),
    )

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
    return UserCreateResponse.model_validate(user).model_copy(
        update={"initial_password": initial_password}
    )


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
    """Reset a user's password (admin only).

    ``new_password`` optional — omitted means a random password is
    generated. The target user is flagged ``must_change_password=True``
    and all of their refresh tokens are revoked. The plaintext is
    returned once in ``initial_password``.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    initial_password = _resolve_initial_password(data.new_password)

    user.password_hash = _hash_password(initial_password)
    user.must_change_password = True
    _revoke_all_refresh_tokens(db, user.id)
    db.commit()

    logger.info(
        "Admin %s reset password for user_id=%s (%s)",
        sanitize(actor.username),
        user_id,
        sanitize(user.username),
    )

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
    return {"message": "Password reset successfully", "initial_password": initial_password}


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

    logger.warning(
        "Admin %s deleted user: %s",
        sanitize(actor.username),
        sanitize(f"user_id={user_id} username={deleted_username}"),
    )

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
