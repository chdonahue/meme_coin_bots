"""Performance routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories import StrategyRepository, PerformanceRepository
from src.api.dependencies import get_db_session, get_current_user
from src.api.schemas.performance import PerformanceResponse


router = APIRouter(prefix="/strategies/{strategy_id}/performance", tags=["performance"])


@router.get("", response_model=list[PerformanceResponse])
async def get_performance_history(
    strategy_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(default=30, ge=1, le=365),
):
    """Get performance history for a strategy."""
    strategy_repo = StrategyRepository(session)
    strategy = await strategy_repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    perf_repo = PerformanceRepository(session)
    return await perf_repo.get_history(strategy_id, days=days)
