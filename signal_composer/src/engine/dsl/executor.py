"""Execute strategy triggers against market data."""

from dataclasses import dataclass
from typing import Any

from .types import (
    Strategy,
    Trigger,
    Action,
    Condition,
    SimpleCondition,
    AllCondition,
    AnyCondition,
    NotCondition,
    Operator,
)


@dataclass
class TriggeredAction:
    """An action that was triggered."""

    trigger_id: str
    action: Action


class ConditionEvaluator:
    """Evaluate conditions against market data."""

    def evaluate(self, condition: Condition, market_data: dict[str, Any]) -> bool:
        """
        Evaluate a condition.

        Args:
            condition: Condition to evaluate
            market_data: Market data in format:
                {
                    "TOKEN": {
                        "metric_name": {"window": value}
                    },
                    "_derived": {
                        "stream_id": {"current": value, "previous": value}
                    }
                }

        Returns:
            True if condition is met
        """
        if isinstance(condition, SimpleCondition):
            return self._evaluate_simple(condition, market_data)
        elif isinstance(condition, AllCondition):
            return all(self.evaluate(c, market_data) for c in condition.all)
        elif isinstance(condition, AnyCondition):
            return any(self.evaluate(c, market_data) for c in condition.any)
        elif isinstance(condition, NotCondition):
            return not self.evaluate(condition.not_, market_data)
        return False

    def _evaluate_simple(self, condition: SimpleCondition, market_data: dict[str, Any]) -> bool:
        """Evaluate a simple condition."""
        # Get the value to compare
        left_value = self._get_metric_value(
            condition.metric,
            condition.token,
            condition.window.value if condition.window else None,
            market_data,
        )

        if left_value is None:
            return False

        # Get comparison value
        if condition.compare_to:
            right_value = self._get_derived_current(condition.compare_to, market_data)
            if right_value is None:
                return False
        else:
            right_value = condition.value

        if right_value is None:
            return False

        # Handle crosses_above/crosses_below
        if condition.op in (Operator.CROSSES_ABOVE, Operator.CROSSES_BELOW):
            return self._evaluate_cross(
                condition.metric,
                condition.compare_to,
                condition.op,
                market_data,
            )

        # Standard comparisons
        return self._compare(left_value, condition.op, right_value)

    def _get_metric_value(
        self,
        metric: str,
        token: str | None,
        window: str | None,
        market_data: dict[str, Any],
    ) -> float | None:
        """Get a metric value from market data."""
        # Check if it's a derived stream
        if "_derived" in market_data and metric in market_data["_derived"]:
            return market_data["_derived"][metric].get("current")

        # Otherwise it's a token metric
        if token is None:
            return None

        token_data = market_data.get(token, {})
        metric_data = token_data.get(metric, {})

        if isinstance(metric_data, dict) and window:
            return metric_data.get(window)
        elif isinstance(metric_data, (int, float)):
            return metric_data

        return None

    def _get_derived_current(self, stream_id: str, market_data: dict[str, Any]) -> float | None:
        """Get current value of a derived stream."""
        derived = market_data.get("_derived", {})
        stream_data = derived.get(stream_id, {})
        return stream_data.get("current")

    def _evaluate_cross(
        self,
        left_metric: str,
        right_metric: str | None,
        op: Operator,
        market_data: dict[str, Any],
    ) -> bool:
        """Evaluate crosses_above or crosses_below."""
        if right_metric is None:
            return False

        derived = market_data.get("_derived", {})
        left_data = derived.get(left_metric, {})
        right_data = derived.get(right_metric, {})

        left_current = left_data.get("current")
        left_previous = left_data.get("previous")
        right_current = right_data.get("current")
        right_previous = right_data.get("previous")

        if None in (left_current, left_previous, right_current, right_previous):
            return False

        if op == Operator.CROSSES_ABOVE:
            # Was below or equal, now above
            return left_previous <= right_previous and left_current > right_current
        else:  # CROSSES_BELOW
            # Was above or equal, now below
            return left_previous >= right_previous and left_current < right_current

    def _compare(self, left: float, op: Operator, right: float) -> bool:
        """Perform comparison."""
        match op:
            case Operator.GT:
                return left > right
            case Operator.LT:
                return left < right
            case Operator.GTE:
                return left >= right
            case Operator.LTE:
                return left <= right
            case Operator.EQ:
                return left == right
            case _:
                return False


class StrategyExecutor:
    """Execute a strategy against market data."""

    def __init__(self, strategy: Strategy):
        self.strategy = strategy
        self.condition_evaluator = ConditionEvaluator()

    def evaluate(self, market_data: dict[str, Any]) -> list[TriggeredAction]:
        """
        Evaluate all triggers and return actions for those that fire.

        Args:
            market_data: Current market state

        Returns:
            List of triggered actions
        """
        triggered = []

        for trigger in self.strategy.triggers:
            if self.condition_evaluator.evaluate(trigger.when, market_data):
                triggered.append(
                    TriggeredAction(
                        trigger_id=trigger.id,
                        action=trigger.action,
                    )
                )

        return triggered
