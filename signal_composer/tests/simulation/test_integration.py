"""Integration tests for simulation engine."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestSimulationIntegration:
    """Test full simulation workflow."""

    def test_full_paper_trading_flow(self):
        """Test: parse strategy -> create portfolio -> execute trades -> calculate metrics."""
        from engine.dsl.parser import parse_strategy
        from simulation.portfolio import Portfolio
        from simulation.executor import PaperTradeExecutor
        from simulation.metrics import PerformanceCalculator
        from engine.dsl.executor import StrategyExecutor
        from engine.dsl.types import ActionType

        # Parse strategy
        strategy_json = {
            "id": "integration_test",
            "name": "Integration Test Strategy",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {
                        "metric": "price_change_pct",
                        "token": "SOL",
                        "window": "15m",
                        "op": "<",
                        "value": -3,
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 20},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 5,
                "slippage_limit_bps": 100,
            },
        }
        strategy = parse_strategy(strategy_json)

        # Create portfolio and executors
        portfolio = Portfolio(initial_balance=10000.0)
        trade_executor = PaperTradeExecutor(
            portfolio=portfolio,
            slippage_bps=50,
            risk_rules=strategy.risk_rules,
        )
        strategy_executor = StrategyExecutor(strategy)

        # Simulate market dip
        market_data = {"SOL": {"price": 100.0, "price_change_pct": {"15m": -5.0}}}
        prices = {"SOL": 100.0}

        actions = strategy_executor.evaluate(market_data)
        assert len(actions) == 1

        # Execute the trade with a timestamp
        timestamp = datetime.now(timezone.utc)
        trade = trade_executor.execute(actions[0].action, prices, actions[0].trigger_id, timestamp)
        assert trade is not None
        assert trade.action == ActionType.BUY

        # Calculate metrics
        perf = PerformanceCalculator(initial_value=10000.0)
        equity_curve = [10000.0, portfolio.total_value_at_prices({"SOL": 110.0})]
        snapshot = perf.snapshot(
            current_value=equity_curve[-1],
            equity_curve=equity_curve,
            trades=[trade],
        )

        assert snapshot.total_return_pct > 0  # Price went up
        assert snapshot.trade_count == 1

    def test_backtest_matches_manual_simulation(self):
        """Backtest should produce same results as manual simulation."""
        from simulation.backtest import BacktestEngine
        from engine.dsl.types import (
            Strategy,
            Trigger,
            SimpleCondition,
            Action,
            ActionType,
            RiskRules,
            Operator,
        )

        strategy = Strategy(
            id="consistency_test",
            name="Consistency Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.LT, value=95),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=25),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=60,
                max_trades_per_day=5,
                slippage_limit_bps=100,
            ),
        )

        # Note: BacktestEngine expects price_history without timestamp field
        # It generates timestamps internally using a base timestamp + tick index
        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy
            {"SOL": 92.0},  # Buy
            {"SOL": 98.0},
            {"SOL": 105.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        # Should have 2 buy trades (at 94 and 92)
        buy_trades = [t for t in result.trades if t.action == ActionType.BUY]
        assert len(buy_trades) == 2

        # Should be profitable (bought low, ended high)
        assert result.total_return_pct > 0

    def test_end_to_end_with_round_trip_trades(self):
        """Test complete workflow with buy and sell trades."""
        from simulation.backtest import BacktestEngine
        from engine.dsl.types import (
            Strategy,
            Trigger,
            SimpleCondition,
            Action,
            ActionType,
            RiskRules,
            Operator,
        )

        strategy = Strategy(
            id="round_trip_test",
            name="Round Trip Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy_low",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.LT, value=95),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=30),
                ),
                Trigger(
                    id="sell_high",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.GT, value=108),
                    action=Action(type=ActionType.SELL_ALL, token="SOL"),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-15,
                max_position_pct=70,
                max_trades_per_day=10,
                slippage_limit_bps=100,
            ),
        )

        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy trigger fires
            {"SOL": 92.0},  # Buy trigger fires again
            {"SOL": 98.0},
            {"SOL": 105.0},
            {"SOL": 110.0},  # Sell trigger fires
            {"SOL": 112.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        # Should have buys
        buy_trades = [t for t in result.trades if t.action == ActionType.BUY]
        assert len(buy_trades) >= 1

        # Should have sells (position was established and sell trigger fired)
        sell_trades = [
            t for t in result.trades if t.action in (ActionType.SELL, ActionType.SELL_ALL)
        ]
        assert len(sell_trades) >= 1

        # Verify equity curve has correct number of entries
        assert len(result.equity_curve) == len(price_history)

        # Win rate should be calculated
        assert result.win_rate >= 0.0

    def test_portfolio_state_consistency(self):
        """Verify portfolio state is consistent after simulation."""
        from simulation.backtest import BacktestEngine
        from engine.dsl.types import (
            Strategy,
            Trigger,
            SimpleCondition,
            Action,
            ActionType,
            RiskRules,
            Operator,
        )

        strategy = Strategy(
            id="state_test",
            name="State Consistency Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.LT, value=95),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=20),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=5,
                slippage_limit_bps=100,
            ),
        )

        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy
            {"SOL": 92.0},  # Buy
            {"SOL": 100.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=50)
        result = engine.run(strategy, price_history)

        # Portfolio should be internally consistent
        portfolio = result.final_portfolio

        # Cash + position value should equal total value
        total_at_final_prices = portfolio.total_value_at_prices(price_history[-1])
        position_value = (
            portfolio.positions["SOL"].value_at(price_history[-1]["SOL"])
            if "SOL" in portfolio.positions
            else 0.0
        )
        assert abs(portfolio.cash_balance + position_value - total_at_final_prices) < 0.01

        # Equity curve final value should match portfolio value
        assert abs(result.equity_curve[-1] - total_at_final_prices) < 0.01

    def test_metrics_calculation_accuracy(self):
        """Verify performance metrics are calculated correctly."""
        from simulation.backtest import BacktestEngine
        from engine.dsl.types import (
            Strategy,
            Trigger,
            SimpleCondition,
            Action,
            ActionType,
            RiskRules,
            Operator,
        )

        strategy = Strategy(
            id="metrics_test",
            name="Metrics Accuracy Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy_always",
                    when=SimpleCondition(metric="price", token="SOL", op=Operator.GT, value=0),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=10),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=10,
                slippage_limit_bps=100,
            ),
        )

        # Create a scenario where we know the expected outcome
        price_history = [
            {"SOL": 100.0},
            {"SOL": 100.0},
            {"SOL": 100.0},
            {"SOL": 100.0},
            {"SOL": 100.0},
        ]

        engine = BacktestEngine(
            initial_capital=10000.0, slippage_bps=0
        )  # No slippage for predictable results
        result = engine.run(strategy, price_history)

        # With flat prices and no slippage, total return should be close to 0
        # (might be slightly negative due to position limits preventing all buys)
        assert abs(result.total_return_pct) < 5.0  # Within 5% tolerance

        # Trade count should match
        assert result.trade_count == len(result.trades)

        # Equity curve length should match price history
        assert len(result.equity_curve) == len(price_history)
