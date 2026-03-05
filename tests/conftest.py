import asyncio
import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.core.database import Base, get_db
from app.core.redis import redis_client
from app.models.user import User, UserRole
from app.core.security import get_password_hash, create_access_token

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # Mock Redis
    redis_client._client = MagicMock()
    redis_client._client.get = AsyncMock(return_value=None)
    redis_client._client.setex = AsyncMock(return_value=True)
    redis_client._client.exists = AsyncMock(return_value=0)
    redis_client._client.incr = AsyncMock(return_value=1)
    redis_client._client.expire = AsyncMock(return_value=True)
    redis_client._client.pipeline = MagicMock(return_value=AsyncMock(
        execute=AsyncMock(return_value=[1, True]),
        incr=AsyncMock(),
        expire=AsyncMock(),
    ))

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def operator_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="operateur_test",
        email="operateur@test.com",
        hashed_password=get_password_hash("Test@1234!"),
        full_name="Opérateur Test",
        role=UserRole.OPERATEUR_MOBILE,
        phone_number="+221771234567",
        organization="Orange Money SN",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def dgid_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="dgid_agent",
        email="agent@dgid.sn",
        hashed_password=get_password_hash("Dgid@5678!"),
        full_name="Agent DGID Test",
        role=UserRole.AGENT_DGID,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auditor_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="auditeur_test",
        email="auditeur@test.com",
        hashed_password=get_password_hash("Audit@9012!"),
        full_name="Auditeur Test",
        role=UserRole.AUDITEUR_FISCAL,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}
