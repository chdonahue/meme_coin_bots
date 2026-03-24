# signal_composer/tests/test_integration.py
"""Integration tests for the core engine."""
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestCoreEngineIntegration:
    """Test the full flow from parsing to execution."""

    def test_full_strategy_flow(self, sample_strategy_json):
        """Test: parse -> validate -> build executor -> evaluate."""
        from engine.dsl.parser import parse_strategy
        from engine.dsl.validator import validate_strategy
        from engine.dsl.executor import StrategyExecutor

        # Parse
        strategy = parse_strategy(sample_strategy_json)
        assert strategy.id == "test_strategy_001"

        # Validate
        errors = validate_strategy(strategy)
        assert errors == []

        # Execute
        executor = StrategyExecutor(strategy)

        # Trigger should fire (price_change_pct of -10 is < -5)
        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}
        actions = executor.evaluate(market_data)
        assert len(actions) == 1
        assert actions[0].action.type.value == "buy"

        # Trigger should NOT fire (price_change_pct of -2 is NOT < -5)
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}
        actions = executor.evaluate(market_data)
        assert len(actions) == 0

    def test_strategy_with_derived_streams(self):
        """Test strategy using derived streams (MA crossover)."""
        from engine.dsl.parser import parse_strategy
        from engine.dsl.validator import validate_strategy
        from engine.dsl.executor import StrategyExecutor

        strategy_json = {
            "id": "ma_crossover",
            "name": "MA Crossover",
            "description": "Golden cross strategy",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [
                {"id": "sol_ma_4h", "type": "moving_average", "token": "SOL", "window": "4h"},
                {"id": "sol_ma_48h", "type": "moving_average", "token": "SOL", "window": "1d"},
            ],
            "triggers": [
                {
                    "id": "golden_cross",
                    "when": {
                        "metric": "sol_ma_4h",
                        "op": "crosses_above",
                        "compare_to": "sol_ma_48h",
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 30},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 5,
                "slippage_limit_bps": 200,
            },
        }

        strategy = parse_strategy(strategy_json)
        errors = validate_strategy(strategy)
        assert errors == []

        executor = StrategyExecutor(strategy)

        # Golden cross scenario
        market_data = {
            "_derived": {
                "sol_ma_4h": {"current": 150.0, "previous": 145.0},
                "sol_ma_48h": {"current": 148.0, "previous": 147.0},
            }
        }
        actions = executor.evaluate(market_data)
        assert len(actions) == 1
        assert actions[0].trigger_id == "golden_cross"

    def test_derived_stream_calculations(self):
        """Test derived stream calculator."""
        from engine.streams.derived import (
            moving_average,
            ema,
            rsi,
            volatility,
        )

        prices = [100, 102, 98, 105, 103, 107, 110, 108, 112, 115]

        ma = moving_average(prices, window=5)
        assert ma is not None
        assert 105 < ma < 115  # Recent average

        ema_val = ema(prices, window=5)
        assert ema_val is not None
        assert ema_val > ma  # EMA weighted toward recent

        rsi_val = rsi(prices + [118, 120, 122, 125, 127], periods=14)
        assert rsi_val is not None
        assert rsi_val > 50  # Uptrend

        vol = volatility(prices)
        assert vol > 0  # Some variance
