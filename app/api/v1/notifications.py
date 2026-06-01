"""Notification API routes."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_notification_service
from app.schemas.notification import (
    NotificationConfigCreate,
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationLogListResponse,
    SendTestResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("/configs", response_model=List[NotificationConfigResponse])
def list_configs(
    service: NotificationService = Depends(get_notification_service),
):
    """List all notification configurations."""
    return service.get_configs()


@router.post("/configs", response_model=NotificationConfigResponse, status_code=201)
def create_config(
    data: NotificationConfigCreate,
    service: NotificationService = Depends(get_notification_service),
):
    """Create a new notification configuration."""
    return service.create_config(
        name=data.name,
        channel_type=data.channel_type,
        config_json=data.config_json,
    )


@router.put("/configs/{config_id}", response_model=NotificationConfigResponse)
def update_config(
    config_id: int,
    data: NotificationConfigUpdate,
    service: NotificationService = Depends(get_notification_service),
):
    """Update a notification configuration."""
    update_data = data.model_dump(exclude_unset=True)
    result = service.update_config(config_id, **update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Config not found")
    return result


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
):
    """Delete a notification configuration."""
    if not service.delete_config(config_id):
        raise HTTPException(status_code=404, detail="Config not found")
    return None


@router.post("/configs/{config_id}/test", response_model=SendTestResponse)
def test_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
):
    """Test a notification configuration."""
    result = service.send_notification(config_id, test=True)
    return SendTestResponse(**result)


@router.get("/logs", response_model=NotificationLogListResponse)
def get_logs(
    limit: int = 50,
    service: NotificationService = Depends(get_notification_service),
):
    """Get notification send logs."""
    items = service.get_logs(limit=limit)
    return NotificationLogListResponse(items=items)
