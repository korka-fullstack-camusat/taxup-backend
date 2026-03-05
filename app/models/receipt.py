import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class FiscalReceipt(Base):
    __tablename__ = "fiscal_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    receipt_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, unique=True
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    tax_base: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # e.g., 0.1800
    tax_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="XOF", nullable=False)
    digital_signature: Mapped[str] = mapped_column(Text, nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(50), default="RSA-SHA256", nullable=False)
    qr_code_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    fiscal_year: Mapped[int] = mapped_column(nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g., "2024-Q1"
    is_certified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    transaction = relationship("Transaction", back_populates="receipt")
    operator = relationship("User", foreign_keys=[operator_id])

    def __repr__(self) -> str:
        return f"<FiscalReceipt {self.receipt_number}>"
