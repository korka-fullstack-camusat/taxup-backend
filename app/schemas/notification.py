import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    recipient_id: uuid.UUID
    notification_type: NotificationType
    title: str
    message: str
    metadata_: Optional[Dict[str, Any]]
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime]

    model_config = {"from_attributes": True}
