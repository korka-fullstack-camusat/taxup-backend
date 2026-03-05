import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Numeric, Enum, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class FraudType(str, enum.Enum):
    VELOCITY = "VELOCITY"           # Too many transactions in short time
    LARGE_AMOUNT = "LARGE_AMOUNT"   # Unusually large amount
    ROUND_TRIPPING = "ROUND_TRIPPING"  # Money goes back to sender
    STRUCTURING = "STRUCTURING"     # Breaking large amounts into smaller ones
    UNUSUAL_PATTERN = "UNUSUAL_PATTERN"
    BLACKLISTED = "BLACKLISTED"


class FraudStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    RESOLVED = "RESOLVED"


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )
    fraud_type: Mapped[FraudType] = mapped_column(Enum(FraudType), nullable=False)
    status: Mapped[FraudStatus] = mapped_column(
        Enum(FraudStatus), default=FraudStatus.DETECTED, nullable=False
    )
    risk_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # 0.0 - 1.0
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    transaction = relationship("Transaction", back_populates="fraud_alerts")

    def __repr__(self) -> str:
        return f"<FraudAlert {self.fraud_type} score={self.risk_score}>"
