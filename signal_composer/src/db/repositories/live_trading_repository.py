"""Repository for live trading sessions."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import LiveTradingSessionModel, LiveTransactionModel
from .base import BaseRepository


class LiveTradingRepository(BaseRepository[LiveTradingSessionModel]):
    """Repository for live trading sessions with transactions."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LiveTradingSessionModel)

    async def create_session(
        self,
        strategy_id: int,
        user_id: int,
        wallet_address: str,
        max_trade_usd: Decimal = Decimal("500"),
        max_daily_usd: Decimal = Decimal("2000"),
        max_daily_loss_usd: Decimal = Decimal("500"),
    ) -> LiveTradingSessionModel:
        """Create a new live trading session."""
        session_model = LiveTradingSessionModel(
            strategy_id=strategy_id,
            user_id=user_id,
            wallet_address=wallet_address,
            max_trade_usd=max_trade_usd,
            max_daily_usd=max_daily_usd,
            max_daily_loss_usd=max_daily_loss_usd,
            status="running",
        )
        return await self.create(session_model)

    async def get_with_transactions(self, session_id: int) -> LiveTradingSessionModel | None:
        """Get session with transactions eagerly loaded."""
        stmt = (
            select(LiveTradingSessionModel)
            .options(selectinload(LiveTradingSessionModel.transactions))
            .where(LiveTradingSessionModel.id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_sessions(self) -> list[LiveTradingSessionModel]:
        """Get all running sessions."""
        stmt = (
            select(LiveTradingSessionModel)
            .options(selectinload(LiveTradingSessionModel.transactions))
            .where(LiveTradingSessionModel.status == "running")
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_sessions(
        self, user_id: int, include_stopped: bool = False
    ) -> list[LiveTradingSessionModel]:
        """Get sessions for a user."""
        stmt = select(LiveTradingSessionModel).where(LiveTradingSessionModel.user_id == user_id)
        if not include_stopped:
            stmt = stmt.where(LiveTradingSessionModel.status != "stopped")
        stmt = stmt.options(selectinload(LiveTradingSessionModel.transactions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def stop_session(self, session_id: int) -> LiveTradingSessionModel | None:
        """Stop a live trading session (graceful stop)."""
        session_model = await self.get_by_id(session_id)
        if session_model:
            session_model.status = "stopped"
            session_model.stopped_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(session_model)
        return session_model

    async def kill_session(self, session_id: int) -> LiveTradingSessionModel | None:
        """Kill a live trading session (emergency stop)."""
        session_model = await self.get_by_id(session_id)
        if session_model:
            session_model.status = "killed"
            session_model.stopped_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(session_model)
        return session_model

    async def emergency_stop_all(self) -> int:
        """Emergency stop ALL active sessions. Returns number stopped."""
        active_sessions = await self.get_active_sessions()
        count = 0
        now = datetime.now(timezone.utc)
        for session_model in active_sessions:
            session_model.status = "killed"
            session_model.stopped_at = now
            count += 1
        if count > 0:
            await self.session.flush()
        return count

    async def update_last_tick(self, session_id: int) -> None:
        """Update the last tick timestamp."""
        session_model = await self.get_by_id(session_id)
        if session_model:
            session_model.last_tick_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def get_pending_transaction_count(self, session_id: int) -> int:
        """Get count of pending transactions for a session."""
        stmt = (
            select(func.count())
            .select_from(LiveTransactionModel)
            .where(
                LiveTransactionModel.session_id == session_id,
                LiveTransactionModel.state.in_(["pending", "submitted"]),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_session_transactions(
        self, session_id: int, limit: int = 100
    ) -> list[LiveTransactionModel]:
        """Get transactions for a session."""
        stmt = (
            select(LiveTransactionModel)
            .where(LiveTransactionModel.session_id == session_id)
            .order_by(LiveTransactionModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
