# Real Price Data Integration - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synthetic backtest data with real historical prices from Birdeye API.

**Architecture:** New `PriceDataLoader` class orchestrates cache-check → Birdeye fetch → cache-write. Integrates with existing `BirdeyeDataSource` and `BacktestEngine`. Simple JSON file caching with daily expiration.

**Tech Stack:** Python 3.11+, httpx (async HTTP), Birdeye API, JSON file cache

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/data/tokens.py` | NEW - Token symbol to mint address mapping |
| `src/data/loader.py` | NEW - PriceDataLoader with cache logic |
| `src/api/schemas/strategy.py` | MODIFY - Add use_real_data, data_source fields |
| `src/api/routes/strategies.py` | MODIFY - Use PriceDataLoader in backtest |
| `.gitignore` | MODIFY - Add .cache/ |
| `tests/data/test_price_loader.py` | NEW - Unit tests for loader |
| `scripts/demo_api.py` | MODIFY - Show real data backtest |

---

### Task 1: Token Address Mapping

**Files:**
- Create: `src/data/tokens.py`
- Test: `tests/data/test_tokens.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_tokens.py
"""Tests for token mapping."""

from src.data.tokens import get_mint_address, TOKEN_MINTS


class TestGetMintAddress:
    """Test token symbol to mint address lookup."""

    def test_sol_returns_mint_address(self):
        """SOL returns correct mint address."""
        result = get_mint_address("SOL")
        assert result == "So11111111111111111111111111111111111111112"

    def test_usdc_returns_mint_address(self):
        """USDC returns correct mint address."""
        result = get_mint_address("USDC")
        assert result == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def test_unknown_token_returns_none(self):
        """Unknown token returns None."""
        result = get_mint_address("UNKNOWN")
        assert result is None

    def test_case_insensitive(self):
        """Lookup is case-insensitive."""
        assert get_mint_address("sol") == get_mint_address("SOL")
        assert get_mint_address("Sol") == get_mint_address("SOL")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_tokens.py -v`
Expected: FAIL with "No module named 'src.data.tokens'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/data/tokens.py
"""Token symbol to mint address mapping."""

# Solana token mint addresses
TOKEN_MINTS: dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}


def get_mint_address(symbol: str) -> str | None:
    """
    Get mint address for a token symbol.

    Args:
        symbol: Token symbol (e.g., "SOL", "USDC")

    Returns:
        Mint address string or None if not found
    """
    return TOKEN_MINTS.get(symbol.upper())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_tokens.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/data/tokens.py tests/data/test_tokens.py
git commit -m "feat(data): add token symbol to mint address mapping"
```

---

### Task 2: PriceDataLoader - Cache Key Generation

**Files:**
- Create: `src/data/loader.py`
- Create: `tests/data/test_price_loader.py`

- [ ] **Step 1: Write the failing test for cache key**

```python
# tests/data/test_price_loader.py
"""Tests for PriceDataLoader."""

from datetime import date
from unittest.mock import patch

from src.data.loader import PriceDataLoader


class TestCacheKey:
    """Test cache key generation."""

    def test_cache_key_format(self):
        """Cache key follows {token}_{interval}_{days}d_{date} format."""
        loader = PriceDataLoader()

        with patch("src.data.loader.date") as mock_date:
            mock_date.today.return_value = date(2025, 3, 27)
            key = loader._build_cache_key("SOL", "1H", 30)

        assert key == "SOL_1H_30d_2025-03-27"

    def test_cache_key_different_params(self):
        """Different parameters produce different keys."""
        loader = PriceDataLoader()

        with patch("src.data.loader.date") as mock_date:
            mock_date.today.return_value = date(2025, 3, 27)
            key1 = loader._build_cache_key("SOL", "1H", 30)
            key2 = loader._build_cache_key("SOL", "1H", 7)
            key3 = loader._build_cache_key("USDC", "1H", 30)

        assert key1 != key2
        assert key1 != key3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_price_loader.py::TestCacheKey -v`
Expected: FAIL with "No module named 'src.data.loader'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/data/loader.py
"""Price data loader with caching."""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from src.data.sources.birdeye import BirdeyeDataSource
from src.data.tokens import get_mint_address


class PriceDataLoader:
    """Load price data with file-based caching."""

    def __init__(self, cache_dir: str = ".cache/ohlcv"):
        self.cache_dir = Path(cache_dir)
        self._birdeye: BirdeyeDataSource | None = None

    def _build_cache_key(self, token: str, interval: str, days: int) -> str:
        """Build cache key from parameters."""
        today = date.today().isoformat()
        return f"{token}_{interval}_{days}d_{today}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_price_loader.py::TestCacheKey -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/data/loader.py tests/data/test_price_loader.py
git commit -m "feat(data): add PriceDataLoader with cache key generation"
```

---

### Task 3: PriceDataLoader - Cache Read/Write

**Files:**
- Modify: `src/data/loader.py`
- Modify: `tests/data/test_price_loader.py`

- [ ] **Step 1: Write the failing tests for cache operations**

```python
# Add to tests/data/test_price_loader.py

import tempfile
import json
from pathlib import Path


class TestCacheOperations:
    """Test cache read/write operations."""

    def test_cache_path_created(self):
        """Cache directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "new_cache"
            loader = PriceDataLoader(cache_dir=str(cache_dir))
            loader._ensure_cache_dir()
            assert cache_dir.exists()

    def test_write_and_read_cache(self):
        """Data can be written and read from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            test_data = [{"price": 100.0, "timestamp": "2025-03-27T00:00:00Z"}]

            loader._write_cache("test_key", test_data)
            result = loader._read_cache("test_key")

            assert result == test_data

    def test_read_missing_cache_returns_none(self):
        """Reading missing cache file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            result = loader._read_cache("nonexistent_key")
            assert result is None

    def test_read_corrupt_cache_returns_none(self):
        """Reading corrupt cache file returns None and deletes file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            cache_file = Path(tmpdir) / "corrupt_key.json"
            cache_file.write_text("not valid json {{{")

            result = loader._read_cache("corrupt_key")

            assert result is None
            assert not cache_file.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_price_loader.py::TestCacheOperations -v`
Expected: FAIL with "AttributeError: 'PriceDataLoader' object has no attribute '_ensure_cache_dir'"

- [ ] **Step 3: Implement cache operations**

```python
# Add to src/data/loader.py PriceDataLoader class

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> list[dict] | None:
        """Read data from cache file."""
        path = self._cache_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Corrupt file - delete and return None
            path.unlink(missing_ok=True)
            return None

    def _write_cache(self, key: str, data: list[dict]) -> None:
        """Write data to cache file."""
        self._ensure_cache_dir()
        path = self._cache_path(key)
        with open(path, "w") as f:
            json.dump(data, f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_price_loader.py::TestCacheOperations -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/data/loader.py tests/data/test_price_loader.py
git commit -m "feat(data): add cache read/write operations to PriceDataLoader"
```

---

### Task 4: PriceDataLoader - Data Transformation

**Files:**
- Modify: `src/data/loader.py`
- Modify: `tests/data/test_price_loader.py`

- [ ] **Step 1: Write the failing test for data transformation**

```python
# Add to tests/data/test_price_loader.py

from datetime import datetime, timezone
from src.data.sources.base import OHLCV


class TestDataTransformation:
    """Test OHLCV to backtest format transformation."""

    def test_transform_ohlcv_to_backtest_format(self):
        """OHLCV candles are transformed to backtest format."""
        loader = PriceDataLoader()
        ohlcv_data = [
            OHLCV(
                token="So11111111111111111111111111111111111111112",
                open=180.0,
                high=185.0,
                low=178.0,
                close=183.5,
                volume=1000000,
                timestamp=datetime(2025, 3, 27, 12, 0, tzinfo=timezone.utc),
                source="birdeye",
            ),
            OHLCV(
                token="So11111111111111111111111111111111111111112",
                open=183.5,
                high=190.0,
                low=182.0,
                close=188.0,
                volume=1200000,
                timestamp=datetime(2025, 3, 27, 13, 0, tzinfo=timezone.utc),
                source="birdeye",
            ),
        ]

        result = loader._transform_to_backtest_format(ohlcv_data, "SOL")

        assert len(result) == 2
        assert result[0]["SOL"] == 183.5  # close price
        assert result[0]["timestamp"] == datetime(2025, 3, 27, 12, 0, tzinfo=timezone.utc)
        assert result[1]["SOL"] == 188.0
        assert result[1]["timestamp"] == datetime(2025, 3, 27, 13, 0, tzinfo=timezone.utc)

    def test_transform_empty_list(self):
        """Empty OHLCV list returns empty result."""
        loader = PriceDataLoader()
        result = loader._transform_to_backtest_format([], "SOL")
        assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_price_loader.py::TestDataTransformation -v`
Expected: FAIL with "AttributeError: 'PriceDataLoader' object has no attribute '_transform_to_backtest_format'"

- [ ] **Step 3: Implement data transformation**

```python
# Add to src/data/loader.py PriceDataLoader class

from src.data.sources.base import OHLCV

    def _transform_to_backtest_format(
        self, ohlcv_data: list[OHLCV], token_symbol: str
    ) -> list[dict]:
        """
        Transform OHLCV candles to backtest engine format.

        Args:
            ohlcv_data: List of OHLCV candles from Birdeye
            token_symbol: Token symbol (e.g., "SOL")

        Returns:
            List of dicts with {token_symbol: close_price, timestamp: datetime}
        """
        return [
            {
                token_symbol: candle.close,
                "timestamp": candle.timestamp,
            }
            for candle in ohlcv_data
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_price_loader.py::TestDataTransformation -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/data/loader.py tests/data/test_price_loader.py
git commit -m "feat(data): add OHLCV to backtest format transformation"
```

---

### Task 5: PriceDataLoader - Main Load Method

**Files:**
- Modify: `src/data/loader.py`
- Modify: `tests/data/test_price_loader.py`

- [ ] **Step 1: Write the failing tests for load_price_history**

```python
# Add to tests/data/test_price_loader.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestLoadPriceHistory:
    """Test main load_price_history method."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self):
        """When cache exists, API is not called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)

            # Pre-populate cache
            cached_data = [{"SOL": 185.0, "timestamp": "2025-03-27T12:00:00+00:00"}]
            with patch.object(loader, "_build_cache_key", return_value="test_key"):
                loader._write_cache("test_key", cached_data)

                # Mock Birdeye to verify it's not called
                mock_birdeye = AsyncMock()
                loader._birdeye = mock_birdeye

                result, source = await loader.load_price_history("SOL", "1H", 7)

            assert source == "cache"
            assert result == cached_data
            mock_birdeye.get_ohlcv.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self):
        """When cache misses, API is called and result cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)

            mock_ohlcv = [
                OHLCV(
                    token="So11111111111111111111111111111111111111112",
                    open=180.0, high=185.0, low=178.0, close=183.5,
                    volume=1000000,
                    timestamp=datetime(2025, 3, 27, 12, 0, tzinfo=timezone.utc),
                    source="birdeye",
                ),
            ]

            mock_birdeye = AsyncMock()
            mock_birdeye.get_ohlcv.return_value = mock_ohlcv
            loader._birdeye = mock_birdeye

            with patch.object(loader, "_build_cache_key", return_value="test_key"):
                result, source = await loader.load_price_history("SOL", "1H", 7)

            assert source == "birdeye"
            assert len(result) == 1
            assert result[0]["SOL"] == 183.5
            mock_birdeye.get_ohlcv.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_token_raises_error(self):
        """Unknown token symbol raises ValueError."""
        loader = PriceDataLoader()

        with pytest.raises(ValueError, match="Unknown token"):
            await loader.load_price_history("UNKNOWN_TOKEN", "1H", 7)

    @pytest.mark.asyncio
    async def test_api_returns_empty_raises_error(self):
        """When API returns no data, raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)

            mock_birdeye = AsyncMock()
            mock_birdeye.get_ohlcv.return_value = []
            loader._birdeye = mock_birdeye

            with pytest.raises(ValueError, match="No price data available"):
                await loader.load_price_history("SOL", "1H", 7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_price_loader.py::TestLoadPriceHistory -v`
Expected: FAIL with "AttributeError: 'PriceDataLoader' object has no attribute 'load_price_history'"

- [ ] **Step 3: Implement load_price_history method**

```python
# Add to src/data/loader.py PriceDataLoader class

    def _get_birdeye(self) -> BirdeyeDataSource:
        """Get or create Birdeye data source."""
        if self._birdeye is None:
            self._birdeye = BirdeyeDataSource()
        return self._birdeye

    def _serialize_for_cache(self, data: list[dict]) -> list[dict]:
        """Serialize data for JSON cache (convert datetime to ISO string)."""
        result = []
        for item in data:
            serialized = {}
            for key, value in item.items():
                if isinstance(value, datetime):
                    serialized[key] = value.isoformat()
                else:
                    serialized[key] = value
            result.append(serialized)
        return result

    def _deserialize_from_cache(self, data: list[dict]) -> list[dict]:
        """Deserialize data from JSON cache (convert ISO string to datetime)."""
        result = []
        for item in data:
            deserialized = {}
            for key, value in item.items():
                if key == "timestamp" and isinstance(value, str):
                    deserialized[key] = datetime.fromisoformat(value)
                else:
                    deserialized[key] = value
            result.append(deserialized)
        return result

    async def load_price_history(
        self,
        token_symbol: str,
        interval: str = "1H",
        days: int = 30,
    ) -> tuple[list[dict], str]:
        """
        Load price history for a token.

        Args:
            token_symbol: Token symbol (e.g., "SOL")
            interval: Candle interval (1H, 4H, 1D)
            days: Number of days of history

        Returns:
            Tuple of (price_history, data_source)
            - price_history: List of {token: price, timestamp: datetime}
            - data_source: "cache" or "birdeye"

        Raises:
            ValueError: If token unknown or no data available
        """
        # Resolve token symbol to mint address
        mint_address = get_mint_address(token_symbol)
        if mint_address is None:
            raise ValueError(f"Unknown token: {token_symbol}")

        # Check cache first
        cache_key = self._build_cache_key(token_symbol, interval, days)
        cached_data = self._read_cache(cache_key)
        if cached_data is not None:
            return self._deserialize_from_cache(cached_data), "cache"

        # Fetch from Birdeye
        birdeye = self._get_birdeye()
        # Calculate limit: candles per day depends on interval
        candles_per_day = {"1H": 24, "4H": 6, "1D": 1}.get(interval, 24)
        limit = days * candles_per_day

        ohlcv_data = await birdeye.get_ohlcv(mint_address, interval, limit)

        if not ohlcv_data:
            raise ValueError(f"No price data available for {token_symbol}")

        # Transform to backtest format
        price_history = self._transform_to_backtest_format(ohlcv_data, token_symbol)

        # Cache the result
        self._write_cache(cache_key, self._serialize_for_cache(price_history))

        return price_history, "birdeye"

    async def close(self) -> None:
        """Close any open connections."""
        if self._birdeye is not None:
            await self._birdeye.close()
            self._birdeye = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/data/test_price_loader.py::TestLoadPriceHistory -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/data/loader.py tests/data/test_price_loader.py
git commit -m "feat(data): add main load_price_history method with cache"
```

---

### Task 6: Update API Schemas

**Files:**
- Modify: `src/api/schemas/strategy.py`

- [ ] **Step 1: Add new fields to BacktestRequest and BacktestResponse**

```python
# Modify src/api/schemas/strategy.py

# Update BacktestRequest class
class BacktestRequest(BaseModel):
    """Backtest parameters."""

    days: int = 30
    initial_capital: float = 10000.0
    slippage_bps: int = 100
    use_real_data: bool = True


# Update BacktestResponse class
class BacktestResponse(BaseModel):
    """Backtest results."""

    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    trade_count: int
    win_rate: float | None
    equity_curve: list[float]
    saved: bool
    data_source: str = "synthetic"
```

- [ ] **Step 2: Run existing API tests to verify no regression**

Run: `pytest tests/api/test_strategies.py -v`
Expected: PASS (existing tests still work)

- [ ] **Step 3: Commit**

```bash
git add src/api/schemas/strategy.py
git commit -m "feat(api): add use_real_data and data_source to backtest schemas"
```

---

### Task 7: Update Backtest Endpoint

**Files:**
- Modify: `src/api/routes/strategies.py`

- [ ] **Step 1: Read current backtest endpoint implementation**

Read `src/api/routes/strategies.py` lines 178-235 (the run_backtest function).

- [ ] **Step 2: Update endpoint to use PriceDataLoader**

Replace the synthetic price generation with real data fetching:

```python
# In src/api/routes/strategies.py

# Add import at top
from src.data.loader import PriceDataLoader

# Replace the run_backtest function (around line 178-235)
@router.post("/{strategy_id}/backtest", response_model=BacktestResponse)
async def run_backtest(
    strategy_id: int,
    data: BacktestRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BacktestResponse:
    """Run backtest on a strategy."""
    repo = StrategyRepository(session)
    strategy = await repo.get_by_id(strategy_id)

    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if strategy.creator_id != current_user.id and not strategy.is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Parse DSL
    strategy_dsl = parse_strategy(strategy.dsl_json)

    # Get price history
    data_source = "synthetic"

    if data.use_real_data:
        loader = PriceDataLoader()
        try:
            # Load data for first token (primary token)
            if not strategy_dsl.tokens:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Strategy has no tokens defined",
                )

            price_history, data_source = await loader.load_price_history(
                token_symbol=strategy_dsl.tokens[0],
                interval="1H",
                days=data.days,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        finally:
            await loader.close()
    else:
        # Generate synthetic price history (existing logic)
        base_price = 100.0
        base_time = datetime.now(timezone.utc) - timedelta(days=data.days)
        price_history = []

        for i in range(data.days * 24):  # Hourly candles
            timestamp = base_time + timedelta(hours=i)
            change = random.gauss(0.001, 0.02)
            base_price *= 1 + change

            tick = {"timestamp": timestamp}
            for token in strategy_dsl.tokens:
                tick[token] = base_price * (1 + random.gauss(0, 0.01))
            price_history.append(tick)

    # Run backtest
    engine = BacktestEngine(
        initial_capital=data.initial_capital,
        slippage_bps=data.slippage_bps,
    )
    result = engine.run(strategy_dsl, price_history)

    # Save results
    trade_repo = TradeRepository(session)
    perf_repo = PerformanceRepository(session)
    persistence = SimulationPersistence(trade_repo, perf_repo)
    await persistence.save_backtest_result(strategy.id, result)
    await session.commit()

    return BacktestResponse(
        total_return_pct=result.total_return_pct,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown_pct=result.max_drawdown_pct,
        trade_count=result.trade_count,
        win_rate=result.win_rate,
        equity_curve=result.equity_curve,
        saved=True,
        data_source=data_source,
    )
```

- [ ] **Step 3: Run API tests to verify no regression**

Run: `pytest tests/api/test_strategies.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/api/routes/strategies.py
git commit -m "feat(api): use real Birdeye data in backtest endpoint"
```

---

### Task 8: Add .cache to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Update .gitignore**

```
# .gitignore
.env
.cache/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .cache directory to gitignore"
```

---

### Task 9: Update Demo Script

**Files:**
- Modify: `scripts/demo_api.py`

- [ ] **Step 1: Update demo to show real data backtest**

Add after step 8 (Run Backtest) in the demo script:

```python
    # 8. Run a backtest with REAL data
    print("\n8. Run Backtest (Real Birdeye Data)")
    print("-" * 40)
    resp = requests.post(
        f"{BASE_URL}/strategies/{strategy_id}/backtest",
        json={
            "days": 7,  # 7 days to conserve API credits
            "initial_capital": 10000.0,
            "slippage_bps": 50,
            "use_real_data": True,
        },
        headers=headers,
    )
    print(f"   POST /strategies/{strategy_id}/backtest -> {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"   Data Source: {result['data_source']}")
        print(f"   Total Return: {result['total_return_pct']:.2f}%")
        print(f"   Max Drawdown: {result['max_drawdown_pct']:.2f}%")
        print(f"   Trade Count: {result['trade_count']}")
        print(f"   Sharpe Ratio: {result.get('sharpe_ratio', 'N/A')}")
        print(f"   Win Rate: {result.get('win_rate', 'N/A')}")
    else:
        print(f"   Error: {resp.json()}")
```

- [ ] **Step 2: Commit**

```bash
git add scripts/demo_api.py
git commit -m "feat(demo): show real Birdeye data in backtest demo"
```

---

### Task 10: Integration Test (Manual)

**No code changes - manual verification**

- [ ] **Step 1: Start the API server**

```bash
cd signal_composer
set JWT_SECRET=demo-secret && uvicorn src.api.main:app --reload
```

- [ ] **Step 2: Run the demo script**

```bash
python scripts/demo_api.py
```

- [ ] **Step 3: Verify output shows**

Expected output includes:
```
8. Run Backtest (Real Birdeye Data)
----------------------------------------
   POST /strategies/1/backtest -> 200
   Data Source: birdeye
   Total Return: X.XX%
   ...
```

- [ ] **Step 4: Run demo again to verify cache hit**

```bash
python scripts/demo_api.py
```

Expected: `Data Source: cache` on second run (same day).

- [ ] **Step 5: Check cache file created**

```bash
dir .cache\ohlcv
```

Expected: See `SOL_1H_7d_2025-03-27.json` file.

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Token address mapping | 4 unit tests |
| 2 | Cache key generation | 2 unit tests |
| 3 | Cache read/write | 4 unit tests |
| 4 | Data transformation | 2 unit tests |
| 5 | Main load method | 4 unit tests |
| 6 | API schema updates | Regression tests |
| 7 | Backtest endpoint | Regression tests |
| 8 | Gitignore update | N/A |
| 9 | Demo script update | Manual |
| 10 | Integration test | Manual |

**Total: 10 tasks, ~16 unit tests, 1 manual integration test**
