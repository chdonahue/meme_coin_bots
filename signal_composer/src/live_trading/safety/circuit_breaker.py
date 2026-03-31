"""Circuit breaker for live trading."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CircuitState(Enum):
    """State of the circuit breaker."""

    CLOSED = "closed"  # Normal operation, trades allowed
    OPEN = "open"  # Tripped, trades blocked


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
