# Database Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate PostgreSQL with the simulation engine so backtest results, trades, and strategies persist to a database.

**Architecture:** Docker-based PostgreSQL for local dev, Alembic for migrations, repository pattern for data access, and a persistence service bridging the simulation engine to storage.

**Tech Stack:** PostgreSQL 16, SQLAlchemy 2.0 (async), Alembic, asyncpg, Docker Compose

**Spec:** `docs/superpowers/specs/2026-03-24-database-integration-design.md`

---

## File Structure

```
signal_composer/
├── docker-compose.yml                    # PostgreSQL container
├── .env.example                          # Environment template
├── src/db/
│   ├── alembic.ini                       # Alembic config
│   ├── migrations/
│   │   ├── env.py                        # Async migration runner
│   │   ├── script.py.mako                # Migration template
│   │   └── versions/
│   │       └── 001_initial_schema.py     # Initial tables
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py                       # BaseRepository
│   │   ├── user_repository.py
│   │   ├── strategy_repository.py
│   │   ├── trade_repository.py
│   │   └── performance_repository.py
│   ├── connection.py                     # (exists - minor update)
│   └── __init__.py                       # (exists - add exports)
├── src/simulation/
│   └── persistence.py                    # SimulationPersistence service
├── src/cli.py                            # (exists - add --save flag)
└── tests/db/
    ├── __init__.py
    ├── conftest.py                       # DB test fixtures
    ├── test_user_repository.py
    ├── test_strategy_repository.py
    ├── test_trade_repository.py
    ├── test_performance_repository.py
    └── test_persistence.py
```

---

## Task 1: Docker and Environment Setup

**Files:**
- Create: `signal_composer/docker-compose.yml`
- Create: `signal_composer/.env.example`
- Modify: `signal_composer/.gitignore`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    container_name: signal_composer_db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: signal_composer
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

- [ ] **Step 2: Create .env.example**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer
SQL_ECHO=false

# Test database
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer_test
```

- [ ] **Step 3: Update .gitignore to exclude .env**

Add to `.gitignore`:
```
.env
```

- [ ] **Step 4: Create local .env file (copy from example)**

```bash
cp .env.example .env
```

- [ ] **Step 5: Start PostgreSQL and verify**

Run: `docker-compose up -d`
Run: `docker-compose ps`
Expected: `signal_composer_db` running, healthy

- [ ] **Step 6: Create test database**

Run: `docker exec -it signal_composer_db psql -U postgres -c "CREATE DATABASE signal_composer_test;"`
Expected: `CREATE DATABASE`

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example .gitignore
git commit -m "infra: add Docker Compose for PostgreSQL"
```

---

## Task 2: Alembic Setup

**Files:**
- Create: `signal_composer/src/db/alembic.ini`
- Create: `signal_composer/src/db/migrations/env.py`
- Create: `signal_composer/src/db/migrations/script.py.mako`
- Modify: `signal_composer/pyproject.toml` (add alembic dependency)

- [ ] **Step 1: Add alembic to dependencies**

In `pyproject.toml`, add to dependencies:
```toml
"alembic>=1.13",
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -e ".[dev]"`

- [ ] **Step 3: Create alembic.ini**

```ini
[alembic]
script_location = migrations
prepend_sys_path = .

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Create migrations directory**

```bash
mkdir -p src/db/migrations/versions
```

- [ ] **Step 5: Create script.py.mako template**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Create env.py for async migrations**

```python
"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.db.models import Base

# Load environment variables
load_dotenv()

# Alembic Config object
config = context.config

# Set database URL from environment
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", ""))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/db/alembic.ini src/db/migrations/
git commit -m "infra: add Alembic migration setup"
```

---

## Task 3: Initial Migration

**Files:**
- Create: `signal_composer/src/db/migrations/versions/001_initial_schema.py`

- [ ] **Step 1: Generate initial migration**

Run from `signal_composer/src/db`:
```bash
cd src/db && alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 2: Rename migration file to 001_initial_schema.py**

The generated file will have a random revision ID. Rename it to `001_initial_schema.py` for clarity (keep the revision ID inside the file).

- [ ] **Step 3: Review generated migration**

Verify it creates all tables: users, strategies, strategy_performance, paper_trades, price_data, portfolios

- [ ] **Step 4: Run migration**

```bash
alembic upgrade head
```

Expected: Tables created in database

- [ ] **Step 5: Verify tables exist**

```bash
docker exec -it signal_composer_db psql -U postgres -d signal_composer -c "\dt"
```

Expected: List of 6 tables

- [ ] **Step 6: Commit**

```bash
git add src/db/migrations/versions/
git commit -m "db: add initial schema migration"
```

---

## Task 4: Base Repository

**Files:**
- Create: `signal_composer/src/db/repositories/__init__.py`
- Create: `signal_composer/src/db/repositories/base.py`
- Create: `signal_composer/tests/db/__init__.py`
- Create: `signal_composer/tests/db/conftest.py`

- [ ] **Step 1: Create repositories __init__.py**

```python
"""Database repositories."""

from .base import BaseRepository

__all__ = ["BaseRepository"]
```

- [ ] **Step 2: Create test db package __init__.py**

```python
"""Database tests."""
```

- [ ] **Step 3: Create test conftest.py with fixtures**

```python
"""Database test fixtures."""

import os
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, User, Strategy

# Use test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signal_composer_test"
)


@pytest.fixture
async def db_engine():
    """Create test database engine and tables."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Fresh database session for each test."""
    async_session_maker = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_user(db_session):
    """Pre-created user for tests."""
    user = User(wallet_address="test_wallet_abc123")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def sample_strategy(db_session, sample_user):
    """Pre-created strategy for tests."""
    strategy = Strategy(
        external_id="test_strategy_001",
        creator_id=sample_user.id,
        name="Test Strategy",
        description="A test strategy",
        dsl_json={"id": "test_strategy_001", "name": "Test Strategy", "tokens": ["SOL"]},
        is_public=True,
        status="active",
    )
    db_session.add(strategy)
    await db_session.flush()
    return strategy
```

- [ ] **Step 4: Write failing test for BaseRepository**

Create `tests/db/test_base_repository.py`:

```python
"""Tests for BaseRepository."""

import pytest
from src.db.models import User
from src.db.repositories.base import BaseRepository


class TestBaseRepository:
    """Test base repository CRUD operations."""

    @pytest.mark.asyncio
    async def test_create(self, db_session):
        """Create adds entity to database."""
        repo = BaseRepository(db_session, User)
        user = User(wallet_address="new_wallet_123")

        result = await repo.create(user)

        assert result.id is not None
        assert result.wallet_address == "new_wallet_123"

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session, sample_user):
        """Get by ID returns entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.get_by_id(sample_user.id)

        assert result is not None
        assert result.id == sample_user.id
        assert result.wallet_address == sample_user.wallet_address

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session):
        """Get by ID returns None for missing entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.get_by_id(99999)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, db_session, sample_user):
        """Delete removes entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.delete(sample_user.id)

        assert result is True
        assert await repo.get_by_id(sample_user.id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db_session):
        """Delete returns False for missing entity."""
        repo = BaseRepository(db_session, User)

        result = await repo.delete(99999)

        assert result is False
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/db/test_base_repository.py -v`
Expected: FAIL (BaseRepository not implemented)

- [ ] **Step 6: Implement BaseRepository**

```python
"""Base repository with common CRUD operations."""

from typing import TypeVar, Generic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository with common CRUD operations."""

    def __init__(self, session: AsyncSession, model_class: type[T]):
        """Initialize repository with session and model class."""
        self.session = session
        self.model_class = model_class

    async def create(self, obj: T) -> T:
        """Create a new entity."""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get_by_id(self, id: int) -> T | None:
        """Get entity by ID."""
        return await self.session.get(self.model_class, id)

    async def delete(self, id: int) -> bool:
        """Delete entity by ID. Returns True if deleted."""
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()
            return True
        return False

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """List all entities with pagination."""
        stmt = select(self.model_class).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/db/test_base_repository.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/db/repositories/ tests/db/
git commit -m "feat(db): add BaseRepository with CRUD operations"
```

---

## Task 5: User Repository

**Files:**
- Create: `signal_composer/src/db/repositories/user_repository.py`
- Create: `signal_composer/tests/db/test_user_repository.py`
- Modify: `signal_composer/src/db/repositories/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for UserRepository."""

import pytest
from src.db.models import User
from src.db.repositories.user_repository import UserRepository


class TestUserRepository:
    """Test user repository operations."""

    @pytest.mark.asyncio
    async def test_get_by_wallet(self, db_session, sample_user):
        """Get user by wallet address."""
        repo = UserRepository(db_session)

        result = await repo.get_by_wallet(sample_user.wallet_address)

        assert result is not None
        assert result.id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_by_wallet_not_found(self, db_session):
        """Get by wallet returns None for unknown address."""
        repo = UserRepository(db_session)

        result = await repo.get_by_wallet("unknown_wallet")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, db_session, sample_user):
        """Get or create returns existing user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create(sample_user.wallet_address)

        assert result.id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, db_session):
        """Get or create creates new user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create("brand_new_wallet")

        assert result.id is not None
        assert result.wallet_address == "brand_new_wallet"

    @pytest.mark.asyncio
    async def test_get_or_create_with_username(self, db_session):
        """Get or create can set username for new user."""
        repo = UserRepository(db_session)

        result = await repo.get_or_create("wallet_with_name", username="trader123")

        assert result.username == "trader123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_user_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement UserRepository**

```python
"""User repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, User)

    async def get_by_wallet(self, wallet_address: str) -> User | None:
        """Get user by wallet address."""
        stmt = select(User).where(User.wallet_address == wallet_address)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, wallet_address: str, username: str | None = None
    ) -> User:
        """Get existing user or create new one."""
        user = await self.get_by_wallet(wallet_address)
        if user:
            return user

        user = User(wallet_address=wallet_address, username=username)
        return await self.create(user)
```

- [ ] **Step 4: Update __init__.py**

```python
"""Database repositories."""

from .base import BaseRepository
from .user_repository import UserRepository

__all__ = ["BaseRepository", "UserRepository"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/db/test_user_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/repositories/ tests/db/test_user_repository.py
git commit -m "feat(db): add UserRepository with get_by_wallet and get_or_create"
```

---

## Task 6: Strategy Repository

**Files:**
- Create: `signal_composer/src/db/repositories/strategy_repository.py`
- Create: `signal_composer/tests/db/test_strategy_repository.py`
- Modify: `signal_composer/src/db/repositories/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for StrategyRepository."""

import pytest
from src.db.models import Strategy
from src.db.repositories.strategy_repository import StrategyRepository


class TestStrategyRepository:
    """Test strategy repository operations."""

    @pytest.mark.asyncio
    async def test_get_by_external_id(self, db_session, sample_strategy):
        """Get strategy by external ID."""
        repo = StrategyRepository(db_session)

        result = await repo.get_by_external_id(sample_strategy.external_id)

        assert result is not None
        assert result.id == sample_strategy.id

    @pytest.mark.asyncio
    async def test_get_by_external_id_not_found(self, db_session):
        """Get by external ID returns None for unknown."""
        repo = StrategyRepository(db_session)

        result = await repo.get_by_external_id("unknown_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_user(self, db_session, sample_user, sample_strategy):
        """List strategies by user."""
        repo = StrategyRepository(db_session)

        result = await repo.list_by_user(sample_user.id)

        assert len(result) == 1
        assert result[0].id == sample_strategy.id

    @pytest.mark.asyncio
    async def test_list_by_user_empty(self, db_session, sample_user):
        """List by user returns empty for user with no strategies."""
        repo = StrategyRepository(db_session)

        # sample_user has no strategies yet (no sample_strategy fixture)
        result = await repo.list_by_user(sample_user.id)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_public(self, db_session, sample_strategy):
        """List public strategies."""
        repo = StrategyRepository(db_session)

        result = await repo.list_public(limit=10)

        assert len(result) == 1
        assert result[0].is_public is True

    @pytest.mark.asyncio
    async def test_save_dsl(self, db_session, sample_strategy):
        """Save updated DSL JSON."""
        repo = StrategyRepository(db_session)
        new_dsl = {"id": "test", "name": "Updated", "tokens": ["ETH"]}

        result = await repo.save_dsl(sample_strategy.id, new_dsl)

        assert result.dsl_json == new_dsl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_strategy_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement StrategyRepository**

```python
"""Strategy repository."""

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Strategy
from .base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    """Repository for Strategy operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, Strategy)

    async def get_by_external_id(self, external_id: str) -> Strategy | None:
        """Get strategy by external ID."""
        stmt = select(Strategy).where(Strategy.external_id == external_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> list[Strategy]:
        """List strategies created by a user."""
        stmt = (
            select(Strategy)
            .where(Strategy.creator_id == user_id)
            .order_by(Strategy.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_public(self, limit: int = 100, offset: int = 0) -> list[Strategy]:
        """List public strategies."""
        stmt = (
            select(Strategy)
            .where(Strategy.is_public == True)
            .where(Strategy.status == "active")
            .order_by(Strategy.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_dsl(self, strategy_id: int, dsl_json: dict[str, Any]) -> Strategy:
        """Update strategy DSL JSON."""
        strategy = await self.get_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        strategy.dsl_json = dsl_json
        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy
```

- [ ] **Step 4: Update __init__.py**

```python
"""Database repositories."""

from .base import BaseRepository
from .user_repository import UserRepository
from .strategy_repository import StrategyRepository

__all__ = ["BaseRepository", "UserRepository", "StrategyRepository"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/db/test_strategy_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/repositories/ tests/db/test_strategy_repository.py
git commit -m "feat(db): add StrategyRepository with list_by_user and list_public"
```

---

## Task 7: Trade Repository

**Files:**
- Create: `signal_composer/src/db/repositories/trade_repository.py`
- Create: `signal_composer/tests/db/test_trade_repository.py`
- Modify: `signal_composer/src/db/repositories/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for TradeRepository."""

from datetime import datetime, timezone

import pytest
from src.db.models import PaperTrade
from src.db.repositories.trade_repository import TradeRepository


class TestTradeRepository:
    """Test trade repository operations."""

    @pytest.mark.asyncio
    async def test_list_by_strategy(self, db_session, sample_strategy):
        """List trades by strategy."""
        repo = TradeRepository(db_session)

        # Create some trades
        trade = PaperTrade(
            strategy_id=sample_strategy.id,
            trigger_id="buy_trigger",
            token="SOL",
            action="buy",
            amount=10.0,
            price_at_exec=100.0,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        await db_session.flush()

        result = await repo.list_by_strategy(sample_strategy.id)

        assert len(result) == 1
        assert result[0].token == "SOL"

    @pytest.mark.asyncio
    async def test_bulk_create(self, db_session, sample_strategy):
        """Bulk create trades."""
        repo = TradeRepository(db_session)

        trades = [
            PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id="trigger_1",
                token="SOL",
                action="buy",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
            ),
            PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id="trigger_2",
                token="SOL",
                action="sell",
                amount=5.0,
                price_at_exec=110.0,
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        result = await repo.bulk_create(trades)

        assert len(result) == 2
        assert all(t.id is not None for t in result)

    @pytest.mark.asyncio
    async def test_count_by_strategy(self, db_session, sample_strategy):
        """Count trades for a strategy."""
        repo = TradeRepository(db_session)

        # Create trades
        for i in range(3):
            trade = PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id=f"trigger_{i}",
                token="SOL",
                action="buy",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(trade)
        await db_session.flush()

        result = await repo.count_by_strategy(sample_strategy.id)

        assert result == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_trade_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TradeRepository**

```python
"""Trade repository."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PaperTrade
from .base import BaseRepository


class TradeRepository(BaseRepository[PaperTrade]):
    """Repository for PaperTrade operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, PaperTrade)

    async def list_by_strategy(
        self, strategy_id: int, limit: int = 100, offset: int = 0
    ) -> list[PaperTrade]:
        """List trades for a strategy, newest first."""
        stmt = (
            select(PaperTrade)
            .where(PaperTrade.strategy_id == strategy_id)
            .order_by(PaperTrade.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, trades: list[PaperTrade]) -> list[PaperTrade]:
        """Create multiple trades at once."""
        self.session.add_all(trades)
        await self.session.flush()
        for trade in trades:
            await self.session.refresh(trade)
        return trades

    async def count_by_strategy(self, strategy_id: int) -> int:
        """Count trades for a strategy."""
        stmt = (
            select(func.count())
            .select_from(PaperTrade)
            .where(PaperTrade.strategy_id == strategy_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
```

- [ ] **Step 4: Update __init__.py**

```python
"""Database repositories."""

from .base import BaseRepository
from .user_repository import UserRepository
from .strategy_repository import StrategyRepository
from .trade_repository import TradeRepository

__all__ = ["BaseRepository", "UserRepository", "StrategyRepository", "TradeRepository"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/db/test_trade_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/repositories/ tests/db/test_trade_repository.py
git commit -m "feat(db): add TradeRepository with bulk_create and list_by_strategy"
```

---

## Task 8: Performance Repository

**Files:**
- Create: `signal_composer/src/db/repositories/performance_repository.py`
- Create: `signal_composer/tests/db/test_performance_repository.py`
- Modify: `signal_composer/src/db/repositories/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for PerformanceRepository."""

from datetime import datetime, timezone, timedelta

import pytest
from src.db.models import StrategyPerformance
from src.db.repositories.performance_repository import PerformanceRepository


class TestPerformanceRepository:
    """Test performance repository operations."""

    @pytest.mark.asyncio
    async def test_get_latest(self, db_session, sample_strategy):
        """Get latest performance snapshot."""
        repo = PerformanceRepository(db_session)

        # Create performance records
        perf = StrategyPerformance(
            strategy_id=sample_strategy.id,
            date=datetime.now(timezone.utc),
            total_return_pct=10.5,
            sharpe_ratio=1.2,
            max_drawdown_pct=-5.0,
            trade_count=15,
            win_rate=60.0,
        )
        db_session.add(perf)
        await db_session.flush()

        result = await repo.get_latest(sample_strategy.id)

        assert result is not None
        assert result.total_return_pct == 10.5

    @pytest.mark.asyncio
    async def test_get_latest_none(self, db_session, sample_strategy):
        """Get latest returns None when no records."""
        repo = PerformanceRepository(db_session)

        result = await repo.get_latest(sample_strategy.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_history(self, db_session, sample_strategy):
        """Get performance history."""
        repo = PerformanceRepository(db_session)

        # Create historical records
        now = datetime.now(timezone.utc)
        for i in range(5):
            perf = StrategyPerformance(
                strategy_id=sample_strategy.id,
                date=now - timedelta(days=i),
                total_return_pct=float(i),
                trade_count=i,
            )
            db_session.add(perf)
        await db_session.flush()

        result = await repo.get_history(sample_strategy.id, days=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_upsert_daily_creates(self, db_session, sample_strategy):
        """Upsert creates new record."""
        repo = PerformanceRepository(db_session)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        result = await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=5.5,
            sharpe_ratio=0.8,
            max_drawdown_pct=-3.0,
            trade_count=10,
            win_rate=55.0,
        )

        assert result.id is not None
        assert result.total_return_pct == 5.5

    @pytest.mark.asyncio
    async def test_upsert_daily_updates(self, db_session, sample_strategy):
        """Upsert updates existing record."""
        repo = PerformanceRepository(db_session)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create initial
        await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=5.0,
            trade_count=10,
        )

        # Update
        result = await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=7.5,
            trade_count=12,
        )

        assert result.total_return_pct == 7.5
        assert result.trade_count == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_performance_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Implement PerformanceRepository**

```python
"""Performance repository."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import StrategyPerformance
from .base import BaseRepository


class PerformanceRepository(BaseRepository[StrategyPerformance]):
    """Repository for StrategyPerformance operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, StrategyPerformance)

    async def get_latest(self, strategy_id: int) -> StrategyPerformance | None:
        """Get most recent performance snapshot."""
        stmt = (
            select(StrategyPerformance)
            .where(StrategyPerformance.strategy_id == strategy_id)
            .order_by(StrategyPerformance.date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(
        self, strategy_id: int, days: int = 30
    ) -> list[StrategyPerformance]:
        """Get performance history for last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(StrategyPerformance)
            .where(StrategyPerformance.strategy_id == strategy_id)
            .where(StrategyPerformance.date >= cutoff)
            .order_by(StrategyPerformance.date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_daily(
        self,
        strategy_id: int,
        date: datetime,
        total_return_pct: float,
        sharpe_ratio: float | None = None,
        max_drawdown_pct: float | None = None,
        trade_count: int = 0,
        win_rate: float | None = None,
    ) -> StrategyPerformance:
        """Insert or update daily performance snapshot."""
        # Normalize date to start of day
        normalized_date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if exists
        stmt = select(StrategyPerformance).where(
            and_(
                StrategyPerformance.strategy_id == strategy_id,
                StrategyPerformance.date == normalized_date,
            )
        )
        result = await self.session.execute(stmt)
        perf = result.scalar_one_or_none()

        if perf:
            # Update existing
            perf.total_return_pct = total_return_pct
            perf.sharpe_ratio = sharpe_ratio
            perf.max_drawdown_pct = max_drawdown_pct
            perf.trade_count = trade_count
            perf.win_rate = win_rate
        else:
            # Create new
            perf = StrategyPerformance(
                strategy_id=strategy_id,
                date=normalized_date,
                total_return_pct=total_return_pct,
                sharpe_ratio=sharpe_ratio,
                max_drawdown_pct=max_drawdown_pct,
                trade_count=trade_count,
                win_rate=win_rate,
            )
            self.session.add(perf)

        await self.session.flush()
        await self.session.refresh(perf)
        return perf
```

- [ ] **Step 4: Update __init__.py**

```python
"""Database repositories."""

from .base import BaseRepository
from .user_repository import UserRepository
from .strategy_repository import StrategyRepository
from .trade_repository import TradeRepository
from .performance_repository import PerformanceRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "StrategyRepository",
    "TradeRepository",
    "PerformanceRepository",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/db/test_performance_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/db/repositories/ tests/db/test_performance_repository.py
git commit -m "feat(db): add PerformanceRepository with upsert_daily and get_history"
```

---

## Task 9: Simulation Persistence Service

**Files:**
- Create: `signal_composer/src/simulation/persistence.py`
- Create: `signal_composer/tests/db/test_persistence.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for SimulationPersistence service."""

from datetime import datetime, timezone

import pytest
from src.db.models import PaperTrade, StrategyPerformance
from src.db.repositories.trade_repository import TradeRepository
from src.db.repositories.performance_repository import PerformanceRepository
from src.simulation.persistence import SimulationPersistence
from src.simulation.executor import TradeRecord
from src.simulation.backtest import BacktestResult
from src.simulation.portfolio import Portfolio
from src.engine.dsl.types import ActionType


class TestSimulationPersistence:
    """Test simulation persistence service."""

    @pytest.mark.asyncio
    async def test_save_backtest_result(self, db_session, sample_strategy):
        """Save complete backtest result to database."""
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)

        # Create a backtest result
        trades = [
            TradeRecord(
                action=ActionType.BUY,
                token="SOL",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
                trigger_id="buy_trigger",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="SOL",
                amount=10.0,
                price_at_exec=110.0,
                timestamp=datetime.now(timezone.utc),
                trigger_id="sell_trigger",
                slippage_bps=100,
            ),
        ]

        result = BacktestResult(
            total_return_pct=10.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=-5.0,
            trade_count=2,
            win_rate=100.0,
            equity_curve=[10000.0, 10500.0, 11000.0],
            trades=trades,
            final_portfolio=Portfolio(initial_balance=11000.0),
        )

        await persistence.save_backtest_result(sample_strategy.id, result)

        # Verify trades saved
        saved_trades = await trade_repo.list_by_strategy(sample_strategy.id)
        assert len(saved_trades) == 2

        # Verify performance saved
        perf = await perf_repo.get_latest(sample_strategy.id)
        assert perf is not None
        assert perf.total_return_pct == 10.0
        assert perf.sharpe_ratio == 1.5

    @pytest.mark.asyncio
    async def test_save_backtest_empty_trades(self, db_session, sample_strategy):
        """Save backtest with no trades."""
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)

        result = BacktestResult(
            total_return_pct=0.0,
            sharpe_ratio=None,
            max_drawdown_pct=0.0,
            trade_count=0,
            win_rate=0.0,
            equity_curve=[10000.0],
            trades=[],
            final_portfolio=Portfolio(initial_balance=10000.0),
        )

        await persistence.save_backtest_result(sample_strategy.id, result)

        # Verify no trades saved
        saved_trades = await trade_repo.list_by_strategy(sample_strategy.id)
        assert len(saved_trades) == 0

        # Verify performance still saved
        perf = await perf_repo.get_latest(sample_strategy.id)
        assert perf is not None
        assert perf.trade_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_persistence.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SimulationPersistence**

```python
"""Persistence service for simulation results."""

from datetime import datetime, timezone

from ..db.models import PaperTrade
from ..db.repositories.trade_repository import TradeRepository
from ..db.repositories.performance_repository import PerformanceRepository
from .backtest import BacktestResult


class SimulationPersistence:
    """Bridges simulation engine with database storage."""

    def __init__(
        self,
        trade_repo: TradeRepository,
        performance_repo: PerformanceRepository,
    ):
        """Initialize with repositories."""
        self.trade_repo = trade_repo
        self.performance_repo = performance_repo

    async def save_backtest_result(
        self,
        strategy_id: int,
        result: BacktestResult,
    ) -> None:
        """
        Save complete backtest results to database.

        Converts TradeRecord objects to PaperTrade models and
        creates a performance snapshot from metrics.
        """
        # Save trades (if any)
        if result.trades:
            paper_trades = [
                PaperTrade(
                    strategy_id=strategy_id,
                    trigger_id=trade.trigger_id,
                    token=trade.token,
                    action=trade.action.value,
                    amount=trade.amount,
                    price_at_exec=trade.price_at_exec,
                    timestamp=trade.timestamp,
                )
                for trade in result.trades
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_persistence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/simulation/persistence.py tests/db/test_persistence.py
git commit -m "feat(simulation): add SimulationPersistence to save backtest results"
```

---

## Task 10: CLI --save Flag

**Files:**
- Modify: `signal_composer/src/cli.py`

- [ ] **Step 1: Update CLI to add --save flag**

Add to `backtest_parser` arguments:
```python
backtest_parser.add_argument(
    "--save",
    action="store_true",
    help="Save results to database",
)
```

- [ ] **Step 2: Update cmd_backtest function**

Add after printing results:
```python
if args.save:
    from .db.connection import get_session
    from .db.repositories.strategy_repository import StrategyRepository
    from .db.repositories.trade_repository import TradeRepository
    from .db.repositories.performance_repository import PerformanceRepository
    from .db.repositories.user_repository import UserRepository
    from .simulation.persistence import SimulationPersistence

    async with get_session() as session:
        # Get or create user (placeholder wallet for CLI)
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create("cli_user_local")

        # Get or create strategy
        strategy_repo = StrategyRepository(session)
        db_strategy = await strategy_repo.get_by_external_id(strategy.id)

        if not db_strategy:
            from .db.models import Strategy as StrategyModel
            db_strategy = StrategyModel(
                external_id=strategy.id,
                creator_id=user.id,
                name=strategy.name,
                description=strategy.description or "",
                dsl_json=strategy_json,
                status="active",
            )
            db_strategy = await strategy_repo.create(db_strategy)

        # Save results
        trade_repo = TradeRepository(session)
        perf_repo = PerformanceRepository(session)
        persistence = SimulationPersistence(trade_repo, perf_repo)
        await persistence.save_backtest_result(db_strategy.id, result)

        print(f"\nResults saved to database (strategy_id={db_strategy.id})")
```

- [ ] **Step 3: Test CLI manually**

Run: `signal-composer backtest examples/sample_strategy.json --days 10 --save`
Expected: Results printed AND "Results saved to database" message

- [ ] **Step 4: Verify data in database**

```bash
docker exec -it signal_composer_db psql -U postgres -d signal_composer -c "SELECT * FROM strategies;"
docker exec -it signal_composer_db psql -U postgres -d signal_composer -c "SELECT * FROM strategy_performance;"
```

- [ ] **Step 5: Commit**

```bash
git add src/cli.py
git commit -m "feat(cli): add --save flag to persist backtest results"
```

---

## Task 11: Update DB Module Exports

**Files:**
- Modify: `signal_composer/src/db/__init__.py`

- [ ] **Step 1: Update __init__.py to export repositories**

```python
"""Database module."""

from .connection import get_session, init_db, drop_db, engine
from .models import User, Strategy, StrategyPerformance, PaperTrade, PriceData, Portfolio
from .repositories import (
    BaseRepository,
    UserRepository,
    StrategyRepository,
    TradeRepository,
    PerformanceRepository,
)

__all__ = [
    # Connection
    "get_session",
    "init_db",
    "drop_db",
    "engine",
    # Models
    "User",
    "Strategy",
    "StrategyPerformance",
    "PaperTrade",
    "PriceData",
    "Portfolio",
    # Repositories
    "BaseRepository",
    "UserRepository",
    "StrategyRepository",
    "TradeRepository",
    "PerformanceRepository",
]
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/db/__init__.py
git commit -m "chore(db): export repositories from db module"
```

---

## Task 12: Final Integration Test

**Files:**
- Create: `signal_composer/tests/db/test_full_integration.py`

- [ ] **Step 1: Write full integration test**

```python
"""Full integration test for database workflow."""

import pytest
from datetime import datetime, timezone

from src.db.models import User, Strategy
from src.db.repositories import (
    UserRepository,
    StrategyRepository,
    TradeRepository,
    PerformanceRepository,
)
from src.simulation.persistence import SimulationPersistence
from src.simulation.backtest import BacktestEngine
from src.engine.dsl.types import (
    Strategy as StrategyDSL,
    Trigger,
    SimpleCondition,
    Action,
    ActionType,
    RiskRules,
    Operator,
)


class TestFullDatabaseIntegration:
    """Test complete workflow: create strategy -> backtest -> save -> query."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, db_session):
        """Full workflow from strategy creation to querying results."""
        # 1. Create user
        user_repo = UserRepository(db_session)
        user = await user_repo.get_or_create("integration_test_wallet")
        assert user.id is not None

        # 2. Create strategy DSL
        strategy_dsl = StrategyDSL(
            id="integration_test_strategy",
            name="Integration Test",
            version=1,
            tokens=["SOL"],
            derived_streams=[],
            triggers=[
                Trigger(
                    id="buy_low",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(type=ActionType.BUY, token="SOL", amount_pct=25),
                )
            ],
            risk_rules=RiskRules(
                stop_loss_pct=-10,
                max_position_pct=50,
                max_trades_per_day=10,
                slippage_limit_bps=200,
            ),
        )

        # 3. Save strategy to database
        strategy_repo = StrategyRepository(db_session)
        db_strategy = Strategy(
            external_id=strategy_dsl.id,
            creator_id=user.id,
            name=strategy_dsl.name,
            description="Integration test strategy",
            dsl_json=strategy_dsl.model_dump(),
            status="active",
            is_public=True,
        )
        db_strategy = await strategy_repo.create(db_strategy)
        assert db_strategy.id is not None

        # 4. Run backtest
        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy trigger
            {"SOL": 92.0},  # Buy trigger
            {"SOL": 105.0},
        ]
        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy_dsl, price_history)

        assert result.trade_count >= 1

        # 5. Save backtest results
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)
        await persistence.save_backtest_result(db_strategy.id, result)

        # 6. Query and verify
        saved_trades = await trade_repo.list_by_strategy(db_strategy.id)
        assert len(saved_trades) == result.trade_count

        perf = await perf_repo.get_latest(db_strategy.id)
        assert perf is not None
        assert perf.total_return_pct == result.total_return_pct

        # 7. Query strategy with trades
        strategy_from_db = await strategy_repo.get_by_external_id("integration_test_strategy")
        assert strategy_from_db is not None
        assert strategy_from_db.name == "Integration Test"
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/db/test_full_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (should be 90+ tests now)

- [ ] **Step 4: Commit**

```bash
git add tests/db/test_full_integration.py
git commit -m "test(db): add full integration test for database workflow"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Docker + Environment | Manual |
| 2 | Alembic Setup | Manual |
| 3 | Initial Migration | Manual |
| 4 | Base Repository | 5 tests |
| 5 | User Repository | 5 tests |
| 6 | Strategy Repository | 6 tests |
| 7 | Trade Repository | 3 tests |
| 8 | Performance Repository | 5 tests |
| 9 | Simulation Persistence | 2 tests |
| 10 | CLI --save Flag | Manual |
| 11 | Module Exports | - |
| 12 | Full Integration | 1 test |

**Total new tests:** ~27
**Expected total tests after completion:** ~106
