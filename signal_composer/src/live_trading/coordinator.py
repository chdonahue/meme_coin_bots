"""Transaction coordinator for live trading."""

import logging
from typing import Callable, Awaitable
from uuid import UUID

from src.live_trading.state_machine import Transaction
from src.live_trading.safety.guard import SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker
from src.live_trading.services.jupiter import SwapService
from src.live_trading.services.solana_rpc import TxSubmitter, ConfirmMonitor

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
