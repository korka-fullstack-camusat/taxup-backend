import uuid
import math
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.audit import AuditStatus, AnomalyType
from app.schemas.audit import AuditCreate, AuditUpdate, AuditResponse
from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.models.notification import NotificationType

router = APIRouter(prefix="/audits", tags=["Audits"])


@router.post(
    "",
    response_model=AuditResponse,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.AUDITEUR_FISCAL, UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def create_audit(
    data: AuditCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new audit case for a suspicious transaction."""
    return await AuditService.create_audit(db, current_user, data)


@router.get("", response_model=PaginatedResponse[AuditResponse])
async def list_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    audit_status: Optional[AuditStatus] = Query(None, alias="status"),
    anomaly_type: Optional[AnomalyType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List audits with optional filtering."""
    items, total = await AuditService.list_audits(
        db, current_user, page, page_size, audit_status, anomaly_type
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get("/statistics", dependencies=[Depends(require_roles(UserRole.AUDITEUR_FISCAL, UserRole.AGENT_DGID, UserRole.ADMIN))])
async def get_audit_statistics(db: AsyncSession = Depends(get_db)):
    """Get audit statistics summary."""
    return await AuditService.get_audit_statistics(db)


@router.get("/{audit_id}", response_model=AuditResponse)
async def get_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific audit case."""
    return await AuditService.get_audit(db, audit_id, current_user)


@router.patch(
    "/{audit_id}",
    response_model=AuditResponse,
    dependencies=[Depends(require_roles(UserRole.AUDITEUR_FISCAL, UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def update_audit(
    audit_id: uuid.UUID,
    update_data: AuditUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update an audit case status, findings or resolution."""
    audit = await AuditService.update_audit(db, audit_id, update_data, current_user)
    # Send notification if audit status changed
    if update_data.status:
        await NotificationService.create_notification(
            db=db,
            recipient_id=audit.auditor_id,
            notification_type=NotificationType.AUDIT_UPDATE,
            title=f"Audit {audit.audit_number} mis à jour",
            message=f"Statut: {audit.status}. {update_data.resolution or ''}",
        )
    return audit
