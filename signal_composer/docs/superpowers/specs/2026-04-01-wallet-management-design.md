# Wallet Management Architecture Design

**Date:** 2026-04-01
**Status:** Approved
**Author:** Claude + User collaboration

## Overview

Minimal wallet management for live trading MVP. Solves the core problem: wallets that don't break (rent protection) and clean strategy-to-wallet mapping.

---

## MVP Scope

| Include | Exclude (Future) |
|---------|------------------|
| Store encrypted private key per wallet | Mnemonic-based derivation |
| Reserve 0.002 SOL from trades | Wallet listing API |
| Link wallet to strategy | Elaborate state machine |
| Basic balance check before trade | Balance caching |

---

## Data Model

```sql
-- Trading wallets with encrypted private keys
CREATE TABLE trading_wallets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    address VARCHAR(44) NOT NULL UNIQUE,
    encrypted_private_key BYTEA NOT NULL,
    label VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add wallet_id to strategies
ALTER TABLE strategies ADD COLUMN wallet_id INT REFERENCES trading_wallets(id);
```

---

## Core Logic

### 1. Key Storage

```python
from cryptography.fernet import Fernet
from base58 import b58decode, b58encode

PLATFORM_KEY = os.getenv("WALLET_ENCRYPTION_KEY")  # Generate with Fernet.generate_key()

def encrypt_private_key(private_key_b58: str) -> bytes:
    """Encrypt a base58-encoded private key."""
    return Fernet(PLATFORM_KEY).encrypt(private_key_b58.encode())

def decrypt_private_key(encrypted: bytes) -> str:
    """Decrypt to base58-encoded private key."""
    return Fernet(PLATFORM_KEY).decrypt(encrypted).decode()

def get_keypair(encrypted: bytes) -> Keypair:
    """Get usable keypair from encrypted storage."""
    private_key_b58 = decrypt_private_key(encrypted)
    key_bytes = b58decode(private_key_b58)
    if len(key_bytes) == 32:
        return Keypair.from_seed(key_bytes)
    else:
        return Keypair.from_bytes(key_bytes)
```

### 2. Reserve Protection

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
keypair = get_keypair(wallet.encrypted_private_key)

# Before each trade
balance = fetch_balance(wallet.address)
available = get_available_capital(balance)
if trade_amount > available:
    trade_amount = available  # Reduce to available, protecting reserve
```

---

## User Flow (MVP)

1. **Add wallet:** Provide private key (base58), system encrypts and stores
2. **Create strategy:** Select wallet to link
3. **Fund wallet:** Send SOL to wallet address
4. **Start trading:** Session uses keypair, respects reserve

---

## Implementation Checklist

1. [ ] Add `WALLET_ENCRYPTION_KEY` to .env (generate with `Fernet.generate_key()`)
2. [ ] Create database migration (1 table + 1 column)
3. [ ] Add `encrypt_private_key()` / `decrypt_private_key()` / `get_keypair()` functions
4. [ ] Add `get_available_capital()` reserve logic
5. [ ] Update `LiveTradingSession` to get keypair from strategy's wallet
6. [ ] Add reserve check in `SafetyGuard` before trades
7. [ ] Simple script to add your wallet

---

## Future Enhancements (Not MVP)

- Mnemonic-based derivation (one mnemonic → many wallets)
- Wallet listing API
- Balance caching
- Multiple users
