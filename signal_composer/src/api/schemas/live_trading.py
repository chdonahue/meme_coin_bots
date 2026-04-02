"""Pydantic schemas for live trading API."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    """Request to start a live trading session."""

    strategy_id: int
    wallet_address: str = Field(..., min_length=32, max_length=44)
    max_trade_usd: Decimal = Field(default=Decimal("500"), ge=Decimal("0"))
    max_daily_usd: Decimal = Field(default=Decimal("2000"), ge=Decimal("0"))
    max_daily_loss_usd: Decimal = Field(default=Decimal("500"), ge=Decimal("0"))


class SessionResponse(BaseModel):
    """Response with session details."""

    id: int
    strategy_id: int
    wallet_address: str
    status: str
    started_at: datetime
    total_value_usd: float | None = None
    daily_pnl_usd: float | None = None
    pending_txs: int = 0


class SessionListResponse(BaseModel):
    """Response with list of sessions."""

    sessions: list[SessionResponse]


class TransactionResponse(BaseModel):
    """Response with transaction details."""

    id: str
    trigger_id: str
    action_type: str
    state: str
    token_address: str
    tx_signature: str | None = None
    created_at: datetime


class StopSessionResponse(BaseModel):
    """Response after stopping a session."""

    session_id: int
    status: str
    message: str


class EmergencyStopResponse(BaseModel):
    """Response after emergency stop."""

    stopped_sessions: int
    message: str
