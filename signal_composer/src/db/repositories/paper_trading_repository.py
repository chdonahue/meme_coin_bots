"""Repository for paper trading sessions."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import PaperTradingSession, PaperTradingPosition, PaperTradingSessionTrade
from .base import BaseRepository


class PaperTradingRepository(BaseRepository[PaperTradingSession]):
    """Repository for paper trading sessions with positions and trades."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, PaperTradingSession)

    async def create_session(
        self,
        strategy_id: int,
        user_id: int,
        initial_capital: float = 10000.0,
        polling_interval_seconds: int = 60,
    ) -> PaperTradingSession:
        """Create a new paper trading session."""
        session = PaperTradingSession(
            strategy_id=strategy_id,
            user_id=user_id,
            initial_capital=initial_capital,
            cash_balance=initial_capital,
            polling_interval_seconds=polling_interval_seconds,
            status="running",
        )
        return await self.create(session)

    async def get_with_positions(self, session_id: int) -> PaperTradingSession | None:
        """Get session with positions eagerly loaded."""
        stmt = (
            select(PaperTradingSession)
            .options(selectinload(PaperTradingSession.positions))
            .where(PaperTradingSession.id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_sessions(self) -> list[PaperTradingSession]:
        """Get all running sessions."""
        stmt = (
            select(PaperTradingSession)
            .options(selectinload(PaperTradingSession.positions))
            .where(PaperTradingSession.status == "running")
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_sessions(
        self, user_id: int, include_stopped: bool = False
    ) -> list[PaperTradingSession]:
        """Get sessions for a user."""
        stmt = select(PaperTradingSession).where(PaperTradingSession.user_id == user_id)
        if not include_stopped:
            stmt = stmt.where(PaperTradingSession.status != "stopped")
        stmt = stmt.options(selectinload(PaperTradingSession.positions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def stop_session(self, session_id: int) -> PaperTradingSession | None:
        """Stop a paper trading session."""
        session = await self.get_by_id(session_id)
        if session:
            session.status = "stopped"
            session.stopped_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(session)
        return session

    async def pause_session(self, session_id: int) -> PaperTradingSession | None:
        """Pause a paper trading session."""
        session = await self.get_by_id(session_id)
        if session:
            session.status = "paused"
            await self.session.flush()
            await self.session.refresh(session)
        return session

    async def resume_session(self, session_id: int) -> PaperTradingSession | None:
        """Resume a paused paper trading session."""
        session = await self.get_by_id(session_id)
        if session and session.status == "paused":
            session.status = "running"
            await self.session.flush()
            await self.session.refresh(session)
        return session

    async def update_last_tick(self, session_id: int) -> None:
        """Update the last tick timestamp."""
        session = await self.get_by_id(session_id)
        if session:
            session.last_tick_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def update_cash_balance(self, session_id: int, new_balance: float) -> None:
        """Update the cash balance for a session."""
        session = await self.get_by_id(session_id)
        if session:
            session.cash_balance = new_balance
            await self.session.flush()

    # Position methods
    async def get_position(self, session_id: int, token: str) -> PaperTradingPosition | None:
        """Get a specific position."""
        stmt = select(PaperTradingPosition).where(
            PaperTradingPosition.session_id == session_id,
            PaperTradingPosition.token == token,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_position(
        self,
        session_id: int,
        token: str,
        quantity: float,
        avg_entry_price: float,
        total_cost: float,
    ) -> PaperTradingPosition:
        """Create or update a position."""
        position = await self.get_position(session_id, token)
        if position:
            position.quantity = quantity
            position.avg_entry_price = avg_entry_price
            position.total_cost = total_cost
            await self.session.flush()
            await self.session.refresh(position)
        else:
            position = PaperTradingPosition(
                session_id=session_id,
                token=token,
                quantity=quantity,
                avg_entry_price=avg_entry_price,
                total_cost=total_cost,
            )
            self.session.add(position)
            await self.session.flush()
            await self.session.refresh(position)
        return position

    async def delete_position(self, session_id: int, token: str) -> bool:
        """Delete a position (when fully sold)."""
        position = await self.get_position(session_id, token)
        if position:
            await self.session.delete(position)
            await self.session.flush()
            return True
        return False

    # Trade methods
    async def record_trade(
        self,
        session_id: int,
        trigger_id: str,
        token: str,
        action: str,
        quantity: float,
        price_at_exec: float,
    ) -> PaperTradingSessionTrade:
        """Record a trade in the session."""
        trade = PaperTradingSessionTrade(
            session_id=session_id,
            trigger_id=trigger_id,
            token=token,
            action=action,
            quantity=quantity,
            price_at_exec=price_at_exec,
        )
        self.session.add(trade)
        await self.session.flush()
        await self.session.refresh(trade)
        return trade

    async def get_session_trades(
        self, session_id: int, limit: int = 100
    ) -> list[PaperTradingSessionTrade]:
        """Get trades for a session."""
        stmt = (
            select(PaperTradingSessionTrade)
            .where(PaperTradingSessionTrade.session_id == session_id)
            .order_by(PaperTradingSessionTrade.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
