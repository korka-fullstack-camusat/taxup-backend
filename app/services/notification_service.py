import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.notification import Notification, NotificationType
from app.models.user import User


class NotificationService:

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        recipient_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> Notification:
        notification = Notification(
            recipient_id=recipient_id,
            notification_type=notification_type,
            title=title,
            message=message,
            metadata_=metadata,
        )
        db.add(notification)
        await db.flush()
        await db.refresh(notification)
        return notification

    @staticmethod
    async def notify_fraud_detected(
        db: AsyncSession,
        recipient_id: uuid.UUID,
        transaction_ref: str,
        fraud_type: str,
        risk_score: float,
    ) -> Notification:
        return await NotificationService.create_notification(
            db=db,
            recipient_id=recipient_id,
            notification_type=NotificationType.FRAUD_ALERT,
            title="Alerte Fraude Détectée",
            message=f"Transaction {transaction_ref} a été signalée comme suspecte. Type: {fraud_type}, Score: {risk_score:.0%}",
            metadata={"transaction_ref": transaction_ref, "fraud_type": fraud_type, "risk_score": risk_score},
        )

    @staticmethod
    async def notify_receipt_generated(
        db: AsyncSession,
        recipient_id: uuid.UUID,
        receipt_number: str,
        transaction_ref: str,
        tax_amount: float,
    ) -> Notification:
        return await NotificationService.create_notification(
            db=db,
            recipient_id=recipient_id,
            notification_type=NotificationType.RECEIPT_GENERATED,
            title="Reçu Fiscal Généré",
            message=f"Reçu fiscal {receipt_number} généré pour la transaction {transaction_ref}. Montant TVA: {tax_amount:.2f} XOF",
            metadata={"receipt_number": receipt_number, "transaction_ref": transaction_ref, "tax_amount": tax_amount},
        )

    @staticmethod
    async def get_user_notifications(
        db: AsyncSession,
        user_id: uuid.UUID,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Notification], int]:
        from sqlalchemy import func
        query = select(Notification).where(Notification.recipient_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read == False)

        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        query = query.order_by(Notification.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        return result.scalars().all(), total

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Notification]:
        from datetime import datetime, timezone
        result = await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.recipient_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification and not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await db.flush()
        return notification

    @staticmethod
    async def mark_all_read(db: AsyncSession, user_id: uuid.UUID):
        from datetime import datetime, timezone
        await db.execute(
            update(Notification)
            .where(
                Notification.recipient_id == user_id,
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
