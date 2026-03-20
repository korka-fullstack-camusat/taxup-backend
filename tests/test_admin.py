import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.core.security import get_password_hash, create_access_token
from tests.conftest import auth_headers


# ── Fixtures ─────────────────────────────────────────────────────────────────

async def _create_user(db: AsyncSession, **kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        username="user_" + uuid.uuid4().hex[:8],
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=get_password_hash("Test@1234!"),
        full_name="Test User",
        role=UserRole.CITOYEN,
        is_active=True,
        is_verified=True,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username="admin_test",
        email="admin@test.com",
        full_name="Admin Test",
        role=UserRole.ADMIN,
    )


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    return await _create_user(
        db_session,
        username="regular_test",
        email="regular@test.com",
        full_name="Regular User",
        role=UserRole.CITOYEN,
    )


# ── Tests LIST ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users_as_admin(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.get("/api/v1/users", headers=auth_headers(admin_user))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_users_forbidden_for_non_admin(client: AsyncClient, regular_user: User):
    resp = await client.get("/api/v1/users", headers=auth_headers(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_users_search_filter(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.get(
        "/api/v1/users",
        params={"search": regular_user.username},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(u["username"] == regular_user.username for u in items)


@pytest.mark.asyncio
async def test_list_users_role_filter(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.get(
        "/api/v1/users",
        params={"role": "CITOYEN"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(u["role"] == "CITOYEN" for u in items)


# ── Tests CREATE ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user_as_admin(client: AsyncClient, admin_user: User):
    payload = {
        "username": "newadminuser",
        "email": "newadmin@test.com",
        "password": "Admin@1234!",
        "full_name": "New Admin User",
        "role": "AUDITEUR_FISCAL",
    }
    resp = await client.post("/api/v1/users", json=payload, headers=auth_headers(admin_user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newadminuser"
    assert data["role"] == "AUDITEUR_FISCAL"


@pytest.mark.asyncio
async def test_create_user_duplicate_forbidden(client: AsyncClient, admin_user: User, regular_user: User):
    payload = {
        "username": regular_user.username,
        "email": "other@test.com",
        "password": "Admin@1234!",
        "full_name": "Duplicate",
        "role": "CITOYEN",
    }
    resp = await client.post("/api/v1/users", json=payload, headers=auth_headers(admin_user))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_user_forbidden_for_non_admin(client: AsyncClient, regular_user: User):
    payload = {
        "username": "shouldfail",
        "email": "shouldfail@test.com",
        "password": "Admin@1234!",
        "full_name": "Should Fail",
        "role": "CITOYEN",
    }
    resp = await client.post("/api/v1/users", json=payload, headers=auth_headers(regular_user))
    assert resp.status_code == 403


# ── Tests GET BY ID ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.get(f"/api/v1/users/{regular_user.id}", headers=auth_headers(admin_user))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(regular_user.id)


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, admin_user: User):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/users/{fake_id}", headers=auth_headers(admin_user))
    assert resp.status_code == 404


# ── Tests UPDATE ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_user_role(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.put(
        f"/api/v1/users/{regular_user.id}",
        json={"role": "AUDITEUR_FISCAL"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "AUDITEUR_FISCAL"


@pytest.mark.asyncio
async def test_update_user_forbidden_for_non_admin(client: AsyncClient, regular_user: User):
    resp = await client.put(
        f"/api/v1/users/{regular_user.id}",
        json={"full_name": "Hacked"},
        headers=auth_headers(regular_user),
    )
    assert resp.status_code == 403


# ── Tests ACTIVATE / DEACTIVATE ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_user(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.patch(
        f"/api/v1/users/{regular_user.id}/deactivate",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_activate_user(client: AsyncClient, admin_user: User, regular_user: User):
    # Deactivate first
    await client.patch(
        f"/api/v1/users/{regular_user.id}/deactivate",
        headers=auth_headers(admin_user),
    )
    resp = await client.patch(
        f"/api/v1/users/{regular_user.id}/activate",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_cannot_deactivate_own_account(client: AsyncClient, admin_user: User):
    resp = await client.patch(
        f"/api/v1/users/{admin_user.id}/deactivate",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 400


# ── Tests DELETE ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_user(client: AsyncClient, admin_user: User, regular_user: User):
    resp = await client.delete(
        f"/api/v1/users/{regular_user.id}",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_own_account(client: AsyncClient, admin_user: User):
    resp = await client.delete(
        f"/api/v1/users/{admin_user.id}",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_user_not_found(client: AsyncClient, admin_user: User):
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/v1/users/{fake_id}", headers=auth_headers(admin_user))
    assert resp.status_code == 404
