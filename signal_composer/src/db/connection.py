"""Database connection management."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

# Load environment variables from .env file
load_dotenv()


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost:5432/signal_composer")


# Create engine
_db_url = get_database_url()
_connect_args = {}
if _db_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_async_engine(
    _db_url,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    connect_args=_connect_args,
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
