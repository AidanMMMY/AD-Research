"""Authentication-related Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    username: str
    role: str


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


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterDeviceRequest(BaseModel):
    device_name: str = Field(..., description="e.g. 'iPhone 16 Pro'")
    platform: str = Field(default="ios", description="ios / android / web")
    push_token: Optional[str] = Field(default=None, description="APNs or FCM device token")


class DeviceResponse(BaseModel):
    id: int
    device_name: str
    platform: str
    last_active_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
