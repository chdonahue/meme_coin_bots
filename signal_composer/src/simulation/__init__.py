"""Simulation engine for paper trading."""

from .portfolio import Portfolio, Position, InsufficientFundsError, InsufficientPositionError
from .executor import PaperTradeExecutor, TradeRecord
from .metrics import PerformanceCalculator, PerformanceSnapshot
from .backtest import BacktestEngine, BacktestResult
from .persistence import SimulationPersistence

__all__ = [
    "Portfolio",
    "Position",
    "InsufficientFundsError",
    "InsufficientPositionError",
    "PaperTradeExecutor",
    "TradeRecord",
    "PerformanceCalculator",
    "PerformanceSnapshot",
    "BacktestEngine",
    "BacktestResult",
    "SimulationPersistence",
]
