import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Enum, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AnomalyType(str, enum.Enum):
    MONTANT_SUSPECT = "MONTANT_SUSPECT"
    FREQUENCE_ANORMALE = "FREQUENCE_ANORMALE"
    IDENTITE_DOUTEUSE = "IDENTITE_DOUTEUSE"
    DOUBLE_TRANSACTION = "DOUBLE_TRANSACTION"
    EVASION_FISCALE = "EVASION_FISCALE"
    BLANCHIMENT = "BLANCHIMENT"
    AUTRE = "AUTRE"


class AuditStatus(str, enum.Enum):
    OUVERT = "OUVERT"
    EN_COURS = "EN_COURS"
    RESOLU = "RESOLU"
    ESCALADE = "ESCALADE"
    CLOS = "CLOS"


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    audit_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    auditor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    anomaly_type: Mapped[AnomalyType] = mapped_column(Enum(AnomalyType), nullable=False)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus), default=AuditStatus.OUVERT, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    auditor = relationship("User", back_populates="audits", foreign_keys=[auditor_id])
    transaction = relationship("Transaction", back_populates="audits")

    def __repr__(self) -> str:
        return f"<Audit {self.audit_number} {self.status}>"
