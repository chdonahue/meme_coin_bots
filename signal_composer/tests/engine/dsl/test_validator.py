import pytest
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.parser import parse_strategy
from engine.dsl.validator import validate_strategy


class TestValidator:
    def test_valid_strategy_passes(self, sample_strategy_json):
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert errors == []

    def test_trigger_references_unknown_token(self, sample_strategy_json):
        sample_strategy_json["triggers"][0]["when"]["token"] = "UNKNOWN"
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) == 1
        assert "UNKNOWN" in errors[0]

    def test_derived_stream_references_unknown_token(self, sample_strategy_json):
        sample_strategy_json["derived_streams"] = [
            {"id": "bad_stream", "type": "moving_average", "token": "INVALID", "window": "1h"}
        ]
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) == 1
        assert "INVALID" in errors[0]

    def test_trigger_references_undefined_derived_stream(self, sample_strategy_json):
        sample_strategy_json["triggers"][0]["when"]["metric"] = "undefined_stream"
        sample_strategy_json["triggers"][0]["when"].pop("token", None)
        sample_strategy_json["triggers"][0]["when"].pop("window", None)
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) >= 1

    def test_duplicate_trigger_ids(self, sample_strategy_json):
        # Add duplicate trigger
        sample_strategy_json["triggers"].append(sample_strategy_json["triggers"][0].copy())
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert any("duplicate" in e.lower() for e in errors)

    def test_risk_rules_bounds(self, sample_strategy_json):
        sample_strategy_json["risk_rules"]["stop_loss_pct"] = -150  # Invalid: < -100
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) >= 1
        assert any("stop_loss" in e.lower() for e in errors)
