# Real Money Transaction Execution Design

**Date:** 2026-03-30
**Status:** Approved
**Author:** Claude + User collaboration

## Overview

This document specifies the design for adding real money transaction execution to SignalComposer. The system will execute actual Solana swaps via Jupiter Aggregator, with a robust state machine for tracking transaction lifecycle, retry logic, and safety mechanisms.

## Goals

1. Execute real token swaps on Solana via Jupiter Aggregator
2. Track transaction lifecycle with a state machine (pending → confirmed/failed)
3. Handle failures gracefully with smart retry logic
4. Protect users with circuit breakers and safety limits
5. Maintain position accuracy via on-chain reconciliation
6. Architect for future migration from server-side to client-side signing

## Non-Goals

- Client-side signing (future work)
- Multi-chain support (Solana only)
- Limit orders or advanced order types
- Copy trading or social features

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Wallet management | Hybrid (server-side MVP, client-side later) | Faster development, architected for migration |
| DEX integration | Jupiter Aggregator API | Best prices, route optimization, industry standard |
| Confirmation strategy | Tiered (processed → confirmed → finalized) | Responsive UX with accuracy |
| Retry logic | Smart retry with conditions re-check | Prevents executing stale trades |
| Reconciliation | After trade + periodic (5-10 min) | Accuracy without API overhead |
| Architecture | Shared base class (Paper/Live inherit) | Clean separation, code reuse |
| Safety | Full circuit breaker system | Real money demands paranoia |

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      LiveTradingManager                          │
│  (mirrors PaperTradingManager - orchestrates multiple sessions) │
└─────────────────────────────┬───────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ LiveTradingSession│ │ LiveTradingSession│ │ LiveTradingSession│
│     (User A)     │  │     (User B)     │  │     (User C)     │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │     TransactionCoordinator      │
              │  (singleton, manages all txs)  │
              └───────────────┬────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   ┌───────────┐       ┌────────────┐      ┌──────────────┐
   │SwapService│       │ TxSubmitter │      │ConfirmMonitor│
   │ (Jupiter) │       │  (Solana)   │      │   (Solana)   │
   └───────────┘       └────────────┘      └──────────────┘
```

### Components

- **LiveTradingManager**: Orchestrates multiple live sessions, shared polling loop
- **LiveTradingSession**: Inherits from BaseTradingSession, uses TransactionCoordinator for execution
- **TransactionCoordinator**: Owns state machine, dispatches to workers, enforces circuit breaker
- **SwapService**: Jupiter API wrapper (quote, build swap instruction)
- **TxSubmitter**: Signs transactions with keypair, sends to Solana RPC
- **ConfirmMonitor**: Polls transaction status, triggers state transitions

---

## Transaction State Machine

```
                              ┌─────────┐
                              │ PENDING │
                              └────┬────┘
                                   │
                              ┌────▼────┐
                              │ QUOTING │
                              └────┬────┘
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             ┌───────────┐  ┌───────────┐  ┌─────────────┐
             │QUOTE_FAILED│  │  SIGNING  │  │QUOTE_EXPIRED│
             └─────┬─────┘  └─────┬─────┘  └──────┬──────┘
                   │              │               │
                   │         ┌────▼────┐          │
                   │         │SUBMITTED│          │
                   │         └────┬────┘          │
                   │    ┌─────────┼─────────┐     │
                   │    ▼         ▼         ▼     │
                   │┌───────┐┌────────┐┌───────┐  │
                   ││TIMEOUT││CONFIRMING││DROPPED│  │
                   │└───┬───┘└────┬───┘└───┬───┘  │
                   │    │         │        │      │
                   │    │    ┌────▼────┐   │      │
                   │    │    │CONFIRMED│   │      │
                   │    │    └─────────┘   │      │
                   │    │                  │      │
                   └────┴────────┬─────────┴──────┘
                                 ▼
                          ┌─────────────┐
                          │ RETRY_CHECK │
                          └──────┬──────┘
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
             ┌──────────┐ ┌───────────┐ ┌─────────┐
             │  RETRY   │ │TRADE_STALE│ │MAX_RETRY│
             │(→PENDING)│ │  (abort)  │ │ (fail)  │
             └──────────┘ └───────────┘ └─────────┘
```

### State Definitions

| State | Description | Next Action |
|-------|-------------|-------------|
| `PENDING` | Trade queued, awaiting processing | Get Jupiter quote |
| `QUOTING` | Fetching swap quote from Jupiter | Build transaction |
| `SIGNING` | Building and signing transaction | Submit to RPC |
| `SUBMITTED` | Sent to Solana, awaiting confirmation | Poll status |
| `CONFIRMING` | Seen on-chain, awaiting finality | Continue polling |
| `CONFIRMED` | Finalized - update positions | Done (success) |
| `DROPPED` | Tx not found after timeout | Retry check |
| `TIMEOUT` | Confirmation took too long | Retry check |
| `QUOTE_EXPIRED` | Jupiter quote TTL exceeded | Retry check |
| `RETRY_CHECK` | Re-evaluating if trade still valid | Retry or abort |
| `QUOTE_FAILED` | Jupiter quote failed (permanent) | Terminal failure |
| `TRADE_STALE` | Conditions no longer hold | Terminal (abort) |
| `MAX_RETRY` | Exceeded retry attempts | Terminal failure |

### Timeouts

- Quote timeout: 10 seconds
- Confirmation timeout: 60 seconds
- Max retries: 3

### Quote Failure Handling

- **Transient errors** (network timeout, rate limit): Retry quote up to 2 times with 2s backoff
- **Permanent errors** (invalid token, no liquidity): Terminal failure, log and alert
- **Quote expired**: Go to RETRY_CHECK, re-evaluate conditions, get fresh quote if still valid

---

## Workers

| Worker | Triggered By | Responsibility | Transitions To |
|--------|--------------|----------------|----------------|
| `SwapWorker` | PENDING, QUOTE_EXPIRED | Calls Jupiter for quote, builds swap instruction | SIGNING or QUOTE_FAILED |
| `SubmitWorker` | SIGNING | Signs tx with keypair, sends to RPC | SUBMITTED or error |
| `ConfirmWorker` | SUBMITTED | Polls tx status every 2s | CONFIRMING → CONFIRMED or TIMEOUT |
| `ReconcileWorker` | CONFIRMED, periodic | Checks on-chain balances match expected | Updates positions |

Workers are stateless. All state lives in the Transaction object.

---

## Session Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      BaseTradingSession                          │
│  - price_buffers, derived_values, strategy                      │
│  - _trigger_states (cooldown tracking)                          │
│  + process_tick(), _evaluate_triggers(), _check_stop_losses()   │
│  + _execute_trade()  [ABSTRACT]                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────┐
│ PaperTradingSession │               │  LiveTradingSession │
├─────────────────────┤               ├─────────────────────┤
│ cash_balance        │               │ wallet: WalletConfig│
│ positions           │               │ coordinator         │
│ slippage_bps        │               │ pending_txs         │
├─────────────────────┤               ├─────────────────────┤
│ _execute_trade():   │               │ _execute_trade():   │
│   instant simulation│               │   async via coord   │
└─────────────────────┘               └─────────────────────┘
```

### Shared in BaseTradingSession

- Price buffer management
- Derived stream computation
- Trigger evaluation
- Trigger cooldown tracking
- Stop-loss checking
- Risk rule validation

### Specific to LiveTradingSession

- Async execution via TransactionCoordinator
- Real slippage from Jupiter quote
- Positions synced with on-chain balances
- Pending transaction tracking

---

## Safety & Circuit Breaker

### Trade Limits

| Limit | Default | Scope |
|-------|---------|-------|
| `max_trade_usd` | $500 | Per session |
| `max_daily_usd` | $2,000 | Per session |
| `max_daily_loss_usd` | $500 | Per session |
| `min_trade_interval_sec` | 30 | Global |
| `max_concurrent_txs` | 3 | Per session |

### Circuit Breaker

Trips after 3 consecutive failures. Auto-pauses session and sends alert.

**Counts as failure:**
- Transaction dropped/timeout (after all retries)
- Slippage exceeded limit
- Insufficient balance
- 3+ quote failures in a row

**Does NOT trip breaker:**
- Trade skipped (conditions not met)
- Daily limit reached
- Successful trade

### Kill Switch API

```
POST /live-trading/sessions/{id}/kill     # Kill single session
POST /live-trading/emergency-stop         # Kill ALL user sessions
```

### Alert Events

| Event | Level | Action |
|-------|-------|--------|
| Trade executed | Info | Log only |
| Circuit breaker tripped | Warning | Log + webhook |
| Max daily loss reached | Critical | Log + webhook |
| Kill switch activated | Critical | Log + webhook |
| Reconciliation mismatch | Critical | Log + webhook |

---

## Database Schema

### New Tables

```sql
-- Live trading sessions
CREATE TABLE live_trading_sessions (
    id SERIAL PRIMARY KEY,
    strategy_id INT REFERENCES strategies(id),
    user_id INT REFERENCES users(id),
    wallet_address VARCHAR(44) NOT NULL,
    status VARCHAR(20) DEFAULT 'running',

    -- Safety config
    max_trade_usd DECIMAL(12,2) DEFAULT 500,
    max_daily_usd DECIMAL(12,2) DEFAULT 2000,
    max_daily_loss_usd DECIMAL(12,2) DEFAULT 500,

    -- Circuit breaker
    consecutive_failures INT DEFAULT 0,
    circuit_breaker_tripped_at TIMESTAMP,

    -- Tracking
    started_at TIMESTAMP DEFAULT NOW(),
    stopped_at TIMESTAMP,
    last_tick_at TIMESTAMP,
    last_reconciled_at TIMESTAMP,

    -- Daily counters
    daily_volume_usd DECIMAL(12,2) DEFAULT 0,
    daily_pnl_usd DECIMAL(12,2) DEFAULT 0,
    daily_reset_date DATE DEFAULT CURRENT_DATE
);

-- Transaction records
CREATE TABLE live_transactions (
    id UUID PRIMARY KEY,
    session_id INT REFERENCES live_trading_sessions(id),
    trigger_id VARCHAR(100) NOT NULL,
    action_type VARCHAR(20) NOT NULL,
    token_address VARCHAR(44) NOT NULL,

    -- State machine
    state VARCHAR(20) NOT NULL,
    state_history JSONB DEFAULT '[]',
    retry_count INT DEFAULT 0,

    -- Quote data
    quote_input_mint VARCHAR(44),
    quote_output_mint VARCHAR(44),
    quote_amount_in BIGINT,
    quote_expected_out BIGINT,
    quote_price_impact_pct DECIMAL(5,2),
    quote_expires_at TIMESTAMP,

    -- Execution
    tx_signature VARCHAR(88),
    submitted_at TIMESTAMP,
    confirmed_at TIMESTAMP,
    actual_amount_out BIGINT,
    actual_price DECIMAL(20,8),
    slippage_bps INT,
    fee_lamports BIGINT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Position tracking
CREATE TABLE live_positions (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES live_trading_sessions(id),
    token_address VARCHAR(44) NOT NULL,
    expected_quantity DECIMAL(20,8),
    expected_avg_price DECIMAL(20,8),
    actual_quantity DECIMAL(20,8),
    last_reconciled_at TIMESTAMP,
    has_mismatch BOOLEAN DEFAULT FALSE,
    mismatch_details JSONB,
    UNIQUE(session_id, token_address)
);

-- Encrypted keypairs (MVP server-side signing)
CREATE TABLE wallet_keypairs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    wallet_address VARCHAR(44) NOT NULL UNIQUE,
    encrypted_keypair BYTEA NOT NULL,
    encryption_iv BYTEA NOT NULL,
    label VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP
);
```

---

## Error Handling

### Error Categories

| Category | Examples | Action |
|----------|----------|--------|
| Transient | Network timeout, RPC rate limit, Jupiter 5xx, tx dropped | Retry with backoff |
| Permanent | Invalid token, zero liquidity, slippage exceeded | Abort, no retry |
| Critical | Wallet drained, reconciliation mismatch, 3+ failures | Alert + pause session |

### Retry Configuration

```python
RETRY_CONFIG = {
    "quote": {"max_attempts": 2, "backoff_seconds": [1, 2]},
    "submit": {"max_attempts": 3, "backoff_seconds": [1, 2, 5]},
    "confirm": {"poll_interval_seconds": 2, "timeout_seconds": 60},
}
```

### Graceful Degradation

| Failure | Degradation |
|---------|-------------|
| Jupiter API down | Skip tick, retry next tick |
| Solana RPC overloaded | Switch to backup RPC, increase backoff |
| Single session failing | Pause that session, others continue |
| All sessions failing | Emergency stop, alert, require manual restart |

---

## Testing Strategy

### Unit Tests (fast, no I/O)

- State machine transitions (valid and invalid)
- Safety guard checks (limits, circuit breaker)
- Retry logic conditions

### Integration Tests (mocked services)

- Full trade flow with mock Jupiter and RPC
- Retry on dropped transaction
- Circuit breaker tripping
- Concurrent transaction handling
- Kill switch functionality

### E2E Tests (Solana devnet)

- Actual Jupiter swap on devnet
- Full session lifecycle with real blockchain
- Reconciliation with on-chain state

---

## File Structure

```
src/
├── live_trading/
│   ├── __init__.py
│   ├── session.py          # LiveTradingSession
│   ├── manager.py          # LiveTradingManager
│   ├── coordinator.py      # TransactionCoordinator
│   ├── state_machine.py    # Transaction states and transitions
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── swap_worker.py      # Jupiter quote/build
│   │   ├── submit_worker.py    # Sign and send
│   │   ├── confirm_worker.py   # Poll status
│   │   └── reconcile_worker.py # Balance check
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── guard.py           # SafetyGuard (limits)
│   │   ├── circuit_breaker.py # CircuitBreaker
│   │   └── alerts.py          # AlertSystem
│   └── services/
│       ├── __init__.py
│       ├── jupiter.py         # SwapService
│       ├── solana_rpc.py      # TxSubmitter, ConfirmMonitor
│       └── wallet.py          # Keypair management
├── trading/
│   └── base_session.py        # BaseTradingSession (shared)
├── db/
│   ├── models.py              # Add new tables
│   └── repositories/
│       └── live_trading_repository.py
└── api/
    └── routes/
        └── live_trading.py    # API endpoints
```

---

## API Endpoints

```
POST   /live-trading/sessions              # Start live session
GET    /live-trading/sessions              # List user sessions
GET    /live-trading/sessions/{id}         # Get session status
GET    /live-trading/sessions/{id}/txs     # Get transaction history
POST   /live-trading/sessions/{id}/pause   # Pause session
POST   /live-trading/sessions/{id}/resume  # Resume session
POST   /live-trading/sessions/{id}/stop    # Stop session
POST   /live-trading/sessions/{id}/kill    # Emergency kill
POST   /live-trading/emergency-stop        # Kill all sessions

POST   /wallets/keypairs                   # Upload encrypted keypair
GET    /wallets/keypairs                   # List user keypairs
DELETE /wallets/keypairs/{id}              # Remove keypair
```

---

## Implementation Order

1. **BaseTradingSession extraction** - Refactor Paper/Live inheritance
2. **Transaction state machine** - Core state tracking
3. **SwapService** - Jupiter API integration
4. **TxSubmitter** - Signing and RPC submission
5. **ConfirmMonitor** - Confirmation polling
6. **TransactionCoordinator** - Orchestration
7. **SafetyGuard & CircuitBreaker** - Protection layer
8. **LiveTradingSession** - Full session implementation
9. **LiveTradingManager** - Multi-session orchestration
10. **Database migrations** - New tables
11. **API endpoints** - REST interface
12. **Reconciliation** - Position verification
13. **Testing** - Unit, integration, E2E

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Wallet keypair management? | Server-side signing for MVP, architected for client-side migration |
| Which DEX? | Jupiter Aggregator API |
| Confirmation strategy? | Tiered (processed → confirmed → finalized) |
| Retry logic? | Smart retry with conditions re-check |
| Reconciliation frequency? | After trade + periodic (5-10 min) |
| Session architecture? | Shared BaseTradingSession, Paper/Live inherit |
| Safety mechanisms? | Full circuit breaker with kill switch |

---

## Success Criteria

1. Can execute a real SOL → USDC swap on mainnet
2. Transaction state tracked through full lifecycle
3. Failed transactions retry intelligently (conditions re-checked)
4. Circuit breaker pauses session after 3 failures
5. Kill switch stops all activity immediately
6. Positions reconcile with on-chain balances
7. All safety limits enforced before trade execution
8. Comprehensive test coverage (unit, integration, E2E)
