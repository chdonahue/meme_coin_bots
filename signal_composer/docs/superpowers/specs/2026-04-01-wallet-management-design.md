# Wallet Management Architecture Design

**Date:** 2026-04-01
**Status:** Approved
**Author:** Claude + User collaboration

## Overview

Minimal wallet management for live trading MVP. Solves the core problem: wallets that don't break (rent protection) and clean strategy-to-wallet mapping.

**Phase:** Live trading (builds on Real Money Transactions spec)

---

## MVP Scope

| Include | Exclude (Future) |
|---------|------------------|
| Store one encrypted mnemonic per user | Multiple mnemonics |
| Derive wallet per strategy | Wallet listing API |
| Reserve 0.002 SOL from trades | Elaborate state machine |
| Link wallet to strategy | Balance caching |
| Basic balance check before trade | Race condition handling |

---

## Data Model

```sql
-- User mnemonics (one per user)
CREATE TABLE user_mnemonics (
    id SERIAL PRIMARY KEY,
    user_id INT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    encrypted_mnemonic BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trading wallets (derived from mnemonic)
CREATE TABLE trading_wallets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mnemonic_id INT NOT NULL REFERENCES user_mnemonics(id) ON DELETE CASCADE,
    derivation_index INT NOT NULL,
    address VARCHAR(44) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(mnemonic_id, derivation_index)
);

-- Add wallet_id to strategies
ALTER TABLE strategies ADD COLUMN wallet_id INT REFERENCES trading_wallets(id);
```

---

## Core Logic

### 1. Mnemonic Storage

```python
from cryptography.fernet import Fernet

PLATFORM_KEY = os.getenv("WALLET_ENCRYPTION_KEY")  # Generate with Fernet.generate_key()

def encrypt_mnemonic(mnemonic: str) -> bytes:
    return Fernet(PLATFORM_KEY).encrypt(mnemonic.encode())

def decrypt_mnemonic(encrypted: bytes) -> str:
    return Fernet(PLATFORM_KEY).decrypt(encrypted).decode()
```

### 2. Wallet Derivation

```python
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes
from solders.keypair import Keypair

def derive_keypair(mnemonic: str, index: int) -> Keypair:
    """Derive keypair at index (same as legacy BOT wallets)."""
    seed = Bip39SeedGenerator(mnemonic).Generate()
    bip44 = Bip44.FromSeed(seed, Bip44Coins.SOLANA)
    derived = bip44.Purpose().Coin().Account(index).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)

    priv = derived.PrivateKey().Raw().ToBytes()
    pub = derived.PublicKey().RawUncompressed().ToBytes()[1:]
    return Keypair.from_bytes(priv + pub)
```

### 3. Reserve Protection

```python
RESERVE_SOL = Decimal("0.002")  # Never trade below this

def get_available_capital(on_chain_balance: Decimal) -> Decimal:
    """What the strategy can actually use."""
    return max(on_chain_balance - RESERVE_SOL, Decimal("0"))

def check_can_trade(wallet_address: str, trade_amount: Decimal) -> bool:
    """Check before executing any trade."""
    balance = fetch_balance_from_rpc(wallet_address)
    available = get_available_capital(balance)
    return trade_amount <= available
```

---

## Integration with Live Trading

When starting a live trading session:

```python
# In LiveTradingSession setup
strategy = get_strategy(strategy_id)
wallet = get_wallet(strategy.wallet_id)
mnemonic = decrypt_mnemonic(wallet.mnemonic.encrypted_mnemonic)
keypair = derive_keypair(mnemonic, wallet.derivation_index)

# Before each trade
balance = fetch_balance(wallet.address)
available = get_available_capital(balance)
if trade_amount > available:
    trade_amount = available  # Reduce to available, protecting reserve
```

---

## User Flow (MVP)

1. **Setup (one-time):** User provides 24-word mnemonic via CLI or simple endpoint
2. **Create strategy:** System derives next wallet, links to strategy
3. **Fund wallet:** User sends SOL to derived address
4. **Start trading:** Session uses derived keypair, respects reserve

---

## Implementation Checklist

1. [ ] Add `WALLET_ENCRYPTION_KEY` to .env
2. [ ] Create database migration (2 tables + 1 column)
3. [ ] Add `encrypt_mnemonic()` / `decrypt_mnemonic()` functions
4. [ ] Add `derive_keypair()` function (copy from test_with_mnemonic.py)
5. [ ] Add `get_available_capital()` reserve logic
6. [ ] Update `LiveTradingSession` to derive keypair from strategy's wallet
7. [ ] Add reserve check in `SafetyGuard` before trades
8. [ ] Simple script to set up mnemonic for your user

---

## Future Enhancements (Not MVP)

- Wallet listing API
- Wallet state machine (unfunded/available/active)
- Balance caching
- Multiple users with race-safe index allocation
- User password encryption for mnemonics
- Wallet reassignment between strategies
