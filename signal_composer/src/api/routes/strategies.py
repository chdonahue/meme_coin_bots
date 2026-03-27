"""Strategy routes."""

import uuid
from datetime import datetime, timezone, timedelta
import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Strategy
from src.db.repositories import StrategyRepository, TradeRepository, PerformanceRepository
from src.api.dependencies import get_db_session, get_current_user
from src.api.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    BacktestRequest,
    BacktestResponse,
)
from src.engine.dsl.parser import parse_strategy
from src.engine.dsl.validator import validate_strategy
from src.simulation.backtest import BacktestEngine
from src.simulation.persistence import SimulationPersistence


router = APIRouter(prefix="/strategies", tags=["strategies"])


def _validate_dsl(dsl: dict) -> None:
    """Validate DSL and raise HTTPException if invalid."""
    try:
        strategy = parse_strategy(dsl)
        errors = validate_strategy(strategy)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": "Invalid strategy DSL",
                    "errors": errors,
                },
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "parse_error",
                "message": str(e),
            },
        )


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: StrategyCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Strategy:
    """Create a new strategy."""
    _validate_dsl(data.dsl)

    repo = StrategyRepository(session)

    # Generate external_id from DSL or create one
    external_id = data.dsl.get("id", str(uuid.uuid4()))

    # Check if external_id already exists
    existing = await repo.get_by_external_id(external_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strategy with id '{external_id}' already exists",
        )

    strategy = Strategy(
        external_id=external_id,
        creator_id=current_user.id,
        name=data.name,
        description=data.description,
        dsl_json=data.dsl,
        is_public=data.is_public,
        status="active",
    )

    strategy = await repo.create(strategy)
    await session.commit()
    return strategy


@router.get("", response_model=list[StrategyResponse])
async def list_strategies(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Strategy]:
    """List current user's strategies."""
    repo = StrategyRepository(session)
    return await repo.list_by_user(current_user.id)


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Strategy:
    """Get strategy by ID."""
    repo = StrategyRepository(session)
    strategy = await repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Strategy:
    """Update a strategy."""
    repo = StrategyRepository(session)
    strategy = await repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if data.dsl is not None:
        _validate_dsl(data.dsl)
        strategy.dsl_json = data.dsl

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.is_public is not None:
        strategy.is_public = data.is_public
    if data.status is not None:
        strategy.status = data.status

    await session.flush()
    await session.refresh(strategy)
    await session.commit()
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a strategy."""
    repo = StrategyRepository(session)
    strategy = await repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await repo.delete(strategy_id)
    await session.commit()


@router.post("/{strategy_id}/backtest", response_model=BacktestResponse)
async def run_backtest(
    strategy_id: int,
    data: BacktestRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BacktestResponse:
    """Run backtest on a strategy."""
    repo = StrategyRepository(session)
    strategy = await repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Parse DSL
    strategy_dsl = parse_strategy(strategy.dsl_json)

    # Generate synthetic price history
    base_price = 100.0
    base_time = datetime.now(timezone.utc) - timedelta(days=data.days)
    price_history = []

    for i in range(data.days * 48):
        timestamp = base_time + timedelta(minutes=i * 30)
        change = random.gauss(0.001, 0.02)
        base_price *= 1 + change

        tick = {"timestamp": timestamp}
        for token in strategy_dsl.tokens:
            tick[token] = base_price * (1 + random.gauss(0, 0.01))
        price_history.append(tick)

    # Run backtest
    engine = BacktestEngine(
        initial_capital=data.initial_capital,
        slippage_bps=data.slippage_bps,
    )
    result = engine.run(strategy_dsl, price_history)

    # Save results
    trade_repo = TradeRepository(session)
    perf_repo = PerformanceRepository(session)
    persistence = SimulationPersistence(trade_repo, perf_repo)
    await persistence.save_backtest_result(strategy.id, result)
    await session.commit()

    return BacktestResponse(
        total_return_pct=result.total_return_pct,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown_pct=result.max_drawdown_pct,
        trade_count=result.trade_count,
        win_rate=result.win_rate,
        equity_curve=result.equity_curve,
        saved=True,
    )
