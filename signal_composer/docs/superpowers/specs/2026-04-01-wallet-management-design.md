# Wallet Management Architecture Design

**Date:** 2026-04-01
**Status:** Draft
**Author:** Claude + User collaboration

## Overview

This document specifies the wallet management architecture for SignalComposer's multi-user live trading platform. It defines how wallets are created, mapped to strategies, and secured.

**Phase:** This spec applies to **live trading (Phase 2)** as defined in the original SignalComposer design. It supersedes the `wallet_keypairs` table from the Real Money Transactions spec - we now derive keypairs from user mnemonics rather than storing individual keypairs.

**Relationship to Other Specs:**
- Builds on: `2026-03-30-real-money-transactions-design.md` (LiveTradingSession, TransactionCoordinator)
- Replaces: `wallet_keypairs` table with mnemonic-based derivation
- Compatible with: `2026-03-25-web-api-design.md` (adds new endpoints)

## Goals

1. One wallet per strategy for clean isolation and P&L tracking
2. User provides one mnemonic, platform derives wallets as needed
3. Reserve partitioning to prevent wallet closure (rent protection)
4. Secure mnemonic storage (MVP: platform key, future: user password)
5. Clean wallet lifecycle with orphan support

## Non-Goals

- Smart contract escrow pools (future Phase 2)
- Client-side signing (future)
- Multiple mnemonics per user (future)
- Wallet index recycling

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Custody model | Server-side (MVP) | Simplicity, architected for future migration |
| Wallet-strategy mapping | One wallet per strategy | Clean isolation, clear P&L tracking |
| Wallet provisioning | User mnemonic, platform derives | User controls recovery, platform manages operations |
| Reserve amount | 0.002 SOL | Covers rent-exempt minimum + buffer |
| Mnemonic encryption | Platform key (MVP) | Simplicity; TODO for multi-user security |
| Strategy deletion | Wallet becomes AVAILABLE | Funds never lost, wallet reusable |
| Mnemonics per user | One | Simplicity for MVP |
| Funding requirement | Dry setup allowed | Flexible onboarding |

---

## Data Model

```
User (1:1) Mnemonic (1:N) Wallet (1:1) Strategy

┌─────────────────────────────────────────────────────────────┐
│                          USER                                │
│  id, wallet_address (auth), username                        │
└─────────────────────────────┬───────────────────────────────┘
                              │ 1:1
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     USER_MNEMONIC                            │
│  id, user_id, encrypted_mnemonic, created_at                │
│  (one per user, encrypted with platform key)                │
└─────────────────────────────┬───────────────────────────────┘
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     TRADING_WALLET                           │
│  id, user_id, mnemonic_id, derivation_index                 │
│  address (derived), label, status (unfunded/available/active)│
│  previous_strategy_id, created_at, last_used_at             │
└─────────────────────────────┬───────────────────────────────┘
                              │ 1:1 (optional)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        STRATEGY                              │
│  id, wallet_id (nullable), creator_id, name, dsl_json...   │
└─────────────────────────────────────────────────────────────┘
```

### Relationships

- `User` has one `UserMnemonic` (encrypted)
- `UserMnemonic` derives many `TradingWallet` entries
- `TradingWallet` can be linked to one `Strategy` (or none if AVAILABLE)
- `Strategy.wallet_id` is nullable (unassigned strategies)

---

## Wallet States

```
┌─────────────────────────────────────────────────────────────┐
│                 WALLET STATES                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐     fund      ┌───────────┐  assign  ┌──────┐ │
│  │ UNFUNDED │ ────────────► │ AVAILABLE │ ───────► │ACTIVE│ │
│  └──────────┘               └───────────┘          └──┬───┘ │
│       ▲                           ▲                   │     │
│       │                           │  delete strategy  │     │
│       │      withdraw all         └───────────────────┘     │
│       └─────────────────────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

| State | Balance | Strategy | Description |
|-------|---------|----------|-------------|
| `UNFUNDED` | < 0.002 SOL | None | Awaiting deposit |
| `AVAILABLE` | ≥ 0.002 SOL | None | Funded, can be assigned |
| `ACTIVE` | ≥ 0.002 SOL | Assigned | Running a strategy |

**Transitions:**
- Wallet created → `UNFUNDED`
- Balance crosses 0.002 SOL threshold → `AVAILABLE`
- Assigned to strategy → `ACTIVE`
- Strategy deleted → `AVAILABLE`
- User withdraws all funds → `UNFUNDED`

---

## Reserve Partitioning

```
┌─────────────────────────────────────────────────────────────┐
│                    WALLET BALANCE VIEW                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   On-chain balance: 1.500 SOL                               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░│   │
│   └─────────────────────────────────────────────────────┘   │
│   │◄──────── Strategy Capital: 1.498 SOL ────────►│ │Reserve│
│                                                      0.002  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```python
WALLET_RESERVE_SOL = Decimal("0.002")  # ~$0.30, covers rent + buffer

@dataclass
class WalletBalanceView:
    """What the strategy sees vs what's actually on-chain."""

    on_chain_balance: Decimal
    reserve: Decimal = WALLET_RESERVE_SOL

    @property
    def available_capital(self) -> Decimal:
        """What the strategy can actually use."""
        return max(self.on_chain_balance - self.reserve, Decimal("0"))

    @property
    def is_funded(self) -> bool:
        """Wallet has enough to operate."""
        return self.on_chain_balance >= self.reserve
```

### Behavior

- Strategy says "sell all SOL" → sells `available_capital`, not `on_chain_balance`
- Strategy says "buy with 50% of capital" → 50% of `available_capital`
- Reserve is invisible to strategy logic
- If balance drops below reserve, `available_capital` = 0

### Reserve Exhaustion Handling

If transaction fees cause balance to drop below reserve during trading:

1. **Pre-trade check:** SafetyGuard estimates total cost (trade + fees)
2. **If trade would breach reserve:** Reduce trade size to preserve reserve
3. **If balance already below reserve:** Strategy pauses, alert sent
4. **Recovery:** User deposits more SOL, strategy auto-resumes when `available_capital > 0`

```python
def calculate_safe_trade_amount(
    requested_amount: Decimal,
    available_capital: Decimal,
    estimated_fees: Decimal
) -> Decimal:
    """Reduce trade amount if needed to preserve reserve."""
    max_safe = available_capital - estimated_fees
    return min(requested_amount, max(max_safe, Decimal("0")))
```

### Balance Refresh Strategy

| Scenario | Refresh Frequency | Source |
|----------|------------------|--------|
| Before trade execution | Real-time | RPC call |
| Dashboard display | Cached (5 min TTL) | Database |
| Wallet list API | Cached (5 min TTL) | Database |
| Manual refresh button | Real-time | RPC call |

Balance is fetched from Solana RPC and cached in database with timestamp. Live trading always uses fresh RPC data.

---

## Wallet Derivation

### BIP44 Path

```
m/44'/501'/{index}'/0'

Where:
- 44' = BIP44 purpose
- 501' = Solana coin type
- {index}' = Account index (0, 1, 2, ...)
- 0' = External chain
```

This matches the legacy BOT wallet derivation used in existing code.

### Derivation Flow

```
User provides mnemonic (once)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Encrypt with platform key (Fernet)                 │
│  Store in user_mnemonics table                      │
└─────────────────────────────────────────────────────┘
        │
        ▼
User creates Strategy 1 → derive wallet at index 0
User creates Strategy 2 → derive wallet at index 1
User creates Strategy 3 → derive wallet at index 2
```

### Index Management

```python
async def create_next_wallet(user_id: int, mnemonic_id: int, db: AsyncSession) -> TradingWallet:
    """Atomically create wallet at next available index.

    Uses SELECT FOR UPDATE to prevent race conditions when
    multiple requests try to create wallets simultaneously.
    """
    # Lock user's wallets to prevent concurrent index allocation
    result = await db.execute(
        select(func.coalesce(func.max(TradingWallet.derivation_index), -1))
        .filter(TradingWallet.user_id == user_id)
        .with_for_update()
    )
    max_index = result.scalar()
    next_index = max_index + 1

    # Derive address from mnemonic
    mnemonic = await get_user_mnemonic(user_id, db)
    address = derive_address_at_index(mnemonic, next_index)

    # Create wallet record
    wallet = TradingWallet(
        user_id=user_id,
        mnemonic_id=mnemonic_id,
        derivation_index=next_index,
        address=address,
        status="unfunded"
    )
    db.add(wallet)
    await db.commit()
    return wallet
```

**Race condition prevention:** Uses `SELECT FOR UPDATE` to lock the user's wallet rows during index allocation. The `UNIQUE(mnemonic_id, derivation_index)` constraint provides backup protection.

- Indices are 0-based and never recycled
- User can reuse AVAILABLE wallets instead of deriving new ones

---

## Mnemonic Security

### MVP Implementation

```python
# TODO: SECURITY - Before multi-user launch:
# - Replace platform key with user-password-derived key
# - Add HSM support for platform key storage
# - Implement key rotation

from cryptography.fernet import Fernet

PLATFORM_KEY = os.getenv("WALLET_ENCRYPTION_KEY")  # Fernet key

def encrypt_mnemonic(mnemonic: str) -> bytes:
    """Encrypt mnemonic with platform key."""
    f = Fernet(PLATFORM_KEY)
    return f.encrypt(mnemonic.encode())

def decrypt_mnemonic(encrypted: bytes) -> str:
    """Decrypt mnemonic with platform key."""
    f = Fernet(PLATFORM_KEY)
    return f.decrypt(encrypted).decode()
```

### Future Security (Pre-Multi-User)

| Enhancement | Description |
|-------------|-------------|
| User password encryption | Encrypt with password-derived key (Argon2) |
| HSM support | Store platform key in hardware security module |
| Key rotation | Ability to re-encrypt with new keys |
| Audit logging | Log all mnemonic access |

---

## Database Schema

### New Tables

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
    label VARCHAR(100),
    status VARCHAR(20) DEFAULT 'unfunded',
    previous_strategy_id INT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    UNIQUE(mnemonic_id, derivation_index),
    UNIQUE(address)
);

CREATE INDEX idx_trading_wallets_user ON trading_wallets(user_id);
CREATE INDEX idx_trading_wallets_status ON trading_wallets(status);
```

### Schema Modifications

```sql
-- Add wallet_id to strategies
ALTER TABLE strategies
ADD COLUMN wallet_id INT REFERENCES trading_wallets(id);
```

---

## API Endpoints

### Mnemonic Management

```
POST   /wallets/mnemonic              # Submit mnemonic (one-time setup)
GET    /wallets/mnemonic/status       # Check if mnemonic is configured
```

**POST /wallets/mnemonic**

```python
class MnemonicSubmit(BaseModel):
    mnemonic: str  # 24 words, space-separated

class MnemonicResponse(BaseModel):
    success: bool
    first_wallet_address: str  # Auto-derived wallet 0
```

**Validation:**
- Must be exactly 24 words (BIP39 standard)
- Each word must be in BIP39 English wordlist
- Checksum must be valid (last word encodes checksum)
- Returns 400 error with clear message if invalid

**Idempotency:**
- If user already has a mnemonic, return 409 Conflict
- Mnemonic cannot be changed after submission (security)
- User must contact support to reset (manual process)

**Recovery Note:**
- The user's mnemonic IS their backup
- Platform stores encrypted copy for operations
- User can always recover wallets externally using their mnemonic
- If user loses mnemonic, platform cannot help (by design)

### Wallet Management

```
GET    /wallets                       # List user's wallets
GET    /wallets/{id}                  # Get wallet details + balance
POST   /wallets                       # Derive new wallet (next index)
POST   /wallets/{id}/refresh-balance  # Fetch on-chain balance
```

**GET /wallets**

```python
class WalletResponse(BaseModel):
    id: int
    address: str
    derivation_index: int
    label: str | None
    status: str  # unfunded, available, active
    on_chain_balance_sol: float | None
    available_capital_sol: float | None
    strategy_id: int | None
    strategy_name: str | None
```

### Strategy Modifications

```python
class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    dsl: dict
    is_public: bool = False
    wallet_id: int | None = None  # If None, derive new wallet
```

---

## User Flow

### Onboarding

1. User authenticates (wallet signature - existing)
2. User goes to "Set up trading"
3. Prompt for 24-word mnemonic
4. Platform encrypts and stores mnemonic
5. First wallet derived automatically (index 0)
6. User can now create strategies

### Creating a Strategy

1. User creates strategy (DSL, name, etc.)
2. Option A: Auto-derive new wallet (default)
3. Option B: Select existing AVAILABLE wallet
4. Wallet linked to strategy
5. Strategy shows "Pending funding" until wallet funded

### Deleting a Strategy

1. User deletes strategy
2. Wallet unlinked (wallet_id set to null)
3. Wallet status → AVAILABLE
4. previous_strategy_id set for history
5. User can withdraw funds or reuse wallet

---

## Integration with Live Trading

### Updated Flow

```
LiveTradingSession(strategy_id)
    │
    ├── Get wallet from strategy.wallet_id
    ├── Get mnemonic from wallet.mnemonic_id
    ├── Derive keypair at wallet.derivation_index
    │
    └── TransactionCoordinator
          ├── WalletBalanceView (reserve-aware)
          └── WalletService.sign(derived_keypair)
```

### Component Changes

| Component | Change |
|-----------|--------|
| `LiveTradingSession` | Get wallet from strategy, not passed in |
| `WalletService` | Add `derive_from_mnemonic(encrypted, index)` |
| `TransactionCoordinator` | Use `WalletBalanceView` for reserve logic |
| `SafetyGuard` | Add balance check before trades |

### WalletService Updates

```python
class WalletService:
    def derive_from_mnemonic(
        self,
        encrypted_mnemonic: bytes,
        derivation_index: int
    ) -> Keypair:
        """Derive keypair from encrypted mnemonic at index."""
        mnemonic = decrypt_mnemonic(encrypted_mnemonic)
        seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
        bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.SOLANA)
        bip44_acc = bip44_ctx.Purpose().Coin().Account(derivation_index)
        bip44_chg = bip44_acc.Change(Bip44Changes.CHAIN_EXT)
        bip44_addr = bip44_chg.AddressIndex(0)

        priv_bytes = bip44_addr.PrivateKey().Raw().ToBytes()
        pub_bytes = bip44_addr.PublicKey().RawUncompressed().ToBytes()[1:]

        return Keypair.from_bytes(priv_bytes + pub_bytes)
```

---

## File Structure

```
src/
├── wallets/
│   ├── __init__.py
│   ├── models.py           # UserMnemonic, TradingWallet
│   ├── service.py          # WalletManagementService
│   ├── derivation.py       # BIP44 derivation logic
│   ├── encryption.py       # Mnemonic encryption
│   └── balance.py          # WalletBalanceView, reserve logic
├── db/
│   ├── repositories/
│   │   └── wallet_repository.py
│   └── migrations/
│       └── versions/
│           └── xxxx_add_wallet_management.py
├── api/
│   ├── routes/
│   │   └── wallets.py      # Wallet API endpoints
│   └── schemas/
│       └── wallet.py       # Pydantic schemas
└── live_trading/
    └── services/
        └── wallet.py       # Updated WalletService
```

---

## Testing Strategy

### Unit Tests

- Mnemonic encryption/decryption
- BIP44 derivation (verify addresses match expected)
- WalletBalanceView reserve logic
- Wallet state transitions

### Integration Tests

- Full mnemonic submission flow
- Wallet derivation and storage
- Strategy creation with wallet assignment
- Strategy deletion and wallet orphaning
- Balance refresh from RPC

### Security Tests

- Mnemonic never logged or exposed in errors
- Encrypted mnemonic cannot be decrypted without key
- User isolation (can't access other users' wallets)

---

## Migration Path

**For existing paper-trading users:**
- Paper trading continues to work without mnemonic
- Live trading requires mnemonic setup
- When user wants live trading: prompt "Set up trading wallet" flow
- No automatic migration - user opts in

**For existing `wallet_keypairs` table (from Real Money Transactions spec):**
- This table is deprecated and will not be implemented
- Mnemonic-based derivation replaces per-keypair storage
- Simpler model: one mnemonic → many wallets

---

## Implementation Order

1. Database migrations (new tables, strategy modification)
2. Mnemonic encryption module
3. BIP44 derivation service (with validation)
4. WalletBalanceView and reserve logic
5. Wallet repository (with race-safe index allocation)
6. Wallet API endpoints
7. Strategy creation flow updates
8. LiveTradingSession integration
9. SafetyGuard balance checks
10. Tests

---

## Success Criteria

1. User can submit mnemonic and see derived wallet address
2. Creating a strategy auto-derives a new wallet
3. Strategy deletion leaves wallet in AVAILABLE state
4. Reserve (0.002 SOL) is always protected from trades
5. Live trading session derives correct keypair from stored mnemonic
6. Wallet balances refresh from on-chain data
7. All tests pass

---

## User Account Deletion

When a user deletes their account:

1. **Live sessions stopped first** - All active trading sessions killed
2. **Funds warning** - User warned: "Withdraw all funds before deletion"
3. **Cascade behavior:**
   - `user_mnemonics` deleted (encrypted mnemonic gone)
   - `trading_wallets` deleted (wallet records gone)
   - On-chain wallets still exist with any remaining funds
4. **Recovery** - User can still access on-chain funds using their mnemonic externally

**Important:** Platform cannot recover funds after deletion. The user's mnemonic is their only recovery path.

---

## Capital Units

All capital calculations use **SOL** as the base unit:

| Field | Unit | Example |
|-------|------|---------|
| `on_chain_balance` | SOL | 1.500 |
| `available_capital` | SOL | 1.498 |
| `reserve` | SOL | 0.002 |
| Strategy `amount_pct` | % of available SOL | 50% = 0.749 SOL |
| `max_trade_usd` (SafetyGuard) | USD | $500 (converted via price feed) |

Strategy DSL uses percentage-based amounts. The execution layer converts to SOL amounts using current prices.

---

## Security Notes

**MVP Limitations (acceptable for single-user):**
- Platform key encryption only
- No HSM
- No audit logging

**Required Before Multi-User:**
- [ ] User password encryption for mnemonics
- [ ] HSM for platform key storage
- [ ] Comprehensive audit logging
- [ ] Rate limiting on mnemonic operations
- [ ] Security audit
