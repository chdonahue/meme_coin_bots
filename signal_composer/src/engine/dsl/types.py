"""Pydantic models for Strategy DSL."""

from enum import Enum
from typing import Literal, Union
from pydantic import BaseModel, Field


class Operator(str, Enum):
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    EQ = "=="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class Window(str, Enum):
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    ONE_HOUR = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY = "1d"


class ActionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    SELL_ALL = "sell_all"


class SimpleCondition(BaseModel):
    """A single condition comparing a metric to a value."""

    metric: str
    token: str | None = None
    window: Window | None = None
    op: Operator
    value: float | None = None
    compare_to: str | None = None  # For comparing to another metric/stream


class AllCondition(BaseModel):
    """All conditions must be true (AND)."""

    all: list["Condition"]


class AnyCondition(BaseModel):
    """Any condition must be true (OR)."""

    any: list["Condition"]


class NotCondition(BaseModel):
    """Negate a condition."""

    not_: "Condition" = Field(alias="not")


# Union of all condition types
Condition = Union[SimpleCondition, AllCondition, AnyCondition, NotCondition]

# Update forward refs after Condition is defined
AllCondition.model_rebuild()
AnyCondition.model_rebuild()
NotCondition.model_rebuild()


class Action(BaseModel):
    """Action to take when trigger fires."""

    type: ActionType
    token: str
    amount_pct: float | None = None
    amount_fixed: float | None = None


class Trigger(BaseModel):
    """A trigger that fires an action when conditions are met."""

    id: str
    when: Condition
    action: Action


class DerivedStreamType(str, Enum):
    MOVING_AVERAGE = "moving_average"
    EMA = "ema"
    RSI = "rsi"
    VOLATILITY = "volatility"
    PRICE_DELTA = "price_delta"


class DerivedStream(BaseModel):
    """A computed metric derived from raw data."""

    id: str
    name: str | None = None
    type: DerivedStreamType
    token: str
    metric: str = "price"
    window: Window | None = None
    periods: int | None = None  # For RSI


class RiskRules(BaseModel):
    """Mandatory risk management rules."""

    stop_loss_pct: float
    max_position_pct: float
    max_trades_per_day: int
    slippage_limit_bps: int


class Strategy(BaseModel):
    """Complete strategy definition."""

    id: str
    name: str
    description: str = ""
    version: int = 1
    tokens: list[str]
    derived_streams: list[DerivedStream] = Field(default_factory=list)
    triggers: list[Trigger]
    risk_rules: RiskRules
