from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.transaction import Transaction, TransactionStatus
from app.models.receipt import FiscalReceipt
from app.models.fraud import FraudAlert, FraudStatus
from app.models.audit import Audit, AuditStatus
from app.services.transaction_service import TransactionService
from app.services.fraud_service import FraudDetectionEngine
from app.services.audit_service import AuditService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/overview",
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """
    Main supervision dashboard for DGID agents.
    Returns real-time KPIs across all platform activity.
    """
    tx_stats = await TransactionService.get_dashboard_stats(db)
    fraud_stats = await FraudDetectionEngine.get_fraud_stats(db)
    audit_stats = await AuditService.get_audit_statistics(db)

    # Total tax collected this month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0)
    tax_result = await db.execute(
        select(func.sum(FiscalReceipt.tax_amount)).where(
            FiscalReceipt.issued_at >= month_start,
            FiscalReceipt.is_cancelled == False,
        )
    )
    tax_collected = float(tax_result.scalar() or 0)

    # Receipt count
    receipt_count = await db.execute(select(func.count(FiscalReceipt.id)))

    return {
        "transactions": tx_stats,
        "fraud": fraud_stats,
        "audits": audit_stats,
        "fiscal": {
            "total_receipts": receipt_count.scalar() or 0,
            "month_tax_collected_xof": tax_collected,
        },
    }


@router.get(
    "/realtime",
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL, UserRole.ADMIN))],
)
async def get_realtime_stats(db: AsyncSession = Depends(get_db)):
    """Last 24h real-time transaction stream summary."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    by_type = await db.execute(
        select(Transaction.transaction_type, func.count(Transaction.id), func.sum(Transaction.amount))
        .where(Transaction.created_at >= cutoff)
        .group_by(Transaction.transaction_type)
    )
    by_status = await db.execute(
        select(Transaction.status, func.count(Transaction.id))
        .where(Transaction.created_at >= cutoff)
        .group_by(Transaction.status)
    )
    recent_alerts = await db.execute(
        select(FraudAlert).where(FraudAlert.detected_at >= cutoff)
        .order_by(FraudAlert.detected_at.desc())
        .limit(10)
    )

    return {
        "period_hours": 24,
        "by_type": [
            {"type": row[0], "count": row[1], "volume": float(row[2] or 0)}
            for row in by_type.all()
        ],
        "by_status": [
            {"status": row[0], "count": row[1]}
            for row in by_status.all()
        ],
        "recent_fraud_alerts": [
            {
                "id": str(a.id),
                "transaction_id": str(a.transaction_id),
                "fraud_type": a.fraud_type,
                "risk_score": float(a.risk_score),
                "detected_at": str(a.detected_at),
            }
            for a in recent_alerts.scalars().all()
        ],
    }


@router.get(
    "/fiscal-reports",
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def get_fiscal_reports(db: AsyncSession = Depends(get_db)):
    """Generate fiscal summary reports by period."""
    by_period = await db.execute(
        select(
            FiscalReceipt.fiscal_period,
            func.count(FiscalReceipt.id),
            func.sum(FiscalReceipt.tax_amount),
            func.sum(FiscalReceipt.total_amount),
        )
        .where(FiscalReceipt.is_cancelled == False)
        .group_by(FiscalReceipt.fiscal_period)
        .order_by(FiscalReceipt.fiscal_period.desc())
    )
    return {
        "fiscal_reports": [
            {
                "period": row[0],
                "receipt_count": row[1],
                "total_tax_xof": float(row[2] or 0),
                "total_volume_xof": float(row[3] or 0),
            }
            for row in by_period.all()
        ]
    }
