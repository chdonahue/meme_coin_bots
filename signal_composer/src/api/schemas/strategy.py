"""Strategy schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyCreate(BaseModel):
    """Create a new strategy."""

    name: str
    description: str = ""
    dsl: dict[str, Any]
    is_public: bool = False


class StrategyUpdate(BaseModel):
    """Update an existing strategy."""

    name: str | None = None
    description: str | None = None
    dsl: dict[str, Any] | None = None
    is_public: bool | None = None
    status: str | None = None


class StrategyResponse(BaseModel):
    """Strategy details."""

    id: int
    external_id: str
    name: str
    description: str
    dsl: dict[str, Any] = Field(validation_alias="dsl_json")
    is_public: bool
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BacktestRequest(BaseModel):
    """Backtest parameters."""

    days: int = 30
    initial_capital: float = 10000.0
    slippage_bps: int = 100
    use_real_data: bool = True


class BacktestResponse(BaseModel):
    """Backtest results."""

    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    trade_count: int
    win_rate: float | None
    equity_curve: list[float]
    saved: bool
    data_source: str = "synthetic"
