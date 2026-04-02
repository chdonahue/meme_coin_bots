"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session
from src.db.models import User
from src.db.repositories import UserRepository
from src.api.auth.jwt import decode_access_token, JWTError
from src.paper_trading import PaperTradingManager


security = HTTPBearer()

# Singleton paper trading manager (initialized in main.py lifespan)
_paper_trading_manager: PaperTradingManager | None = None


def set_paper_trading_manager(manager: PaperTradingManager) -> None:
    """Set the global paper trading manager instance."""
    global _paper_trading_manager
    _paper_trading_manager = manager


def get_paper_trading_manager() -> PaperTradingManager:
    """Get the paper trading manager instance."""
    if _paper_trading_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paper trading manager not initialized",
        )
    return _paper_trading_manager


async def get_db_session():
    """Get database session."""
    async with get_session() as session:
        yield session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
