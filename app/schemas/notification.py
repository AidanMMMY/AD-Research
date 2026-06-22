"""Notification Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationConfigBase(BaseModel):
    """Base notification config schema."""

    name: str
    channel_type: str
    config_json: dict[str, Any]
    is_active: bool = True


class NotificationConfigCreate(NotificationConfigBase):
    """Create notification config schema."""

    pass


class NotificationConfigUpdate(BaseModel):
    """Update notification config schema."""

    name: str | None = None
    channel_type: str | None = None
    config_json: dict[str, Any] | None = None
    is_active: bool | None = None


class NotificationConfigResponse(NotificationConfigBase):
    """Notification config response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NotificationLogItem(BaseModel):
    """Notification log item."""

    id: int
    config_id: int
    report_id: int | None = None
    status: str
    error_msg: str | None = None
    sent_at: str | None = None
    created_at: str | None = None


class NotificationLogListResponse(BaseModel):
    """Notification log list response."""

    items: list[NotificationLogItem]


class SendTestResponse(BaseModel):
    """Send test response."""

    success: bool
    error: str | None = None
