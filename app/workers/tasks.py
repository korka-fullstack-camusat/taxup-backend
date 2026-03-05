"""
Celery background tasks for TAXUP.
Handles fraud analysis, receipt generation, and notifications asynchronously.
"""
import asyncio
import uuid
import logging
from typing import Optional

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper to run async code in a sync Celery task context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _process_transaction(transaction_id: str, operator_id: str):
    """Core async logic: fraud detection + receipt generation + notifications."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.database import AsyncSessionLocal
    from app.models.transaction import Transaction, TransactionStatus
    from app.models.user import User
    from app.models.notification import NotificationType
    from app.services.fraud_service import FraudDetectionEngine
    from app.services.receipt_service import ReceiptService
    from app.services.notification_service import NotificationService
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            # Fetch transaction and operator
            tx_result = await db.execute(
                select(Transaction).where(Transaction.id == uuid.UUID(transaction_id))
            )
            transaction = tx_result.scalar_one_or_none()
            if not transaction:
                logger.error(f"Transaction {transaction_id} not found")
                return

            op_result = await db.execute(
                select(User).where(User.id == uuid.UUID(operator_id))
            )
            operator = op_result.scalar_one_or_none()
            if not operator:
                logger.error(f"Operator {operator_id} not found")
                return

            # 1. Fraud detection
            fraud_alerts = await FraudDetectionEngine.analyze_transaction(db, transaction)

            if fraud_alerts:
                logger.warning(
                    f"Fraud alerts for transaction {transaction_id}: "
                    f"{[a.fraud_type for a in fraud_alerts]}"
                )
                # Notify operator and DGID about fraud
                for alert in fraud_alerts:
                    await NotificationService.notify_fraud_detected(
                        db=db,
                        recipient_id=operator.id,
                        transaction_ref=transaction.reference,
                        fraud_type=alert.fraud_type,
                        risk_score=float(alert.risk_score),
                    )
            else:
                # 2. Auto-generate receipt for clean transactions
                receipt = await ReceiptService.generate_receipt(db, transaction, operator)
                logger.info(f"Receipt {receipt.receipt_number} generated for {transaction_id}")

                await NotificationService.notify_receipt_generated(
                    db=db,
                    recipient_id=operator.id,
                    receipt_number=receipt.receipt_number,
                    transaction_ref=transaction.reference,
                    tax_amount=float(receipt.tax_amount),
                )

            await db.commit()
            logger.info(f"Transaction {transaction_id} processing complete.")
        except Exception as e:
            await db.rollback()
            logger.error(f"Error processing transaction {transaction_id}: {e}", exc_info=True)
            raise


def process_transaction_async(transaction_id: str, operator_id: str):
    """
    Background task: fraud detection + receipt generation.
    Called as FastAPI BackgroundTask (not via Celery broker) for immediate processing.
    Can also be called via Celery for deferred processing.
    """
    _run_async(_process_transaction(transaction_id, operator_id))


@celery_app.task(
    name="app.workers.tasks.process_transaction_celery",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_transaction_celery(self, transaction_id: str, operator_id: str):
    """Celery task version for deferred/retry processing."""
    try:
        _run_async(_process_transaction(transaction_id, operator_id))
    except Exception as exc:
        logger.error(f"Celery task failed for {transaction_id}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(name="app.workers.tasks.send_fraud_notification")
def send_fraud_notification(recipient_id: str, message: str, fraud_type: str):
    """Send fraud notification (email/SMS) - extend with real integration."""
    logger.info(f"[NOTIFICATION] Fraud alert to {recipient_id}: {fraud_type} - {message}")
    # TODO: integrate with SMTP / SMS gateway


@celery_app.task(name="app.workers.tasks.generate_daily_report")
def generate_daily_report():
    """Generate and store daily fiscal report."""
    async def _generate():
        from app.core.database import AsyncSessionLocal
        from app.services.transaction_service import TransactionService
        async with AsyncSessionLocal() as db:
            stats = await TransactionService.get_dashboard_stats(db)
            logger.info(f"Daily Report: {stats}")
            # TODO: persist to a report table or send via email

    _run_async(_generate())


@celery_app.task(name="app.workers.tasks.cleanup_expired_sessions")
def cleanup_expired_sessions():
    """Redis cleanup is automatic via TTL - this is a placeholder."""
    logger.info("Session cleanup tick - Redis TTLs handle expiry automatically.")
