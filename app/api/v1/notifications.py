import uuid
import math
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.notification import NotificationResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List notifications for the current user."""
    items, total = await NotificationService.get_user_notifications(
        db, current_user.id, unread_only, page, page_size
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mark a notification as read."""
    from fastapi import HTTPException
    notification = await NotificationService.mark_as_read(db, notification_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Mark all notifications as read for the current user."""
    await NotificationService.mark_all_read(db, current_user.id)
    return MessageResponse(message="All notifications marked as read")
