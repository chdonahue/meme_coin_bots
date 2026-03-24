import pytest
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestConditionEvaluator:
    def test_simple_less_than_true(self):
        from engine.dsl.executor import ConditionEvaluator
        from engine.dsl.types import SimpleCondition, Operator, Window

        evaluator = ConditionEvaluator()

        condition = SimpleCondition(
            metric="price_change_pct",
            token="SOL",
            window=Window.FIFTEEN_MIN,
            op=Operator.LT,
            value=-5.0,
        )

        # Price dropped 10%
        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}

        result = evaluator.evaluate(condition, market_data)
        assert result is True

    def test_simple_less_than_false(self):
        from engine.dsl.executor import ConditionEvaluator
        from engine.dsl.types import SimpleCondition, Operator, Window

        evaluator = ConditionEvaluator()

        condition = SimpleCondition(
            metric="price_change_pct",
            token="SOL",
            window=Window.FIFTEEN_MIN,
            op=Operator.LT,
            value=-5.0,
        )

        # Price dropped only 2%
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}

        result = evaluator.evaluate(condition, market_data)
        assert result is False

    def test_all_condition(self):
        from engine.dsl.executor import ConditionEvaluator
        from engine.dsl.types import SimpleCondition, AllCondition, Operator, Window

        evaluator = ConditionEvaluator()

        condition = AllCondition(
            all=[
                SimpleCondition(
                    metric="price_change_pct",
                    token="SOL",
                    window=Window.FIFTEEN_MIN,
                    op=Operator.LT,
                    value=-5.0,
                ),
                SimpleCondition(
                    metric="volume",
                    token="SOL",
                    window=Window.FIFTEEN_MIN,
                    op=Operator.GT,
                    value=1000000,
                ),
            ]
        )

        market_data = {
            "SOL": {
                "price_change_pct": {"15m": -10.0},
                "volume": {"15m": 2000000},
            }
        }

        result = evaluator.evaluate(condition, market_data)
        assert result is True

    def test_any_condition(self):
        from engine.dsl.executor import ConditionEvaluator
        from engine.dsl.types import SimpleCondition, AnyCondition, Operator, Window

        evaluator = ConditionEvaluator()

        condition = AnyCondition(
            any=[
                SimpleCondition(
                    metric="price_change_pct",
                    token="SOL",
                    window=Window.FIFTEEN_MIN,
                    op=Operator.LT,
                    value=-5.0,
                ),
                SimpleCondition(
                    metric="price_change_pct",
                    token="SOL",
                    window=Window.FIFTEEN_MIN,
                    op=Operator.GT,
                    value=5.0,
                ),
            ]
        )

        # Only first condition is true
        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}

        result = evaluator.evaluate(condition, market_data)
        assert result is True

    def test_compare_to_derived_stream(self):
        from engine.dsl.executor import ConditionEvaluator
        from engine.dsl.types import SimpleCondition, Operator

        evaluator = ConditionEvaluator()

        condition = SimpleCondition(
            metric="sol_ma_4h",
            op=Operator.CROSSES_ABOVE,
            compare_to="sol_ma_48h",
        )

        # Current: 4h MA crossed above 48h MA
        market_data = {
            "_derived": {
                "sol_ma_4h": {"current": 150.0, "previous": 145.0},
                "sol_ma_48h": {"current": 148.0, "previous": 147.0},
            }
        }

        result = evaluator.evaluate(condition, market_data)
        assert result is True


class TestStrategyExecutor:
    def test_evaluate_triggers(self, sample_strategy_json):
        from engine.dsl.parser import parse_strategy
        from engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 1
        assert actions[0].action.type.value == "buy"
        assert actions[0].action.token == "SOL"

    def test_no_triggers_fire(self, sample_strategy_json):
        from engine.dsl.parser import parse_strategy
        from engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        # Price didn't drop enough
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 0
