"""Tests for the create/reset user password management scripts.

The scripts share the API password policy and must preserve the same
first-login and refresh-token revocation semantics as the admin routes.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import pytest

from app.models.refresh_token import RefreshToken
from app.models.user import User
from scripts.create_user import _hash_password
from scripts.create_user import create_user as script_create_user
from scripts.reset_user_password import reset_password as script_reset_password

OLD_PASSWORD = "Old-passw0rd123"
NEW_PASSWORD = "N3w-passw0rd123"  # gitleaks:allow


def _seed_user(db_session, username: str = "script_user") -> User:
    user = User(
        username=username,
        password_hash=_hash_password(OLD_PASSWORD),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_user_script_rejects_weak_password(db_session):
    with pytest.raises(ValueError, match="密码"):
        script_create_user(db_session, "weak_script_user", "short1")

    assert db_session.query(User).filter(User.username == "weak_script_user").first() is None


def test_create_user_script_marks_password_change(db_session):
    user = script_create_user(db_session, "new_script_user", NEW_PASSWORD)
    assert user.must_change_password is True


def test_reset_script_rejects_weak_password_without_touching_hash(db_session):
    user = _seed_user(db_session)
    old_hash = user.password_hash

    with pytest.raises(ValueError, match="密码"):
        script_reset_password(db_session, user.username, "short1")

    db_session.refresh(user)
    assert user.password_hash == old_hash


def test_reset_script_marks_password_change_and_revokes_refresh_tokens(db_session):
    user = _seed_user(db_session)
    db_session.add_all(
        [
            RefreshToken(
                user_id=user.id,
                token_hash="script-active-token",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                revoked=False,
            ),
            RefreshToken(
                user_id=user.id,
                token_hash="script-revoked-token",
                expires_at=datetime.now(UTC) + timedelta(days=1),
                revoked=True,
            ),
        ]
    )
    db_session.commit()

    assert script_reset_password(db_session, user.username, NEW_PASSWORD) is True

    db_session.refresh(user)
    assert user.must_change_password is True
    assert bcrypt.checkpw(NEW_PASSWORD.encode("utf-8"), user.password_hash.encode("utf-8"))
    tokens = db_session.query(RefreshToken).filter(RefreshToken.user_id == user.id).all()
    assert len(tokens) == 2
    assert all(token.revoked for token in tokens)
