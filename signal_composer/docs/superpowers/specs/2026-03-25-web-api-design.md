# Web API Design Spec

**Date:** 2026-03-25
**Status:** Draft
**Scope:** FastAPI REST API for SignalComposer

## Overview

REST API exposing SignalComposer's strategy management and backtesting functionality. Enables frontend applications to create strategies, run backtests, and view results.

## Decisions

| Decision | Choice |
|----------|--------|
| Authentication | Wallet-based (Solana signature + JWT) |
| Scope | Core CRUD + Backtest |
| Backtest execution | Synchronous |
| Documentation | Swagger UI + ReDoc |
| Project structure | `src/api/` package |
| Architecture | Repository injection via FastAPI Depends |

## File Structure

```
src/api/
├── __init__.py
├── main.py              # FastAPI app, CORS, lifespan
├── dependencies.py      # get_db_session, get_current_user
├── auth/
│   ├── __init__.py
│   ├── wallet.py        # Wallet signature verification
│   └── jwt.py           # JWT token creation/validation
├── routes/
│   ├── __init__.py
│   ├── auth.py          # POST /auth/challenge, POST /auth/verify
│   ├── strategies.py    # CRUD + backtest
│   ├── performance.py   # GET performance history
│   └── trades.py        # GET trade history
└── schemas/
    ├── __init__.py
    ├── auth.py          # ChallengeRequest, TokenResponse
    ├── strategy.py      # StrategyCreate, StrategyResponse, etc.
    ├── performance.py   # PerformanceResponse
    └── trade.py         # TradeResponse
```

## Authentication Flow

Wallet auth uses challenge-response:

1. **Request challenge:** `POST /auth/challenge { wallet_address }`
   Returns: `{ challenge: "signalcomposer:<nonce>:<timestamp>" }`

2. **User signs** the challenge string with their Solana wallet (Ed25519)

3. **Verify signature:** `POST /auth/verify { wallet_address, signature, challenge }`
   Server verifies Ed25519 signature, returns: `{ access_token: "jwt..." }`

4. **Authenticated requests** include header: `Authorization: Bearer <jwt>`

**Challenge security:**
- Challenge format: `signalcomposer:<uuid4>:<unix_timestamp>`
- Challenge TTL: 5 minutes (reject if timestamp too old)
- Nonce stored in memory dict (or Redis in production) to prevent replay
- Each nonce valid for single use only

**JWT payload:**
```json
{
  "sub": "wallet_address",
  "user_id": 123,
  "exp": 1234567890
}
```

**User ID derivation:** On verify, lookup user by wallet_address using `UserRepository.get_or_create()`. The returned `user.id` goes into JWT.

**Token expiry:** 24 hours (configurable via `JWT_EXPIRY_HOURS` env var). No refresh tokens in v1 - user re-authenticates when expired.

## API Endpoints

### Auth (public)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/challenge` | Get challenge string to sign |
| POST | `/auth/verify` | Submit signature, get JWT |

### Strategies (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/strategies` | Create strategy (validates DSL) |
| GET | `/strategies` | List user's strategies |
| GET | `/strategies/{id}` | Get strategy details |
| PUT | `/strategies/{id}` | Update strategy |
| DELETE | `/strategies/{id}` | Delete strategy |
| POST | `/strategies/{id}/backtest` | Run backtest, save results |

### Performance & Trades (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/strategies/{id}/performance` | Get performance history |
| GET | `/strategies/{id}/trades` | Get trade history (paginated) |

### Health (public)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

## Request/Response Schemas

### Strategy Create
```python
class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    dsl: dict  # Full DSL JSON, validated by engine
    is_public: bool = False
```

### Strategy Response
```python
class StrategyResponse(BaseModel):
    id: int
    external_id: str
    name: str
    description: str
    dsl: dict
    is_public: bool
    status: str
    created_at: datetime
    updated_at: datetime
```

### Backtest Request
```python
class BacktestRequest(BaseModel):
    days: int = 30
    initial_capital: float = 10000.0
    slippage_bps: int = 100
```

### Backtest Response
```python
class BacktestResponse(BaseModel):
    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float
    trade_count: int
    win_rate: float | None
    equity_curve: list[float]
    saved: bool  # True if results were persisted
```

**Backtest behavior:** Results are persisted to database via `SimulationPersistence.save_backtest_result()`, which stores trades in `paper_trades` table and metrics in `strategy_performance` table. The performance history and trade list are then available via the GET endpoints.

### Performance Response
```python
class PerformanceResponse(BaseModel):
    id: int
    date: datetime
    total_return_pct: float
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    trade_count: int
    win_rate: float | None
```

### Trade Response
```python
class TradeResponse(BaseModel):
    id: int
    trigger_id: str
    token: str
    action: str  # "buy", "sell", "sell_all"
    amount: float
    price_at_exec: float
    timestamp: datetime
```

### Pagination (for trades)
```python
class PaginatedTradesResponse(BaseModel):
    items: list[TradeResponse]
    total: int
    page: int
    page_size: int
```

## Error Handling

### Standard Error Response
```python
class ErrorResponse(BaseModel):
    error: str       # Error code
    message: str     # Human-readable message
    details: dict | None = None
```

### HTTP Status Codes
| Code | When |
|------|------|
| 400 | Invalid request body, DSL validation fails |
| 401 | Missing/invalid JWT token |
| 403 | Accessing another user's strategy |
| 404 | Strategy not found |
| 422 | Pydantic validation error |
| 500 | Unexpected server error |

### DSL Validation
DSL validation occurs on:
- `POST /strategies` (create)
- `PUT /strategies/{id}` (update)
- `POST /strategies/{id}/backtest` (before running)

Uses existing `engine.dsl.validator.validate_strategy()`. Returns 400 with error details:
```json
{
  "error": "validation_error",
  "message": "Invalid strategy DSL",
  "details": {
    "errors": ["Unknown token: XYZ", "Trigger 'buy_low' references undefined stream"]
  }
}
```

## Dependencies

Add to `pyproject.toml`:
```toml
"fastapi>=0.109",
"uvicorn>=0.27",
"python-jose[cryptography]>=3.3",
"solders>=0.21",
```

## Testing

### Test Structure
```
tests/api/
├── __init__.py
├── conftest.py          # TestClient, auth fixtures
├── test_auth.py
├── test_strategies.py
├── test_performance.py
└── test_trades.py
```

### Approach
- Unit tests for auth (signature verification, JWT creation/validation)
- Integration tests for each route using FastAPI `TestClient`
- Mock wallet signatures using known test keypairs
- Reuse existing `db_session` fixture for database tests

## Configuration

Environment variables:
```bash
# Existing
DATABASE_URL=postgresql+asyncpg://...

# New
JWT_SECRET=<random-secret-key>
JWT_EXPIRY_HOURS=24                    # Default: 24
CORS_ORIGINS=http://localhost:3000     # Comma-separated, default allows localhost:3000
CHALLENGE_TTL_MINUTES=5                # Default: 5
```

**Local development defaults:** If `CORS_ORIGINS` not set, defaults to `http://localhost:3000` for frontend dev.

## Run Command

```bash
uvicorn src.api.main:app --reload --port 8000
```

Access docs at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
