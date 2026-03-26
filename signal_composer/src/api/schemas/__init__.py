"""API schemas (Pydantic models)."""

from .auth import ChallengeRequest, ChallengeResponse, VerifyRequest, TokenResponse
from .strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    BacktestRequest,
    BacktestResponse,
)
from .performance import PerformanceResponse
from .trade import TradeResponse, PaginatedTradesResponse
from .common import ErrorResponse

__all__ = [
    "ChallengeRequest",
    "ChallengeResponse",
    "VerifyRequest",
    "TokenResponse",
    "StrategyCreate",
    "StrategyUpdate",
    "StrategyResponse",
    "BacktestRequest",
    "BacktestResponse",
    "PerformanceResponse",
    "TradeResponse",
    "PaginatedTradesResponse",
    "ErrorResponse",
]
