# SignalComposer Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core engine that parses strategy DSL, fetches market data, computes derived streams, and evaluates triggers.

**Architecture:** Strategy definitions (JSON DSL) are parsed into typed Python objects, validated, then evaluated against real-time data streams. Data is fetched from Jupiter/Birdeye, cached in Redis, and stored in TimescaleDB. Derived streams (MAs, RSI) are computed incrementally.

**Tech Stack:** Python 3.11+, Pydantic (DSL types), asyncio, httpx (API calls), Redis (caching), PostgreSQL + TimescaleDB (storage), pytest, SQLAlchemy

**Spec:** `docs/superpowers/specs/2026-03-23-signal-composer-design.md`

---

## File Structure

```
signal_composer/
├── src/
│   ├── __init__.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── dsl/
│   │   │   ├── __init__.py
│   │   │   ├── types.py           # Pydantic models for DSL
│   │   │   ├── parser.py          # Parse JSON to typed objects
│   │   │   ├── validator.py       # Business rule validation
│   │   │   └── executor.py        # Evaluate triggers against data
│   │   └── streams/
│   │       ├── __init__.py
│   │       ├── derived.py         # MA, EMA, RSI calculations
│   │       └── registry.py        # Track active streams
│   ├── data/
│   │   ├── __init__.py
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # Abstract data source
│   │   │   ├── jupiter.py         # Jupiter quote API
│   │   │   └── birdeye.py         # Birdeye OHLCV API
│   │   ├── ingestion.py           # Polling coordinator
│   │   └── cache.py               # Redis price cache
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py              # SQLAlchemy + TimescaleDB models
│   │   └── connection.py          # Async DB sessions
│   └── cli.py                     # CLI for testing engine
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── engine/
│   │   ├── dsl/
│   │   │   ├── test_types.py
│   │   │   ├── test_parser.py
│   │   │   ├── test_validator.py
│   │   │   └── test_executor.py
│   │   └── streams/
│   │       └── test_derived.py
│   └── data/
│       └── sources/
│           ├── test_jupiter.py
│           └── test_birdeye.py
├── pyproject.toml
└── requirements.txt
```

---

## Task 1: Project Setup

**Files:**
- Create: `signal_composer/pyproject.toml`
- Create: `signal_composer/requirements.txt`
- Create: `signal_composer/src/__init__.py`
- Create: `signal_composer/tests/__init__.py`
- Create: `signal_composer/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "signal-composer"
version = "0.1.0"
description = "Composable trading strategy marketplace"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.25",
    "redis>=5.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
    "black>=24.0",
    "ruff>=0.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create requirements.txt**

```
pydantic>=2.0
httpx>=0.25
redis>=5.0
sqlalchemy>=2.0
asyncpg>=0.29
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.0
```

- [ ] **Step 3: Create package structure**

Create empty `__init__.py` files:
- `signal_composer/src/__init__.py`
- `signal_composer/tests/__init__.py`

- [ ] **Step 4: Create conftest.py with basic fixtures**

```python
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
```

- [ ] **Step 5: Install dependencies and verify**

Run:
```bash
cd signal_composer && pip install -e ".[dev]"
pytest --collect-only
```

Expected: `no tests ran` (no test files yet, but pytest runs)

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(signal_composer): initialize project structure with dependencies"
```

---

## Task 2: DSL Type Definitions

**Files:**
- Create: `signal_composer/src/engine/__init__.py`
- Create: `signal_composer/src/engine/dsl/__init__.py`
- Create: `signal_composer/src/engine/dsl/types.py`
- Create: `signal_composer/tests/engine/__init__.py`
- Create: `signal_composer/tests/engine/dsl/__init__.py`
- Create: `signal_composer/tests/engine/dsl/test_types.py`

- [ ] **Step 1: Write failing test for Strategy type**

```python
# signal_composer/tests/engine/dsl/test_types.py
import pytest
from pydantic import ValidationError


class TestStrategyType:
    def test_valid_strategy_parses(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.types import Strategy

        strategy = Strategy.model_validate(sample_strategy_json)

        assert strategy.id == "test_strategy_001"
        assert strategy.name == "Test Strategy"
        assert len(strategy.triggers) == 1
        assert strategy.risk_rules.stop_loss_pct == -15

    def test_missing_required_field_raises(self):
        from signal_composer.src.engine.dsl.types import Strategy

        invalid_json = {"id": "test", "name": "Test"}  # missing required fields

        with pytest.raises(ValidationError):
            Strategy.model_validate(invalid_json)

    def test_invalid_operator_raises(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.types import Strategy

        sample_strategy_json["triggers"][0]["when"]["op"] = "INVALID"

        with pytest.raises(ValidationError):
            Strategy.model_validate(sample_strategy_json)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && pytest tests/engine/dsl/test_types.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'signal_composer.src.engine'`

- [ ] **Step 3: Create package structure**

Create empty `__init__.py` files:
- `signal_composer/src/engine/__init__.py`
- `signal_composer/src/engine/dsl/__init__.py`
- `signal_composer/tests/engine/__init__.py`
- `signal_composer/tests/engine/dsl/__init__.py`

- [ ] **Step 4: Implement DSL types**

```python
# signal_composer/src/engine/dsl/types.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/engine/dsl/test_types.py -v`

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(dsl): add Pydantic type definitions for Strategy DSL"
```

---

## Task 3: DSL Parser

**Files:**
- Create: `signal_composer/src/engine/dsl/parser.py`
- Create: `signal_composer/tests/engine/dsl/test_parser.py`

- [ ] **Step 1: Write failing tests for parser**

```python
# signal_composer/tests/engine/dsl/test_parser.py
import pytest
import json


class TestParser:
    def test_parse_json_string(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy

        json_str = json.dumps(sample_strategy_json)
        strategy = parse_strategy(json_str)

        assert strategy.id == "test_strategy_001"
        assert strategy.name == "Test Strategy"

    def test_parse_dict(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy

        strategy = parse_strategy(sample_strategy_json)

        assert strategy.id == "test_strategy_001"

    def test_parse_file(self, sample_strategy_json, tmp_path):
        from signal_composer.src.engine.dsl.parser import parse_strategy_file

        file_path = tmp_path / "strategy.json"
        file_path.write_text(json.dumps(sample_strategy_json))

        strategy = parse_strategy_file(file_path)

        assert strategy.id == "test_strategy_001"

    def test_parse_invalid_json_raises(self):
        from signal_composer.src.engine.dsl.parser import parse_strategy, ParseError

        with pytest.raises(ParseError):
            parse_strategy("not valid json")

    def test_parse_invalid_strategy_raises(self):
        from signal_composer.src.engine.dsl.parser import parse_strategy, ParseError

        with pytest.raises(ParseError):
            parse_strategy({"id": "incomplete"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/engine/dsl/test_parser.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement parser**

```python
# signal_composer/src/engine/dsl/parser.py
"""Parse Strategy DSL from JSON."""
import json
from pathlib import Path
from typing import Union

from pydantic import ValidationError

from .types import Strategy


class ParseError(Exception):
    """Raised when strategy parsing fails."""

    def __init__(self, message: str, details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


def parse_strategy(source: Union[str, dict]) -> Strategy:
    """
    Parse a strategy from JSON string or dict.

    Args:
        source: JSON string or dict containing strategy definition

    Returns:
        Validated Strategy object

    Raises:
        ParseError: If parsing or validation fails
    """
    # Convert JSON string to dict if needed
    if isinstance(source, str):
        try:
            data = json.loads(source)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e.msg}", details=str(e))
    else:
        data = source

    # Validate against Pydantic model
    try:
        return Strategy.model_validate(data)
    except ValidationError as e:
        raise ParseError("Strategy validation failed", details=str(e))


def parse_strategy_file(path: Union[str, Path]) -> Strategy:
    """
    Parse a strategy from a JSON file.

    Args:
        path: Path to JSON file

    Returns:
        Validated Strategy object

    Raises:
        ParseError: If file reading, parsing, or validation fails
    """
    path = Path(path)

    try:
        content = path.read_text()
    except FileNotFoundError:
        raise ParseError(f"Strategy file not found: {path}")
    except IOError as e:
        raise ParseError(f"Error reading file: {path}", details=str(e))

    return parse_strategy(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/engine/dsl/test_parser.py -v`

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(dsl): add strategy parser with JSON and file support"
```

---

## Task 4: DSL Validator (Business Rules)

**Files:**
- Create: `signal_composer/src/engine/dsl/validator.py`
- Create: `signal_composer/tests/engine/dsl/test_validator.py`

- [ ] **Step 1: Write failing tests for validator**

```python
# signal_composer/tests/engine/dsl/test_validator.py
import pytest


class TestValidator:
    def test_valid_strategy_passes(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert errors == []

    def test_trigger_references_unknown_token(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        sample_strategy_json["triggers"][0]["when"]["token"] = "UNKNOWN"
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) == 1
        assert "UNKNOWN" in errors[0]

    def test_derived_stream_references_unknown_token(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        sample_strategy_json["derived_streams"] = [
            {"id": "bad_stream", "type": "moving_average", "token": "INVALID", "window": "1h"}
        ]
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) == 1
        assert "INVALID" in errors[0]

    def test_trigger_references_undefined_derived_stream(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        sample_strategy_json["triggers"][0]["when"]["metric"] = "undefined_stream"
        sample_strategy_json["triggers"][0]["when"].pop("token", None)
        sample_strategy_json["triggers"][0]["when"].pop("window", None)
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) >= 1

    def test_duplicate_trigger_ids(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        # Add duplicate trigger
        sample_strategy_json["triggers"].append(sample_strategy_json["triggers"][0].copy())
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert any("duplicate" in e.lower() for e in errors)

    def test_risk_rules_bounds(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy

        sample_strategy_json["risk_rules"]["stop_loss_pct"] = -150  # Invalid: < -100
        strategy = parse_strategy(sample_strategy_json)
        errors = validate_strategy(strategy)

        assert len(errors) >= 1
        assert any("stop_loss" in e.lower() for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/engine/dsl/test_validator.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement validator**

```python
# signal_composer/src/engine/dsl/validator.py
"""Business rule validation for Strategy DSL."""
from .types import (
    Strategy,
    Condition,
    SimpleCondition,
    AllCondition,
    AnyCondition,
    NotCondition,
)

# Known built-in metrics (not derived streams)
BUILTIN_METRICS = {
    "price",
    "price_change_pct",
    "volume",
    "volume_change_pct",
    "position_gain_pct",
    "position_size",
}


def validate_strategy(strategy: Strategy) -> list[str]:
    """
    Validate business rules for a strategy.

    Args:
        strategy: Parsed Strategy object

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Collect valid identifiers
    valid_tokens = set(strategy.tokens)
    derived_stream_ids = {ds.id for ds in strategy.derived_streams}

    # Validate derived streams reference valid tokens
    for ds in strategy.derived_streams:
        if ds.token not in valid_tokens:
            errors.append(
                f"Derived stream '{ds.id}' references unknown token: {ds.token}"
            )

    # Check for duplicate derived stream IDs
    seen_ds_ids: set[str] = set()
    for ds in strategy.derived_streams:
        if ds.id in seen_ds_ids:
            errors.append(f"Duplicate derived stream ID: {ds.id}")
        seen_ds_ids.add(ds.id)

    # Check for duplicate trigger IDs
    seen_trigger_ids: set[str] = set()
    for trigger in strategy.triggers:
        if trigger.id in seen_trigger_ids:
            errors.append(f"Duplicate trigger ID: {trigger.id}")
        seen_trigger_ids.add(trigger.id)

    # Validate triggers
    for trigger in strategy.triggers:
        errors.extend(
            _validate_condition(
                trigger.when,
                valid_tokens,
                derived_stream_ids,
                f"trigger '{trigger.id}'",
            )
        )

        # Validate action references valid token
        if trigger.action.token not in valid_tokens:
            errors.append(
                f"Trigger '{trigger.id}' action references unknown token: {trigger.action.token}"
            )

    # Validate risk rules bounds
    rr = strategy.risk_rules
    if rr.stop_loss_pct < -100 or rr.stop_loss_pct > 0:
        errors.append(
            f"stop_loss_pct must be between -100 and 0, got: {rr.stop_loss_pct}"
        )
    if rr.max_position_pct <= 0 or rr.max_position_pct > 100:
        errors.append(
            f"max_position_pct must be between 0 and 100, got: {rr.max_position_pct}"
        )
    if rr.max_trades_per_day <= 0:
        errors.append(
            f"max_trades_per_day must be positive, got: {rr.max_trades_per_day}"
        )
    if rr.slippage_limit_bps < 0 or rr.slippage_limit_bps > 10000:
        errors.append(
            f"slippage_limit_bps must be between 0 and 10000, got: {rr.slippage_limit_bps}"
        )

    return errors


def _validate_condition(
    condition: Condition,
    valid_tokens: set[str],
    derived_stream_ids: set[str],
    context: str,
) -> list[str]:
    """Recursively validate a condition."""
    errors: list[str] = []

    if isinstance(condition, SimpleCondition):
        # Check if metric is builtin, derived, or invalid
        metric = condition.metric
        if metric not in BUILTIN_METRICS and metric not in derived_stream_ids:
            # Might be a builtin metric that requires a token
            if condition.token is None and metric in BUILTIN_METRICS:
                pass  # OK, some metrics don't need token
            elif condition.token is None:
                errors.append(
                    f"In {context}: metric '{metric}' is not a known builtin or derived stream"
                )

        # Check token reference if present
        if condition.token is not None and condition.token not in valid_tokens:
            errors.append(
                f"In {context}: condition references unknown token: {condition.token}"
            )

        # Check compare_to reference if present
        if condition.compare_to is not None:
            if (
                condition.compare_to not in BUILTIN_METRICS
                and condition.compare_to not in derived_stream_ids
            ):
                errors.append(
                    f"In {context}: compare_to references unknown metric: {condition.compare_to}"
                )

    elif isinstance(condition, AllCondition):
        for sub in condition.all:
            errors.extend(
                _validate_condition(sub, valid_tokens, derived_stream_ids, context)
            )

    elif isinstance(condition, AnyCondition):
        for sub in condition.any:
            errors.extend(
                _validate_condition(sub, valid_tokens, derived_stream_ids, context)
            )

    elif isinstance(condition, NotCondition):
        errors.extend(
            _validate_condition(
                condition.not_, valid_tokens, derived_stream_ids, context
            )
        )

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/engine/dsl/test_validator.py -v`

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(dsl): add business rule validator for strategies"
```

---

## Task 5: Derived Streams Engine

**Files:**
- Create: `signal_composer/src/engine/streams/__init__.py`
- Create: `signal_composer/src/engine/streams/derived.py`
- Create: `signal_composer/tests/engine/streams/__init__.py`
- Create: `signal_composer/tests/engine/streams/test_derived.py`

- [ ] **Step 1: Write failing tests for derived streams**

```python
# signal_composer/tests/engine/streams/test_derived.py
import pytest


class TestMovingAverage:
    def test_simple_moving_average(self):
        from signal_composer.src.engine.streams.derived import moving_average

        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = moving_average(prices, window=3)

        # MA of last 3: (30 + 40 + 50) / 3 = 40
        assert result == 40.0

    def test_moving_average_insufficient_data(self):
        from signal_composer.src.engine.streams.derived import moving_average

        prices = [10.0, 20.0]
        result = moving_average(prices, window=5)

        # Not enough data, return average of what we have
        assert result == 15.0

    def test_moving_average_empty_data(self):
        from signal_composer.src.engine.streams.derived import moving_average

        result = moving_average([], window=3)

        assert result is None


class TestEMA:
    def test_exponential_moving_average(self):
        from signal_composer.src.engine.streams.derived import ema

        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = ema(prices, window=3)

        # EMA gives more weight to recent values
        assert result is not None
        assert result > 40.0  # Should be weighted toward recent (50)


class TestRSI:
    def test_rsi_overbought(self):
        from signal_composer.src.engine.streams.derived import rsi

        # Consistently rising prices
        prices = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0,
                  60.0, 65.0, 70.0, 75.0, 80.0]
        result = rsi(prices, periods=14)

        # Strong uptrend = high RSI
        assert result is not None
        assert result > 70

    def test_rsi_oversold(self):
        from signal_composer.src.engine.streams.derived import rsi

        # Consistently falling prices
        prices = [80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0, 45.0, 40.0, 35.0,
                  30.0, 25.0, 20.0, 15.0, 10.0]
        result = rsi(prices, periods=14)

        # Strong downtrend = low RSI
        assert result is not None
        assert result < 30

    def test_rsi_insufficient_data(self):
        from signal_composer.src.engine.streams.derived import rsi

        prices = [10.0, 20.0, 30.0]
        result = rsi(prices, periods=14)

        assert result is None


class TestVolatility:
    def test_volatility_stable(self):
        from signal_composer.src.engine.streams.derived import volatility

        # Stable prices
        prices = [100.0, 100.0, 100.0, 100.0, 100.0]
        result = volatility(prices)

        assert result == 0.0

    def test_volatility_variable(self):
        from signal_composer.src.engine.streams.derived import volatility

        # Variable prices
        prices = [100.0, 110.0, 90.0, 120.0, 80.0]
        result = volatility(prices)

        assert result > 0


class TestDerivedStreamCalculator:
    def test_calculate_derived_stream(self):
        from signal_composer.src.engine.streams.derived import DerivedStreamCalculator
        from signal_composer.src.engine.dsl.types import DerivedStream, DerivedStreamType, Window

        calculator = DerivedStreamCalculator()

        stream_def = DerivedStream(
            id="sol_ma_1h",
            type=DerivedStreamType.MOVING_AVERAGE,
            token="SOL",
            window=Window.ONE_HOUR,
        )

        prices = [100.0, 110.0, 120.0, 130.0, 140.0]
        result = calculator.calculate(stream_def, prices)

        assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/engine/streams/test_derived.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create package structure**

Create empty `__init__.py` files:
- `signal_composer/src/engine/streams/__init__.py`
- `signal_composer/tests/engine/streams/__init__.py`

- [ ] **Step 4: Implement derived streams**

```python
# signal_composer/src/engine/streams/derived.py
"""Derived stream calculations (MA, EMA, RSI, etc.)."""
import statistics
from typing import Sequence

from ..dsl.types import DerivedStream, DerivedStreamType


def moving_average(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate simple moving average.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods to average

    Returns:
        Moving average or None if no data
    """
    if not prices:
        return None

    # Use available data if less than window
    data = prices[-window:] if len(prices) >= window else prices
    return statistics.mean(data)


def ema(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate exponential moving average.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods for EMA

    Returns:
        EMA value or None if no data
    """
    if not prices:
        return None

    multiplier = 2 / (window + 1)
    ema_value = prices[0]

    for price in prices[1:]:
        ema_value = (price * multiplier) + (ema_value * (1 - multiplier))

    return ema_value


def rsi(prices: Sequence[float], periods: int = 14) -> float | None:
    """
    Calculate Relative Strength Index.

    Args:
        prices: List of prices (oldest first)
        periods: RSI period (typically 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < periods + 1:
        return None

    # Calculate price changes
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # Separate gains and losses
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]

    # Calculate average gain/loss over period
    avg_gain = statistics.mean(gains[-periods:])
    avg_loss = statistics.mean(losses[-periods:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def volatility(prices: Sequence[float]) -> float:
    """
    Calculate price volatility (standard deviation).

    Args:
        prices: List of prices

    Returns:
        Standard deviation of prices
    """
    if len(prices) < 2:
        return 0.0

    return statistics.stdev(prices)


def price_delta(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate price change over window.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods to look back

    Returns:
        Price change (current - past) or None if insufficient data
    """
    if len(prices) < window:
        return None

    return prices[-1] - prices[-window]


class DerivedStreamCalculator:
    """Calculate derived stream values from price data."""

    def calculate(self, stream: DerivedStream, prices: Sequence[float]) -> float | None:
        """
        Calculate a derived stream value.

        Args:
            stream: Derived stream definition
            prices: Historical price data

        Returns:
            Calculated value or None if insufficient data
        """
        window_sizes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
        }

        window = window_sizes.get(stream.window.value, 60) if stream.window else 60

        match stream.type:
            case DerivedStreamType.MOVING_AVERAGE:
                return moving_average(prices, window)
            case DerivedStreamType.EMA:
                return ema(prices, window)
            case DerivedStreamType.RSI:
                periods = stream.periods or 14
                return rsi(prices, periods)
            case DerivedStreamType.VOLATILITY:
                return volatility(prices[-window:] if len(prices) >= window else prices)
            case DerivedStreamType.PRICE_DELTA:
                return price_delta(prices, window)
            case _:
                return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/engine/streams/test_derived.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add signal_composer/
git commit -m "feat(streams): add derived stream calculations (MA, EMA, RSI, volatility)"
```

---

## Task 6: Data Source Base Interface

**Files:**
- Create: `signal_composer/src/data/__init__.py`
- Create: `signal_composer/src/data/sources/__init__.py`
- Create: `signal_composer/src/data/sources/base.py`
- Create: `signal_composer/tests/data/__init__.py`
- Create: `signal_composer/tests/data/sources/__init__.py`

- [ ] **Step 1: Write the data source base interface**

```python
# signal_composer/src/data/sources/base.py
"""Abstract base class for data sources."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class PriceTick:
    """A single price data point."""
    token: str
    price: float
    volume: float | None
    timestamp: datetime
    source: str


@dataclass
class OHLCV:
    """OHLCV candle data."""
    token: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    source: str


class DataSource(ABC):
    """Abstract base class for market data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this data source."""
        ...

    @abstractmethod
    async def get_price(self, token: str) -> PriceTick | None:
        """
        Get current price for a token.

        Args:
            token: Token symbol (e.g., "SOL") or mint address

        Returns:
            PriceTick or None if unavailable
        """
        ...

    @abstractmethod
    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """
        Get current prices for multiple tokens.

        Args:
            tokens: List of token symbols or mint addresses

        Returns:
            Dict mapping token to PriceTick
        """
        ...

    async def health_check(self) -> bool:
        """Check if data source is available."""
        return True
```

- [ ] **Step 2: Create package structure**

Create empty `__init__.py` files:
- `signal_composer/src/data/__init__.py`
- `signal_composer/src/data/sources/__init__.py`
- `signal_composer/tests/data/__init__.py`
- `signal_composer/tests/data/sources/__init__.py`

- [ ] **Step 3: Commit**

```bash
git add signal_composer/
git commit -m "feat(data): add abstract DataSource interface"
```

---

## Task 7: Jupiter Data Source

**Files:**
- Create: `signal_composer/src/data/sources/jupiter.py`
- Create: `signal_composer/tests/data/sources/test_jupiter.py`

- [ ] **Step 1: Write failing tests for Jupiter source**

```python
# signal_composer/tests/data/sources/test_jupiter.py
import pytest
from unittest.mock import AsyncMock, patch


# Well-known Solana token addresses
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class TestJupiterDataSource:
    @pytest.fixture
    def jupiter_source(self):
        from signal_composer.src.data.sources.jupiter import JupiterDataSource
        return JupiterDataSource()

    def test_source_name(self, jupiter_source):
        assert jupiter_source.name == "jupiter"

    @pytest.mark.asyncio
    async def test_get_price_returns_tick(self, jupiter_source):
        # Mock the HTTP response
        mock_response = {
            "data": {
                SOL_MINT: {"id": SOL_MINT, "price": "150.50"}
            }
        }

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await jupiter_source.get_price(SOL_MINT)

            assert tick is not None
            assert tick.token == SOL_MINT
            assert tick.price == 150.50
            assert tick.source == "jupiter"

    @pytest.mark.asyncio
    async def test_get_prices_multiple_tokens(self, jupiter_source):
        mock_response = {
            "data": {
                SOL_MINT: {"id": SOL_MINT, "price": "150.50"},
                USDC_MINT: {"id": USDC_MINT, "price": "1.00"},
            }
        }

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            prices = await jupiter_source.get_prices([SOL_MINT, USDC_MINT])

            assert len(prices) == 2
            assert prices[SOL_MINT].price == 150.50
            assert prices[USDC_MINT].price == 1.00

    @pytest.mark.asyncio
    async def test_get_price_not_found(self, jupiter_source):
        mock_response = {"data": {}}

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await jupiter_source.get_price("UNKNOWN_TOKEN")

            assert tick is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/data/sources/test_jupiter.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Jupiter data source**

```python
# signal_composer/src/data/sources/jupiter.py
"""Jupiter API data source."""
from datetime import datetime, UTC
from typing import Any

import httpx

from .base import DataSource, PriceTick


class JupiterDataSource(DataSource):
    """Fetch price data from Jupiter API."""

    BASE_URL = "https://api.jup.ag/price/v2"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "jupiter"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _fetch_prices(self, tokens: list[str]) -> dict[str, Any]:
        """Fetch prices from Jupiter API."""
        client = await self._get_client()
        ids = ",".join(tokens)
        response = await client.get(f"{self.BASE_URL}?ids={ids}")
        response.raise_for_status()
        return response.json()

    async def get_price(self, token: str) -> PriceTick | None:
        """Get current price for a token."""
        prices = await self.get_prices([token])
        return prices.get(token)

    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """Get current prices for multiple tokens."""
        if not tokens:
            return {}

        try:
            data = await self._fetch_prices(tokens)
        except httpx.HTTPError:
            return {}

        result = {}
        price_data = data.get("data", {})

        for token in tokens:
            if token in price_data and price_data[token]:
                price_str = price_data[token].get("price")
                if price_str:
                    result[token] = PriceTick(
                        token=token,
                        price=float(price_str),
                        volume=None,  # Jupiter doesn't provide volume
                        timestamp=datetime.now(UTC),
                        source=self.name,
                    )

        return result

    async def health_check(self) -> bool:
        """Check if Jupiter API is available."""
        try:
            client = await self._get_client()
            # Use SOL as test token
            response = await client.get(
                f"{self.BASE_URL}?ids=So11111111111111111111111111111111111111112"
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/data/sources/test_jupiter.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(data): add Jupiter data source for price feeds"
```

---

## Task 8: Birdeye Data Source

**Files:**
- Create: `signal_composer/src/data/sources/birdeye.py`
- Create: `signal_composer/tests/data/sources/test_birdeye.py`

- [ ] **Step 1: Write failing tests for Birdeye source**

```python
# signal_composer/tests/data/sources/test_birdeye.py
import pytest
from unittest.mock import AsyncMock, patch
import os


SOL_MINT = "So11111111111111111111111111111111111111112"


class TestBirdeyeDataSource:
    @pytest.fixture
    def birdeye_source(self):
        from signal_composer.src.data.sources.birdeye import BirdeyeDataSource
        # Use test API key
        return BirdeyeDataSource(api_key="test_key")

    def test_source_name(self, birdeye_source):
        assert birdeye_source.name == "birdeye"

    @pytest.mark.asyncio
    async def test_get_price_returns_tick(self, birdeye_source):
        mock_response = {
            "success": True,
            "data": {
                "value": 150.50,
                "updateUnixTime": 1700000000,
            }
        }

        with patch.object(birdeye_source, "_fetch_price", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await birdeye_source.get_price(SOL_MINT)

            assert tick is not None
            assert tick.price == 150.50
            assert tick.source == "birdeye"

    @pytest.mark.asyncio
    async def test_get_ohlcv(self, birdeye_source):
        from signal_composer.src.data.sources.base import OHLCV

        mock_response = {
            "success": True,
            "data": {
                "items": [
                    {
                        "o": 100.0,
                        "h": 110.0,
                        "l": 95.0,
                        "c": 105.0,
                        "v": 1000000,
                        "unixTime": 1700000000,
                    }
                ]
            }
        }

        with patch.object(birdeye_source, "_fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            candles = await birdeye_source.get_ohlcv(SOL_MINT, interval="1m", limit=1)

            assert len(candles) == 1
            assert candles[0].open == 100.0
            assert candles[0].close == 105.0

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self, birdeye_source):
        with patch.object(birdeye_source, "_fetch_price", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            tick = await birdeye_source.get_price(SOL_MINT)

            assert tick is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/data/sources/test_birdeye.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Birdeye data source**

```python
# signal_composer/src/data/sources/birdeye.py
"""Birdeye API data source."""
import os
from datetime import datetime, UTC
from typing import Any

import httpx

from .base import DataSource, PriceTick, OHLCV


class BirdeyeDataSource(DataSource):
    """Fetch price and OHLCV data from Birdeye API."""

    BASE_URL = "https://public-api.birdeye.so"

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or os.getenv("BIRDEYE_API_KEY", "")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "birdeye"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"X-API-KEY": self.api_key} if self.api_key else {}
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    async def _fetch_price(self, token: str) -> dict[str, Any]:
        """Fetch price from Birdeye API."""
        client = await self._get_client()
        response = await client.get(
            f"{self.BASE_URL}/defi/price",
            params={"address": token}
        )
        response.raise_for_status()
        return response.json()

    async def _fetch_ohlcv(
        self, token: str, interval: str, limit: int
    ) -> dict[str, Any]:
        """Fetch OHLCV from Birdeye API."""
        client = await self._get_client()
        response = await client.get(
            f"{self.BASE_URL}/defi/ohlcv",
            params={
                "address": token,
                "type": interval,
                "limit": limit,
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_price(self, token: str) -> PriceTick | None:
        """Get current price for a token."""
        try:
            data = await self._fetch_price(token)
            if not data.get("success") or not data.get("data"):
                return None

            price_data = data["data"]
            return PriceTick(
                token=token,
                price=float(price_data["value"]),
                volume=None,
                timestamp=datetime.fromtimestamp(
                    price_data.get("updateUnixTime", datetime.now(UTC).timestamp()),
                    tz=UTC
                ),
                source=self.name,
            )
        except Exception:
            return None

    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """Get current prices for multiple tokens."""
        result = {}
        for token in tokens:
            tick = await self.get_price(token)
            if tick:
                result[token] = tick
        return result

    async def get_ohlcv(
        self, token: str, interval: str = "1m", limit: int = 100
    ) -> list[OHLCV]:
        """
        Get OHLCV candle data.

        Args:
            token: Token mint address
            interval: Candle interval (1m, 5m, 15m, 1H, 4H, 1D)
            limit: Number of candles to fetch

        Returns:
            List of OHLCV candles
        """
        try:
            data = await self._fetch_ohlcv(token, interval, limit)
            if not data.get("success") or not data.get("data"):
                return []

            items = data["data"].get("items", [])
            return [
                OHLCV(
                    token=token,
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=float(item["v"]),
                    timestamp=datetime.fromtimestamp(item["unixTime"], tz=UTC),
                    source=self.name,
                )
                for item in items
            ]
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Check if Birdeye API is available."""
        try:
            tick = await self.get_price(
                "So11111111111111111111111111111111111111112"
            )
            return tick is not None
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/data/sources/test_birdeye.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(data): add Birdeye data source for OHLCV data"
```

---

## Task 9: DSL Executor

**Files:**
- Create: `signal_composer/src/engine/dsl/executor.py`
- Create: `signal_composer/tests/engine/dsl/test_executor.py`

- [ ] **Step 1: Write failing tests for executor**

```python
# signal_composer/tests/engine/dsl/test_executor.py
import pytest
from datetime import datetime, UTC


class TestConditionEvaluator:
    def test_simple_less_than_true(self):
        from signal_composer.src.engine.dsl.executor import ConditionEvaluator
        from signal_composer.src.engine.dsl.types import SimpleCondition, Operator, Window

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
        from signal_composer.src.engine.dsl.executor import ConditionEvaluator
        from signal_composer.src.engine.dsl.types import SimpleCondition, Operator, Window

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
        from signal_composer.src.engine.dsl.executor import ConditionEvaluator
        from signal_composer.src.engine.dsl.types import (
            SimpleCondition, AllCondition, Operator, Window
        )

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
        from signal_composer.src.engine.dsl.executor import ConditionEvaluator
        from signal_composer.src.engine.dsl.types import (
            SimpleCondition, AnyCondition, Operator, Window
        )

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
        from signal_composer.src.engine.dsl.executor import ConditionEvaluator
        from signal_composer.src.engine.dsl.types import SimpleCondition, Operator

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
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 1
        assert actions[0].action.type.value == "buy"
        assert actions[0].action.token == "SOL"

    def test_no_triggers_fire(self, sample_strategy_json):
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.executor import StrategyExecutor

        strategy = parse_strategy(sample_strategy_json)
        executor = StrategyExecutor(strategy)

        # Price didn't drop enough
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}

        actions = executor.evaluate(market_data)

        assert len(actions) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd signal_composer && pytest tests/engine/dsl/test_executor.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement executor**

```python
# signal_composer/src/engine/dsl/executor.py
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

    def _evaluate_simple(
        self, condition: SimpleCondition, market_data: dict[str, Any]
    ) -> bool:
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

    def _get_derived_current(
        self, stream_id: str, market_data: dict[str, Any]
    ) -> float | None:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && pytest tests/engine/dsl/test_executor.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(dsl): add condition evaluator and strategy executor"
```

---

## Task 10: Database Models

**Files:**
- Create: `signal_composer/src/db/__init__.py`
- Create: `signal_composer/src/db/models.py`
- Create: `signal_composer/src/db/connection.py`

- [ ] **Step 1: Create database models**

```python
# signal_composer/src/db/models.py
"""SQLAlchemy models for SignalComposer."""
from datetime import datetime, UTC
from typing import Any

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    """User account."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Relationships
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="creator")


class Strategy(Base):
    """Trading strategy."""
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    dsl_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, active, paused
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    creator: Mapped["User"] = relationship(back_populates="strategies")
    performance: Mapped[list["StrategyPerformance"]] = relationship(back_populates="strategy")
    trades: Mapped[list["PaperTrade"]] = relationship(back_populates="strategy")


class StrategyPerformance(Base):
    """Daily performance snapshots."""
    __tablename__ = "strategy_performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="performance")

    __table_args__ = (
        Index("ix_perf_strategy_date", "strategy_id", "date", unique=True),
    )


class PaperTrade(Base):
    """Simulated trade record."""
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    trigger_id: Mapped[str] = mapped_column(String(50))
    token: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(10))  # buy, sell, sell_all
    amount: Mapped[float] = mapped_column(Float)
    price_at_exec: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(back_populates="trades")


class PriceData(Base):
    """Time-series price data."""
    __tablename__ = "price_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20))

    __table_args__ = (
        Index("ix_price_token_time", "token", "timestamp"),
    )
```

- [ ] **Step 2: Create database connection helper**

```python
# signal_composer/src/db/connection.py
"""Database connection management."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://localhost:5432/signal_composer"
    )


# Create engine
engine = create_async_engine(
    get_database_url(),
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 3: Create __init__.py**

```python
# signal_composer/src/db/__init__.py
"""Database module."""
from .connection import get_session, init_db, drop_db
from .models import User, Strategy, StrategyPerformance, PaperTrade, PriceData

__all__ = [
    "get_session",
    "init_db",
    "drop_db",
    "User",
    "Strategy",
    "StrategyPerformance",
    "PaperTrade",
    "PriceData",
]
```

- [ ] **Step 4: Commit**

```bash
git add signal_composer/
git commit -m "feat(db): add SQLAlchemy models for users, strategies, trades, prices"
```

---

## Task 11: CLI for Testing

**Files:**
- Create: `signal_composer/src/cli.py`

- [ ] **Step 1: Create CLI**

```python
# signal_composer/src/cli.py
"""CLI for testing SignalComposer engine."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from .engine.dsl.parser import parse_strategy, parse_strategy_file, ParseError
from .engine.dsl.validator import validate_strategy
from .engine.dsl.executor import StrategyExecutor
from .data.sources.jupiter import JupiterDataSource


def cmd_parse(args: argparse.Namespace) -> int:
    """Parse and validate a strategy file."""
    try:
        strategy = parse_strategy_file(args.file)
        print(f"✓ Parsed strategy: {strategy.name}")
        print(f"  ID: {strategy.id}")
        print(f"  Tokens: {', '.join(strategy.tokens)}")
        print(f"  Triggers: {len(strategy.triggers)}")
        print(f"  Derived streams: {len(strategy.derived_streams)}")

        errors = validate_strategy(strategy)
        if errors:
            print("\n✗ Validation errors:")
            for error in errors:
                print(f"  - {error}")
            return 1
        else:
            print("\n✓ Validation passed")
            return 0

    except ParseError as e:
        print(f"✗ Parse error: {e.message}")
        if e.details:
            print(f"  Details: {e.details}")
        return 1


async def cmd_price(args: argparse.Namespace) -> int:
    """Fetch current price for a token."""
    source = JupiterDataSource()
    try:
        tick = await source.get_price(args.token)
        if tick:
            print(f"Token: {tick.token}")
            print(f"Price: ${tick.price:.6f}")
            print(f"Source: {tick.source}")
            print(f"Time: {tick.timestamp.isoformat()}")
            return 0
        else:
            print(f"✗ Could not fetch price for {args.token}")
            return 1
    finally:
        await source.close()


async def cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a strategy against current market data."""
    try:
        strategy = parse_strategy_file(args.file)
        print(f"Evaluating strategy: {strategy.name}")

        # Fetch prices for tokens
        source = JupiterDataSource()
        try:
            prices = await source.get_prices(strategy.tokens)
        finally:
            await source.close()

        # Build market data (simplified - just current price)
        market_data = {}
        for token, tick in prices.items():
            market_data[token] = {
                "price": tick.price,
                "price_change_pct": {"15m": 0.0},  # Placeholder
                "volume": {"15m": 0},  # Placeholder
            }
            print(f"  {token}: ${tick.price:.6f}")

        # Evaluate
        executor = StrategyExecutor(strategy)
        actions = executor.evaluate(market_data)

        if actions:
            print(f"\n{len(actions)} trigger(s) fired:")
            for ta in actions:
                print(f"  - {ta.trigger_id}: {ta.action.type.value} {ta.action.token}")
        else:
            print("\nNo triggers fired")

        return 0

    except ParseError as e:
        print(f"✗ Parse error: {e.message}")
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SignalComposer CLI",
        prog="signal-composer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse command
    parse_parser = subparsers.add_parser("parse", help="Parse and validate a strategy")
    parse_parser.add_argument("file", type=Path, help="Strategy JSON file")

    # price command
    price_parser = subparsers.add_parser("price", help="Get current price for a token")
    price_parser.add_argument("token", help="Token mint address")

    # evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate strategy against market")
    eval_parser.add_argument("file", type=Path, help="Strategy JSON file")

    args = parser.parse_args()

    if args.command == "parse":
        return cmd_parse(args)
    elif args.command == "price":
        return asyncio.run(cmd_price(args))
    elif args.command == "evaluate":
        return asyncio.run(cmd_evaluate(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add CLI entry point to pyproject.toml**

Add to `signal_composer/pyproject.toml`:

```toml
[project.scripts]
signal-composer = "signal_composer.src.cli:main"
```

- [ ] **Step 3: Create sample strategy file for testing**

```json
# signal_composer/examples/sample_strategy.json
{
  "id": "sample_001",
  "name": "SOL Dip Buyer",
  "description": "Buys SOL when it dips 5% in 15 minutes",
  "version": 1,
  "tokens": ["So11111111111111111111111111111111111111112"],
  "derived_streams": [],
  "triggers": [
    {
      "id": "buy_the_dip",
      "when": {
        "metric": "price_change_pct",
        "token": "So11111111111111111111111111111111111111112",
        "window": "15m",
        "op": "<",
        "value": -5
      },
      "action": {
        "type": "buy",
        "token": "So11111111111111111111111111111111111111112",
        "amount_pct": 25
      }
    }
  ],
  "risk_rules": {
    "stop_loss_pct": -15,
    "max_position_pct": 40,
    "max_trades_per_day": 10,
    "slippage_limit_bps": 300
  }
}
```

- [ ] **Step 4: Test CLI commands**

Run:
```bash
cd signal_composer
pip install -e .
signal-composer parse examples/sample_strategy.json
signal-composer price So11111111111111111111111111111111111111112
```

Expected: Both commands run successfully

- [ ] **Step 5: Commit**

```bash
git add signal_composer/
git commit -m "feat(cli): add CLI for parsing, price fetching, and strategy evaluation"
```

---

## Task 12: Final Integration Test

**Files:**
- Create: `signal_composer/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# signal_composer/tests/test_integration.py
"""Integration tests for the core engine."""
import pytest


class TestCoreEngineIntegration:
    """Test the full flow from parsing to execution."""

    def test_full_strategy_flow(self, sample_strategy_json):
        """Test: parse → validate → build executor → evaluate."""
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy
        from signal_composer.src.engine.dsl.executor import StrategyExecutor

        # Parse
        strategy = parse_strategy(sample_strategy_json)
        assert strategy.id == "test_strategy_001"

        # Validate
        errors = validate_strategy(strategy)
        assert errors == []

        # Execute
        executor = StrategyExecutor(strategy)

        # Trigger should fire
        market_data = {"SOL": {"price_change_pct": {"15m": -10.0}}}
        actions = executor.evaluate(market_data)
        assert len(actions) == 1
        assert actions[0].action.type.value == "buy"

        # Trigger should NOT fire
        market_data = {"SOL": {"price_change_pct": {"15m": -2.0}}}
        actions = executor.evaluate(market_data)
        assert len(actions) == 0

    def test_strategy_with_derived_streams(self):
        """Test strategy using derived streams (MA crossover)."""
        from signal_composer.src.engine.dsl.parser import parse_strategy
        from signal_composer.src.engine.dsl.validator import validate_strategy
        from signal_composer.src.engine.dsl.executor import StrategyExecutor

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
        from signal_composer.src.engine.streams.derived import (
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
```

- [ ] **Step 2: Run all tests**

Run: `cd signal_composer && pytest -v --cov=src`

Expected: All tests pass with good coverage

- [ ] **Step 3: Final commit**

```bash
git add signal_composer/
git commit -m "test: add integration tests for core engine"
```

---

## Summary

After completing all tasks, you will have:

1. **Strategy DSL** - Pydantic types, parser, validator
2. **Derived Streams** - MA, EMA, RSI, volatility calculations
3. **Data Sources** - Jupiter and Birdeye API clients
4. **Executor** - Condition evaluator and strategy executor
5. **Database Models** - SQLAlchemy models for all entities
6. **CLI** - Command-line tool for testing

**Next Plan:** Plan 2 (Simulation Engine) will add paper trading, P&L tracking, and backtesting.
