import uuid
import secrets
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.audit import Audit, AuditStatus, AnomalyType
from app.models.user import User, UserRole
from app.schemas.audit import AuditCreate, AuditUpdate


class AuditService:

    @staticmethod
    def _generate_audit_number() -> str:
        rand = secrets.token_hex(3).upper()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"AUD-{ts}-{rand}"

    @staticmethod
    async def create_audit(
        db: AsyncSession, auditor: User, data: AuditCreate
    ) -> Audit:
        if auditor.role not in (UserRole.AUDITEUR_FISCAL, UserRole.AGENT_DGID, UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only auditors and DGID agents can create audits",
            )

        audit = Audit(
            audit_number=AuditService._generate_audit_number(),
            auditor_id=auditor.id,
            transaction_id=data.transaction_id,
            anomaly_type=data.anomaly_type,
            title=data.title,
            description=data.description,
            status=AuditStatus.OUVERT,
        )
        db.add(audit)
        await db.flush()
        await db.refresh(audit)
        return audit

    @staticmethod
    async def get_audit(db: AsyncSession, audit_id: uuid.UUID, current_user: User) -> Audit:
        result = await db.execute(select(Audit).where(Audit.id == audit_id))
        audit = result.scalar_one_or_none()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        return audit

    @staticmethod
    async def list_audits(
        db: AsyncSession,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        audit_status: Optional[AuditStatus] = None,
        anomaly_type: Optional[AnomalyType] = None,
    ) -> tuple[List[Audit], int]:
        query = select(Audit)

        if current_user.role == UserRole.AUDITEUR_FISCAL:
            query = query.where(Audit.auditor_id == current_user.id)

        if audit_status:
            query = query.where(Audit.status == audit_status)
        if anomaly_type:
            query = query.where(Audit.anomaly_type == anomaly_type)

        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        query = query.order_by(Audit.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def update_audit(
        db: AsyncSession,
        audit_id: uuid.UUID,
        update_data: AuditUpdate,
        current_user: User,
    ) -> Audit:
        result = await db.execute(select(Audit).where(Audit.id == audit_id))
        audit = result.scalar_one_or_none()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")

        if current_user.role == UserRole.AUDITEUR_FISCAL and audit.auditor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        for field, value in update_data.model_dump(exclude_none=True).items():
            setattr(audit, field, value)

        if update_data.status in (AuditStatus.RESOLU, AuditStatus.CLOS):
            audit.resolved_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(audit)
        return audit

    @staticmethod
    async def get_audit_statistics(db: AsyncSession) -> dict:
        total = await db.execute(select(func.count(Audit.id)))
        open_audits = await db.execute(
            select(func.count(Audit.id)).where(Audit.status == AuditStatus.OUVERT)
        )
        by_type = await db.execute(
            select(Audit.anomaly_type, func.count(Audit.id)).group_by(Audit.anomaly_type)
        )
        return {
            "total": total.scalar() or 0,
            "open": open_audits.scalar() or 0,
            "by_type": {row[0]: row[1] for row in by_type.all()},
        }
