"""SQLAlchemy models for SignalComposer."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="creator")
    trading_wallets: Mapped[list["TradingWallet"]] = relationship(back_populates="user")


class TradingWallet(Base):
    """Trading wallet with encrypted private key."""

    __tablename__ = "trading_wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    address: Mapped[str] = mapped_column(String(44), unique=True)
    encrypted_private_key: Mapped[bytes] = mapped_column(LargeBinary)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="trading_wallets")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="wallet")


class Strategy(Base):
    """Trading strategy."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    wallet_id: Mapped[int | None] = mapped_column(ForeignKey("trading_wallets.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    dsl_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, active, paused
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    creator: Mapped["User"] = relationship(back_populates="strategies")
    wallet: Mapped["TradingWallet | None"] = relationship(back_populates="strategies")
    performance: Mapped[list["StrategyPerformance"]] = relationship(back_populates="strategy")
    trades: Mapped[list["PaperTrade"]] = relationship(back_populates="strategy")


class StrategyPerformance(Base):
    """Daily performance snapshots."""

    __tablename__ = "strategy_performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="performance")

    __table_args__ = (Index("ix_perf_strategy_date", "strategy_id", "date", unique=True),)


class PaperTrade(Base):
    """Simulated trade record."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    trigger_id: Mapped[str] = mapped_column(String(50))
    token: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(10))  # buy, sell, sell_all
    amount: Mapped[float] = mapped_column(Float)
    price_at_exec: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="trades")


class PaperTradingSession(Base):
    """Live paper trading session."""

    __tablename__ = "paper_trading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # Session state
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, paused, stopped
    initial_capital: Mapped[float] = mapped_column(Float, default=10000.0)
    cash_balance: Mapped[float] = mapped_column(Float, default=10000.0)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Config
    polling_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)

    # Relationships
    positions: Mapped[list["PaperTradingPosition"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    session_trades: Mapped[list["PaperTradingSessionTrade"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PaperTradingPosition(Base):
    """Current position in a paper trading session."""

    __tablename__ = "paper_trading_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    session: Mapped["PaperTradingSession"] = relationship(back_populates="positions")

    __table_args__ = (Index("ix_paper_position_session_token", "session_id", "token", unique=True),)


class PaperTradingSessionTrade(Base):
    """Trade executed in a paper trading session."""

    __tablename__ = "paper_trading_session_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"), index=True
    )
    trigger_id: Mapped[str] = mapped_column(String(50))
    token: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(10))  # buy, sell, sell_all
    quantity: Mapped[float] = mapped_column(Float)
    price_at_exec: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    session: Mapped["PaperTradingSession"] = relationship(back_populates="session_trades")


class PriceData(Base):
    """Time-series price data."""

    __tablename__ = "price_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20))

    __table_args__ = (Index("ix_price_token_time", "token", "timestamp"),)


class Portfolio(Base):
    """User's portfolio investment in a strategy."""

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    shares_owned: Mapped[float] = mapped_column(Float, default=0.0)
    entry_value: Mapped[float] = mapped_column(Float, default=0.0)  # Total invested
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("ix_portfolio_user_strategy", "user_id", "strategy_id", unique=True),)


class LiveTradingSessionModel(Base):
    """Live trading session model.

    Note: Uses 'Model' suffix to distinguish from the domain class LiveTradingSession
    in live_trading/session.py, which is a runtime session manager. This class represents
    the persistent database record.
    """

    __tablename__ = "live_trading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    wallet_address: Mapped[str] = mapped_column(String(44), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running")

    # Safety config
    max_trade_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=500)
    max_daily_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=2000)
    max_daily_loss_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=500)

    # Circuit breaker
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_breaker_tripped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Tracking
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Daily counters
    daily_volume_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    daily_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    daily_reset_date: Mapped[date] = mapped_column(Date, default=date.today)

    # Relationships
    transactions: Mapped[list["LiveTransactionModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class LiveTransactionModel(Base):
    """Live transaction record.

    Note: Uses 'Model' suffix to maintain consistent naming pattern with LiveTradingSessionModel
    and to be explicit that this is a database model (vs domain/runtime transaction objects).
    """

    __tablename__ = "live_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    session_id: Mapped[int] = mapped_column(
        ForeignKey("live_trading_sessions.id", ondelete="CASCADE"), index=True
    )
    trigger_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    token_address: Mapped[str] = mapped_column(String(44), nullable=False)

    # State
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    state_history: Mapped[list] = mapped_column(JSON, default=list)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Quote data
    quote_input_mint: Mapped[str | None] = mapped_column(String(44), nullable=True)
    quote_output_mint: Mapped[str | None] = mapped_column(String(44), nullable=True)
    quote_amount_in: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quote_expected_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quote_price_impact_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quote_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Execution
    tx_signature: Mapped[str | None] = mapped_column(String(88), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_amount_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_lamports: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    session: Mapped["LiveTradingSessionModel"] = relationship(back_populates="transactions")
