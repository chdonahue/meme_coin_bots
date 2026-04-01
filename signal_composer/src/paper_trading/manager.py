"""Paper trading manager for orchestrating multiple sessions."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from ..data.sources.birdeye import BirdeyeDataSource
from ..db.repositories.paper_trading_repository import PaperTradingRepository
from ..db.repositories.strategy_repository import StrategyRepository
from ..engine.dsl.parser import parse_strategy
from .session import PaperTradingSession, LivePosition, LiveTrade

logger = logging.getLogger(__name__)


class PaperTradingManager:
    """
    Manages multiple paper trading sessions with a shared polling loop.

    Responsibilities:
    - Fetch prices once per tick, distribute to all active sessions
    - Persist session state to database after trades
    - Start/stop individual sessions
    - Run background polling loop
    """

    def __init__(
        self,
        db_session_factory: Callable[[], Awaitable[AsyncSession]],
        data_source: BirdeyeDataSource | None = None,
        default_polling_interval: int = 60,
    ):
        """
        Initialize the manager.

        Args:
            db_session_factory: Async factory that returns a new database session
            data_source: Price data source (defaults to Birdeye)
            default_polling_interval: Default seconds between price ticks
        """
        self.db_session_factory = db_session_factory
        self.data_source = data_source or BirdeyeDataSource()
        self.default_polling_interval = default_polling_interval

        # Active in-memory sessions: session_id -> PaperTradingSession
        self._sessions: dict[int, PaperTradingSession] = {}
        self._running = False
        self._poll_task: asyncio.Task | None = None

    @property
    def active_session_count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)

    @property
    def is_running(self) -> bool:
        """Whether the polling loop is running."""
        return self._running

    async def start_session(
        self,
        strategy_id: int,
        user_id: int,
        initial_capital: float = 10000.0,
        slippage_bps: int = 100,
    ) -> int:
        """
        Start a new paper trading session.

        Args:
            strategy_id: Database ID of the strategy to run
            user_id: Database ID of the user
            initial_capital: Starting capital in USD
            slippage_bps: Slippage in basis points (100 = 1%)

        Returns:
            Session ID
        """
        async with await self.db_session_factory() as db_session:
            # Load strategy from database
            strategy_repo = StrategyRepository(db_session)
            strategy_model = await strategy_repo.get_by_id(strategy_id)
            if not strategy_model:
                raise ValueError(f"Strategy {strategy_id} not found")

            # Parse DSL JSON to Strategy object
            strategy = parse_strategy(strategy_model.dsl_json)

            # Create database record
            paper_repo = PaperTradingRepository(db_session)
            db_session_record = await paper_repo.create_session(
                strategy_id=strategy_id,
                user_id=user_id,
                initial_capital=initial_capital,
                polling_interval_seconds=self.default_polling_interval,
            )
            await db_session.commit()
            session_id = db_session_record.id

        # Create in-memory session
        session = PaperTradingSession(
            session_id=session_id,
            strategy=strategy,
            initial_capital=initial_capital,
            slippage_bps=slippage_bps,
        )
        self._sessions[session_id] = session

        logger.info(f"Started paper trading session {session_id} for strategy {strategy_id}")
        return session_id

    async def stop_session(self, session_id: int) -> bool:
        """
        Stop a paper trading session.

        Args:
            session_id: Session to stop

        Returns:
            True if session was stopped, False if not found
        """
        if session_id not in self._sessions:
            return False

        # Remove from active sessions
        del self._sessions[session_id]

        # Update database
        async with await self.db_session_factory() as db_session:
            paper_repo = PaperTradingRepository(db_session)
            await paper_repo.stop_session(session_id)
            await db_session.commit()

        logger.info(f"Stopped paper trading session {session_id}")
        return True

    async def pause_session(self, session_id: int) -> bool:
        """Pause a session (keeps in memory but skips ticks)."""
        if session_id not in self._sessions:
            return False

        async with await self.db_session_factory() as db_session:
            paper_repo = PaperTradingRepository(db_session)
            await paper_repo.pause_session(session_id)
            await db_session.commit()

        # Remove from active processing
        del self._sessions[session_id]
        logger.info(f"Paused paper trading session {session_id}")
        return True

    async def resume_session(self, session_id: int) -> bool:
        """Resume a paused session."""
        async with await self.db_session_factory() as db_session:
            paper_repo = PaperTradingRepository(db_session)
            db_session_record = await paper_repo.get_with_positions(session_id)

            if not db_session_record or db_session_record.status != "paused":
                return False

            # Load strategy
            strategy_repo = StrategyRepository(db_session)
            strategy_model = await strategy_repo.get_by_id(db_session_record.strategy_id)
            if not strategy_model:
                return False

            strategy = parse_strategy(strategy_model.dsl_json)

            # Reconstruct in-memory session
            session = PaperTradingSession(
                session_id=session_id,
                strategy=strategy,
                initial_capital=db_session_record.initial_capital,
            )
            # Restore cash balance
            session.cash_balance = db_session_record.cash_balance

            # Restore positions
            for pos in db_session_record.positions:
                session.positions[pos.token] = LivePosition(
                    token=pos.token,
                    quantity=pos.quantity,
                    avg_entry_price=pos.avg_entry_price,
                    total_cost=pos.total_cost,
                )

            self._sessions[session_id] = session

            # Update status in database
            await paper_repo.resume_session(session_id)
            await db_session.commit()

        logger.info(f"Resumed paper trading session {session_id}")
        return True

    async def get_session_status(self, session_id: int) -> dict | None:
        """Get status of a session."""
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]

        # Fetch current prices for accurate valuation
        tokens = list(session.strategy.tokens)
        prices = await self._fetch_prices(tokens)

        return session.get_status(prices)

    async def _fetch_prices(self, tokens: list[str]) -> dict[str, float]:
        """Fetch current prices for all tokens."""
        prices = {}
        price_ticks = await self.data_source.get_prices(tokens)
        for token, tick in price_ticks.items():
            prices[token] = tick.price
        return prices

    async def _process_tick(self) -> dict[int, list[LiveTrade]]:
        """
        Process one tick across all active sessions.

        Returns:
            Dict mapping session_id to list of trades executed
        """
        if not self._sessions:
            return {}

        # Collect all unique tokens across sessions
        all_tokens: set[str] = set()
        for session in self._sessions.values():
            all_tokens.update(session.strategy.tokens)

        # Fetch prices once
        prices = await self._fetch_prices(list(all_tokens))
        timestamp = datetime.now(timezone.utc)

        # Process each session
        all_trades: dict[int, list[LiveTrade]] = {}

        for session_id, session in list(self._sessions.items()):
            try:
                # Filter prices to just this session's tokens
                session_prices = {
                    token: price
                    for token, price in prices.items()
                    if token in session.strategy.tokens
                }

                trades = session.process_tick(session_prices, timestamp)
                all_trades[session_id] = trades

                # Persist state to database
                await self._persist_session_state(session_id, session, trades)

            except Exception as e:
                logger.error(f"Error processing tick for session {session_id}: {e}")

        return all_trades

    async def _persist_session_state(
        self,
        session_id: int,
        session: PaperTradingSession,
        trades: list[LiveTrade],
    ) -> None:
        """Persist session state to database after tick."""
        async with await self.db_session_factory() as db_session:
            paper_repo = PaperTradingRepository(db_session)

            # Update last tick timestamp
            await paper_repo.update_last_tick(session_id)

            # Update cash balance
            await paper_repo.update_cash_balance(session_id, session.cash_balance)

            # Record any new trades
            for trade in trades:
                await paper_repo.record_trade(
                    session_id=session_id,
                    trigger_id=trade.trigger_id,
                    token=trade.token,
                    action=trade.action,
                    quantity=trade.quantity,
                    price_at_exec=trade.price_at_exec,
                )

            # Update positions
            # First, get current DB positions to find ones we need to delete
            for token, position in session.positions.items():
                await paper_repo.upsert_position(
                    session_id=session_id,
                    token=token,
                    quantity=position.quantity,
                    avg_entry_price=position.avg_entry_price,
                    total_cost=position.total_cost,
                )

            # Delete positions that were fully sold
            db_record = await paper_repo.get_with_positions(session_id)
            if db_record:
                for db_pos in db_record.positions:
                    if db_pos.token not in session.positions:
                        await paper_repo.delete_position(session_id, db_pos.token)

            await db_session.commit()

    async def start_polling(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._polling_loop())
        logger.info("Started paper trading polling loop")

    async def stop_polling(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("Stopped paper trading polling loop")

    async def _polling_loop(self) -> None:
        """Main polling loop that runs in the background."""
        while self._running:
            try:
                if self._sessions:
                    trades = await self._process_tick()
                    total_trades = sum(len(t) for t in trades.values())
                    if total_trades > 0:
                        logger.info(
                            f"Processed tick: {total_trades} trades across {len(trades)} sessions"
                        )

            except Exception as e:
                logger.error(f"Error in polling loop: {e}")

            # Wait for next tick
            await asyncio.sleep(self.default_polling_interval)

    async def load_active_sessions(self) -> int:
        """
        Load all active sessions from database on startup.

        Returns:
            Number of sessions loaded
        """
        async with await self.db_session_factory() as db_session:
            paper_repo = PaperTradingRepository(db_session)
            strategy_repo = StrategyRepository(db_session)

            active_sessions = await paper_repo.get_active_sessions()

            for db_session_record in active_sessions:
                try:
                    # Load strategy
                    strategy_model = await strategy_repo.get_by_id(db_session_record.strategy_id)
                    if not strategy_model:
                        logger.warning(
                            f"Strategy {db_session_record.strategy_id} not found "
                            f"for session {db_session_record.id}"
                        )
                        continue

                    strategy = parse_strategy(strategy_model.dsl_json)

                    # Reconstruct in-memory session
                    session = PaperTradingSession(
                        session_id=db_session_record.id,
                        strategy=strategy,
                        initial_capital=db_session_record.initial_capital,
                    )
                    session.cash_balance = db_session_record.cash_balance

                    # Restore positions
                    for pos in db_session_record.positions:
                        session.positions[pos.token] = LivePosition(
                            token=pos.token,
                            quantity=pos.quantity,
                            avg_entry_price=pos.avg_entry_price,
                            total_cost=pos.total_cost,
                        )

                    self._sessions[db_session_record.id] = session
                    logger.info(f"Loaded session {db_session_record.id}")

                except Exception as e:
                    logger.error(f"Error loading session {db_session_record.id}: {e}")

        return len(self._sessions)

    async def close(self) -> None:
        """Clean shutdown of the manager."""
        await self.stop_polling()
        await self.data_source.close()
        self._sessions.clear()
