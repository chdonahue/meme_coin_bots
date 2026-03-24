import pytest
import json
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.parser import parse_strategy, parse_strategy_file, ParseError


class TestParser:
    def test_parse_json_string(self, sample_strategy_json):
        json_str = json.dumps(sample_strategy_json)
        strategy = parse_strategy(json_str)

        assert strategy.id == "test_strategy_001"
        assert strategy.name == "Test Strategy"

    def test_parse_dict(self, sample_strategy_json):
        strategy = parse_strategy(sample_strategy_json)

        assert strategy.id == "test_strategy_001"

    def test_parse_file(self, sample_strategy_json, tmp_path):
        file_path = tmp_path / "strategy.json"
        file_path.write_text(json.dumps(sample_strategy_json))

        strategy = parse_strategy_file(file_path)

        assert strategy.id == "test_strategy_001"

    def test_parse_invalid_json_raises(self):
        with pytest.raises(ParseError):
            parse_strategy("not valid json")

    def test_parse_invalid_strategy_raises(self):
        with pytest.raises(ParseError):
            parse_strategy({"id": "incomplete"})
