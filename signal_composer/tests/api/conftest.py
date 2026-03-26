"""API test fixtures."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, User, Strategy
from src.api.main import app
from src.api.dependencies import get_db_session
from src.api.auth.jwt import create_access_token
from src.api.auth.wallet import clear_challenges


# Set test environment
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("CHALLENGE_TTL_MINUTES", "5")

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer_test",
)


@pytest.fixture
async def db_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Get test database session."""
    async_session_maker = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def client(db_session):
    """Test client with overridden dependencies."""

    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    clear_challenges()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session) -> User:
    """Create test user."""
    user = User(wallet_address="TestWallet123")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def auth_headers(test_user) -> dict:
    """Auth headers with valid JWT."""
    token = create_access_token(
        wallet_address=test_user.wallet_address,
        user_id=test_user.id,
    )
    return {"Authorization": f"Bearer {token}"}
