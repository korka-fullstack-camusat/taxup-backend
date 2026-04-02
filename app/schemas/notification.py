import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    recipient_id: uuid.UUID
    notification_type: NotificationType
    title: str
    message: str
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime]

    model_config = {"from_attributes": True, "populate_by_name": True}
