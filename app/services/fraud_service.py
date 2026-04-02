"""
Fraud detection engine using heuristic rules and statistical analysis.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.transaction import Transaction, TransactionStatus
from app.models.fraud import FraudAlert, FraudType, FraudStatus
from app.core.config import settings


class FraudDetectionEngine:
    # Thresholds
    VELOCITY_WINDOW_MINUTES = 60
    VELOCITY_MAX_COUNT = 10
    LARGE_AMOUNT_THRESHOLD = 1_000_000  # XOF
    ROUND_TRIP_WINDOW_HOURS = 24
    STRUCTURING_WINDOW_HOURS = 24
    STRUCTURING_THRESHOLD = 500_000

    @staticmethod
    async def analyze_transaction(
        db: AsyncSession, transaction: Transaction
    ) -> List[FraudAlert]:
        alerts = []
        checks = [
            FraudDetectionEngine._check_velocity,
            FraudDetectionEngine._check_large_amount,
            FraudDetectionEngine._check_round_tripping,
            FraudDetectionEngine._check_structuring,
        ]
        for check in checks:
            alert = await check(db, transaction)
            if alert:
                db.add(alert)
                alerts.append(alert)

        if alerts:
            transaction.status = TransactionStatus.UNDER_REVIEW

        await db.flush()
        return alerts

    @staticmethod
    async def _check_velocity(
        db: AsyncSession, transaction: Transaction
    ) -> FraudAlert | None:
        window_start = datetime.now(timezone.utc) - timedelta(
            minutes=FraudDetectionEngine.VELOCITY_WINDOW_MINUTES
        )
        result = await db.execute(
            select(func.count(Transaction.id)).where(
                and_(
                    Transaction.sender_phone == transaction.sender_phone,
                    Transaction.created_at >= window_start,
                    Transaction.id != transaction.id,
                )
            )
        )
        count = result.scalar() or 0
        if count >= FraudDetectionEngine.VELOCITY_MAX_COUNT:
            risk_score = min(1.0, 0.5 + (count - FraudDetectionEngine.VELOCITY_MAX_COUNT) * 0.05)
            return FraudAlert(
                transaction_id=transaction.id,
                fraud_type=FraudType.VELOCITY,
                status=FraudStatus.DETECTED,
                risk_score=risk_score,
                description=f"High frequency: {count} transactions in last {FraudDetectionEngine.VELOCITY_WINDOW_MINUTES} min",
                details={"transaction_count": count, "window_minutes": FraudDetectionEngine.VELOCITY_WINDOW_MINUTES},
            )
        return None

    @staticmethod
    async def _check_large_amount(
        db: AsyncSession, transaction: Transaction
    ) -> FraudAlert | None:
        if float(transaction.amount) >= FraudDetectionEngine.LARGE_AMOUNT_THRESHOLD:
            risk_score = min(
                1.0,
                float(transaction.amount) / (FraudDetectionEngine.LARGE_AMOUNT_THRESHOLD * 2)
            )
            return FraudAlert(
                transaction_id=transaction.id,
                fraud_type=FraudType.LARGE_AMOUNT,
                status=FraudStatus.DETECTED,
                risk_score=round(risk_score, 4),
                description=f"Transaction amount {transaction.amount} exceeds threshold",
                details={"amount": float(transaction.amount), "threshold": FraudDetectionEngine.LARGE_AMOUNT_THRESHOLD},
            )
        return None

    @staticmethod
    async def _check_round_tripping(
        db: AsyncSession, transaction: Transaction
    ) -> FraudAlert | None:
        window_start = datetime.now(timezone.utc) - timedelta(
            hours=FraudDetectionEngine.ROUND_TRIP_WINDOW_HOURS
        )
        result = await db.execute(
            select(func.count(Transaction.id)).where(
                and_(
                    Transaction.sender_phone == transaction.receiver_phone,
                    Transaction.receiver_phone == transaction.sender_phone,
                    Transaction.created_at >= window_start,
                    Transaction.id != transaction.id,
                )
            )
        )
        count = result.scalar() or 0
        if count > 0:
            return FraudAlert(
                transaction_id=transaction.id,
                fraud_type=FraudType.ROUND_TRIPPING,
                status=FraudStatus.DETECTED,
                risk_score=0.85,
                description="Detected round-trip transaction between same parties",
                details={"reverse_count": count, "window_hours": FraudDetectionEngine.ROUND_TRIP_WINDOW_HOURS},
            )
        return None

    @staticmethod
    async def _check_structuring(
        db: AsyncSession, transaction: Transaction
    ) -> FraudAlert | None:
        window_start = datetime.now(timezone.utc) - timedelta(
            hours=FraudDetectionEngine.STRUCTURING_WINDOW_HOURS
        )
        result = await db.execute(
            select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.sender_phone == transaction.sender_phone,
                    Transaction.created_at >= window_start,
                    Transaction.id != transaction.id,
                )
            )
        )
        total = float(result.scalar() or 0) + float(transaction.amount)
        if total >= FraudDetectionEngine.STRUCTURING_THRESHOLD:
            risk_score = min(1.0, total / (FraudDetectionEngine.STRUCTURING_THRESHOLD * 2))
            return FraudAlert(
                transaction_id=transaction.id,
                fraud_type=FraudType.STRUCTURING,
                status=FraudStatus.DETECTED,
                risk_score=round(risk_score, 4),
                description=f"Cumulative amount {total:.2f} in 24h suggests structuring",
                details={"cumulative_amount": total, "threshold": FraudDetectionEngine.STRUCTURING_THRESHOLD},
            )
        return None

    @staticmethod
    async def get_fraud_stats(db: AsyncSession) -> dict:
        total = await db.execute(select(func.count(FraudAlert.id)))
        by_type = await db.execute(
            select(FraudAlert.fraud_type, func.count(FraudAlert.id))
            .group_by(FraudAlert.fraud_type)
        )
        confirmed = await db.execute(
            select(func.count(FraudAlert.id)).where(
                FraudAlert.status == FraudStatus.CONFIRMED
            )
        )
        return {
            "total_alerts": total.scalar() or 0,
            "confirmed_fraud": confirmed.scalar() or 0,
            "by_type": {row[0]: row[1] for row in by_type.all()},
        }
