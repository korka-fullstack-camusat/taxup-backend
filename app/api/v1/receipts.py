import uuid
import math
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.receipt import FiscalReceipt
from app.models.transaction import Transaction
from app.schemas.receipt import FiscalReceiptResponse, ReceiptVerifyRequest, ReceiptVerifyResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/receipts", tags=["Fiscal Receipts"])


@router.post(
    "/generate/{transaction_id}",
    response_model=FiscalReceiptResponse,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.OPERATEUR_MOBILE, UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def generate_receipt(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a certified digital fiscal receipt for a transaction."""
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return await ReceiptService.generate_receipt(db, transaction, current_user)


@router.get("", response_model=PaginatedResponse[FiscalReceiptResponse])
async def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    fiscal_year: Optional[int] = None,
    fiscal_period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List fiscal receipts with optional filtering."""
    query = select(FiscalReceipt)

    if current_user.role == UserRole.OPERATEUR_MOBILE:
        query = query.where(FiscalReceipt.operator_id == current_user.id)

    if fiscal_year:
        query = query.where(FiscalReceipt.fiscal_year == fiscal_year)
    if fiscal_period:
        query = query.where(FiscalReceipt.fiscal_period == fiscal_period)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    query = query.order_by(FiscalReceipt.issued_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get("/{receipt_id}", response_model=FiscalReceiptResponse)
async def get_receipt(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a fiscal receipt by ID."""
    return await ReceiptService.get_receipt(db, receipt_id, current_user)


@router.post("/verify", response_model=ReceiptVerifyResponse)
async def verify_receipt(
    request: ReceiptVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Publicly verify the authenticity of a fiscal receipt by its number and digital signature.
    No authentication required.
    """
    return await ReceiptService.verify_receipt(db, request.receipt_number, request.digital_signature)


@router.delete(
    "/{receipt_id}",
    response_model=FiscalReceiptResponse,
    dependencies=[Depends(require_roles(UserRole.AGENT_DGID, UserRole.ADMIN))],
)
async def cancel_receipt(
    receipt_id: uuid.UUID,
    reason: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel a fiscal receipt (DGID agents only)."""
    return await ReceiptService.cancel_receipt(db, receipt_id, reason, current_user)
