import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from tests.conftest import auth_headers
import uuid


async def _create_transaction(db: AsyncSession, operator_user) -> Transaction:
    tx = Transaction(
        id=uuid.uuid4(),
        reference=f"TXN-TEST-{uuid.uuid4().hex[:8].upper()}",
        operator_id=operator_user.id,
        amount=100000.00,
        currency="XOF",
        transaction_type=TransactionType.TRANSFERT,
        sender_phone="+221771234567",
        receiver_phone="+221787654321",
        status=TransactionStatus.PENDING,
        transaction_date=datetime.now(timezone.utc),
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


@pytest.mark.asyncio
async def test_generate_receipt(client: AsyncClient, db_session: AsyncSession, operator_user):
    tx = await _create_transaction(db_session, operator_user)
    headers = auth_headers(operator_user)

    resp = await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["receipt_number"].startswith("REC-")
    assert data["is_certified"] is True
    assert float(data["tax_rate"]) == pytest.approx(0.18, rel=1e-3)
    assert float(data["tax_amount"]) == pytest.approx(18000.00, rel=1e-2)


@pytest.mark.asyncio
async def test_generate_receipt_duplicate(client: AsyncClient, db_session: AsyncSession, operator_user):
    tx = await _create_transaction(db_session, operator_user)
    headers = auth_headers(operator_user)

    await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)
    resp = await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_receipts(client: AsyncClient, db_session: AsyncSession, operator_user):
    tx = await _create_transaction(db_session, operator_user)
    headers = auth_headers(operator_user)
    await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)

    resp = await client.get("/api/v1/receipts", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_verify_receipt(client: AsyncClient, db_session: AsyncSession, operator_user):
    tx = await _create_transaction(db_session, operator_user)
    headers = auth_headers(operator_user)
    create_resp = await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)
    receipt = create_resp.json()

    verify_resp = await client.post("/api/v1/receipts/verify", json={
        "receipt_number": receipt["receipt_number"],
        "digital_signature": receipt["digital_signature"],
    })
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["is_valid"] is True


@pytest.mark.asyncio
async def test_verify_invalid_signature(client: AsyncClient, db_session: AsyncSession, operator_user):
    tx = await _create_transaction(db_session, operator_user)
    headers = auth_headers(operator_user)
    create_resp = await client.post(f"/api/v1/receipts/generate/{tx.id}", headers=headers)
    receipt = create_resp.json()

    verify_resp = await client.post("/api/v1/receipts/verify", json={
        "receipt_number": receipt["receipt_number"],
        "digital_signature": "invalidsignature==",
    })
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_valid"] is False
