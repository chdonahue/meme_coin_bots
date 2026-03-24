import pytest
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.streams.derived import moving_average, ema, rsi, volatility, DerivedStreamCalculator
from engine.dsl.types import DerivedStream, DerivedStreamType, Window


class TestMovingAverage:
    def test_simple_moving_average(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = moving_average(prices, window=3)

        # MA of last 3: (30 + 40 + 50) / 3 = 40
        assert result == 40.0

    def test_moving_average_insufficient_data(self):
        prices = [10.0, 20.0]
        result = moving_average(prices, window=5)

        # Not enough data, return average of what we have
        assert result == 15.0

    def test_moving_average_empty_data(self):
        result = moving_average([], window=3)

        assert result is None


class TestEMA:
    def test_exponential_moving_average(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = ema(prices, window=3)

        # EMA gives more weight to recent values
        assert result is not None
        assert result > 40.0  # Should be weighted toward recent (50)


class TestRSI:
    def test_rsi_overbought(self):
        # Consistently rising prices
        prices = [
            10.0,
            15.0,
            20.0,
            25.0,
            30.0,
            35.0,
            40.0,
            45.0,
            50.0,
            55.0,
            60.0,
            65.0,
            70.0,
            75.0,
            80.0,
        ]
        result = rsi(prices, periods=14)

        # Strong uptrend = high RSI
        assert result is not None
        assert result > 70

    def test_rsi_oversold(self):
        # Consistently falling prices
        prices = [
            80.0,
            75.0,
            70.0,
            65.0,
            60.0,
            55.0,
            50.0,
            45.0,
            40.0,
            35.0,
            30.0,
            25.0,
            20.0,
            15.0,
            10.0,
        ]
        result = rsi(prices, periods=14)

        # Strong downtrend = low RSI
        assert result is not None
        assert result < 30

    def test_rsi_insufficient_data(self):
        prices = [10.0, 20.0, 30.0]
        result = rsi(prices, periods=14)

        assert result is None


class TestVolatility:
    def test_volatility_stable(self):
        # Stable prices
        prices = [100.0, 100.0, 100.0, 100.0, 100.0]
        result = volatility(prices)

        assert result == 0.0

    def test_volatility_variable(self):
        # Variable prices
        prices = [100.0, 110.0, 90.0, 120.0, 80.0]
        result = volatility(prices)

        assert result > 0


class TestDerivedStreamCalculator:
    def test_calculate_derived_stream(self):
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
