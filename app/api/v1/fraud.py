import uuid
import math
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.fraud import FraudAlert, FraudStatus, FraudType
from app.schemas.fraud import FraudAlertResponse, FraudAlertUpdate
from app.schemas.common import PaginatedResponse
from app.services.fraud_service import FraudDetectionEngine

router = APIRouter(prefix="/fraud", tags=["Fraud Detection"])


@router.get(
    "/alerts",
    response_model=PaginatedResponse[FraudAlertResponse],
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL, UserRole.ADMIN))],
)
async def list_fraud_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    alert_status: Optional[FraudStatus] = Query(None, alias="status"),
    fraud_type: Optional[FraudType] = None,
    min_risk_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """List all fraud alerts with optional filtering."""
    query = select(FraudAlert)
    if alert_status:
        query = query.where(FraudAlert.status == alert_status)
    if fraud_type:
        query = query.where(FraudAlert.fraud_type == fraud_type)
    if min_risk_score is not None:
        query = query.where(FraudAlert.risk_score >= min_risk_score)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(FraudAlert.detected_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)

    return PaginatedResponse(
        items=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get(
    "/statistics",
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL, UserRole.ADMIN))],
)
async def get_fraud_statistics(db: AsyncSession = Depends(get_db)):
    """Get fraud detection statistics."""
    return await FraudDetectionEngine.get_fraud_stats(db)


@router.get(
    "/alerts/{alert_id}",
    response_model=FraudAlertResponse,
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL, UserRole.ADMIN))],
)
async def get_fraud_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific fraud alert by ID."""
    result = await db.execute(select(FraudAlert).where(FraudAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fraud alert not found")
    return alert


@router.patch(
    "/alerts/{alert_id}",
    response_model=FraudAlertResponse,
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL, UserRole.ADMIN))],
)
async def update_fraud_alert(
    alert_id: uuid.UUID,
    update_data: FraudAlertUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a fraud alert (confirm or mark as false positive)."""
    result = await db.execute(select(FraudAlert).where(FraudAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fraud alert not found")

    alert.status = update_data.status
    if update_data.description:
        alert.description = update_data.description
    if update_data.status in (FraudStatus.RESOLVED, FraudStatus.FALSE_POSITIVE):
        alert.resolved_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(alert)
    return alert
