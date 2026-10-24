"""User management Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserAdminResponse(BaseModel):
    """Full user response for admin management."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserCreateResponse(UserAdminResponse):
    """Create/reset response carrying the one-time plaintext password.

    ``initial_password`` is only present in the create/reset response —
    it is never persisted or logged.
    """

    initial_password: str | None = None


class UserCreateRequest(BaseModel):
    """Request to create a new user.

    ``password`` is optional: when omitted the server generates a random
    16-character password and returns it once in the response. Either way
    the new user is flagged ``must_change_password=True``.
    """

    username: str = Field(..., min_length=1, max_length=50)
    password: str | None = Field(default=None)
    role: str = Field(default="user", pattern="^(admin|user)$")
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    """Request to update an existing user."""

    role: str | None = Field(None, pattern="^(admin|user)$")
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    """Request to reset a user's password.

    ``new_password`` optional — omitted means "generate a random one".
    """

    new_password: str | None = Field(default=None)
