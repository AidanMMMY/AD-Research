"""Authentication-related Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    # True ⇒ the frontend forces a redirect to /change-password until the
    # user sets a new password. Defaults False for backward compatibility
    # with older rows/clients.
    must_change_password: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="Short-lived JWT (15 min)")
    refresh_token: str = Field(..., description="Long-lived token for renewal (30 days)")
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Self-service registration (2026-10-25 design §3.2) ──
# Field formats (email regex / username ^[a-zA-Z0-9_]{3,30}$ / password
# policy) are enforced in the endpoints via app.services.password_policy
# and app.services.registration_service so all paths share one rule.


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class VerifyRegistrationRequest(BaseModel):
    email: str
    code: str


class ResendVerificationRequest(BaseModel):
    email: str


class CheckUsernameResponse(BaseModel):
    available: bool
    suggestions: list[str] | None = None


class ChangePasswordRequest(BaseModel):
    """Self-service password change for the logged-in user."""

    old_password: str = Field(..., min_length=1)
    # Policy (>=12 chars, letter + digit) is enforced in the endpoint via
    # app.services.password_policy so all password paths share one rule.
    new_password: str


class ChangePasswordResponse(BaseModel):
    """New session tokens keep the current session alive after rotation."""

    detail: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str = Field(..., description="Rotated refresh token; the old one is revoked")
    token_type: str = "bearer"


class RegisterDeviceRequest(BaseModel):
    device_name: str = Field(..., description="e.g. 'iPhone 16 Pro'")
    platform: str = Field(default="ios", description="ios / android / web")
    push_token: str | None = Field(default=None, description="APNs or FCM device token")


class DeviceResponse(BaseModel):
    id: int
    device_name: str
    platform: str
    last_active_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
