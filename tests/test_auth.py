import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "Test@1234!",
        "full_name": "New User",
        "role": "CITOYEN",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["role"] == "CITOYEN"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, operator_user):
    payload = {
        "username": operator_user.username,
        "email": "another@example.com",
        "password": "Test@1234!",
        "full_name": "Another User",
        "role": "CITOYEN",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    payload = {
        "username": "weakpass",
        "email": "weak@example.com",
        "password": "password",  # no uppercase, no digit, no special
        "full_name": "Weak User",
        "role": "CITOYEN",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, operator_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": operator_user.username, "password": "Test@1234!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, operator_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": operator_user.username, "password": "WrongPass@1!"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == operator_user.username
    assert data["role"] == "OPERATEUR_MOBILE"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_me(client: AsyncClient, operator_user):
    headers = auth_headers(operator_user)
    resp = await client.put(
        "/api/v1/auth/me",
        headers=headers,
        json={"full_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"
