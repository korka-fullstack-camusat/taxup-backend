import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_create_audit_as_auditor(client: AsyncClient, auditor_user):
    headers = auth_headers(auditor_user)
    payload = {
        "anomaly_type": "MONTANT_SUSPECT",
        "title": "Transaction suspecte détectée",
        "description": "Montant anormalement élevé pour ce profil utilisateur.",
    }
    resp = await client.post("/api/v1/audits", headers=headers, json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["audit_number"].startswith("AUD-")
    assert data["status"] == "OUVERT"
    assert data["anomaly_type"] == "MONTANT_SUSPECT"


@pytest.mark.asyncio
async def test_create_audit_forbidden_for_operator(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    resp = await client.post("/api/v1/audits", headers=headers, json={
        "anomaly_type": "AUTRE",
        "title": "Test",
        "description": "Test audit by operator",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_audits(client: AsyncClient, auditor_user):
    headers = auth_headers(auditor_user)
    await client.post("/api/v1/audits", headers=headers, json={
        "anomaly_type": "FREQUENCE_ANORMALE",
        "title": "Test audit",
        "description": "Fréquence anormale de transactions.",
    })
    resp = await client.get("/api/v1/audits", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_update_audit(client: AsyncClient, auditor_user):
    headers = auth_headers(auditor_user)
    create_resp = await client.post("/api/v1/audits", headers=headers, json={
        "anomaly_type": "BLANCHIMENT",
        "title": "Blanchiment potentiel",
        "description": "Flux suspects entre plusieurs comptes.",
    })
    audit_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/audits/{audit_id}",
        headers=headers,
        json={"status": "EN_COURS", "findings": "Investigation en cours."},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "EN_COURS"


@pytest.mark.asyncio
async def test_audit_statistics(client: AsyncClient, auditor_user):
    headers = auth_headers(auditor_user)
    resp = await client.get("/api/v1/audits/statistics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "open" in data
