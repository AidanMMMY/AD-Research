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
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserCreateRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern="^(admin|user)$")
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    """Request to update an existing user."""

    role: str | None = Field(None, pattern="^(admin|user)$")
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    """Request to reset a user's password."""

    new_password: str = Field(..., min_length=6)
