"""Database test fixtures."""

import os
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, User, Strategy

# Use test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer_test",
)


@pytest.fixture
async def db_engine():
    """Create test database engine and tables."""
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
    """Fresh database session for each test."""
    async_session_maker = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_user(db_session):
    """Pre-created user for tests."""
    user = User(wallet_address="test_wallet_abc123")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def sample_strategy(db_session, sample_user):
    """Pre-created strategy for tests."""
    strategy = Strategy(
        external_id="test_strategy_001",
        creator_id=sample_user.id,
        name="Test Strategy",
        description="A test strategy",
        dsl_json={"id": "test_strategy_001", "name": "Test Strategy", "tokens": ["SOL"]},
        is_public=True,
        status="active",
    )
    db_session.add(strategy)
    await db_session.flush()
    return strategy
