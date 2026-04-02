"""Paper trading routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories import PaperTradingRepository, StrategyRepository
from src.api.dependencies import get_db_session, get_current_user, get_paper_trading_manager
from src.api.schemas.paper_trading import (
    StartSessionRequest,
    StartSessionResponse,
    SessionStatusResponse,
    SessionListItem,
    StopSessionResponse,
    TradeResponse,
)
from src.paper_trading import PaperTradingManager


router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


@router.post("/sessions", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    data: StartSessionRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[PaperTradingManager, Depends(get_paper_trading_manager)],
) -> StartSessionResponse:
    """Start a new paper trading session."""
    # Verify strategy exists and user has access
    strategy_repo = StrategyRepository(session)
    strategy = await strategy_repo.get_by_id(data.strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        session_id = await manager.start_session(
            strategy_id=data.strategy_id,
            user_id=current_user.id,
            initial_capital=data.initial_capital,
            slippage_bps=data.slippage_bps,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return StartSessionResponse(
        session_id=session_id,
        strategy_id=data.strategy_id,
        initial_capital=data.initial_capital,
        status="running",
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    include_stopped: bool = False,
) -> list[SessionListItem]:
    """List current user's paper trading sessions."""
    repo = PaperTradingRepository(session)
    sessions = await repo.get_user_sessions(current_user.id, include_stopped=include_stopped)

    return [
        SessionListItem(
            id=s.id,
            strategy_id=s.strategy_id,
            status=s.status,
            initial_capital=s.initial_capital,
            cash_balance=s.cash_balance,
            started_at=s.started_at,
            last_tick_at=s.last_tick_at,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[PaperTradingManager, Depends(get_paper_trading_manager)],
) -> SessionStatusResponse:
    """Get status of a paper trading session."""
    # Verify ownership
    repo = PaperTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Get live status from manager if session is active
    status_data = await manager.get_session_status(session_id)

    if status_data:
        return SessionStatusResponse(**status_data)

    # Session not active in manager, return from database
    session_with_positions = await repo.get_with_positions(session_id)
    if not session_with_positions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    positions_dict = {
        pos.token: {
            "quantity": pos.quantity,
            "avg_entry_price": pos.avg_entry_price,
            "current_value": pos.total_cost,  # Use cost as value when not live
            "pnl_pct": 0.0,
        }
        for pos in session_with_positions.positions
    }

    position_value = sum(pos.total_cost for pos in session_with_positions.positions)
    total_value = session_with_positions.cash_balance + position_value

    return SessionStatusResponse(
        session_id=session_id,
        initial_capital=session_with_positions.initial_capital,
        cash_balance=session_with_positions.cash_balance,
        total_value=total_value,
        pnl_pct=(
            (total_value - session_with_positions.initial_capital)
            / session_with_positions.initial_capital
        )
        * 100,
        positions=positions_dict,
        trade_count=(
            len(session_with_positions.session_trades)
            if hasattr(session_with_positions, "session_trades")
            else 0
        ),
    )


@router.post("/sessions/{session_id}/stop", response_model=StopSessionResponse)
async def stop_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[PaperTradingManager, Depends(get_paper_trading_manager)],
) -> StopSessionResponse:
    """Stop a paper trading session."""
    # Verify ownership
    repo = PaperTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if session_record.status == "stopped":
        return StopSessionResponse(
            session_id=session_id,
            status="stopped",
            message="Session was already stopped",
        )

    stopped = await manager.stop_session(session_id)

    return StopSessionResponse(
        session_id=session_id,
        status="stopped",
        message="Session stopped successfully" if stopped else "Session was not active",
    )


@router.post("/sessions/{session_id}/pause", response_model=StopSessionResponse)
async def pause_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[PaperTradingManager, Depends(get_paper_trading_manager)],
) -> StopSessionResponse:
    """Pause a paper trading session."""
    # Verify ownership
    repo = PaperTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    paused = await manager.pause_session(session_id)

    return StopSessionResponse(
        session_id=session_id,
        status="paused" if paused else session_record.status,
        message="Session paused successfully" if paused else "Session was not active",
    )


@router.post("/sessions/{session_id}/resume", response_model=StopSessionResponse)
async def resume_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    manager: Annotated[PaperTradingManager, Depends(get_paper_trading_manager)],
) -> StopSessionResponse:
    """Resume a paused paper trading session."""
    # Verify ownership
    repo = PaperTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    resumed = await manager.resume_session(session_id)

    return StopSessionResponse(
        session_id=session_id,
        status="running" if resumed else session_record.status,
        message="Session resumed successfully" if resumed else "Session could not be resumed",
    )


@router.get("/sessions/{session_id}/trades", response_model=list[TradeResponse])
async def get_session_trades(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = 100,
) -> list[TradeResponse]:
    """Get trades for a paper trading session."""
    # Verify ownership
    repo = PaperTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    trades = await repo.get_session_trades(session_id, limit=limit)

    return [
        TradeResponse(
            id=t.id,
            trigger_id=t.trigger_id,
            token=t.token,
            action=t.action,
            quantity=t.quantity,
            price_at_exec=t.price_at_exec,
            timestamp=t.timestamp,
        )
        for t in trades
    ]
