# Real Price Data Integration - Design Spec

## Goal

Replace synthetic random price data in backtests with real historical data from Birdeye API, enabling meaningful strategy validation against actual market movements.

## Scope

**In scope:**
- Fetch historical OHLCV data from Birdeye for established tokens (SOL, USDC, etc.)
- Simple file-based caching to conserve API credits
- Integration with existing backtest endpoint
- Flexible duration (user-specified days)

**Out of scope (future work):**
- Database-backed cache with overlap optimization
- Meme coin support (shorter history)
- Multiple data source fallbacks (CoinGecko, etc.)

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Backtest API   │────▶│  PriceDataLoader │────▶│ JSON Cache  │
│  /backtest      │     │  (new component) │     │ .cache/     │
└─────────────────┘     └────────┬─────────┘     └─────────────┘
                                 │
                                 │ cache miss
                                 ▼
                        ┌────────────────────┐
                        │ BirdeyeDataSource  │
                        │ (already exists)   │
                        └────────────────────┘
```

### Components

**New:**
- `PriceDataLoader` class in `src/data/loader.py`
  - Orchestrates cache check → API fetch → cache write
  - Transforms OHLCV data to backtest format

**Modified:**
- `src/api/routes/strategies.py` - Use PriceDataLoader instead of synthetic data

**Unchanged:**
- `BirdeyeDataSource` - Already implements `get_ohlcv()`
- `BacktestEngine` - Already accepts price history list

## Cache Design

### File Structure

```
.cache/
  ohlcv/
    SOL_1h_30d_2025-03-27.json
    SOL_1h_7d_2025-03-25.json
```

### File Naming

Format: `{token}_{interval}_{days}d_{date}.json`

- `token`: Token symbol (SOL, not full mint address for readability)
- `interval`: Candle interval (1h, 4h, 1d)
- `days`: Number of days requested
- `date`: Request date (YYYY-MM-DD)

### Cache Logic

1. Build cache key from request parameters
2. Check if cache file exists
3. If hit: load JSON and return
4. If miss: fetch from Birdeye → save JSON → return

### Expiration

Files include today's date in the name:
- Same-day requests reuse cache
- Next day creates new cache key (fresh fetch)
- Old files can be manually deleted

## Data Transformation

Birdeye returns OHLCV candles:
```json
[
  {"timestamp": 1711540800, "open": 185.2, "high": 186.1, "low": 184.8, "close": 185.9, "volume": 12345},
  ...
]
```

Backtest engine expects:
```python
[
  {"SOL": 185.9, "timestamp": datetime(...)},
  ...
]
```

Transformation uses `close` price from each candle.

## API Changes

### Backtest Request

Add optional `use_real_data` flag (default: `true`):

```json
{
  "days": 30,
  "initial_capital": 10000.0,
  "slippage_bps": 50,
  "use_real_data": true
}
```

### Backtest Response

Add `data_source` field:

```json
{
  "total_return_pct": 12.5,
  "data_source": "birdeye",
  ...
}
```

Possible values: `"birdeye"`, `"cache"`, `"synthetic"`

## Error Handling

| Scenario | Response |
|----------|----------|
| BIRDEYE_API_KEY not set | 500: "BIRDEYE_API_KEY environment variable not configured" |
| Rate limit (429) | 429: "Birdeye rate limit exceeded. Try again later." |
| Token not found | 400: "No price data available for {token}" |
| Insufficient history | 400: "Only {n} days of history available for {token}" |
| Network timeout | Retry once, then 502: "Failed to fetch price data" |
| Corrupt cache | Delete file, re-fetch |
| Cache dir missing | Auto-create `.cache/ohlcv/` |

## Token Address Mapping

Strategies use token symbols (e.g., "SOL") but Birdeye needs mint addresses.

Add token mapping in `src/data/tokens.py`:

```python
TOKEN_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    # Add more as needed
}
```

## Testing

### Unit Tests (`tests/data/test_price_loader.py`)

- Cache key generation
- Cache hit returns data without API call
- Cache miss triggers API call and saves file
- Data transformation correctness
- Error handling for missing API key

### Integration Tests (`tests/data/test_birdeye_integration.py`)

- Live fetch for SOL (marked `@pytest.mark.integration`)
- Skipped in CI, run manually

### Manual Testing

Update `scripts/demo_api.py` to demonstrate real data backtest.

## File Changes Summary

| File | Change |
|------|--------|
| `src/data/loader.py` | NEW - PriceDataLoader class |
| `src/data/tokens.py` | NEW - Token symbol to mint mapping |
| `src/api/routes/strategies.py` | MODIFY - Use PriceDataLoader |
| `src/api/schemas/strategy.py` | MODIFY - Add use_real_data, data_source |
| `tests/data/test_price_loader.py` | NEW - Unit tests |
| `tests/data/test_birdeye_integration.py` | NEW - Integration test |
| `scripts/demo_api.py` | MODIFY - Demo real data |
| `.gitignore` | MODIFY - Add .cache/ |

## Future Improvements

When this prototype proves value:

1. **Database cache** - PostgreSQL table for OHLCV with proper range queries
2. **Overlap optimization** - Fetch only missing data ranges
3. **Multiple sources** - CoinGecko fallback for rate limits
4. **Meme coin support** - Handle tokens with limited history
5. **Cache warming** - Background job to pre-fetch popular tokens
