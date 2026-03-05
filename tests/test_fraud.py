import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.fraud import FraudAlert, FraudType, FraudStatus
from app.services.fraud_service import FraudDetectionEngine
from tests.conftest import auth_headers


async def _make_transaction(db: AsyncSession, operator_user, amount=50000.0, sender="+221771234567") -> Transaction:
    tx = Transaction(
        id=uuid.uuid4(),
        reference=f"TXN-{uuid.uuid4().hex[:10].upper()}",
        operator_id=operator_user.id,
        amount=amount,
        currency="XOF",
        transaction_type=TransactionType.TRANSFERT,
        sender_phone=sender,
        receiver_phone="+221787654321",
        status=TransactionStatus.PENDING,
        transaction_date=datetime.now(timezone.utc),
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


@pytest.mark.asyncio
async def test_large_amount_detection(db_session: AsyncSession, operator_user):
    tx = await _make_transaction(db_session, operator_user, amount=2_000_000.0)
    alerts = await FraudDetectionEngine.analyze_transaction(db_session, tx)
    fraud_types = [a.fraud_type for a in alerts]
    assert FraudType.LARGE_AMOUNT in fraud_types


@pytest.mark.asyncio
async def test_normal_amount_no_alert(db_session: AsyncSession, operator_user):
    tx = await _make_transaction(db_session, operator_user, amount=5000.0)
    alerts = await FraudDetectionEngine.analyze_transaction(db_session, tx)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_list_fraud_alerts_as_agent(client: AsyncClient, dgid_user):
    headers = auth_headers(dgid_user)
    resp = await client.get("/api/v1/fraud/alerts", headers=headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_fraud_statistics(client: AsyncClient, dgid_user):
    headers = auth_headers(dgid_user)
    resp = await client.get("/api/v1/fraud/statistics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_alerts" in data
    assert "confirmed_fraud" in data


@pytest.mark.asyncio
async def test_fraud_access_denied_for_operator(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    resp = await client.get("/api/v1/fraud/alerts", headers=headers)
    assert resp.status_code == 403
