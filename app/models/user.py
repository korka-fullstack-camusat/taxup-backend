import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class UserRole(str, enum.Enum):
    OPERATEUR_MOBILE = "OPERATEUR_MOBILE"
    AUDITEUR_FISCAL = "AUDITEUR_FISCAL"
    CITOYEN = "CITOYEN"
    AGENT_DGID = "AGENT_DGID"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.CITOYEN)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    transactions = relationship("Transaction", back_populates="operator", foreign_keys="Transaction.operator_id")
    audits = relationship("Audit", back_populates="auditor", foreign_keys="Audit.auditor_id")
    notifications = relationship("Notification", back_populates="recipient")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"
