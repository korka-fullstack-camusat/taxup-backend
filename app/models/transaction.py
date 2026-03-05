import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Numeric, Enum, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class TransactionType(str, enum.Enum):
    TRANSFERT = "TRANSFERT"
    PAIEMENT = "PAIEMENT"
    RETRAIT = "RETRAIT"
    DEPOT = "DEPOT"
    REMBOURSEMENT = "REMBOURSEMENT"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNDER_REVIEW = "UNDER_REVIEW"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="XOF", nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType), nullable=False
    )
    sender_phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    receiver_phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receiver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False
    )
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    operator = relationship("User", back_populates="transactions", foreign_keys=[operator_id])
    receipt = relationship("FiscalReceipt", back_populates="transaction", uselist=False)
    audits = relationship("Audit", back_populates="transaction")
    fraud_alerts = relationship("FraudAlert", back_populates="transaction")

    __table_args__ = (
        Index("ix_transactions_operator_date", "operator_id", "transaction_date"),
        Index("ix_transactions_status_date", "status", "transaction_date"),
    )

    def __repr__(self) -> str:
        return f"<Transaction {self.reference} {self.amount} {self.currency}>"
