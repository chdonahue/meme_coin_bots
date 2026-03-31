# Real Money Transaction Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real money transaction execution to SignalComposer via Jupiter Aggregator with robust state machine, safety guards, and position reconciliation.

**Architecture:** State machine-driven transaction lifecycle (PENDING → CONFIRMED/FAILED) with async workers for Jupiter quotes, TX submission, and confirmation monitoring. Shared BaseTradingSession for Paper/Live sessions.

**Tech Stack:** Python, asyncio, httpx, solders (Solana), SQLAlchemy, FastAPI

---

## File Structure Overview

**New files to create:**
- `src/trading/base_session.py` - Shared session logic extracted from paper trading
- `src/live_trading/__init__.py` - Package init
- `src/live_trading/session.py` - LiveTradingSession
- `src/live_trading/manager.py` - LiveTradingManager
- `src/live_trading/coordinator.py` - TransactionCoordinator
- `src/live_trading/state_machine.py` - Transaction states and transitions
- `src/live_trading/workers/__init__.py` - Workers package
- `src/live_trading/workers/swap_worker.py` - Jupiter quote/build
- `src/live_trading/workers/submit_worker.py` - Sign and send
- `src/live_trading/workers/confirm_worker.py` - Poll status
- `src/live_trading/workers/reconcile_worker.py` - Balance check
- `src/live_trading/safety/__init__.py` - Safety package
- `src/live_trading/safety/guard.py` - SafetyGuard
- `src/live_trading/safety/circuit_breaker.py` - CircuitBreaker
- `src/live_trading/safety/alerts.py` - AlertSystem
- `src/live_trading/services/__init__.py` - Services package
- `src/live_trading/services/jupiter.py` - SwapService
- `src/live_trading/services/solana_rpc.py` - TxSubmitter, ConfirmMonitor
- `src/live_trading/services/wallet.py` - Keypair management
- `src/db/repositories/live_trading_repository.py` - Database layer
- `src/api/routes/live_trading.py` - API endpoints
- `src/api/schemas/live_trading.py` - Pydantic schemas
- `tests/live_trading/` - All test files

**Files to modify:**
- `src/paper_trading/session.py` - Extract base class
- `src/db/models.py` - Add new tables
- `src/api/main.py` - Register routes

---

## Task 1: Transaction State Machine

**Files:**
- Create: `src/live_trading/__init__.py`
- Create: `src/live_trading/state_machine.py`
- Test: `tests/live_trading/test_state_machine.py`

- [ ] **Step 1: Create package and test file**

Create the live_trading package directory and test file:

```bash
mkdir -p src/live_trading
mkdir -p tests/live_trading
touch src/live_trading/__init__.py
touch tests/live_trading/__init__.py
```

- [ ] **Step 2: Write test for TransactionState enum**

```python
# tests/live_trading/test_state_machine.py
"""Tests for transaction state machine."""

import pytest
from src.live_trading.state_machine import TransactionState


class TestTransactionState:
    """Tests for TransactionState enum."""

    def test_all_states_defined(self):
        """Verify all expected states exist."""
        expected = [
            "PENDING", "QUOTING", "SIGNING", "SUBMITTED",
            "CONFIRMING", "CONFIRMED", "DROPPED", "TIMEOUT",
            "QUOTE_FAILED", "QUOTE_EXPIRED", "RETRY_CHECK",
            "TRADE_STALE", "MAX_RETRY"
        ]
        actual = [s.name for s in TransactionState]
        assert set(expected) == set(actual)

    def test_terminal_states(self):
        """Terminal states should be identified."""
        terminal = [
            TransactionState.CONFIRMED,
            TransactionState.QUOTE_FAILED,
            TransactionState.TRADE_STALE,
            TransactionState.MAX_RETRY,
        ]
        for state in terminal:
            assert state.is_terminal

    def test_non_terminal_states(self):
        """Non-terminal states should not be marked terminal."""
        non_terminal = [
            TransactionState.PENDING,
            TransactionState.QUOTING,
            TransactionState.SUBMITTED,
        ]
        for state in non_terminal:
            assert not state.is_terminal
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py -v`
Expected: FAIL with "No module named 'src.live_trading.state_machine'"

- [ ] **Step 4: Implement TransactionState enum**

```python
# src/live_trading/state_machine.py
"""Transaction state machine for live trading."""

from enum import Enum


class TransactionState(Enum):
    """States in the transaction lifecycle."""

    PENDING = "pending"
    QUOTING = "quoting"
    SIGNING = "signing"
    SUBMITTED = "submitted"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    DROPPED = "dropped"
    TIMEOUT = "timeout"
    QUOTE_FAILED = "quote_failed"
    QUOTE_EXPIRED = "quote_expired"
    RETRY_CHECK = "retry_check"
    TRADE_STALE = "trade_stale"
    MAX_RETRY = "max_retry"

    @property
    def is_terminal(self) -> bool:
        """Whether this state is a final state."""
        return self in {
            TransactionState.CONFIRMED,
            TransactionState.QUOTE_FAILED,
            TransactionState.TRADE_STALE,
            TransactionState.MAX_RETRY,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py::TestTransactionState -v`
Expected: PASS

- [ ] **Step 6: Write test for valid transitions**

Add to `tests/live_trading/test_state_machine.py`:

```python
from src.live_trading.state_machine import TransactionState, VALID_TRANSITIONS, can_transition


class TestTransitions:
    """Tests for state transitions."""

    def test_pending_to_quoting_valid(self):
        """PENDING -> QUOTING is valid."""
        assert can_transition(TransactionState.PENDING, TransactionState.QUOTING)

    def test_quoting_to_signing_valid(self):
        """QUOTING -> SIGNING is valid."""
        assert can_transition(TransactionState.QUOTING, TransactionState.SIGNING)

    def test_quoting_to_quote_failed_valid(self):
        """QUOTING -> QUOTE_FAILED is valid."""
        assert can_transition(TransactionState.QUOTING, TransactionState.QUOTE_FAILED)

    def test_submitted_to_confirming_valid(self):
        """SUBMITTED -> CONFIRMING is valid."""
        assert can_transition(TransactionState.SUBMITTED, TransactionState.CONFIRMING)

    def test_invalid_transition_fails(self):
        """Invalid transitions should return False."""
        assert not can_transition(TransactionState.PENDING, TransactionState.CONFIRMED)
        assert not can_transition(TransactionState.CONFIRMED, TransactionState.PENDING)

    def test_terminal_state_has_no_transitions(self):
        """Terminal states have no valid outgoing transitions."""
        for state in [TransactionState.CONFIRMED, TransactionState.MAX_RETRY]:
            assert state not in VALID_TRANSITIONS or len(VALID_TRANSITIONS[state]) == 0
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py::TestTransitions -v`
Expected: FAIL with "cannot import name 'VALID_TRANSITIONS'"

- [ ] **Step 8: Implement transition logic**

Add to `src/live_trading/state_machine.py`:

```python
# Valid state transitions
VALID_TRANSITIONS: dict[TransactionState, set[TransactionState]] = {
    TransactionState.PENDING: {TransactionState.QUOTING},
    TransactionState.QUOTING: {
        TransactionState.SIGNING,
        TransactionState.QUOTE_FAILED,
        TransactionState.QUOTE_EXPIRED,
    },
    TransactionState.SIGNING: {TransactionState.SUBMITTED},
    TransactionState.SUBMITTED: {
        TransactionState.CONFIRMING,
        TransactionState.DROPPED,
        TransactionState.TIMEOUT,
    },
    TransactionState.CONFIRMING: {
        TransactionState.CONFIRMED,
        TransactionState.TIMEOUT,
    },
    TransactionState.DROPPED: {TransactionState.RETRY_CHECK},
    TransactionState.TIMEOUT: {TransactionState.RETRY_CHECK},
    TransactionState.QUOTE_EXPIRED: {TransactionState.RETRY_CHECK},
    TransactionState.RETRY_CHECK: {
        TransactionState.PENDING,  # Retry
        TransactionState.TRADE_STALE,
        TransactionState.MAX_RETRY,
    },
    # Terminal states - no outgoing transitions
    TransactionState.CONFIRMED: set(),
    TransactionState.QUOTE_FAILED: set(),
    TransactionState.TRADE_STALE: set(),
    TransactionState.MAX_RETRY: set(),
}


def can_transition(from_state: TransactionState, to_state: TransactionState) -> bool:
    """Check if a state transition is valid."""
    valid_next = VALID_TRANSITIONS.get(from_state, set())
    return to_state in valid_next
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py::TestTransitions -v`
Expected: PASS

- [ ] **Step 10: Write test for Transaction dataclass**

Add to `tests/live_trading/test_state_machine.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4
from src.live_trading.state_machine import Transaction


class TestTransaction:
    """Tests for Transaction class."""

    def test_create_transaction(self):
        """Test creating a new transaction."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )
        assert tx.state == TransactionState.PENDING
        assert tx.retry_count == 0
        assert tx.id is not None

    def test_transition_updates_state(self):
        """Test that transition updates state and history."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        tx.transition_to(TransactionState.QUOTING)
        assert tx.state == TransactionState.QUOTING
        assert len(tx.state_history) == 1
        assert tx.state_history[0]["from"] == "PENDING"
        assert tx.state_history[0]["to"] == "QUOTING"

    def test_invalid_transition_raises(self):
        """Invalid transition should raise ValueError."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        with pytest.raises(ValueError, match="Invalid transition"):
            tx.transition_to(TransactionState.CONFIRMED)
```

- [ ] **Step 11: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py::TestTransaction -v`
Expected: FAIL with "cannot import name 'Transaction'"

- [ ] **Step 12: Implement Transaction class**

Add to `src/live_trading/state_machine.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Transaction:
    """A live trading transaction with state machine."""

    session_id: int
    trigger_id: str
    action_type: str  # "buy", "sell", "sell_all"
    token_address: str
    amount_pct: float

    # State
    id: UUID = field(default_factory=uuid4)
    state: TransactionState = TransactionState.PENDING
    state_history: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0

    # Quote data
    quote_input_mint: str | None = None
    quote_output_mint: str | None = None
    quote_amount_in: int | None = None
    quote_expected_out: int | None = None
    quote_price_impact_pct: float | None = None
    quote_expires_at: datetime | None = None

    # Execution data
    tx_signature: str | None = None
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None
    actual_amount_out: int | None = None
    actual_price: float | None = None
    slippage_bps: int | None = None
    fee_lamports: int | None = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def transition_to(self, new_state: TransactionState) -> None:
        """Transition to a new state."""
        if not can_transition(self.state, new_state):
            raise ValueError(
                f"Invalid transition: {self.state.name} -> {new_state.name}"
            )

        self.state_history.append({
            "from": self.state.name,
            "to": new_state.name,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
```

- [ ] **Step 13: Run all state machine tests**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_state_machine.py -v`
Expected: PASS (all tests)

- [ ] **Step 14: Commit**

```bash
cd signal_composer && git add src/live_trading/ tests/live_trading/ && git commit -m "feat(live-trading): add transaction state machine

- TransactionState enum with all lifecycle states
- Valid transition rules (PENDING -> QUOTING -> SIGNING -> etc)
- Transaction dataclass with state history tracking
- Terminal state detection (CONFIRMED, FAILED states)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Safety Guard

**Files:**
- Create: `src/live_trading/safety/__init__.py`
- Create: `src/live_trading/safety/guard.py`
- Test: `tests/live_trading/test_safety_guard.py`

- [ ] **Step 1: Create safety package**

```bash
mkdir -p src/live_trading/safety
touch src/live_trading/safety/__init__.py
```

- [ ] **Step 2: Write test for SafetyConfig**

```python
# tests/live_trading/test_safety_guard.py
"""Tests for SafetyGuard."""

import pytest
from decimal import Decimal
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard


class TestSafetyConfig:
    """Tests for SafetyConfig."""

    def test_default_config(self):
        """Test default safety configuration."""
        config = SafetyConfig()
        assert config.max_trade_usd == Decimal("500")
        assert config.max_daily_usd == Decimal("2000")
        assert config.max_daily_loss_usd == Decimal("500")
        assert config.min_trade_interval_sec == 30
        assert config.max_concurrent_txs == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_safety_guard.py::TestSafetyConfig -v`
Expected: FAIL with "No module named 'src.live_trading.safety.guard'"

- [ ] **Step 4: Implement SafetyConfig**

```python
# src/live_trading/safety/guard.py
"""Safety guards for live trading."""

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone


@dataclass
class SafetyConfig:
    """Configuration for safety limits."""

    max_trade_usd: Decimal = Decimal("500")
    max_daily_usd: Decimal = Decimal("2000")
    max_daily_loss_usd: Decimal = Decimal("500")
    min_trade_interval_sec: int = 30
    max_concurrent_txs: int = 3
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_safety_guard.py::TestSafetyConfig -v`
Expected: PASS

- [ ] **Step 6: Write tests for SafetyGuard checks**

Add to `tests/live_trading/test_safety_guard.py`:

```python
class TestSafetyGuard:
    """Tests for SafetyGuard."""

    @pytest.fixture
    def guard(self):
        """Create a SafetyGuard with default config."""
        return SafetyGuard(SafetyConfig())

    def test_check_trade_size_within_limit(self, guard):
        """Trade within limit should pass."""
        result = guard.check_trade_size(Decimal("100"))
        assert result.allowed
        assert result.reason == ""

    def test_check_trade_size_exceeds_limit(self, guard):
        """Trade exceeding limit should fail."""
        result = guard.check_trade_size(Decimal("600"))
        assert not result.allowed
        assert "exceeds max" in result.reason.lower()

    def test_check_daily_volume_within_limit(self, guard):
        """Daily volume within limit should pass."""
        result = guard.check_daily_volume(
            current_daily_usd=Decimal("1000"),
            proposed_trade_usd=Decimal("500"),
        )
        assert result.allowed

    def test_check_daily_volume_exceeds_limit(self, guard):
        """Daily volume exceeding limit should fail."""
        result = guard.check_daily_volume(
            current_daily_usd=Decimal("1800"),
            proposed_trade_usd=Decimal("500"),
        )
        assert not result.allowed
        assert "daily limit" in result.reason.lower()

    def test_check_daily_loss_within_limit(self, guard):
        """Daily loss within limit should pass."""
        result = guard.check_daily_loss(current_daily_loss_usd=Decimal("400"))
        assert result.allowed

    def test_check_daily_loss_exceeds_limit(self, guard):
        """Daily loss exceeding limit should fail."""
        result = guard.check_daily_loss(current_daily_loss_usd=Decimal("600"))
        assert not result.allowed
        assert "daily loss" in result.reason.lower()

    def test_check_trade_interval_ok(self, guard):
        """Trade after minimum interval should pass."""
        last_trade = datetime.now(timezone.utc).replace(
            second=datetime.now(timezone.utc).second - 60
        )
        result = guard.check_trade_interval(last_trade)
        assert result.allowed

    def test_check_trade_interval_too_soon(self, guard):
        """Trade before minimum interval should fail."""
        last_trade = datetime.now(timezone.utc)
        result = guard.check_trade_interval(last_trade)
        assert not result.allowed
        assert "interval" in result.reason.lower()

    def test_check_concurrent_txs_within_limit(self, guard):
        """Concurrent txs within limit should pass."""
        result = guard.check_concurrent_txs(current_count=2)
        assert result.allowed

    def test_check_concurrent_txs_at_limit(self, guard):
        """Concurrent txs at limit should fail."""
        result = guard.check_concurrent_txs(current_count=3)
        assert not result.allowed
        assert "concurrent" in result.reason.lower()
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_safety_guard.py::TestSafetyGuard -v`
Expected: FAIL

- [ ] **Step 8: Implement SafetyGuard**

Add to `src/live_trading/safety/guard.py`:

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone, timedelta


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""

    allowed: bool
    reason: str = ""


class SafetyGuard:
    """Enforces trading safety limits."""

    def __init__(self, config: SafetyConfig):
        self.config = config

    def check_trade_size(self, trade_usd: Decimal) -> SafetyCheckResult:
        """Check if trade size is within limit."""
        if trade_usd > self.config.max_trade_usd:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Trade ${trade_usd} exceeds max ${self.config.max_trade_usd}",
            )
        return SafetyCheckResult(allowed=True)

    def check_daily_volume(
        self,
        current_daily_usd: Decimal,
        proposed_trade_usd: Decimal,
    ) -> SafetyCheckResult:
        """Check if daily volume limit allows this trade."""
        new_total = current_daily_usd + proposed_trade_usd
        if new_total > self.config.max_daily_usd:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Would exceed daily limit: ${new_total} > ${self.config.max_daily_usd}",
            )
        return SafetyCheckResult(allowed=True)

    def check_daily_loss(self, current_daily_loss_usd: Decimal) -> SafetyCheckResult:
        """Check if daily loss limit has been exceeded."""
        if current_daily_loss_usd >= self.config.max_daily_loss_usd:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Daily loss limit reached: ${current_daily_loss_usd}",
            )
        return SafetyCheckResult(allowed=True)

    def check_trade_interval(self, last_trade_at: datetime | None) -> SafetyCheckResult:
        """Check if minimum interval has passed since last trade."""
        if last_trade_at is None:
            return SafetyCheckResult(allowed=True)

        elapsed = (datetime.now(timezone.utc) - last_trade_at).total_seconds()
        if elapsed < self.config.min_trade_interval_sec:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Trade interval too short: {elapsed:.0f}s < {self.config.min_trade_interval_sec}s",
            )
        return SafetyCheckResult(allowed=True)

    def check_concurrent_txs(self, current_count: int) -> SafetyCheckResult:
        """Check if concurrent transaction limit allows another."""
        if current_count >= self.config.max_concurrent_txs:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Max concurrent txs reached: {current_count}",
            )
        return SafetyCheckResult(allowed=True)

    def run_all_checks(
        self,
        trade_usd: Decimal,
        current_daily_usd: Decimal,
        current_daily_loss_usd: Decimal,
        last_trade_at: datetime | None,
        concurrent_tx_count: int,
    ) -> SafetyCheckResult:
        """Run all safety checks, return first failure or success."""
        checks = [
            self.check_trade_size(trade_usd),
            self.check_daily_volume(current_daily_usd, trade_usd),
            self.check_daily_loss(current_daily_loss_usd),
            self.check_trade_interval(last_trade_at),
            self.check_concurrent_txs(concurrent_tx_count),
        ]
        for check in checks:
            if not check.allowed:
                return check
        return SafetyCheckResult(allowed=True)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_safety_guard.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
cd signal_composer && git add src/live_trading/safety/ tests/live_trading/test_safety_guard.py && git commit -m "feat(live-trading): add SafetyGuard with trade limits

- SafetyConfig with configurable limits
- Per-trade size limit check
- Daily volume limit check
- Daily loss limit check
- Minimum trade interval check
- Concurrent transaction limit check

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Circuit Breaker

**Files:**
- Create: `src/live_trading/safety/circuit_breaker.py`
- Test: `tests/live_trading/test_circuit_breaker.py`

- [ ] **Step 1: Write test for CircuitBreaker**

```python
# tests/live_trading/test_circuit_breaker.py
"""Tests for CircuitBreaker."""

import pytest
from datetime import datetime, timezone
from src.live_trading.safety.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create a CircuitBreaker with threshold of 3."""
        return CircuitBreaker(failure_threshold=3)

    def test_initial_state_closed(self, breaker):
        """Circuit should start closed (allowing trades)."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()

    def test_single_failure_stays_closed(self, breaker):
        """Single failure should not trip breaker."""
        breaker.record_failure("tx_dropped")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()

    def test_consecutive_failures_trips_breaker(self, breaker):
        """3 consecutive failures should trip breaker."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_failure("slippage_exceeded")

        assert breaker.state == CircuitState.OPEN
        assert not breaker.allows_trade()
        assert breaker.tripped_at is not None

    def test_success_resets_failure_count(self, breaker):
        """Success should reset consecutive failure count."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_success()
        breaker.record_failure("tx_dropped")

        assert breaker.state == CircuitState.CLOSED
        assert breaker.consecutive_failures == 1

    def test_manual_reset(self, breaker):
        """Manual reset should close the circuit."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_failure("slippage_exceeded")
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()
        assert breaker.consecutive_failures == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_circuit_breaker.py -v`
Expected: FAIL with "No module named 'src.live_trading.safety.circuit_breaker'"

- [ ] **Step 3: Implement CircuitBreaker**

```python
# src/live_trading/safety/circuit_breaker.py
"""Circuit breaker for live trading."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CircuitState(Enum):
    """State of the circuit breaker."""

    CLOSED = "closed"  # Normal operation, trades allowed
    OPEN = "open"      # Tripped, trades blocked


@dataclass
class CircuitBreaker:
    """Circuit breaker that trips after consecutive failures."""

    failure_threshold: int = 3
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    failure_reasons: list[str] = field(default_factory=list)
    tripped_at: datetime | None = None

    def allows_trade(self) -> bool:
        """Check if trades are allowed."""
        return self.state == CircuitState.CLOSED

    def record_failure(self, reason: str) -> None:
        """Record a failure. May trip the breaker."""
        self.consecutive_failures += 1
        self.failure_reasons.append(reason)

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.tripped_at = datetime.now(timezone.utc)

    def record_success(self) -> None:
        """Record a success. Resets failure count."""
        self.consecutive_failures = 0
        self.failure_reasons.clear()

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.failure_reasons.clear()
        self.tripped_at = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_circuit_breaker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/live_trading/safety/circuit_breaker.py tests/live_trading/test_circuit_breaker.py && git commit -m "feat(live-trading): add CircuitBreaker

- Trips after N consecutive failures (default 3)
- Blocks all trades when open
- Success resets failure count
- Manual reset capability

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Jupiter SwapService

**Files:**
- Create: `src/live_trading/services/__init__.py`
- Create: `src/live_trading/services/jupiter.py`
- Test: `tests/live_trading/test_jupiter_service.py`

- [ ] **Step 1: Create services package**

```bash
mkdir -p src/live_trading/services
touch src/live_trading/services/__init__.py
```

- [ ] **Step 2: Write test for SwapQuote dataclass**

```python
# tests/live_trading/test_jupiter_service.py
"""Tests for Jupiter SwapService."""

import pytest
from datetime import datetime, timezone, timedelta
from src.live_trading.services.jupiter import SwapQuote, SwapService


class TestSwapQuote:
    """Tests for SwapQuote dataclass."""

    def test_quote_not_expired(self):
        """Fresh quote should not be expired."""
        quote = SwapQuote(
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            in_amount=1_000_000_000,  # 1 SOL in lamports
            out_amount=100_000_000,   # 100 USDC
            price_impact_pct=0.1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            route_plan=[],
            swap_transaction="base64_tx_data",
        )
        assert not quote.is_expired

    def test_quote_expired(self):
        """Old quote should be expired."""
        quote = SwapQuote(
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            in_amount=1_000_000_000,
            out_amount=100_000_000,
            price_impact_pct=0.1,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            route_plan=[],
            swap_transaction="base64_tx_data",
        )
        assert quote.is_expired
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_jupiter_service.py::TestSwapQuote -v`
Expected: FAIL

- [ ] **Step 4: Implement SwapQuote**

```python
# src/live_trading/services/jupiter.py
"""Jupiter Aggregator integration for swaps."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class SwapQuote:
    """Quote from Jupiter for a swap."""

    input_mint: str
    output_mint: str
    in_amount: int  # In smallest units (lamports)
    out_amount: int
    price_impact_pct: float
    expires_at: datetime
    route_plan: list[dict[str, Any]]
    swap_transaction: str  # Base64 encoded transaction

    @property
    def is_expired(self) -> bool:
        """Check if quote has expired."""
        return datetime.now(timezone.utc) > self.expires_at
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_jupiter_service.py::TestSwapQuote -v`
Expected: PASS

- [ ] **Step 6: Write test for SwapService.get_quote (mocked)**

Add to `tests/live_trading/test_jupiter_service.py`:

```python
from unittest.mock import AsyncMock, patch


class TestSwapService:
    """Tests for SwapService."""

    @pytest.fixture
    def service(self):
        """Create SwapService."""
        return SwapService()

    @pytest.mark.asyncio
    async def test_get_quote_success(self, service):
        """Test getting a quote from Jupiter."""
        mock_response = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "inAmount": "1000000000",
            "outAmount": "100000000",
            "priceImpactPct": "0.1",
            "routePlan": [],
        }

        mock_swap_response = {
            "swapTransaction": "base64_encoded_transaction_data",
        }

        with patch.object(service, "_fetch_quote", new_callable=AsyncMock) as mock_quote:
            with patch.object(service, "_fetch_swap_tx", new_callable=AsyncMock) as mock_swap:
                mock_quote.return_value = mock_response
                mock_swap.return_value = mock_swap_response

                quote = await service.get_quote(
                    input_mint="So11111111111111111111111111111111111111112",
                    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    amount=1_000_000_000,
                    slippage_bps=100,
                )

                assert quote is not None
                assert quote.in_amount == 1_000_000_000
                assert quote.out_amount == 100_000_000
                assert not quote.is_expired

    @pytest.mark.asyncio
    async def test_get_quote_no_route(self, service):
        """Test handling no route found."""
        with patch.object(service, "_fetch_quote", new_callable=AsyncMock) as mock_quote:
            mock_quote.return_value = None

            quote = await service.get_quote(
                input_mint="invalid_mint",
                output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                amount=1_000_000_000,
                slippage_bps=100,
            )

            assert quote is None
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_jupiter_service.py::TestSwapService -v`
Expected: FAIL

- [ ] **Step 8: Implement SwapService**

Add to `src/live_trading/services/jupiter.py`:

```python
import httpx
from datetime import timedelta
from typing import Any
import logging

logger = logging.getLogger(__name__)

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
QUOTE_TTL_SECONDS = 30


class SwapService:
    """Jupiter Aggregator swap service."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
    ) -> dict[str, Any] | None:
        """Fetch quote from Jupiter API."""
        client = await self._get_client()
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
        }
        try:
            response = await client.get(JUPITER_QUOTE_URL, params=params)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Jupiter quote failed: {response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Jupiter quote request error: {e}")
            return None

    async def _fetch_swap_tx(
        self,
        quote_response: dict[str, Any],
        user_public_key: str,
    ) -> dict[str, Any] | None:
        """Fetch swap transaction from Jupiter API."""
        client = await self._get_client()
        payload = {
            "quoteResponse": quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": True,
        }
        try:
            response = await client.post(JUPITER_SWAP_URL, json=payload)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Jupiter swap tx failed: {response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Jupiter swap request error: {e}")
            return None

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
        user_public_key: str = "",
    ) -> SwapQuote | None:
        """Get a swap quote from Jupiter."""
        quote_data = await self._fetch_quote(input_mint, output_mint, amount, slippage_bps)
        if quote_data is None:
            return None

        # For now, skip swap tx fetch if no public key (unit testing)
        swap_tx = ""
        if user_public_key:
            swap_response = await self._fetch_swap_tx(quote_data, user_public_key)
            if swap_response:
                swap_tx = swap_response.get("swapTransaction", "")

        return SwapQuote(
            input_mint=quote_data["inputMint"],
            output_mint=quote_data["outputMint"],
            in_amount=int(quote_data["inAmount"]),
            out_amount=int(quote_data["outAmount"]),
            price_impact_pct=float(quote_data.get("priceImpactPct", 0)),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=QUOTE_TTL_SECONDS),
            route_plan=quote_data.get("routePlan", []),
            swap_transaction=swap_tx,
        )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_jupiter_service.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
cd signal_composer && git add src/live_trading/services/ tests/live_trading/test_jupiter_service.py && git commit -m "feat(live-trading): add Jupiter SwapService

- SwapQuote dataclass with expiry tracking
- SwapService for Jupiter Aggregator API
- Quote fetching with slippage config
- Swap transaction building

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Solana RPC Services (TxSubmitter + ConfirmMonitor)

**Files:**
- Create: `src/live_trading/services/solana_rpc.py`
- Test: `tests/live_trading/test_solana_rpc.py`

- [ ] **Step 1: Write test for TxSubmitter**

```python
# tests/live_trading/test_solana_rpc.py
"""Tests for Solana RPC services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.live_trading.services.solana_rpc import TxSubmitter, ConfirmMonitor, TxStatus


class TestTxSubmitter:
    """Tests for TxSubmitter."""

    @pytest.fixture
    def submitter(self):
        """Create TxSubmitter."""
        return TxSubmitter(rpc_url="https://api.mainnet-beta.solana.com")

    @pytest.mark.asyncio
    async def test_submit_transaction_success(self, submitter):
        """Test successful transaction submission."""
        mock_signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(submitter, "_send_transaction", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_signature

            result = await submitter.submit(
                signed_tx_base64="signed_transaction_base64"
            )

            assert result.signature == mock_signature
            assert result.success

    @pytest.mark.asyncio
    async def test_submit_transaction_failure(self, submitter):
        """Test failed transaction submission."""
        with patch.object(submitter, "_send_transaction", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None

            result = await submitter.submit(
                signed_tx_base64="invalid_transaction"
            )

            assert not result.success
            assert result.signature is None


class TestConfirmMonitor:
    """Tests for ConfirmMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create ConfirmMonitor."""
        return ConfirmMonitor(rpc_url="https://api.mainnet-beta.solana.com")

    @pytest.mark.asyncio
    async def test_check_status_confirmed(self, monitor):
        """Test checking confirmed transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "confirmed",
                "err": None,
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_check_status_not_found(self, monitor):
        """Test checking non-existent transaction."""
        signature = "invalid_signature"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = None

            status = await monitor.check_status(signature)

            assert status == TxStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_check_status_failed(self, monitor):
        """Test checking failed transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "confirmed",
                "err": {"InstructionError": [0, "Custom"]},
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.FAILED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_solana_rpc.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TxSubmitter and ConfirmMonitor**

```python
# src/live_trading/services/solana_rpc.py
"""Solana RPC services for transaction submission and monitoring."""

import base64
import httpx
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TxStatus(Enum):
    """Transaction confirmation status."""

    NOT_FOUND = "not_found"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FINALIZED = "finalized"
    FAILED = "failed"


@dataclass
class SubmitResult:
    """Result of transaction submission."""

    success: bool
    signature: str | None = None
    error: str | None = None


class TxSubmitter:
    """Submits transactions to Solana RPC."""

    def __init__(self, rpc_url: str, timeout: float = 30.0):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _send_transaction(self, tx_base64: str) -> str | None:
        """Send transaction to RPC."""
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [
                tx_base64,
                {"encoding": "base64", "skipPreflight": False},
            ],
        }
        try:
            response = await client.post(self.rpc_url, json=payload)
            data = response.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                logger.error(f"RPC error: {data['error']}")
            return None
        except httpx.RequestError as e:
            logger.error(f"RPC request error: {e}")
            return None

    async def submit(self, signed_tx_base64: str) -> SubmitResult:
        """Submit a signed transaction."""
        signature = await self._send_transaction(signed_tx_base64)
        if signature:
            return SubmitResult(success=True, signature=signature)
        return SubmitResult(success=False, error="Failed to submit transaction")


class ConfirmMonitor:
    """Monitors transaction confirmation status."""

    def __init__(self, rpc_url: str, timeout: float = 10.0):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get_signature_status(self, signature: str) -> dict[str, Any] | None:
        """Get signature status from RPC."""
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignatureStatuses",
            "params": [[signature]],
        }
        try:
            response = await client.post(self.rpc_url, json=payload)
            data = response.json()
            if "result" in data and data["result"]["value"]:
                return data["result"]["value"][0]
            return None
        except httpx.RequestError as e:
            logger.error(f"RPC request error: {e}")
            return None

    async def check_status(self, signature: str) -> TxStatus:
        """Check transaction confirmation status."""
        status_data = await self._get_signature_status(signature)

        if status_data is None:
            return TxStatus.NOT_FOUND

        if status_data.get("err"):
            return TxStatus.FAILED

        confirmation = status_data.get("confirmationStatus")
        if confirmation == "finalized":
            return TxStatus.FINALIZED
        elif confirmation == "confirmed":
            return TxStatus.CONFIRMED
        elif confirmation == "processed":
            return TxStatus.PROCESSING

        return TxStatus.NOT_FOUND
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_solana_rpc.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/live_trading/services/solana_rpc.py tests/live_trading/test_solana_rpc.py && git commit -m "feat(live-trading): add Solana RPC services

- TxSubmitter for transaction submission
- ConfirmMonitor for status polling
- TxStatus enum for confirmation levels

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Wallet Service (Keypair Management)

**Files:**
- Create: `src/live_trading/services/wallet.py`
- Test: `tests/live_trading/test_wallet_service.py`

- [ ] **Step 1: Write test for WalletService**

```python
# tests/live_trading/test_wallet_service.py
"""Tests for WalletService."""

import pytest
from unittest.mock import MagicMock
from src.live_trading.services.wallet import WalletService


class TestWalletService:
    """Tests for WalletService."""

    def test_sign_transaction(self):
        """Test signing a transaction."""
        # Using a test keypair (DO NOT use in production)
        test_keypair_bytes = bytes([
            174, 47, 154, 16, 202, 193, 206, 113,
            199, 190, 53, 133, 169, 175, 31, 56,
            222, 53, 138, 189, 224, 216, 117, 173,
            10, 149, 53, 45, 73, 251, 237, 246,
            15, 23, 189, 78, 100, 132, 190, 231,
            63, 64, 195, 57, 48, 63, 154, 79,
            180, 237, 64, 21, 3, 15, 176, 128,
            196, 75, 92, 35, 220, 131, 189, 83,
        ])

        service = WalletService()
        service.load_keypair(test_keypair_bytes)

        assert service.public_key is not None
        assert len(service.public_key) == 44  # Base58 encoded

    def test_no_keypair_loaded(self):
        """Test error when no keypair loaded."""
        service = WalletService()

        with pytest.raises(ValueError, match="No keypair loaded"):
            service.sign_message(b"test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_wallet_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement WalletService**

```python
# src/live_trading/services/wallet.py
"""Wallet and keypair management."""

import base64
import base58
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os


class WalletService:
    """Manages wallet keypairs for signing transactions."""

    def __init__(self):
        self._keypair: bytes | None = None
        self._public_key: str | None = None

    @property
    def public_key(self) -> str | None:
        """Get the public key as base58 string."""
        return self._public_key

    def load_keypair(self, keypair_bytes: bytes) -> None:
        """Load a keypair from raw bytes (64 bytes: 32 secret + 32 public)."""
        if len(keypair_bytes) != 64:
            raise ValueError("Keypair must be 64 bytes")

        self._keypair = keypair_bytes
        # Public key is the last 32 bytes
        public_key_bytes = keypair_bytes[32:]
        self._public_key = base58.b58encode(public_key_bytes).decode("utf-8")

    def sign_message(self, message: bytes) -> bytes:
        """Sign a message with the loaded keypair."""
        if self._keypair is None:
            raise ValueError("No keypair loaded")

        # Import nacl for signing (Ed25519)
        try:
            from nacl.signing import SigningKey
        except ImportError:
            raise ImportError("PyNaCl required for signing: pip install pynacl")

        # First 32 bytes are the secret key
        secret_key = self._keypair[:32]
        signing_key = SigningKey(secret_key)
        signed = signing_key.sign(message)
        return signed.signature

    @staticmethod
    def encrypt_keypair(keypair_bytes: bytes, password: str) -> tuple[bytes, bytes]:
        """Encrypt a keypair with a password. Returns (encrypted_data, salt)."""
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        encrypted = fernet.encrypt(keypair_bytes)
        return encrypted, salt

    @staticmethod
    def decrypt_keypair(encrypted_data: bytes, salt: bytes, password: str) -> bytes:
        """Decrypt a keypair with password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_wallet_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/live_trading/services/wallet.py tests/live_trading/test_wallet_service.py && git commit -m "feat(live-trading): add WalletService for keypair management

- Load keypair from bytes
- Sign messages with Ed25519
- Encrypt/decrypt keypairs with password

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: TransactionCoordinator

**Files:**
- Create: `src/live_trading/coordinator.py`
- Test: `tests/live_trading/test_coordinator.py`

- [ ] **Step 1: Write test for TransactionCoordinator**

```python
# tests/live_trading/test_coordinator.py
"""Tests for TransactionCoordinator."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.state_machine import Transaction, TransactionState
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker


class TestTransactionCoordinator:
    """Tests for TransactionCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    def test_queue_transaction(self, coordinator):
        """Test queuing a transaction."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        coordinator.queue(tx)

        assert len(coordinator.pending_transactions) == 1
        assert coordinator.pending_transactions[0].id == tx.id

    def test_queue_blocked_by_circuit_breaker(self, coordinator):
        """Test that circuit breaker blocks new transactions."""
        # Trip the breaker
        for _ in range(3):
            coordinator.circuit_breaker.record_failure("test")

        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        with pytest.raises(RuntimeError, match="Circuit breaker"):
            coordinator.queue(tx)

    def test_get_transaction_by_id(self, coordinator):
        """Test retrieving a transaction by ID."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )
        coordinator.queue(tx)

        found = coordinator.get_transaction(tx.id)

        assert found is not None
        assert found.id == tx.id

    def test_get_pending_count(self, coordinator):
        """Test getting count of pending transactions."""
        for i in range(3):
            tx = Transaction(
                session_id=1,
                trigger_id=f"trigger_{i}",
                action_type="buy",
                token_address="So11111111111111111111111111111111111111112",
                amount_pct=10.0,
            )
            coordinator.queue(tx)

        assert coordinator.pending_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_coordinator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TransactionCoordinator**

```python
# src/live_trading/coordinator.py
"""Transaction coordinator for live trading."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable
from uuid import UUID

from src.live_trading.state_machine import Transaction, TransactionState
from src.live_trading.safety.guard import SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker
from src.live_trading.services.jupiter import SwapService
from src.live_trading.services.solana_rpc import TxSubmitter, ConfirmMonitor, TxStatus

logger = logging.getLogger(__name__)


class TransactionCoordinator:
    """Coordinates transaction lifecycle."""

    def __init__(
        self,
        safety_guard: SafetyGuard,
        circuit_breaker: CircuitBreaker,
        rpc_url: str,
    ):
        self.safety_guard = safety_guard
        self.circuit_breaker = circuit_breaker
        self.rpc_url = rpc_url

        # Transaction storage
        self.pending_transactions: list[Transaction] = []
        self.active_transactions: dict[UUID, Transaction] = {}
        self.completed_transactions: list[Transaction] = []

        # Services (lazy initialized)
        self._swap_service: SwapService | None = None
        self._tx_submitter: TxSubmitter | None = None
        self._confirm_monitor: ConfirmMonitor | None = None

        # Callbacks
        self._on_confirmed: Callable[[Transaction], Awaitable[None]] | None = None
        self._on_failed: Callable[[Transaction], Awaitable[None]] | None = None

    @property
    def pending_count(self) -> int:
        """Get count of pending transactions."""
        return len(self.pending_transactions)

    def queue(self, tx: Transaction) -> None:
        """Queue a transaction for processing."""
        if not self.circuit_breaker.allows_trade():
            raise RuntimeError("Circuit breaker is open - no new trades allowed")

        self.pending_transactions.append(tx)
        logger.info(f"Queued transaction {tx.id} for {tx.action_type} {tx.token_address}")

    def get_transaction(self, tx_id: UUID) -> Transaction | None:
        """Get a transaction by ID."""
        for tx in self.pending_transactions:
            if tx.id == tx_id:
                return tx
        return self.active_transactions.get(tx_id)

    def set_callbacks(
        self,
        on_confirmed: Callable[[Transaction], Awaitable[None]] | None = None,
        on_failed: Callable[[Transaction], Awaitable[None]] | None = None,
    ) -> None:
        """Set callbacks for transaction completion."""
        self._on_confirmed = on_confirmed
        self._on_failed = on_failed

    async def close(self) -> None:
        """Close all services."""
        if self._swap_service:
            await self._swap_service.close()
        if self._tx_submitter:
            await self._tx_submitter.close()
        if self._confirm_monitor:
            await self._confirm_monitor.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_coordinator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/live_trading/coordinator.py tests/live_trading/test_coordinator.py && git commit -m "feat(live-trading): add TransactionCoordinator

- Queue transactions with circuit breaker check
- Transaction storage (pending/active/completed)
- Callback support for completion events

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: BaseTradingSession Extraction

**Files:**
- Create: `src/trading/__init__.py`
- Create: `src/trading/base_session.py`
- Modify: `src/paper_trading/session.py`
- Test: `tests/trading/test_base_session.py`

- [ ] **Step 1: Create trading package**

```bash
mkdir -p src/trading
touch src/trading/__init__.py
```

- [ ] **Step 2: Write test for BaseTradingSession**

```python
# tests/trading/test_base_session.py
"""Tests for BaseTradingSession."""

import pytest
from datetime import datetime, timezone
from src.trading.base_session import BaseTradingSession
from src.engine.dsl.parser import parse_strategy


class ConcreteSession(BaseTradingSession):
    """Concrete implementation for testing."""

    def __init__(self, strategy, **kwargs):
        super().__init__(session_id=1, strategy=strategy)
        self.executed_trades = []

    def _execute_trade(self, action, prices, trigger_id, timestamp):
        """Record trade for testing."""
        self.executed_trades.append({
            "action": action,
            "prices": prices,
            "trigger_id": trigger_id,
        })
        return {"executed": True}


class TestBaseTradingSession:
    """Tests for BaseTradingSession."""

    @pytest.fixture
    def strategy_json(self):
        """Simple strategy for testing."""
        return {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {
                        "metric": "price_change_pct",
                        "token": "SOL",
                        "window": "5m",
                        "op": "<",
                        "value": -5,
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 25},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    def test_process_tick_updates_price_buffer(self, strategy_json):
        """Test that price buffer is updated."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        session.process_tick({"SOL": 100.0})
        session.process_tick({"SOL": 101.0})

        assert len(session.price_buffers["SOL"]) == 2
        assert session.price_buffers["SOL"] == [100.0, 101.0]

    def test_trigger_cooldown(self, strategy_json):
        """Test trigger cooldown mechanism."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        # First trigger should not be active
        assert session._trigger_states.get("buy_dip", False) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/trading/test_base_session.py -v`
Expected: FAIL with "No module named 'src.trading.base_session'"

- [ ] **Step 4: Extract BaseTradingSession from paper trading session**

```python
# src/trading/base_session.py
"""Base trading session with shared logic."""

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
import logging

from src.engine.dsl.types import Strategy, Action, Trigger

logger = logging.getLogger(__name__)


class BaseTradingSession(ABC):
    """Base class for trading sessions (paper and live)."""

    def __init__(self, session_id: int, strategy: Strategy):
        self.session_id = session_id
        self.strategy = strategy

        # Price tracking
        self.price_buffers: dict[str, list[float]] = defaultdict(list)
        self.derived_values: dict[str, dict[str, Any]] = {}

        # Trigger cooldown tracking
        self._trigger_states: dict[str, bool] = {}

        # Timestamps
        self.started_at = datetime.now(timezone.utc)
        self.last_tick_at: datetime | None = None

    def process_tick(
        self,
        prices: dict[str, float],
        timestamp: datetime | None = None,
    ) -> list[Any]:
        """Process a price tick. Returns list of executed trades."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        self.last_tick_at = timestamp

        # Update price buffers
        for token, price in prices.items():
            self.price_buffers[token].append(price)

        # Compute derived streams
        self._compute_derived_streams(prices)

        # Check stop-losses first
        trades = self._check_stop_losses(prices, timestamp)

        # Evaluate triggers
        triggered_actions = self._evaluate_triggers(prices)

        # Apply cooldown: only fire on FALSE -> TRUE transition
        triggered_ids = {t.trigger_id for t in triggered_actions}
        for triggered in triggered_actions:
            was_active = self._trigger_states.get(triggered.trigger_id, False)
            if was_active:
                logger.debug(f"Trigger '{triggered.trigger_id}' skipped: cooldown active")
                continue

            trade = self._execute_trade(
                triggered.action, prices, triggered.trigger_id, timestamp
            )
            if trade:
                trades.append(trade)

        # Update trigger states for next tick
        for trigger in self.strategy.triggers:
            self._trigger_states[trigger.id] = trigger.id in triggered_ids

        return trades

    def _compute_derived_streams(self, prices: dict[str, float]) -> None:
        """Compute derived streams from price buffers."""
        for stream in self.strategy.derived_streams:
            token = stream.token
            if token not in self.price_buffers:
                continue

            buffer = self.price_buffers[token]

            if stream.type == "moving_average":
                # Convert window to tick count (assuming 1 tick per minute for now)
                window_minutes = self._parse_window(stream.window)
                if len(buffer) >= window_minutes:
                    ma_value = sum(buffer[-window_minutes:]) / window_minutes
                    self.derived_values[stream.id] = {
                        "current": ma_value,
                        "previous": self.derived_values.get(stream.id, {}).get("current"),
                    }

    def _parse_window(self, window: str) -> int:
        """Parse window string to minutes (e.g., '5m' -> 5)."""
        if window.endswith("m"):
            return int(window[:-1])
        elif window.endswith("h"):
            return int(window[:-1]) * 60
        return int(window)

    def _evaluate_triggers(self, prices: dict[str, float]) -> list[Any]:
        """Evaluate all triggers and return those that fired."""
        from dataclasses import dataclass

        @dataclass
        class TriggeredAction:
            trigger_id: str
            action: Action

        triggered = []
        for trigger in self.strategy.triggers:
            if self._evaluate_condition(trigger.when, prices):
                triggered.append(TriggeredAction(
                    trigger_id=trigger.id,
                    action=trigger.action,
                ))
        return triggered

    def _evaluate_condition(self, condition: Any, prices: dict[str, float]) -> bool:
        """Evaluate a trigger condition."""
        metric = condition.metric
        op = condition.op

        # Get metric value
        if metric == "price_change_pct":
            token = condition.token
            window = self._parse_window(condition.window)
            buffer = self.price_buffers.get(token, [])
            if len(buffer) < window:
                return False
            old_price = buffer[-window]
            new_price = buffer[-1]
            value = ((new_price - old_price) / old_price) * 100
        elif metric in self.derived_values:
            value = self.derived_values[metric].get("current")
            if value is None:
                return False
        else:
            return False

        # Compare
        if op == "<":
            return value < condition.value
        elif op == ">":
            return value > condition.value
        elif op == "crosses_above":
            current = self.derived_values.get(metric, {}).get("current")
            previous = self.derived_values.get(metric, {}).get("previous")
            compare_to = condition.compare_to
            compare_current = self.derived_values.get(compare_to, {}).get("current")
            compare_previous = self.derived_values.get(compare_to, {}).get("previous")

            if None in (current, previous, compare_current, compare_previous):
                return False

            return previous <= compare_previous and current > compare_current
        elif op == "crosses_below":
            current = self.derived_values.get(metric, {}).get("current")
            previous = self.derived_values.get(metric, {}).get("previous")
            compare_to = condition.compare_to
            compare_current = self.derived_values.get(compare_to, {}).get("current")
            compare_previous = self.derived_values.get(compare_to, {}).get("previous")

            if None in (current, previous, compare_current, compare_previous):
                return False

            return previous >= compare_previous and current < compare_current

        return False

    @abstractmethod
    def _check_stop_losses(
        self, prices: dict[str, float], timestamp: datetime
    ) -> list[Any]:
        """Check and execute stop-losses. Implemented by subclass."""
        pass

    @abstractmethod
    def _execute_trade(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> Any:
        """Execute a trade. Implemented by subclass."""
        pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/trading/test_base_session.py -v`
Expected: PASS

- [ ] **Step 6: Update PaperTradingSession to inherit from BaseTradingSession**

Modify `src/paper_trading/session.py` to import and extend BaseTradingSession, removing duplicated code.

- [ ] **Step 7: Run existing paper trading tests**

Run: `cd signal_composer && python -m pytest tests/paper_trading/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
cd signal_composer && git add src/trading/ tests/trading/ src/paper_trading/session.py && git commit -m "refactor: extract BaseTradingSession for Paper/Live inheritance

- Move shared logic to BaseTradingSession
- Price buffer management
- Derived stream computation
- Trigger evaluation with cooldown
- PaperTradingSession now extends base

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: LiveTradingSession

**Files:**
- Create: `src/live_trading/session.py`
- Test: `tests/live_trading/test_live_session.py`

- [ ] **Step 1: Write test for LiveTradingSession**

```python
# tests/live_trading/test_live_session.py
"""Tests for LiveTradingSession."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.live_trading.session import LiveTradingSession
from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker
from src.engine.dsl.parser import parse_strategy


class TestLiveTradingSession:
    """Tests for LiveTradingSession."""

    @pytest.fixture
    def strategy_json(self):
        """Simple strategy for testing."""
        return {
            "id": "live_test",
            "name": "Live Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {
                        "metric": "price_change_pct",
                        "token": "SOL",
                        "window": "5m",
                        "op": "<",
                        "value": -5,
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 25},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def session(self, strategy_json):
        """Create LiveTradingSession."""
        strategy = parse_strategy(strategy_json)
        coordinator = TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_initial_state(self, session):
        """Test initial session state."""
        assert session.session_id == 1
        assert session.wallet_address is not None
        assert len(session.positions) == 0

    def test_process_tick_updates_buffers(self, session):
        """Test that price buffers are updated."""
        session.process_tick({"SOL": 100.0})
        session.process_tick({"SOL": 101.0})

        assert len(session.price_buffers["SOL"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_live_session.py -v`
Expected: FAIL

- [ ] **Step 3: Implement LiveTradingSession**

```python
# src/live_trading/session.py
"""Live trading session implementation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import logging

from src.trading.base_session import BaseTradingSession
from src.engine.dsl.types import Strategy, Action, ActionType
from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.state_machine import Transaction

logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """A position in live trading."""

    token: str
    quantity: Decimal
    avg_entry_price: Decimal
    last_reconciled_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def total_cost(self) -> Decimal:
        """Total cost basis."""
        return self.quantity * self.avg_entry_price

    def value_at(self, price: Decimal) -> Decimal:
        """Current value at given price."""
        return self.quantity * price

    def pnl_pct(self, current_price: Decimal) -> float:
        """P&L percentage at current price."""
        if self.avg_entry_price == 0:
            return 0.0
        return float((current_price - self.avg_entry_price) / self.avg_entry_price * 100)


class LiveTradingSession(BaseTradingSession):
    """Live trading session with real transaction execution."""

    def __init__(
        self,
        session_id: int,
        strategy: Strategy,
        coordinator: TransactionCoordinator,
        wallet_address: str,
    ):
        super().__init__(session_id=session_id, strategy=strategy)

        self.coordinator = coordinator
        self.wallet_address = wallet_address

        # Position tracking
        self.positions: dict[str, LivePosition] = {}

        # Daily counters
        self.daily_volume_usd = Decimal("0")
        self.daily_pnl_usd = Decimal("0")
        self.daily_reset_date = datetime.now(timezone.utc).date()

        # Trade history
        self.trades: list[Transaction] = []

    def _check_stop_losses(
        self, prices: dict[str, float], timestamp: datetime
    ) -> list[Transaction]:
        """Check and queue stop-loss transactions."""
        stop_loss_txs = []
        stop_loss_pct = self.strategy.risk_rules.stop_loss_pct

        for token, position in list(self.positions.items()):
            if token not in prices:
                continue

            current_price = Decimal(str(prices[token]))
            pnl = position.pnl_pct(current_price)

            if pnl <= stop_loss_pct:
                logger.warning(
                    f"Stop-loss triggered for {token}: {pnl:.1f}% <= {stop_loss_pct}%"
                )

                tx = Transaction(
                    session_id=self.session_id,
                    trigger_id="stop_loss",
                    action_type="sell_all",
                    token_address=token,
                    amount_pct=100.0,
                )

                try:
                    self.coordinator.queue(tx)
                    stop_loss_txs.append(tx)
                except RuntimeError as e:
                    logger.error(f"Failed to queue stop-loss: {e}")

        return stop_loss_txs

    def _execute_trade(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> Transaction | None:
        """Queue a trade transaction."""
        tx = Transaction(
            session_id=self.session_id,
            trigger_id=trigger_id,
            action_type=action.type.value,
            token_address=action.token,
            amount_pct=getattr(action, "amount_pct", 100.0),
        )

        try:
            self.coordinator.queue(tx)
            self.trades.append(tx)
            logger.info(
                f"Queued {action.type.value} for {action.token} (trigger: {trigger_id})"
            )
            return tx
        except RuntimeError as e:
            logger.error(f"Failed to queue trade: {e}")
            return None

    def get_status(self, prices: dict[str, float]) -> dict[str, Any]:
        """Get current session status."""
        total_value = sum(
            pos.value_at(Decimal(str(prices.get(token, 0))))
            for token, pos in self.positions.items()
        )

        return {
            "session_id": self.session_id,
            "wallet_address": self.wallet_address,
            "positions": {
                token: {
                    "quantity": float(pos.quantity),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "pnl_pct": pos.pnl_pct(Decimal(str(prices.get(token, pos.avg_entry_price)))),
                }
                for token, pos in self.positions.items()
            },
            "total_value_usd": float(total_value),
            "daily_volume_usd": float(self.daily_volume_usd),
            "daily_pnl_usd": float(self.daily_pnl_usd),
            "pending_txs": self.coordinator.pending_count,
            "trade_count": len(self.trades),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_live_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/live_trading/session.py tests/live_trading/test_live_session.py && git commit -m "feat(live-trading): add LiveTradingSession

- Extends BaseTradingSession
- Position tracking with LivePosition
- Stop-loss queueing via coordinator
- Trade execution via coordinator
- Daily counters and status reporting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Database Migrations

**Files:**
- Modify: `src/db/models.py`
- Create: `src/db/migrations/versions/xxx_add_live_trading_tables.py`

- [ ] **Step 1: Add live trading models**

Add to `src/db/models.py`:

```python
class LiveTradingSession(Base):
    """Live trading session model."""

    __tablename__ = "live_trading_sessions"

    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    user_id = Column(Integer)
    wallet_address = Column(String(44), nullable=False)
    status = Column(String(20), default="running")

    # Safety config
    max_trade_usd = Column(Numeric(12, 2), default=500)
    max_daily_usd = Column(Numeric(12, 2), default=2000)
    max_daily_loss_usd = Column(Numeric(12, 2), default=500)

    # Circuit breaker
    consecutive_failures = Column(Integer, default=0)
    circuit_breaker_tripped_at = Column(DateTime)

    # Tracking
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime)
    last_tick_at = Column(DateTime)
    last_reconciled_at = Column(DateTime)

    # Daily counters
    daily_volume_usd = Column(Numeric(12, 2), default=0)
    daily_pnl_usd = Column(Numeric(12, 2), default=0)
    daily_reset_date = Column(Date, default=date.today)


class LiveTransaction(Base):
    """Live transaction record."""

    __tablename__ = "live_transactions"

    id = Column(String(36), primary_key=True)  # UUID
    session_id = Column(Integer, ForeignKey("live_trading_sessions.id"))
    trigger_id = Column(String(100), nullable=False)
    action_type = Column(String(20), nullable=False)
    token_address = Column(String(44), nullable=False)

    # State
    state = Column(String(20), nullable=False)
    state_history = Column(JSON, default=list)
    retry_count = Column(Integer, default=0)

    # Quote data
    quote_input_mint = Column(String(44))
    quote_output_mint = Column(String(44))
    quote_amount_in = Column(BigInteger)
    quote_expected_out = Column(BigInteger)
    quote_price_impact_pct = Column(Numeric(5, 2))
    quote_expires_at = Column(DateTime)

    # Execution
    tx_signature = Column(String(88))
    submitted_at = Column(DateTime)
    confirmed_at = Column(DateTime)
    actual_amount_out = Column(BigInteger)
    actual_price = Column(Numeric(20, 8))
    slippage_bps = Column(Integer)
    fee_lamports = Column(BigInteger)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Create migration**

Run: `cd signal_composer && alembic revision --autogenerate -m "add live trading tables"`

- [ ] **Step 3: Apply migration**

Run: `cd signal_composer && alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
cd signal_composer && git add src/db/models.py src/db/migrations/versions/ && git commit -m "feat(db): add live trading database tables

- live_trading_sessions table
- live_transactions table
- live_positions table (via migration)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Live Trading API Endpoints

**Files:**
- Create: `src/api/routes/live_trading.py`
- Create: `src/api/schemas/live_trading.py`
- Modify: `src/api/main.py`

- [ ] **Step 1: Create Pydantic schemas**

```python
# src/api/schemas/live_trading.py
"""Pydantic schemas for live trading API."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from typing import Any


class StartSessionRequest(BaseModel):
    """Request to start a live trading session."""

    strategy_id: int
    wallet_address: str
    max_trade_usd: Decimal = Decimal("500")
    max_daily_usd: Decimal = Decimal("2000")
    max_daily_loss_usd: Decimal = Decimal("500")


class SessionResponse(BaseModel):
    """Response with session details."""

    id: int
    strategy_id: int
    wallet_address: str
    status: str
    started_at: datetime
    total_value_usd: float | None = None
    daily_pnl_usd: float | None = None
    pending_txs: int = 0


class TransactionResponse(BaseModel):
    """Response with transaction details."""

    id: str
    trigger_id: str
    action_type: str
    state: str
    token_address: str
    tx_signature: str | None = None
    created_at: datetime
```

- [ ] **Step 2: Create API routes**

```python
# src/api/routes/live_trading.py
"""API routes for live trading."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated

from src.api.schemas.live_trading import (
    StartSessionRequest,
    SessionResponse,
    TransactionResponse,
)
from src.db.repositories.live_trading_repository import LiveTradingRepository

router = APIRouter(prefix="/live-trading", tags=["live-trading"])


@router.post("/sessions", response_model=SessionResponse)
async def start_session(
    request: StartSessionRequest,
    repo: Annotated[LiveTradingRepository, Depends()],
):
    """Start a new live trading session."""
    session = await repo.create_session(
        strategy_id=request.strategy_id,
        wallet_address=request.wallet_address,
        max_trade_usd=request.max_trade_usd,
        max_daily_usd=request.max_daily_usd,
        max_daily_loss_usd=request.max_daily_loss_usd,
    )
    return SessionResponse(
        id=session.id,
        strategy_id=session.strategy_id,
        wallet_address=session.wallet_address,
        status=session.status,
        started_at=session.started_at,
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    repo: Annotated[LiveTradingRepository, Depends()],
):
    """List all live trading sessions."""
    sessions = await repo.get_all_sessions()
    return [
        SessionResponse(
            id=s.id,
            strategy_id=s.strategy_id,
            wallet_address=s.wallet_address,
            status=s.status,
            started_at=s.started_at,
        )
        for s in sessions
    ]


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: int,
    repo: Annotated[LiveTradingRepository, Depends()],
):
    """Stop a live trading session."""
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await repo.update_session_status(session_id, "stopped")
    return {"status": "stopped"}


@router.post("/sessions/{session_id}/kill")
async def kill_session(
    session_id: int,
    repo: Annotated[LiveTradingRepository, Depends()],
):
    """Emergency kill a live trading session."""
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await repo.update_session_status(session_id, "killed")
    return {"status": "killed"}


@router.post("/emergency-stop")
async def emergency_stop(
    repo: Annotated[LiveTradingRepository, Depends()],
):
    """Emergency stop ALL live trading sessions."""
    count = await repo.stop_all_sessions()
    return {"stopped_sessions": count}
```

- [ ] **Step 3: Register routes in main.py**

Add to `src/api/main.py`:

```python
from src.api.routes.live_trading import router as live_trading_router
app.include_router(live_trading_router)
```

- [ ] **Step 4: Run API tests**

Run: `cd signal_composer && python -m pytest tests/api/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd signal_composer && git add src/api/routes/live_trading.py src/api/schemas/live_trading.py src/api/main.py && git commit -m "feat(api): add live trading API endpoints

- POST /live-trading/sessions - start session
- GET /live-trading/sessions - list sessions
- POST /live-trading/sessions/{id}/stop - stop session
- POST /live-trading/sessions/{id}/kill - emergency kill
- POST /live-trading/emergency-stop - kill all

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Integration Test with Mocked Services

**Files:**
- Create: `tests/live_trading/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/live_trading/test_integration.py
"""Integration tests for live trading with mocked services."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.live_trading.session import LiveTradingSession, LivePosition
from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.state_machine import Transaction, TransactionState
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker
from src.live_trading.services.jupiter import SwapQuote
from src.engine.dsl.parser import parse_strategy


class TestLiveTradingIntegration:
    """Integration tests for live trading flow."""

    @pytest.fixture
    def strategy_json(self):
        """Buy-the-dip strategy."""
        return {
            "id": "integration_test",
            "name": "Integration Test",
            "description": "Test",
            "version": 1,
            "tokens": ["So11111111111111111111111111111111111111112"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {
                        "metric": "price_change_pct",
                        "token": "So11111111111111111111111111111111111111112",
                        "window": "5m",
                        "op": "<",
                        "value": -5,
                    },
                    "action": {
                        "type": "buy",
                        "token": "So11111111111111111111111111111111111111112",
                        "amount_pct": 25,
                    },
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def coordinator(self):
        """Create coordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    @pytest.fixture
    def session(self, strategy_json, coordinator):
        """Create session."""
        strategy = parse_strategy(strategy_json)
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_price_drop_queues_buy(self, session):
        """Test that price drop triggers buy transaction queue."""
        token = "So11111111111111111111111111111111111111112"

        # Build price history
        for price in [100.0, 100.0, 100.0, 100.0, 100.0]:
            session.process_tick({token: price})

        # Price drops 10%
        trades = session.process_tick({token: 90.0})

        # Should have queued a buy
        assert session.coordinator.pending_count == 1
        tx = session.coordinator.pending_transactions[0]
        assert tx.action_type == "buy"
        assert tx.trigger_id == "buy_dip"

    def test_stop_loss_queues_sell(self, session):
        """Test that stop-loss triggers sell transaction queue."""
        token = "So11111111111111111111111111111111111111112"

        # Add a position
        session.positions[token] = LivePosition(
            token=token,
            quantity=Decimal("10"),
            avg_entry_price=Decimal("100"),
        )

        # Price drops 15% - should trigger stop-loss
        trades = session.process_tick({token: 85.0})

        # Should have queued a sell
        assert session.coordinator.pending_count == 1
        tx = session.coordinator.pending_transactions[0]
        assert tx.action_type == "sell_all"
        assert tx.trigger_id == "stop_loss"

    def test_circuit_breaker_blocks_trades(self, session, coordinator):
        """Test that circuit breaker blocks new trades."""
        token = "So11111111111111111111111111111111111111112"

        # Trip circuit breaker
        for _ in range(3):
            coordinator.circuit_breaker.record_failure("test")

        # Build price history and trigger
        for price in [100.0, 100.0, 100.0, 100.0, 100.0]:
            session.process_tick({token: price})

        # Price drop should not queue (circuit breaker open)
        trades = session.process_tick({token: 90.0})

        assert coordinator.pending_count == 0
```

- [ ] **Step 2: Run integration tests**

Run: `cd signal_composer && python -m pytest tests/live_trading/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd signal_composer && git add tests/live_trading/test_integration.py && git commit -m "test(live-trading): add integration tests

- Price drop triggers buy queue
- Stop-loss triggers sell queue
- Circuit breaker blocks trades

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Final Wiring and Run All Tests

- [ ] **Step 1: Update package __init__.py files**

Ensure all packages export their main classes.

- [ ] **Step 2: Run full test suite**

Run: `cd signal_composer && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Final commit**

```bash
cd signal_composer && git add . && git commit -m "feat(live-trading): complete live trading implementation

Components:
- Transaction state machine with lifecycle tracking
- SafetyGuard with trade limits
- CircuitBreaker (trips after 3 failures)
- Jupiter SwapService integration
- Solana RPC services (submit + confirm)
- WalletService for keypair management
- TransactionCoordinator orchestration
- LiveTradingSession (extends BaseTradingSession)
- Database tables and migrations
- REST API endpoints
- Integration tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements real money transaction execution in 13 tasks:

1. **Transaction State Machine** - Core lifecycle tracking
2. **Safety Guard** - Trade limits enforcement
3. **Circuit Breaker** - Failure protection
4. **Jupiter SwapService** - DEX integration
5. **Solana RPC Services** - TX submission and confirmation
6. **Wallet Service** - Keypair management
7. **TransactionCoordinator** - Orchestration layer
8. **BaseTradingSession Extraction** - Refactor for inheritance
9. **LiveTradingSession** - Full live trading session
10. **Database Migrations** - Persistence layer
11. **API Endpoints** - REST interface
12. **Integration Tests** - End-to-end testing
13. **Final Wiring** - Complete implementation

Each task follows TDD with failing tests first, then implementation, then verification.
