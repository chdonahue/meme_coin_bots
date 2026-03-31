"""Transaction state machine for live trading."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


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
            raise ValueError(f"Invalid transition: {self.state.name} -> {new_state.name}")

        self.state_history.append(
            {
                "from": self.state.name,
                "to": new_state.name,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
