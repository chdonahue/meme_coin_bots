import pytest


class TestConditionEvaluator:
    def test_simple_less_than_true(self):
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, Operator, Window

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
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, Operator, Window

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
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, AllCondition, Operator, Window

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
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, AnyCondition, Operator, Window

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
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, Operator

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

    def test_not_condition(self):
        """Test NOT condition negates inner condition."""
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, NotCondition, Operator, Window

        evaluator = ConditionEvaluator()

        # NOT (price < -5) should be True when price is -2 (since -2 is NOT < -5)
        inner_condition = SimpleCondition(
            metric="price_change_pct",
            token="SOL",
            window=Window.FIFTEEN_MIN,
            op=Operator.LT,
            value=-5.0,
        )
        not_condition = NotCondition(**{"not": inner_condition})

        # Price dropped only 2% - inner condition is False, NOT makes it True
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}
        result = evaluator.evaluate(not_condition, market_data)
        assert result is True

        # Price dropped 10% - inner condition is True, NOT makes it False
        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}
        result = evaluator.evaluate(not_condition, market_data)
        assert result is False

    def test_crosses_below(self):
        """Test crosses_below operator."""
        from src.engine.dsl.executor import ConditionEvaluator
        from src.engine.dsl.types import SimpleCondition, Operator

        evaluator = ConditionEvaluator()

        condition = SimpleCondition(
            metric="sol_ma_4h",
            op=Operator.CROSSES_BELOW,
            compare_to="sol_ma_48h",
        )

        # 4h MA crossed below 48h MA (was above, now below)
        market_data = {
            "_derived": {
                "sol_ma_4h": {"current": 145.0, "previous": 150.0},
                "sol_ma_48h": {"current": 148.0, "previous": 147.0},
            }
        }

        result = evaluator.evaluate(condition, market_data)
        assert result is True

        # Did not cross (still above)
        market_data = {
            "_derived": {
                "sol_ma_4h": {"current": 155.0, "previous": 150.0},
                "sol_ma_48h": {"current": 148.0, "previous": 147.0},
            }
        }

        result = evaluator.evaluate(condition, market_data)
        assert result is False


class TestStrategyExecutor:
    def test_evaluate_triggers(self, sample_strategy_json):
        from src.engine.dsl.parser import parse_strategy
        from src.engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 1
        assert actions[0].action.type.value == "buy"
        assert actions[0].action.token == "SOL"

    def test_no_triggers_fire(self, sample_strategy_json):
        from src.engine.dsl.parser import parse_strategy
        from src.engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        # Price didn't drop enough
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 0
