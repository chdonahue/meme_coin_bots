"""API routes for live trading."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.repositories import StrategyRepository, LiveTradingRepository
from src.api.dependencies import get_db_session, get_current_user
from src.api.schemas.live_trading import (
    StartSessionRequest,
    SessionResponse,
    TransactionResponse,
    StopSessionResponse,
    EmergencyStopResponse,
)

router = APIRouter(prefix="/live-trading", tags=["live-trading"])


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    request: StartSessionRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
    """Start a new live trading session."""
    # Verify strategy exists and user has access
    strategy_repo = StrategyRepository(session)
    strategy = await strategy_repo.get_by_id(request.strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Check for existing active session for this strategy
    live_repo = LiveTradingRepository(session)
    user_sessions = await live_repo.get_user_sessions(current_user.id, include_stopped=False)
    for existing_session in user_sessions:
        if (
            existing_session.strategy_id == request.strategy_id
            and existing_session.status == "running"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A live session is already running for this strategy",
            )

    # Create the session
    live_session = await live_repo.create_session(
        strategy_id=request.strategy_id,
        user_id=current_user.id,
        wallet_address=request.wallet_address,
        max_trade_usd=request.max_trade_usd,
        max_daily_usd=request.max_daily_usd,
        max_daily_loss_usd=request.max_daily_loss_usd,
    )

    return SessionResponse(
        id=live_session.id,
        strategy_id=live_session.strategy_id,
        wallet_address=live_session.wallet_address,
        status=live_session.status,
        started_at=live_session.started_at,
        total_value_usd=None,
        daily_pnl_usd=float(live_session.daily_pnl_usd),
        pending_txs=0,
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    include_stopped: bool = False,
) -> list[SessionResponse]:
    """List all live trading sessions for the current user."""
    repo = LiveTradingRepository(session)
    sessions = await repo.get_user_sessions(current_user.id, include_stopped=include_stopped)

    result = []
    for s in sessions:
        pending_count = await repo.get_pending_transaction_count(s.id)
        result.append(
            SessionResponse(
                id=s.id,
                strategy_id=s.strategy_id,
                wallet_address=s.wallet_address,
                status=s.status,
                started_at=s.started_at,
                total_value_usd=None,
                daily_pnl_usd=float(s.daily_pnl_usd),
                pending_txs=pending_count,
            )
        )

    return result


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
    """Get details of a live trading session."""
    repo = LiveTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    pending_count = await repo.get_pending_transaction_count(session_id)

    return SessionResponse(
        id=session_record.id,
        strategy_id=session_record.strategy_id,
        wallet_address=session_record.wallet_address,
        status=session_record.status,
        started_at=session_record.started_at,
        total_value_usd=None,
        daily_pnl_usd=float(session_record.daily_pnl_usd),
        pending_txs=pending_count,
    )


@router.get("/sessions/{session_id}/transactions", response_model=list[TransactionResponse])
async def get_session_transactions(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = 100,
) -> list[TransactionResponse]:
    """Get transactions for a live trading session."""
    repo = LiveTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    transactions = await repo.get_session_transactions(session_id, limit=limit)

    return [
        TransactionResponse(
            id=t.id,
            trigger_id=t.trigger_id,
            action_type=t.action_type,
            state=t.state,
            token_address=t.token_address,
            tx_signature=t.tx_signature,
            created_at=t.created_at,
        )
        for t in transactions
    ]


@router.post("/sessions/{session_id}/stop", response_model=StopSessionResponse)
async def stop_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StopSessionResponse:
    """Stop a live trading session (graceful stop)."""
    repo = LiveTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if session_record.status in ("stopped", "killed"):
        return StopSessionResponse(
            session_id=session_id,
            status=session_record.status,
            message="Session was already stopped",
        )

    await repo.stop_session(session_id)

    return StopSessionResponse(
        session_id=session_id,
        status="stopped",
        message="Session stopped successfully",
    )


@router.post("/sessions/{session_id}/kill", response_model=StopSessionResponse)
async def kill_session(
    session_id: int,
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StopSessionResponse:
    """Emergency kill a live trading session."""
    repo = LiveTradingRepository(db_session)
    session_record = await repo.get_by_id(session_id)

    if not session_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if session_record.status == "killed":
        return StopSessionResponse(
            session_id=session_id,
            status="killed",
            message="Session was already killed",
        )

    await repo.kill_session(session_id)

    return StopSessionResponse(
        session_id=session_id,
        status="killed",
        message="Session killed successfully",
    )


@router.post("/emergency-stop", response_model=EmergencyStopResponse)
async def emergency_stop(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EmergencyStopResponse:
    """Emergency stop ALL live trading sessions for the current user.

    This immediately kills all running sessions without waiting for
    pending transactions to complete.
    """
    repo = LiveTradingRepository(db_session)

    # Get only the current user's active sessions
    user_sessions = await repo.get_user_sessions(current_user.id, include_stopped=False)

    count = 0
    for session_record in user_sessions:
        if session_record.status == "running":
            await repo.kill_session(session_record.id)
            count += 1

    if count == 0:
        return EmergencyStopResponse(
            stopped_sessions=0,
            message="No active sessions to stop",
        )

    return EmergencyStopResponse(
        stopped_sessions=count,
        message=f"Emergency stopped {count} session(s)",
    )
