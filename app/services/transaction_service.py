import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from fastapi import HTTPException, status

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User, UserRole
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.core.config import settings


class TransactionService:

    @staticmethod
    def _generate_reference(operator_id: str) -> str:
        rand = secrets.token_hex(4).upper()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"TXN-{ts}-{rand}"

    @staticmethod
    async def create_transaction(
        db: AsyncSession, operator: User, data: TransactionCreate
    ) -> Transaction:
        if operator.role != UserRole.OPERATEUR_MOBILE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only mobile money operators can submit transactions",
            )

        reference = TransactionService._generate_reference(str(operator.id))
        transaction = Transaction(
            reference=reference,
            operator_id=operator.id,
            amount=data.amount,
            currency=data.currency,
            transaction_type=data.transaction_type,
            sender_phone=data.sender_phone,
            receiver_phone=data.receiver_phone,
            sender_name=data.sender_name,
            receiver_name=data.receiver_name,
            external_reference=data.external_reference,
            metadata_=data.metadata_,
            transaction_date=data.transaction_date,
            status=TransactionStatus.PENDING,
        )
        db.add(transaction)
        await db.flush()
        await db.refresh(transaction)
        return transaction

    @staticmethod
    async def get_transaction(
        db: AsyncSession, transaction_id: uuid.UUID, current_user: User
    ) -> Transaction:
        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Access control
        if current_user.role == UserRole.OPERATEUR_MOBILE:
            if transaction.operator_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role == UserRole.CITOYEN:
            if (transaction.sender_phone != current_user.phone_number and
                    transaction.receiver_phone != current_user.phone_number):
                raise HTTPException(status_code=403, detail="Access denied")

        return transaction

    @staticmethod
    async def list_transactions(
        db: AsyncSession,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
        status: Optional[TransactionStatus] = None,
        transaction_type: Optional[TransactionType] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[List[Transaction], int]:
        query = select(Transaction)

        if current_user.role == UserRole.OPERATEUR_MOBILE:
            query = query.where(Transaction.operator_id == current_user.id)
        elif current_user.role == UserRole.CITOYEN:
            query = query.where(
                or_(
                    Transaction.sender_phone == current_user.phone_number,
                    Transaction.receiver_phone == current_user.phone_number,
                )
            )

        if status:
            query = query.where(Transaction.status == status)
        if transaction_type:
            query = query.where(Transaction.transaction_type == transaction_type)
        if date_from:
            query = query.where(Transaction.transaction_date >= date_from)
        if date_to:
            query = query.where(Transaction.transaction_date <= date_to)

        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        query = query.order_by(Transaction.transaction_date.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def update_transaction_status(
        db: AsyncSession,
        transaction_id: uuid.UUID,
        update_data: TransactionUpdate,
        current_user: User,
    ) -> Transaction:
        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if current_user.role not in (UserRole.AGENT_DGID, UserRole.AUDITEUR_FISCAL):
            if transaction.operator_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied")

        for field, value in update_data.model_dump(exclude_none=True).items():
            setattr(transaction, field, value)

        await db.flush()
        await db.refresh(transaction)
        return transaction

    @staticmethod
    async def get_dashboard_stats(db: AsyncSession) -> dict:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today.replace(day=1)

        total = await db.execute(select(func.count(Transaction.id)))
        today_count = await db.execute(
            select(func.count(Transaction.id)).where(Transaction.created_at >= today)
        )
        month_volume = await db.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.transaction_date >= month_start,
                Transaction.status == TransactionStatus.COMPLETED,
            )
        )
        pending = await db.execute(
            select(func.count(Transaction.id)).where(
                Transaction.status == TransactionStatus.PENDING
            )
        )
        return {
            "total_transactions": total.scalar() or 0,
            "today_transactions": today_count.scalar() or 0,
            "month_volume": float(month_volume.scalar() or 0),
            "pending_transactions": pending.scalar() or 0,
        }
