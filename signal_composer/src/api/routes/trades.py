"""Trade routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories import StrategyRepository, TradeRepository
from src.api.dependencies import get_db_session, get_current_user
from src.api.schemas.trade import TradeResponse, PaginatedTradesResponse


router = APIRouter(prefix="/strategies/{strategy_id}/trades", tags=["trades"])


@router.get("", response_model=PaginatedTradesResponse)
async def get_trades(
    strategy_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    """Get paginated trade history for a strategy."""
    strategy_repo = StrategyRepository(session)
    strategy = await strategy_repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    trade_repo = TradeRepository(session)

    # Get total count
    total = await trade_repo.count_by_strategy(strategy_id)

    # Get paginated trades
    offset = (page - 1) * page_size
    trades = await trade_repo.list_by_strategy(strategy_id, limit=page_size, offset=offset)

    return PaginatedTradesResponse(
        items=[TradeResponse.model_validate(t) for t in trades],
        total=total,
        page=page,
        page_size=page_size,
    )
