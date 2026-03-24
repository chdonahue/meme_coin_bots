"""Tests for DSL type definitions."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.types import Strategy


class TestStrategyType:
    def test_valid_strategy_parses(self, sample_strategy_json):
        strategy = Strategy.model_validate(sample_strategy_json)

        assert strategy.id == "test_strategy_001"
        assert strategy.name == "Test Strategy"
        assert len(strategy.triggers) == 1
        assert strategy.risk_rules.stop_loss_pct == -15

    def test_missing_required_field_raises(self):
        invalid_json = {"id": "test", "name": "Test"}  # missing required fields

        with pytest.raises(ValidationError):
            Strategy.model_validate(invalid_json)

    def test_invalid_operator_raises(self, sample_strategy_json):
        sample_strategy_json["triggers"][0]["when"]["op"] = "INVALID"

        with pytest.raises(ValidationError):
            Strategy.model_validate(sample_strategy_json)
