import uuid
import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, rate_limit
from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.transaction import TransactionStatus, TransactionType
from app.schemas.transaction import (
    TransactionCreate, TransactionResponse, TransactionUpdate
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services.transaction_service import TransactionService
from app.services.receipt_service import ReceiptService
from app.services.fraud_service import FraudDetectionEngine
from app.services.notification_service import NotificationService
from app.models.notification import NotificationType
from app.workers.tasks import process_transaction_async

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    data: TransactionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    _: None = Depends(rate_limit),
):
    """
    Submit a new mobile money transaction.
    Triggers async fraud analysis and receipt generation.
    """
    transaction = await TransactionService.create_transaction(db, current_user, data)
    # Queue async processing: fraud check + receipt generation
    background_tasks.add_task(
        process_transaction_async,
        str(transaction.id),
        str(current_user.id),
    )
    return transaction


@router.get("", response_model=PaginatedResponse[TransactionResponse])
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TransactionStatus] = None,
    transaction_type: Optional[TransactionType] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List transactions with filtering and pagination."""
    items, total = await TransactionService.list_transactions(
        db, current_user, page, page_size, status, transaction_type, date_from, date_to
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a transaction by ID."""
    return await TransactionService.get_transaction(db, transaction_id, current_user)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    update_data: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update transaction status or metadata."""
    return await TransactionService.update_transaction_status(
        db, transaction_id, update_data, current_user
    )
