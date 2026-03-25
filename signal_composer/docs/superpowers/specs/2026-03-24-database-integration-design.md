# Database Integration Design Spec

**Date:** 2026-03-24
**Status:** Draft
**Builds on:** Core Engine (Plan 1), Simulation Engine (Plan 2)

---

## Summary

Integrate the existing simulation engine with PostgreSQL for persistent storage. This enables saving backtest results, tracking trade history, and persisting strategy definitions — making the simulation work actually usable beyond single CLI runs.

**Scope:** Full simulation integration with repository pattern, Alembic migrations, and Docker-based local development.

**Out of scope:** TimescaleDB hypertables (deferred to live data ingestion phase), Redis, API server.

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration scope | Full simulation | Makes simulation work usable, results persist |
| Data access pattern | Repository per entity | Clean separation, testable, matches codebase style |
| Migration tool | Alembic | Industry standard, auto-generates from models |
| Docker setup | Simple (PostgreSQL only) | Lean, add services when needed |

---

## Infrastructure

### Docker Compose

Single PostgreSQL 16 container for local development:

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: signal_composer
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

**Commands:**
- `docker-compose up -d` — start database
- `docker-compose down` — stop database
- `docker-compose down -v` — stop and delete data

### Environment Configuration

```bash
# .env.example
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer
SQL_ECHO=false
```

The existing `connection.py` already reads `DATABASE_URL` from environment.

### Alembic Setup

```
signal_composer/src/db/
├── alembic.ini
└── migrations/
    ├── env.py           # Async-compatible migration runner
    ├── script.py.mako   # Migration template
    └── versions/
        └── 001_initial_schema.py
```

**Commands:**
- `alembic upgrade head` — apply all migrations
- `alembic downgrade -1` — rollback one migration
- `alembic revision --autogenerate -m "description"` — generate migration from model changes

**Initial migration** creates all tables from existing models:
- users
- strategies
- strategy_performance
- paper_trades
- price_data
- portfolios

---

## Repository Layer

### Structure

```
signal_composer/src/db/
├── repositories/
│   ├── __init__.py
│   ├── base.py
│   ├── strategy_repository.py
│   ├── user_repository.py
│   ├── trade_repository.py
│   ├── performance_repository.py
│   └── portfolio_repository.py
```

### Base Repository

Generic base class with common CRUD operations:

```python
from typing import TypeVar, Generic
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model_class: type[T]):
        self.session = session
        self.model_class = model_class

    async def create(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, id: int) -> T | None:
        return await self.session.get(self.model_class, id)

    async def delete(self, id: int) -> bool:
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            return True
        return False
```

### Repository Methods

| Repository | Methods |
|------------|---------|
| **UserRepository** | `get_by_wallet(address)`, `get_or_create(address)` |
| **StrategyRepository** | `get_by_external_id(ext_id)`, `list_by_user(user_id)`, `list_public(limit, offset)`, `save_dsl(strategy_id, dsl_dict)` |
| **TradeRepository** | `list_by_strategy(strategy_id, limit)`, `bulk_create(trades)`, `count_by_strategy(strategy_id)` |
| **PerformanceRepository** | `get_latest(strategy_id)`, `get_history(strategy_id, days)`, `upsert_daily(strategy_id, date, metrics)` |
| **PortfolioRepository** | `get_by_user_strategy(user_id, strategy_id)`, `update_value(portfolio_id, new_value)` |

### Session Management

Repositories receive session via constructor (dependency injection):

```python
async with get_session() as session:
    strategy_repo = StrategyRepository(session)
    user_repo = UserRepository(session)

    user = await user_repo.get_or_create("wallet_address_here")
    strategy = await strategy_repo.create(Strategy(...))
```

---

## Simulation Integration

### Persistence Service

New service that bridges simulation engine with database:

```
signal_composer/src/simulation/
├── ... (existing files)
└── persistence.py
```

```python
class SimulationPersistence:
    """Bridges simulation engine with database storage."""

    def __init__(
        self,
        trade_repo: TradeRepository,
        performance_repo: PerformanceRepository,
    ):
        self.trade_repo = trade_repo
        self.performance_repo = performance_repo

    async def save_backtest_result(
        self,
        strategy_id: int,
        result: BacktestResult,
    ) -> None:
        """
        Save complete backtest results to database.

        - Converts TradeRecord objects to PaperTrade models
        - Creates performance snapshot from metrics
        """
        # Save trades
        paper_trades = [
            PaperTrade(
                strategy_id=strategy_id,
                trigger_id=t.trigger_id,
                token=t.token,
                action=t.action.value,
                amount=t.amount,
                price_at_exec=t.price_at_exec,
                timestamp=t.timestamp,
            )
            for t in result.trades
        ]
        await self.trade_repo.bulk_create(paper_trades)

        # Save performance snapshot
        await self.performance_repo.upsert_daily(
            strategy_id=strategy_id,
            date=datetime.now(timezone.utc),
            total_return_pct=result.total_return_pct,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            trade_count=result.trade_count,
            win_rate=result.win_rate,
        )
```

### Data Flow

```
User runs: signal-composer backtest strategy.json --save
                            │
                            ▼
                    Parse strategy DSL
                            │
                            ▼
                 ┌──────────────────────┐
                 │   BacktestEngine     │
                 │      .run()          │
                 └──────────┬───────────┘
                            │
                            ▼
                     BacktestResult
                  (trades, metrics, equity_curve)
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
    SimulationPersistence         Print to console
     .save_backtest_result()       (existing behavior)
              │
    ┌─────────┴─────────┐
    ▼                   ▼
TradeRepository    PerformanceRepository
.bulk_create()     .upsert_daily()
    │                   │
    ▼                   ▼
paper_trades       strategy_performance
  table                table
```

### CLI Changes

Add `--save` flag to backtest command:

```python
# In cli.py
backtest_parser.add_argument(
    "--save",
    action="store_true",
    help="Save results to database",
)
```

**Behavior:**
- Without `--save`: prints results to console (current behavior, no DB required)
- With `--save`: prints results AND persists to database

This keeps the CLI usable without a database running.

---

## Testing Strategy

### Test Database

Separate database for tests: `signal_composer_test`

```python
# tests/db/conftest.py
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer_test"
```

### Fixtures

```python
@pytest.fixture
async def db_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(db_engine):
    """Fresh session for each test."""
    async_session = async_sessionmaker(db_engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def strategy_repo(db_session):
    """StrategyRepository with test session."""
    return StrategyRepository(db_session)

@pytest.fixture
async def sample_user(db_session):
    """Pre-created user for tests."""
    user = User(wallet_address="test_wallet_123")
    db_session.add(user)
    await db_session.flush()
    return user
```

### Test Structure

```
signal_composer/tests/db/
├── __init__.py
├── conftest.py
├── test_user_repository.py
├── test_strategy_repository.py
├── test_trade_repository.py
├── test_performance_repository.py
└── test_persistence.py
```

### Test Coverage

| Area | Tests |
|------|-------|
| Repository CRUD | Create, read, update, delete for each entity |
| Repository queries | `list_by_user`, `get_by_wallet`, etc. |
| Bulk operations | `bulk_create` for trades |
| Persistence integration | Save BacktestResult → verify in DB |
| Edge cases | Duplicate keys, missing foreign keys, empty results |

---

## File Structure (New/Modified)

```
signal_composer/
├── docker-compose.yml                    # NEW
├── .env.example                          # NEW
├── .env                                  # NEW (gitignored)
├── src/
│   ├── db/
│   │   ├── alembic.ini                   # NEW
│   │   ├── migrations/                   # NEW
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   │       └── 001_initial_schema.py
│   │   ├── repositories/                 # NEW
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── strategy_repository.py
│   │   │   ├── user_repository.py
│   │   │   ├── trade_repository.py
│   │   │   ├── performance_repository.py
│   │   │   └── portfolio_repository.py
│   │   ├── connection.py                 # EXISTS (minor updates)
│   │   ├── models.py                     # EXISTS (no changes)
│   │   └── __init__.py                   # EXISTS (add repo exports)
│   ├── simulation/
│   │   └── persistence.py                # NEW
│   └── cli.py                            # EXISTS (add --save flag)
└── tests/
    └── db/                               # NEW
        ├── __init__.py
        ├── conftest.py
        ├── test_user_repository.py
        ├── test_strategy_repository.py
        ├── test_trade_repository.py
        ├── test_performance_repository.py
        └── test_persistence.py
```

---

## Cloud Migration Path

When ready to move from local Docker to TimescaleDB Cloud:

1. Create TimescaleDB Cloud instance (free tier: 25GB)
2. Update `DATABASE_URL` in `.env` to cloud connection string
3. Run `alembic upgrade head` against cloud database
4. No code changes required — same PostgreSQL-compatible interface

Future phase will add TimescaleDB hypertables for `price_data` table when live data ingestion is implemented.

---

## Dependencies

Already in `pyproject.toml`:
- `sqlalchemy>=2.0` ✓
- `asyncpg>=0.29` ✓

**Add:**
- `alembic>=1.13`

---

## Success Criteria

1. `docker-compose up -d` starts PostgreSQL locally
2. `alembic upgrade head` creates all tables
3. All repository tests pass
4. `signal-composer backtest strategy.json --save` persists results to database
5. Results can be queried: trades, performance snapshots
