import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class NotificationType(str, enum.Enum):
    FRAUD_ALERT = "FRAUD_ALERT"
    AUDIT_UPDATE = "AUDIT_UPDATE"
    RECEIPT_GENERATED = "RECEIPT_GENERATED"
    SYSTEM = "SYSTEM"
    TAX_COMPLIANCE = "TAX_COMPLIANCE"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    recipient = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification {self.notification_type} to {self.recipient_id}>"
