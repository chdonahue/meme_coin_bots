"""Paper trading schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    """Request to start a paper trading session."""

    strategy_id: int
    initial_capital: float = Field(default=10000.0, ge=100.0)
    slippage_bps: int = Field(default=100, ge=0, le=1000)


class StartSessionResponse(BaseModel):
    """Response after starting a session."""

    session_id: int
    strategy_id: int
    initial_capital: float
    status: str


class SessionStatusResponse(BaseModel):
    """Current status of a paper trading session."""

    session_id: int
    initial_capital: float
    cash_balance: float
    total_value: float
    pnl_pct: float
    positions: dict[str, dict]
    trade_count: int


class PositionResponse(BaseModel):
    """Position details."""

    token: str
    quantity: float
    avg_entry_price: float
    current_value: float
    pnl_pct: float


class TradeResponse(BaseModel):
    """Trade record."""

    id: int
    trigger_id: str
    token: str
    action: str
    quantity: float
    price_at_exec: float
    timestamp: datetime


class SessionListItem(BaseModel):
    """Summary of a session for listing."""

    id: int
    strategy_id: int
    status: str
    initial_capital: float
    cash_balance: float
    started_at: datetime
    last_tick_at: datetime | None


class StopSessionResponse(BaseModel):
    """Response after stopping a session."""

    session_id: int
    status: str
    message: str
