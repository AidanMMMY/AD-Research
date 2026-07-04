"""Notification API routes."""


from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_notification_service
from app.schemas.notification import (
    NotificationConfigCreate,
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationLogListResponse,
    SendTestResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/configs", response_model=list[NotificationConfigResponse])
def list_configs(
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """List all notification configurations."""
    return service.get_configs(user_id=current_user.id)


@router.post("/configs", response_model=NotificationConfigResponse, status_code=201)
def create_config(
    data: NotificationConfigCreate,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Create a new notification configuration."""
    return service.create_config(
        name=data.name,
        channel_type=data.channel_type,
        config_json=data.config_json,
        user_id=current_user.id,
    )


@router.put("/configs/{config_id}", response_model=NotificationConfigResponse)
def update_config(
    config_id: int,
    data: NotificationConfigUpdate,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Update a notification configuration."""
    update_data = data.model_dump(exclude_unset=True)
    result = service.update_config(config_id, user_id=current_user.id, **update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Config not found")
    return result


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Delete a notification configuration."""
    if not service.delete_config(config_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Config not found")
    return None


@router.post("/configs/{config_id}/test", response_model=SendTestResponse)
def test_config(
    config_id: int,
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Test a notification configuration."""
    result = service.send_notification(config_id, test=True, user_id=current_user.id)
    return SendTestResponse(**result)


@router.get("/logs", response_model=NotificationLogListResponse)
def get_logs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    service: NotificationService = Depends(get_notification_service),
    current_user = Depends(get_current_user),
):
    """Get notification send logs (paginated).

    Each item contains: id, user_id (config name), channel, target,
    report_id, status, error, sent_at, created_at.
    """
    return service.get_logs(page=page, page_size=page_size, user_id=current_user.id)
