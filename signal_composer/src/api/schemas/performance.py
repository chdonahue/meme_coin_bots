"""Performance schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PerformanceResponse(BaseModel):
    """Performance snapshot."""

    id: int
    date: datetime
    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    trade_count: int
    win_rate: float | None

    model_config = ConfigDict(from_attributes=True)
