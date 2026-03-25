"""SQLAlchemy models for SignalComposer."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
    Index,
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


class Strategy(Base):
    """Trading strategy."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
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
