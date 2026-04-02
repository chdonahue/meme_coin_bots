# Wallet Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add encrypted wallet storage and reserve protection to prevent wallet closure during live trading.

**Architecture:** Store encrypted private keys in database, link wallets to strategies, protect 0.002 SOL reserve on every trade.

**Tech Stack:** SQLAlchemy, Alembic migrations, cryptography (Fernet), solders, base58

**Spec:** `docs/superpowers/specs/2026-04-01-wallet-management-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/wallets/__init__.py` | Package exports |
| `src/wallets/encryption.py` | Fernet encrypt/decrypt for private keys |
| `src/wallets/keypair.py` | Get Keypair from encrypted storage |
| `src/wallets/reserve.py` | Reserve calculation logic |
| `src/db/models.py` | Add TradingWallet model |
| `src/db/migrations/versions/xxxx_add_trading_wallets.py` | Migration |
| `src/db/repositories/wallet_repository.py` | CRUD for wallets |
| `src/live_trading/safety/guard.py` | Add reserve check |
| `scripts/add_wallet.py` | CLI script to add wallet |
| `tests/wallets/test_encryption.py` | Encryption tests |
| `tests/wallets/test_reserve.py` | Reserve logic tests |

---

## Task 1: Generate Encryption Key

**Files:**
- Modify: `.env`

- [ ] **Step 1: Generate Fernet key**

Run:
```bash
cd signal_composer && python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- [ ] **Step 2: Add to .env**

Add line to `.env`:
```
WALLET_ENCRYPTION_KEY=<paste-generated-key>
```

- [ ] **Step 3: Verify key loads**

Run:
```bash
cd signal_composer && python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Key loaded:', bool(os.getenv('WALLET_ENCRYPTION_KEY')))"
```
Expected: `Key loaded: True`

---

## Task 2: Encryption Module

**Files:**
- Create: `src/wallets/__init__.py`
- Create: `src/wallets/encryption.py`
- Create: `tests/wallets/__init__.py`
- Create: `tests/wallets/test_encryption.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p signal_composer/src/wallets signal_composer/tests/wallets
touch signal_composer/src/wallets/__init__.py signal_composer/tests/wallets/__init__.py
```

- [ ] **Step 2: Write failing test**

Create `tests/wallets/test_encryption.py`:
```python
"""Tests for wallet encryption."""

import pytest
from src.wallets.encryption import encrypt_private_key, decrypt_private_key


def test_encrypt_decrypt_roundtrip():
    """Encrypted key can be decrypted back to original."""
    original = "4wBqpZM9k1Sz2LvXbhA9wJrMcPz5mZvNq3aJyR9Kx"
    encrypted = encrypt_private_key(original)
    decrypted = decrypt_private_key(encrypted)
    assert decrypted == original


def test_encrypted_differs_from_original():
    """Encrypted value should not equal original."""
    original = "4wBqpZM9k1Sz2LvXbhA9wJrMcPz5mZvNq3aJyR9Kx"
    encrypted = encrypt_private_key(original)
    assert encrypted != original.encode()


def test_decrypt_invalid_raises():
    """Decrypting invalid data raises error."""
    with pytest.raises(Exception):
        decrypt_private_key(b"invalid-encrypted-data")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/wallets/test_encryption.py -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import"

- [ ] **Step 4: Write implementation**

Create `src/wallets/encryption.py`:
```python
"""Encryption utilities for wallet private keys."""

import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Get Fernet instance with platform key."""
    key = os.getenv("WALLET_ENCRYPTION_KEY")
    if not key:
        raise ValueError("WALLET_ENCRYPTION_KEY environment variable not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_private_key(private_key_b58: str) -> bytes:
    """Encrypt a base58-encoded private key."""
    return _get_fernet().encrypt(private_key_b58.encode())


def decrypt_private_key(encrypted: bytes) -> str:
    """Decrypt to base58-encoded private key."""
    return _get_fernet().decrypt(encrypted).decode()
```

- [ ] **Step 5: Update package exports**

Update `src/wallets/__init__.py`:
```python
"""Wallet management module."""

from .encryption import encrypt_private_key, decrypt_private_key

__all__ = ["encrypt_private_key", "decrypt_private_key"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/wallets/test_encryption.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add signal_composer/src/wallets signal_composer/tests/wallets
git commit -m "feat(wallets): add encryption module for private keys"
```

---

## Task 3: Keypair Module

**Files:**
- Create: `src/wallets/keypair.py`
- Create: `tests/wallets/test_keypair.py`

- [ ] **Step 1: Write failing test**

Create `tests/wallets/test_keypair.py`:
```python
"""Tests for keypair derivation from encrypted storage."""

import pytest
from base58 import b58encode
from solders.keypair import Keypair

from src.wallets.keypair import get_keypair
from src.wallets.encryption import encrypt_private_key


def test_get_keypair_from_seed():
    """Get keypair from 32-byte seed (from_seed path)."""
    # Generate a test keypair and get its seed
    original = Keypair()
    seed_bytes = bytes(original)[:32]
    seed_b58 = b58encode(seed_bytes).decode()

    # Encrypt and recover
    encrypted = encrypt_private_key(seed_b58)
    recovered = get_keypair(encrypted)

    assert str(recovered.pubkey()) == str(original.pubkey())


def test_get_keypair_from_full_bytes():
    """Get keypair from 64-byte full key (from_bytes path)."""
    original = Keypair()
    full_bytes = bytes(original)
    full_b58 = b58encode(full_bytes).decode()

    encrypted = encrypt_private_key(full_b58)
    recovered = get_keypair(encrypted)

    assert str(recovered.pubkey()) == str(original.pubkey())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/wallets/test_keypair.py -v`
Expected: FAIL with "cannot import name 'get_keypair'"

- [ ] **Step 3: Write implementation**

Create `src/wallets/keypair.py`:
```python
"""Keypair utilities for wallet management."""

from base58 import b58decode
from solders.keypair import Keypair

from .encryption import decrypt_private_key


def get_keypair(encrypted: bytes) -> Keypair:
    """Get usable Keypair from encrypted storage.

    Handles both 32-byte seeds and 64-byte full keypairs.
    """
    private_key_b58 = decrypt_private_key(encrypted)
    key_bytes = b58decode(private_key_b58)

    if len(key_bytes) == 32:
        return Keypair.from_seed(key_bytes)
    elif len(key_bytes) == 64:
        return Keypair.from_bytes(key_bytes)
    else:
        raise ValueError(f"Invalid key length: {len(key_bytes)} bytes (expected 32 or 64)")
```

- [ ] **Step 4: Update package exports**

Update `src/wallets/__init__.py`:
```python
"""Wallet management module."""

from .encryption import encrypt_private_key, decrypt_private_key
from .keypair import get_keypair

__all__ = ["encrypt_private_key", "decrypt_private_key", "get_keypair"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/wallets/test_keypair.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add signal_composer/src/wallets signal_composer/tests/wallets
git commit -m "feat(wallets): add keypair recovery from encrypted storage"
```

---

## Task 4: Reserve Logic Module

**Files:**
- Create: `src/wallets/reserve.py`
- Create: `tests/wallets/test_reserve.py`

- [ ] **Step 1: Write failing test**

Create `tests/wallets/test_reserve.py`:
```python
"""Tests for reserve protection logic."""

from decimal import Decimal
import pytest

from src.wallets.reserve import RESERVE_SOL, get_available_capital


def test_reserve_constant():
    """Reserve is 0.002 SOL."""
    assert RESERVE_SOL == Decimal("0.002")


def test_available_capital_normal():
    """Available capital is balance minus reserve."""
    balance = Decimal("1.500")
    available = get_available_capital(balance)
    assert available == Decimal("1.498")


def test_available_capital_exact_reserve():
    """Balance equals reserve means zero available."""
    balance = Decimal("0.002")
    available = get_available_capital(balance)
    assert available == Decimal("0")


def test_available_capital_below_reserve():
    """Balance below reserve returns zero, not negative."""
    balance = Decimal("0.001")
    available = get_available_capital(balance)
    assert available == Decimal("0")


def test_available_capital_zero_balance():
    """Zero balance returns zero available."""
    balance = Decimal("0")
    available = get_available_capital(balance)
    assert available == Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/wallets/test_reserve.py -v`
Expected: FAIL with "cannot import name"

- [ ] **Step 3: Write implementation**

Create `src/wallets/reserve.py`:
```python
"""Reserve protection logic for trading wallets."""

from decimal import Decimal

# Minimum SOL to keep in wallet (covers rent-exempt + buffer)
RESERVE_SOL = Decimal("0.002")


def get_available_capital(on_chain_balance: Decimal) -> Decimal:
    """Calculate capital available for trading.

    Protects reserve amount from being traded away.

    Args:
        on_chain_balance: Current SOL balance from RPC

    Returns:
        Available capital (balance - reserve), minimum 0
    """
    return max(on_chain_balance - RESERVE_SOL, Decimal("0"))
```

- [ ] **Step 4: Update package exports**

Update `src/wallets/__init__.py`:
```python
"""Wallet management module."""

from .encryption import encrypt_private_key, decrypt_private_key
from .keypair import get_keypair
from .reserve import RESERVE_SOL, get_available_capital

__all__ = [
    "encrypt_private_key",
    "decrypt_private_key",
    "get_keypair",
    "RESERVE_SOL",
    "get_available_capital",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/wallets/test_reserve.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add signal_composer/src/wallets signal_composer/tests/wallets
git commit -m "feat(wallets): add reserve protection logic (0.002 SOL)"
```

---

## Task 5: Database Migration

**Files:**
- Modify: `src/db/models.py`
- Create: `src/db/migrations/versions/xxxx_add_trading_wallets.py`

- [ ] **Step 1: Add TradingWallet model**

Add to `src/db/models.py` after existing model imports:
```python
class TradingWallet(Base):
    """Trading wallet with encrypted private key."""

    __tablename__ = "trading_wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    address: Mapped[str] = mapped_column(String(44), unique=True)
    encrypted_private_key: Mapped[bytes] = mapped_column(LargeBinary)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="trading_wallets")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="wallet")
```

- [ ] **Step 2: Add relationship to User model**

Add to `User` class in `src/db/models.py`:
```python
    trading_wallets: Mapped[list["TradingWallet"]] = relationship(back_populates="user")
```

- [ ] **Step 3: Add wallet_id to Strategy model**

Add to `Strategy` class in `src/db/models.py`:
```python
    wallet_id: Mapped[int | None] = mapped_column(ForeignKey("trading_wallets.id"), nullable=True)
    wallet: Mapped["TradingWallet | None"] = relationship(back_populates="strategies")
```

- [ ] **Step 4: Generate migration**

Run:
```bash
cd signal_composer && alembic revision --autogenerate -m "add_trading_wallets"
```

- [ ] **Step 5: Review generated migration**

Check the migration file in `src/db/migrations/versions/` - ensure it creates:
- `trading_wallets` table with correct columns
- `wallet_id` column on `strategies` table
- Foreign key constraints

- [ ] **Step 6: Run migration**

Run:
```bash
cd signal_composer && alembic upgrade head
```

- [ ] **Step 7: Verify tables exist**

Run:
```bash
cd signal_composer && python -c "from src.db.models import TradingWallet; print('TradingWallet model OK')"
```

- [ ] **Step 8: Commit**

```bash
git add signal_composer/src/db
git commit -m "feat(db): add trading_wallets table and strategy.wallet_id"
```

---

## Task 6: Wallet Repository

**Files:**
- Create: `src/db/repositories/wallet_repository.py`
- Modify: `src/db/repositories/__init__.py`

- [ ] **Step 1: Create wallet repository**

Create `src/db/repositories/wallet_repository.py`:
```python
"""Repository for trading wallet operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TradingWallet
from src.wallets import encrypt_private_key


class WalletRepository:
    """CRUD operations for trading wallets."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        address: str,
        private_key_b58: str,
        label: str | None = None,
    ) -> TradingWallet:
        """Create a new trading wallet with encrypted key."""
        encrypted = encrypt_private_key(private_key_b58)
        wallet = TradingWallet(
            user_id=user_id,
            address=address,
            encrypted_private_key=encrypted,
            label=label,
        )
        self.session.add(wallet)
        await self.session.commit()
        await self.session.refresh(wallet)
        return wallet

    async def get_by_id(self, wallet_id: int) -> TradingWallet | None:
        """Get wallet by ID."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def get_by_address(self, address: str) -> TradingWallet | None:
        """Get wallet by address."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.address == address)
        )
        return result.scalar_one_or_none()

    async def get_user_wallets(self, user_id: int) -> list[TradingWallet]:
        """Get all wallets for a user."""
        result = await self.session.execute(
            select(TradingWallet).where(TradingWallet.user_id == user_id)
        )
        return list(result.scalars().all())
```

- [ ] **Step 2: Export from repositories package**

Add to `src/db/repositories/__init__.py`:
```python
from .wallet_repository import WalletRepository
```

- [ ] **Step 3: Commit**

```bash
git add signal_composer/src/db/repositories
git commit -m "feat(db): add WalletRepository for trading wallets"
```

---

## Task 7: Add Wallet Script

**Files:**
- Create: `scripts/add_wallet.py`

- [ ] **Step 1: Create script**

Create `scripts/add_wallet.py`:
```python
"""Add a trading wallet for the current user.

Usage: python scripts/add_wallet.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from base58 import b58decode
from solders.keypair import Keypair

from src.db.database import async_session_factory
from src.db.repositories.wallet_repository import WalletRepository
from src.db.repositories import UserRepository


async def main():
    print("=" * 60)
    print("ADD TRADING WALLET")
    print("=" * 60)

    # Get private key
    private_key = input("\nEnter private key (base58): ").strip()
    if not private_key:
        print("No key provided.")
        return

    # Validate key and derive address
    try:
        key_bytes = b58decode(private_key)
        if len(key_bytes) == 32:
            keypair = Keypair.from_seed(key_bytes)
        elif len(key_bytes) == 64:
            keypair = Keypair.from_bytes(key_bytes)
        else:
            print(f"Invalid key length: {len(key_bytes)} bytes")
            return
        address = str(keypair.pubkey())
    except Exception as e:
        print(f"Invalid key: {e}")
        return

    print(f"\nDerived address: {address}")

    # Get optional label
    label = input("Label (optional): ").strip() or None

    # Get user (for MVP, assume user_id=1 or create if needed)
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        wallet_repo = WalletRepository(session)

        # Check if wallet already exists
        existing = await wallet_repo.get_by_address(address)
        if existing:
            print(f"\nWallet already exists (id={existing.id})")
            return

        # Get or create user (MVP: use first user or wallet address as identifier)
        users = await user_repo.get_all()
        if users:
            user = users[0]
            print(f"\nUsing existing user: {user.wallet_address}")
        else:
            print("\nNo users found. Create one first via /auth/challenge + /auth/verify")
            return

        # Create wallet
        wallet = await wallet_repo.create(
            user_id=user.id,
            address=address,
            private_key_b58=private_key,
            label=label,
        )

        print(f"\nWallet created!")
        print(f"  ID: {wallet.id}")
        print(f"  Address: {wallet.address}")
        print(f"  Label: {wallet.label or '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Test script runs**

Run:
```bash
cd signal_composer && python scripts/add_wallet.py
```
Then press Enter to exit without adding (or add a test wallet)

- [ ] **Step 3: Commit**

```bash
git add signal_composer/scripts/add_wallet.py
git commit -m "feat(scripts): add wallet creation script"
```

---

## Task 8: Integrate with SafetyGuard

**Files:**
- Modify: `src/live_trading/safety/guard.py`
- Create: `tests/live_trading/safety/test_guard_reserve.py`

- [ ] **Step 1: Read current SafetyGuard**

Check existing implementation:
```bash
cat signal_composer/src/live_trading/safety/guard.py
```

- [ ] **Step 2: Write failing test**

Create `tests/live_trading/safety/test_guard_reserve.py`:
```python
"""Tests for reserve protection in SafetyGuard."""

from decimal import Decimal
import pytest

from src.wallets.reserve import RESERVE_SOL, get_available_capital


def test_trade_amount_reduced_to_available():
    """Trade amount should be capped at available capital."""
    balance = Decimal("0.010")  # 0.01 SOL
    requested = Decimal("0.010")  # Want to trade all

    available = get_available_capital(balance)
    actual_trade = min(requested, available)

    assert available == Decimal("0.008")  # 0.01 - 0.002 reserve
    assert actual_trade == Decimal("0.008")  # Capped at available


def test_trade_blocked_when_no_capital():
    """Trade should be blocked when no capital available."""
    balance = Decimal("0.001")  # Below reserve

    available = get_available_capital(balance)

    assert available == Decimal("0")
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd signal_composer && python -m pytest tests/live_trading/safety/test_guard_reserve.py -v`
Expected: 2 passed (these are unit tests for the reserve logic)

- [ ] **Step 4: Add reserve check to SafetyGuard.check_trade()**

The exact modification depends on current SafetyGuard structure. Add to the check_trade method:
```python
from src.wallets.reserve import get_available_capital

# In check_trade method, add:
available_capital = get_available_capital(Decimal(str(wallet_balance)))
if trade_amount_sol > available_capital:
    if available_capital <= 0:
        return CheckResult(allowed=False, reason="Insufficient balance (reserve protected)")
    # Reduce trade to available capital
    trade_amount_sol = available_capital
```

- [ ] **Step 5: Commit**

```bash
git add signal_composer/src/live_trading/safety signal_composer/tests/live_trading/safety
git commit -m "feat(safety): add reserve protection to SafetyGuard"
```

---

## Task 9: Run All Tests

- [ ] **Step 1: Run full test suite**

Run:
```bash
cd signal_composer && python -m pytest tests/wallets -v
```
Expected: All wallet tests pass

- [ ] **Step 2: Run existing tests to check for regressions**

Run:
```bash
cd signal_composer && python -m pytest --ignore=tests/wallets -v
```
Expected: No regressions

---

## Verification Checklist

After completing all tasks:

- [ ] `WALLET_ENCRYPTION_KEY` is in `.env`
- [ ] `trading_wallets` table exists in database
- [ ] `strategies.wallet_id` column exists
- [ ] Can run `python scripts/add_wallet.py` and add a wallet
- [ ] Reserve logic protects 0.002 SOL
- [ ] All tests pass
