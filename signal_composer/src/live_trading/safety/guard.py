"""Safety guards for live trading."""

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone

from src.wallets.reserve import RESERVE_SOL, get_available_capital


@dataclass
class SafetyConfig:
    """Configuration for safety limits."""

    max_trade_usd: Decimal = Decimal("500")
    max_daily_usd: Decimal = Decimal("2000")
    max_daily_loss_usd: Decimal = Decimal("500")
    min_trade_interval_sec: int = 30
    max_concurrent_txs: int = 3


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

    def check_reserve_balance(
        self,
        wallet_balance_sol: Decimal,
        trade_amount_sol: Decimal,
    ) -> SafetyCheckResult:
        """Check if trade amount respects wallet reserve.

        If trade would dip into reserve, returns success with reduced amount in reason.
        If balance is below reserve, blocks the trade entirely.
        """
        available = get_available_capital(wallet_balance_sol)

        if available <= Decimal("0"):
            return SafetyCheckResult(
                allowed=False,
                reason=f"Insufficient balance: {wallet_balance_sol} SOL below reserve ({RESERVE_SOL} SOL)",
            )

        if trade_amount_sol > available:
            return SafetyCheckResult(
                allowed=True,
                reason=f"Trade reduced to available: {available} SOL (reserve protected)",
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
