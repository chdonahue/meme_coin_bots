"""Trade schemas."""

from datetime import datetime

from pydantic import BaseModel


class TradeResponse(BaseModel):
    """Trade record."""

    id: int
    trigger_id: str
    token: str
    action: str
    amount: float
    price_at_exec: float
    timestamp: datetime

    class Config:
        from_attributes = True


class PaginatedTradesResponse(BaseModel):
    """Paginated trade list."""

    items: list[TradeResponse]
    total: int
    page: int
    page_size: int
