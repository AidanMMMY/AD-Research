"""Notification Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class NotificationConfigBase(BaseModel):
    """Base notification config schema."""

    name: str
    channel_type: str
    config_json: Dict[str, Any]
    is_active: bool = True


class NotificationConfigCreate(NotificationConfigBase):
    """Create notification config schema."""

    pass


class NotificationConfigUpdate(BaseModel):
    """Update notification config schema."""

    name: Optional[str] = None
    channel_type: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class NotificationConfigResponse(NotificationConfigBase):
    """Notification config response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NotificationLogItem(BaseModel):
    """Notification log item."""

    id: int
    config_id: int
    report_id: Optional[int] = None
    status: str
    error_msg: Optional[str] = None
    sent_at: Optional[str] = None
    created_at: Optional[str] = None


class NotificationLogListResponse(BaseModel):
    """Notification log list response."""

    items: List[NotificationLogItem]


class SendTestResponse(BaseModel):
    """Send test response."""

    success: bool
    error: Optional[str] = None
