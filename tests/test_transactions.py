import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import patch

from tests.conftest import auth_headers


def transaction_payload():
    return {
        "amount": "50000.00",
        "currency": "XOF",
        "transaction_type": "TRANSFERT",
        "sender_phone": "+221771234567",
        "receiver_phone": "+221787654321",
        "sender_name": "Sender Test",
        "receiver_name": "Receiver Test",
        "transaction_date": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_create_transaction_as_operator(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    with patch("app.api.v1.transactions.process_transaction_async"):
        resp = await client.post(
            "/api/v1/transactions",
            headers=headers,
            json=transaction_payload(),
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reference"].startswith("TXN-")
    assert data["status"] == "PENDING"
    assert data["amount"] == "50000.00"


@pytest.mark.asyncio
async def test_create_transaction_forbidden_for_citoyen(client: AsyncClient):
    # Register a citoyen
    await client.post("/api/v1/auth/register", json={
        "username": "citoyen1",
        "email": "citoyen1@test.com",
        "password": "Citoyen@1!",
        "full_name": "Citoyen Test",
        "role": "CITOYEN",
    })
    login = await client.post("/api/v1/auth/login", json={
        "username": "citoyen1", "password": "Citoyen@1!"
    })
    token = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/transactions",
        headers={"Authorization": f"Bearer {token}"},
        json=transaction_payload(),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_transactions(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    with patch("app.api.v1.transactions.process_transaction_async"):
        await client.post("/api/v1/transactions", headers=headers, json=transaction_payload())

    resp = await client.get("/api/v1/transactions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_transaction_by_id(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    with patch("app.api.v1.transactions.process_transaction_async"):
        create_resp = await client.post(
            "/api/v1/transactions", headers=headers, json=transaction_payload()
        )
    tx_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/transactions/{tx_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tx_id


@pytest.mark.asyncio
async def test_invalid_amount(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    payload = transaction_payload()
    payload["amount"] = "-100"
    resp = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_currency(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    payload = transaction_payload()
    payload["currency"] = "ZZZ"
    resp = await client.post("/api/v1/transactions", headers=headers, json=payload)
    assert resp.status_code == 422
