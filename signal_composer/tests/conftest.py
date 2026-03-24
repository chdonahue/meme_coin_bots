# signal_composer/tests/conftest.py
import pytest


@pytest.fixture
def sample_strategy_json():
    """Minimal valid strategy JSON for testing."""
    return {
        "id": "test_strategy_001",
        "name": "Test Strategy",
        "description": "A test strategy",
        "version": 1,
        "tokens": ["SOL"],
        "derived_streams": [],
        "triggers": [
            {
                "id": "buy_trigger",
                "when": {
                    "metric": "price_change_pct",
                    "token": "SOL",
                    "window": "15m",
                    "op": "<",
                    "value": -5,
                },
                "action": {"type": "buy", "token": "SOL", "amount_pct": 25},
            }
        ],
        "risk_rules": {
            "stop_loss_pct": -15,
            "max_position_pct": 40,
            "max_trades_per_day": 10,
            "slippage_limit_bps": 300,
        },
    }
