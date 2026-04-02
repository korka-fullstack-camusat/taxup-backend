import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.receipt import FiscalReceipt
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, UserRole
from app.services.signature_service import SignatureService
from app.core.config import settings
from app.core.redis import redis_client


class ReceiptService:

    @staticmethod
    async def generate_receipt(
        db: AsyncSession, transaction: Transaction, operator: User
    ) -> FiscalReceipt:
        # Check if receipt already exists (pre-check to give a clear error)
        existing = await db.execute(
            select(FiscalReceipt).where(
                FiscalReceipt.transaction_id == transaction.id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Receipt already exists for this transaction",
            )

        # Cherche le taux dynamique dans Redis
        platform_settings_data = await redis_client.get("platform:settings")
        if platform_settings_data and "default_tax_rate" in platform_settings_data:
            tax_rate = float(platform_settings_data["default_tax_rate"])
        else:
            tax_rate = settings.DEFAULT_TAX_RATE
        tax_base = float(transaction.amount)
        tax_amount = round(tax_base * tax_rate, 2)
        total = round(tax_base + tax_amount, 2)

        now = datetime.now(timezone.utc)
        fiscal_year = now.year
        quarter = (now.month - 1) // 3 + 1
        fiscal_period = f"{fiscal_year}-Q{quarter}"

        receipt_number = SignatureService.generate_receipt_number(
            str(operator.id), transaction.reference
        )

        # Data to sign — deterministic payload
        sign_payload = {
            "receipt_number": receipt_number,
            "transaction_reference": transaction.reference,
            "operator_id": str(operator.id),
            "amount": str(transaction.amount),
            "tax_rate": str(tax_rate),
            "tax_amount": str(tax_amount),
            "currency": transaction.currency,
            "transaction_date": str(transaction.transaction_date),
            "issued_at": str(now),
        }
        digital_signature = SignatureService.sign_receipt(sign_payload)
        qr_data = SignatureService.generate_qr_code(sign_payload)

        receipt = FiscalReceipt(
            receipt_number=receipt_number,
            transaction_id=transaction.id,
            operator_id=operator.id,
            tax_base=tax_base,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total_amount=total,
            currency=transaction.currency,
            digital_signature=digital_signature,
            signature_algorithm="RSA-PSS-SHA256",
            qr_code_data=qr_data,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            is_certified=True,
            issued_at=now,
        )
        db.add(receipt)

        # Mark transaction as completed
        transaction.status = TransactionStatus.COMPLETED
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Receipt already exists for this transaction",
            )
        await db.refresh(receipt)
        return receipt

    @staticmethod
    async def get_receipt(
        db: AsyncSession, receipt_id: uuid.UUID, current_user: User
    ) -> FiscalReceipt:
        result = await db.execute(
            select(FiscalReceipt).where(FiscalReceipt.id == receipt_id)
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt not found")

        if current_user.role == UserRole.OPERATEUR_MOBILE:
            if receipt.operator_id != current_user.id:
                raise HTTPException(status_code=403, detail="Access denied")

        return receipt

    @staticmethod
    async def verify_receipt(
        db: AsyncSession, receipt_number: str, signature: str
    ) -> dict:
        result = await db.execute(
            select(FiscalReceipt).where(FiscalReceipt.receipt_number == receipt_number)
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            return {
                "is_valid": False,
                "receipt_number": receipt_number,
                "message": "Receipt not found",
                "receipt": None,
            }

        # Reconstruct the signed payload from stored receipt data
        tx_result = await db.execute(
            select(Transaction).where(Transaction.id == receipt.transaction_id)
        )
        transaction = tx_result.scalar_one_or_none()

        sign_payload = {
            "receipt_number": receipt.receipt_number,
            "transaction_reference": transaction.reference if transaction else "",
            "operator_id": str(receipt.operator_id),
            "amount": str(transaction.amount) if transaction else "0",
            "tax_rate": str(receipt.tax_rate),
            "tax_amount": str(receipt.tax_amount),
            "currency": receipt.currency,
            "transaction_date": str(transaction.transaction_date) if transaction else "",
            "issued_at": str(receipt.issued_at),
        }

        is_valid = SignatureService.verify_signature(sign_payload, signature)

        return {
            "is_valid": is_valid,
            "receipt_number": receipt_number,
            "message": "Valid fiscal receipt" if is_valid else "Invalid signature",
            "receipt": receipt if is_valid else None,
        }

    @staticmethod
    async def cancel_receipt(
        db: AsyncSession,
        receipt_id: uuid.UUID,
        reason: str,
        current_user: User,
    ) -> FiscalReceipt:
        if current_user.role not in (UserRole.AGENT_DGID, UserRole.ADMIN):
            raise HTTPException(status_code=403, detail="Only DGID agents can cancel receipts")

        result = await db.execute(
            select(FiscalReceipt).where(FiscalReceipt.id == receipt_id)
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt not found")
        if receipt.is_cancelled:
            raise HTTPException(status_code=409, detail="Receipt already cancelled")

        receipt.is_cancelled = True
        receipt.cancellation_reason = reason
        receipt.cancelled_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(receipt)
        return receipt
